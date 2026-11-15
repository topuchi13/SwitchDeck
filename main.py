"""Decky Loader root plugin backend for SwitchDeck."""

from __future__ import annotations

import asyncio
import errno
import inspect
import logging
import os
import socket
import ssl
import sys
from pathlib import Path
from typing import Any, Callable

PLUGIN_DIR = Path(__file__).resolve().parent
for _path_candidate in reversed((PLUGIN_DIR / "py_modules", PLUGIN_DIR / "src")):
    _candidate_str = str(_path_candidate)
    if _path_candidate.is_dir() and _candidate_str not in sys.path:
        sys.path.insert(0, _candidate_str)

from switchdeck.backends import LinuxHardwareBackend  # noqa: E402
from switchdeck.coordinator import SwitchDeckCoordinator  # noqa: E402
from switchdeck.domain import DaemonStatus, DockProfile  # noqa: E402
from switchdeck.tv import SamsungTizenDriver  # noqa: E402

try:
    import decky  # type: ignore[import-not-found]
except ImportError:
    class _FallbackDecky:
        """Fallback shim when running outside Decky Loader (e.g. unit tests)."""

        logger = logging.getLogger("switchdeck.decky")
        DECKY_PLUGIN_SETTINGS_DIR = ""
        DECKY_USER = ""
        DECKY_USER_HOME = ""

        async def emit(self, event: str, *args: Any) -> None:
            self.logger.debug("Fallback decky.emit(%s, %r)", event, args)

    decky = _FallbackDecky()  # type: ignore[assignment]

NETLINK_KOBJECT_UEVENT = 15
RELEVANT_SUBSYSTEMS = (
    "SUBSYSTEM=drm",
    "SUBSYSTEM=usb",
    "SUBSYSTEM=input",
    "SUBSYSTEM=power_supply",
)


def _get_logger() -> logging.Logger:
    logger = getattr(decky, "logger", None)
    if isinstance(logger, logging.Logger):
        return logger
    return logging.getLogger("switchdeck.decky")


def _propagate_decky_env() -> None:
    """Expose Decky-provided user/settings paths to ProfileStore & UserSessionContext."""
    for attr in ("DECKY_PLUGIN_SETTINGS_DIR", "DECKY_USER", "DECKY_USER_HOME"):
        val = getattr(decky, attr, None)
        if val and not os.environ.get(attr):
            os.environ[attr] = str(val)


