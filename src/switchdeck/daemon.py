"""Asyncio background daemon (`switchdeckd`) with AF_NETLINK uevents & Unix socket IPC."""

from __future__ import annotations

import asyncio
import atexit
import errno
import json
import logging
import os
import signal
import socket
import stat
import sys
from pathlib import Path
from typing import Any

from .backends import HardwareBackend, LinuxHardwareBackend
from .coordinator import SwitchDeckCoordinator
from .session import resolve_user_session

LOG = logging.getLogger("switchdeck.daemon")
NETLINK_KOBJECT_UEVENT = 15
NETLINK_RCVBUF_BYTES = 262144
MAX_NETLINK_PACKETS_PER_WAKE = 64
MAX_IPC_REQUEST_BYTES = 8192
RELEVANT_SUBSYSTEMS = ("SUBSYSTEM=drm", "SUBSYSTEM=usb", "SUBSYSTEM=input", "SUBSYSTEM=power_supply")


def default_socket_path() -> Path:
    if os.geteuid() != 0:
        runtime_dir = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
        return Path(runtime_dir) / "switchdeck.sock"
    return resolve_user_session().runtime_dir / "switchdeck.sock"


class SwitchDeckDaemon:
    """Runs event-driven uevent watcher + 1.5s active observer + JSON-RPC socket."""

    def __init__(
        self,
        backend: HardwareBackend | None = None,
        socket_path: Path | None = None,
        observer_interval_sec: float = 1.5,
        debounce_sec: float = 0.15,
    ) -> None:
        self.coordinator = SwitchDeckCoordinator(backend or LinuxHardwareBackend())
        self.socket_path = socket_path or default_socket_path()
        self.observer_interval_sec = observer_interval_sec
        self.debounce_sec = debounce_sec

        self._stop_event = asyncio.Event()
        self._reconcile_lock = asyncio.Lock()
        self._debounce_handle: asyncio.TimerHandle | None = None
        self._reconcile_task: asyncio.Task[None] | None = None
        self._reconcile_pending = False
        self._netlink_sock: socket.socket | None = None
        self._server: asyncio.AbstractServer | None = None
        self._last_status: Any = None
        try:
            self._last_status = self.coordinator.reconcile()
        except Exception:
            LOG.exception("Initial reconcile failed; observer loop will retry")

    def _schedule_reconcile(self, loop: asyncio.AbstractEventLoop) -> None:
        if self._debounce_handle is not None:
            self._debounce_handle.cancel()
        self._debounce_handle = loop.call_later(
            self.debounce_sec,
            self._run_reconcile_task,
            loop,
        )

    def _run_reconcile_task(self, loop: asyncio.AbstractEventLoop | None = None) -> None:
        self._debounce_handle = None
        target_loop = loop or asyncio.get_running_loop()
        if self._reconcile_task is not None and not self._reconcile_task.done():
            self._reconcile_pending = True
            return
        self._reconcile_task = target_loop.create_task(self._reconcile_worker())

    async def _reconcile_worker(self) -> None:
        try:
            while True:
                self._reconcile_pending = False
                await self._run_reconcile_async()
                if not self._reconcile_pending or self._stop_event.is_set():
                    break
        finally:
            self._reconcile_task = None

    async def _run_reconcile_async(self) -> None:
        async with self._reconcile_lock:
            try:
                self._last_status = await asyncio.to_thread(self.coordinator.reconcile)
            except Exception:
                LOG.exception("Unhandled error during reconcile")

    def _start_netlink(self, loop: asyncio.AbstractEventLoop) -> None:
        if not hasattr(socket, "AF_NETLINK"):
            return
        try:
            sock = socket.socket(socket.AF_NETLINK, socket.SOCK_RAW, NETLINK_KOBJECT_UEVENT)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, NETLINK_RCVBUF_BYTES)
            sock.bind((0, 1))
            sock.setblocking(False)
            self._netlink_sock = sock

            def _on_netlink() -> None:
                should_reconcile = False
                for _ in range(MAX_NETLINK_PACKETS_PER_WAKE):
                    try:
                        raw = sock.recv(8192)
                    except BlockingIOError:
                        break
                    except OSError as exc:
                        if exc.errno == errno.ENOBUFS:
                            should_reconcile = True
                            continue
                        break
                    if not raw:
                        break
                    text = raw.decode("utf-8", errors="ignore")
                    if any(sub in text for sub in RELEVANT_SUBSYSTEMS):
                        should_reconcile = True
                if should_reconcile:
                    self._schedule_reconcile(loop)

            loop.add_reader(sock.fileno(), _on_netlink)
            LOG.info("Listening to Linux AF_NETLINK uevents")
        except OSError as exc:
            LOG.warning("AF_NETLINK unavailable (%s); falling back to observer cadence", exc)

    def _safe_unlink_socket(self, *, missing_ok: bool) -> None:
        try:
            st = os.lstat(self.socket_path)
        except FileNotFoundError:
            if missing_ok:
                return
            raise
        if stat.S_ISLNK(st.st_mode) or not stat.S_ISSOCK(st.st_mode):
            raise RuntimeError(f"Refusing to unlink non-socket path: {self.socket_path}")
        self.socket_path.unlink()

    async def _handle_ipc_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            line = await asyncio.wait_for(reader.readline(), timeout=2.0)
            if len(line) > MAX_IPC_REQUEST_BYTES:
                raise ValueError(f"IPC request exceeds {MAX_IPC_REQUEST_BYTES} byte limit")
            req = json.loads(line.decode("utf-8")) if line else {}
            if not isinstance(req, dict):
                raise ValueError("IPC payload must be a JSON object")
            cmd = req.get("cmd", "status")
            response: dict[str, Any]

            if cmd == "status":
                async with self._reconcile_lock:
                    self._last_status = await asyncio.to_thread(self.coordinator.reconcile)
                    response = {"ok": True, "status": self._last_status.to_dict()}
            elif cmd == "set_keep_builtin":
                enabled = req.get("enabled")
                if not isinstance(enabled, bool):
                    raise ValueError("Missing or non-boolean 'enabled' parameter")
                async with self._reconcile_lock:
                    self._last_status = await asyncio.to_thread(
                        self.coordinator.set_keep_builtin, enabled
                    )
                    response = {"ok": True, "status": self._last_status.to_dict()}
            elif cmd == "charge_full":
                async with self._reconcile_lock:
                    self._last_status = await asyncio.to_thread(
                        self.coordinator.set_travel_charge_100
                    )
                    response = {"ok": True, "status": self._last_status.to_dict()}
            elif cmd == "set_charge_override":
                enabled = req.get("enabled")
                if not isinstance(enabled, bool):
                    raise ValueError("Missing or non-boolean 'enabled' parameter")
                async with self._reconcile_lock:
                    self._last_status = await asyncio.to_thread(
                        self.coordinator.set_travel_charge_override, enabled
                    )
                    response = {"ok": True, "status": self._last_status.to_dict()}
            elif cmd == "rebind_builtin":
                async with self._reconcile_lock:
                    self._last_status = await asyncio.to_thread(
                        self.coordinator.force_rebind_builtin
                    )
                    response = {"ok": True, "status": self._last_status.to_dict()}
            elif cmd == "resume_game":
                async with self._reconcile_lock:
                    resumed = await asyncio.to_thread(self.coordinator.resume_paused_game)
                    response = {"ok": True, "resumed": resumed}
            elif cmd == "nudge_display":
                async with self._reconcile_lock:
                    nudged = await asyncio.to_thread(
                        self.coordinator.backend.nudge_gamescope_display
                    )
                    response = {"ok": True, "nudged": nudged}
            elif cmd == "get_profile":
                async with self._reconcile_lock:
                    prof = await asyncio.to_thread(self.coordinator.get_active_profile)
                    response = {"ok": True, "profile": prof.to_dict()}
            elif cmd == "update_profile":
                patch = req.get("patch")
                if not isinstance(patch, dict):
                    raise ValueError("Missing or non-dict 'patch' parameter")
                async with self._reconcile_lock:
                    prof = await asyncio.to_thread(self.coordinator.update_active_profile, patch)
                    response = {"ok": True, "profile": prof.to_dict()}
            elif cmd == "test_tv":
                async with self._reconcile_lock:
                    woken = await asyncio.to_thread(self.coordinator.test_active_tv_wake)
                    response = {"ok": True, "woken": woken}
            else:
                response = {"ok": False, "error": f"Unknown command: {cmd}"}

            writer.write((json.dumps(response) + "\n").encode("utf-8"))
            await writer.drain()
        except Exception as exc:
            try:
                writer.write((json.dumps({"ok": False, "error": str(exc)}) + "\n").encode("utf-8"))
                await writer.drain()
            except OSError:
                pass
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except OSError:
                pass

    async def run(self) -> None:
        loop = asyncio.get_running_loop()
        atexit.register(self.coordinator.close)
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, self._stop_event.set)
            except NotImplementedError:
                pass

        self.socket_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._safe_unlink_socket(missing_ok=True)

        self._server = await asyncio.start_unix_server(
            self._handle_ipc_client,
            path=str(self.socket_path),
            limit=MAX_IPC_REQUEST_BYTES,
        )
        os.chmod(self.socket_path, 0o600)
        self._start_netlink(loop)
        LOG.info("switchdeckd listening on %s", self.socket_path)

        try:
            while not self._stop_event.is_set():
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=self.observer_interval_sec)
                except asyncio.TimeoutError:
                    await self._run_reconcile_async()
        finally:
            if self._debounce_handle is not None:
                self._debounce_handle.cancel()
                self._debounce_handle = None
            if self._reconcile_task is not None and not self._reconcile_task.done():
                try:
                    await self._reconcile_task
                except Exception:
                    LOG.exception("Error waiting for active reconcile task on shutdown")
            if self._netlink_sock is not None:
                try:
                    loop.remove_reader(self._netlink_sock.fileno())
                except Exception:
                    pass
                self._netlink_sock.close()
            if self._server is not None:
                self._server.close()
                await self._server.wait_closed()
            try:
                self._safe_unlink_socket(missing_ok=True)
            except OSError:
                pass
            await asyncio.to_thread(self.coordinator.close)


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    daemon = SwitchDeckDaemon()
    try:
        asyncio.run(daemon.run())
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