class Plugin:
    """Decky Loader plugin lifecycle & RPC surface backed by SwitchDeckCoordinator."""

    observer_interval_sec: float = 1.5
    debounce_sec: float = 0.15

    def __init__(self) -> None:
        self.coordinator: SwitchDeckCoordinator | None = None
        self._lock: asyncio.Lock | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stop_event: asyncio.Event | None = None
        self._observer_task: asyncio.Task[None] | None = None
        self._reconcile_task: asyncio.Task[None] | None = None
        self._reconcile_pending: bool = False
        self._debounce_handle: asyncio.TimerHandle | None = None
        self._netlink_sock: socket.socket | None = None
        self._netlink_fd: int | None = None
        self._last_transition_seq: int = 0
        self._last_status: DaemonStatus | None = None

    def _get_lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    def _ensure_coordinator(self) -> SwitchDeckCoordinator:
        if self.coordinator is None:
            _propagate_decky_env()
            self.coordinator = SwitchDeckCoordinator(LinuxHardwareBackend())
        return self.coordinator

    async def _emit_transition(self, payload: dict[str, Any]) -> None:
        emit_fn = getattr(decky, "emit", None)
        if not callable(emit_fn):
            return
        try:
            result = emit_fn("switchdeck_transition", payload)
            if inspect.isawaitable(result):
                await result
        except Exception:
            _get_logger().exception("Failed emitting switchdeck_transition event")

    async def _run_status_transition(
        self, op: Callable[[SwitchDeckCoordinator], DaemonStatus]
    ) -> DaemonStatus:
        coord = await asyncio.to_thread(self._ensure_coordinator)
        transition_to_emit: dict[str, Any] | None = None
        async with self._get_lock():
            status = await asyncio.to_thread(op, coord)
            self._last_status = status
            seq = int(getattr(status, "transition_seq", 0) or 0)
            transition = getattr(status, "last_transition", None)
            if seq > self._last_transition_seq:
                self._last_transition_seq = seq
                if isinstance(transition, dict):
                    transition_to_emit = dict(transition)

        if transition_to_emit is not None:
            await self._emit_transition(transition_to_emit)
        return status

    async def _reconcile_and_emit(self) -> DaemonStatus:
        return await self._run_status_transition(lambda coord: coord.reconcile())

    def _schedule_reconcile(self, loop: asyncio.AbstractEventLoop) -> None:
        if self._stop_event is not None and self._stop_event.is_set():
            return
        if self._debounce_handle is not None:
            self._debounce_handle.cancel()
        self._debounce_handle = loop.call_later(
            self.debounce_sec,
            self._trigger_debounced_reconcile,
            loop,
        )

    def _trigger_debounced_reconcile(self, loop: asyncio.AbstractEventLoop) -> None:
        self._debounce_handle = None
        if self._stop_event is not None and self._stop_event.is_set():
            return
        if self._reconcile_task is not None and not self._reconcile_task.done():
            self._reconcile_pending = True
            return
        self._reconcile_task = loop.create_task(self._safe_reconcile())

    async def _safe_reconcile(self) -> None:
        while True:
            self._reconcile_pending = False
            try:
                await self._reconcile_and_emit()
            except asyncio.CancelledError:
                raise
            except Exception:
                _get_logger().exception("Unhandled error during SwitchDeck reconcile")
            if not self._reconcile_pending or (
                self._stop_event is not None and self._stop_event.is_set()
            ):
                break

    def _start_netlink(self, loop: asyncio.AbstractEventLoop) -> None:
        if not hasattr(socket, "AF_NETLINK"):
            _get_logger().info("AF_NETLINK unsupported on this platform; using observer loop only")
            return
        if self._netlink_sock is not None:
            return
        try:
            sock = socket.socket(socket.AF_NETLINK, socket.SOCK_RAW, NETLINK_KOBJECT_UEVENT)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 262144)
            sock.bind((0, 1))
            sock.setblocking(False)
            self._netlink_sock = sock
            self._netlink_fd = sock.fileno()

            def _on_netlink() -> None:
                should_reconcile = False
                for _ in range(64):
                    try:
                        raw = sock.recv(8192)
                    except BlockingIOError:
                        break
                    except OSError as exc:
                        if exc.errno == errno.ENOBUFS:
                            should_reconcile = True
                        break
                    text = raw.decode("utf-8", errors="ignore")
                    if any(sub in text for sub in RELEVANT_SUBSYSTEMS):
                        should_reconcile = True
                if should_reconcile:
                    self._schedule_reconcile(loop)

            loop.add_reader(self._netlink_fd, _on_netlink)
            _get_logger().info("SwitchDeck listening on AF_NETLINK uevents")
        except OSError as exc:
            _get_logger().warning("AF_NETLINK unavailable (%s); using 1.5s observer cadence", exc)
            self._close_netlink()

    def _close_netlink(self) -> None:
        if self._loop is not None and self._netlink_fd is not None:
            try:
                self._loop.remove_reader(self._netlink_fd)
            except Exception:
                pass
        self._netlink_fd = None
        if self._netlink_sock is not None:
            try:
                self._netlink_sock.close()
            except OSError:
                pass
            self._netlink_sock = None

    async def _observer_loop(self) -> None:
        assert self._stop_event is not None
        while not self._stop_event.is_set():
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self.observer_interval_sec)
            except asyncio.TimeoutError:
                await self._safe_reconcile()

    def _profile_payload(self, coord: SwitchDeckCoordinator, prof: DockProfile) -> dict[str, Any]:
        get_payload = getattr(coord, "get_profile_payload", None)
        if callable(get_payload):
            return get_payload(prof)
        payload = prof.to_dict()
        host = prof.tv.host
        get_token = getattr(coord.store, "get_token", None)
        get_fp = getattr(coord.store, "get_cert_fingerprint", None)
        payload["tv_paired"] = bool(host and callable(get_token) and get_token(host))
        payload["tv_cert_fingerprint"] = (
            (get_fp(host) if (host and callable(get_fp)) else "") or ""
        )
        return payload

    async def _main(self) -> None:
        _propagate_decky_env()
        await asyncio.to_thread(self._ensure_coordinator)
        self._loop = asyncio.get_running_loop()
        self._stop_event = asyncio.Event()
        await self._safe_reconcile()
        self._start_netlink(self._loop)
        if self._observer_task is None or self._observer_task.done():
            self._observer_task = self._loop.create_task(self._observer_loop())
        _get_logger().info("SwitchDeck Decky plugin initialized")

    async def _shutdown(self) -> None:
        try:
            if self._stop_event is not None:
                self._stop_event.set()
            if self._debounce_handle is not None:
                self._debounce_handle.cancel()
                self._debounce_handle = None
            for task in (self._observer_task, self._reconcile_task):
                if task is not None and not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
            self._observer_task = None
            self._reconcile_task = None
            self._close_netlink()
        finally:
            if self.coordinator is not None:
                try:
                    await asyncio.to_thread(self.coordinator.close)
                except Exception:
                    _get_logger().exception("Error inside SwitchDeck coordinator.close()")

    async def _unload(self) -> None:
        _get_logger().info("Unloading SwitchDeck Decky plugin")
        await self._shutdown()

    async def _uninstall(self) -> None:
        _get_logger().info("Uninstalling SwitchDeck Decky plugin")
        await self._shutdown()

    # ------------------------------------------------------------------
    # Decky RPC Methods (JSON-serializable dicts only)
    # ------------------------------------------------------------------

    async def get_status(self) -> dict[str, Any]:
        status = await self._reconcile_and_emit()
        return status.to_dict()

    async def get_active_profile(self) -> dict[str, Any]:
        coord = await asyncio.to_thread(self._ensure_coordinator)

        def _fetch() -> dict[str, Any]:
            prof = coord.get_active_profile()
            return self._profile_payload(coord, prof)

        async with self._get_lock():
            return await asyncio.to_thread(_fetch)

    async def update_profile(self, patch: dict[str, Any]) -> dict[str, Any]:
        coord = await asyncio.to_thread(self._ensure_coordinator)

        def _update() -> dict[str, Any]:
            prof = coord.update_active_profile(patch or {})
            return self._profile_payload(coord, prof)

        async with self._get_lock():
            return await asyncio.to_thread(_update)

    async def set_keep_builtin(self, enabled: bool) -> dict[str, Any]:
        status = await self._run_status_transition(
            lambda coord: coord.set_keep_builtin(bool(enabled))
        )
        return status.to_dict()

    async def rebind_builtin(self) -> dict[str, Any]:
        status = await self._run_status_transition(lambda coord: coord.force_rebind_builtin())
        return status.to_dict()

    async def set_charge_override(self, enabled: bool) -> dict[str, Any]:
        status = await self._run_status_transition(
            lambda coord: coord.set_travel_charge_override(bool(enabled))
        )
        return status.to_dict()

    async def nudge_display(self) -> dict[str, Any]:
        coord = await asyncio.to_thread(self._ensure_coordinator)
        async with self._get_lock():
            nudged = await asyncio.to_thread(coord.backend.nudge_gamescope_display)
            return {"ok": bool(nudged)}

    async def pair_samsung_tv(
        self,
        host: str,
        port: int = 8002,
        mac: str = "",
        trust_new_cert: bool = False,
    ) -> dict[str, Any]:
        coord = await asyncio.to_thread(self._ensure_coordinator)

        def _do_pair() -> dict[str, Any]:
            clean_host = str(host or "").strip()
            clean_port = int(port)
            clean_mac = str(mac or "").strip()
            trust = bool(trust_new_cert)

            store = coord.store
            get_fp = getattr(store, "get_cert_fingerprint", None)
            set_fp = getattr(store, "set_cert_fingerprint", None)
            clear_fp = getattr(store, "clear_cert_fingerprint", None)

            tv_op_lock = getattr(coord, "_tv_op_lock", None)
            if tv_op_lock is not None:
                tv_op_lock.acquire()
            try:
                if trust and callable(clear_fp) and clean_host:
                    clear_fp(clean_host)

                driver_kwargs: dict[str, Any] = {
                    "get_token": store.get_token,
                    "set_token": store.set_token,
                }
                sig = inspect.signature(SamsungTizenDriver.__init__)
                if "get_cert_fingerprint" in sig.parameters and callable(get_fp):
                    driver_kwargs["get_cert_fingerprint"] = get_fp
                if "set_cert_fingerprint" in sig.parameters and callable(set_fp):
                    driver_kwargs["set_cert_fingerprint"] = set_fp

                driver = SamsungTizenDriver(**driver_kwargs)
                pair_sig = inspect.signature(driver.pair)
                if "trust_new_cert" in pair_sig.parameters:
                    token = driver.pair(clean_host, port=clean_port, trust_new_cert=trust)
                else:
                    token = driver.pair(clean_host, port=clean_port)
            finally:
                if tv_op_lock is not None:
                    tv_op_lock.release()

            current_prof = coord.get_active_profile()
            tv_patch: dict[str, Any] = {
                "driver": "samsung_tizen",
                "host": clean_host,
                "port": clean_port,
            }
            if clean_mac:
                tv_patch["mac_address"] = clean_mac
            elif current_prof.tv.mac_address:
                tv_patch["mac_address"] = current_prof.tv.mac_address

            updated_prof = coord.update_active_profile({"tv": tv_patch})
            cert_fp = get_fp(clean_host) if callable(get_fp) else ""
            return {
                "ok": True,
                "host": clean_host,
                "port": clean_port,
                "token_saved": bool(token),
                "cert_fingerprint": cert_fp or "",
                "profile": self._profile_payload(coord, updated_prof),
            }

        try:
            return await asyncio.to_thread(_do_pair)
        except ssl.SSLCertVerificationError as exc:
            return {
                "ok": False,
                "cert_mismatch": True,
                "error": str(exc),
            }
        except (ValueError, OSError, ConnectionError) as exc:
            return {
                "ok": False,
                "cert_mismatch": False,
                "error": str(exc),
            }

    async def pair_tv(
        self,
        driver: str,
        host: str,
        port: int = 0,
        mac: str = "",
        hdmi_input: str = "",
        psk: str = "",
        trust_new_cert: bool = False,
    ) -> dict[str, Any]:
        coord = await asyncio.to_thread(self._ensure_coordinator)
        try:
            return await asyncio.to_thread(
                coord.pair_tv,
                driver,
                host,
                int(port or 0),
                str(mac or ""),
                str(hdmi_input or ""),
                str(psk or ""),
                bool(trust_new_cert),
            )
        except ssl.SSLCertVerificationError as exc:
            return {
                "ok": False,
                "cert_mismatch": True,
                "error": str(exc),
            }
        except (ValueError, OSError, ConnectionError) as exc:
            return {
                "ok": False,
                "cert_mismatch": False,
                "error": str(exc),
            }

    async def test_tv_wake(self) -> dict[str, Any]:
        coord = await asyncio.to_thread(self._ensure_coordinator)
        ok = await asyncio.to_thread(coord.test_active_tv_wake)
        if ok:
            return {"ok": True}
        err = getattr(coord, "_last_error", None) or "TV wake failed"
        return {
            "ok": False,
            "cert_mismatch": "fingerprint mismatch" in str(err).lower(),
            "error": str(err),
        }
