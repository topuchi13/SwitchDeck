"""Linux / SteamOS production HardwareBackend using stdlib + stock SteamOS tools."""

from __future__ import annotations

import ctypes
import glob
import os
import re
import select
import shutil
import signal
import subprocess
import time
from pathlib import Path

from ..domain import (
    AudioSink,
    AudioState,
    DeckModel,
    DisplayConnector,
    DisplayMode,
    ExternalController,
    GameWindowState,
    ScalingDecision,
    UnhandledDongleWarning,
)
from ..edid import parse_edid
from ..security import (
    apply_runtime_overclock_sysfs,
    find_validated_amdgpu_device,
    find_validated_amdgpu_hwmon,
    reset_runtime_overclock_sysfs,
    safe_write_sysfs,
    validate_game_pid,
    validate_neptune_iface,
    validate_overclock_args,
    validate_wakeup_path,
)
from ..session import UserSessionContext, resolve_user_session

VALVE_VENDOR = "28de"
NEPTUNE_PRODUCT = "1205"
STEAM_VIRTUAL_PRODUCT = "11ff"
PUCK_PRODUCTS = {"1304", "1305"}
XBOX_ADAPTER_USB_IDS = {("045e", "02fe"), ("045e", "02e6")}

BTN_SOUTH_BIT = 0x130
BTN_TRIGGER_BIT = 0x120
ABS_X_BIT = 0x00
ABS_Y_BIT = 0x01
BITS_PER_LONG = ctypes.sizeof(ctypes.c_long) * 8

USB_HID_DRIVER = Path("/sys/bus/usb/drivers/usbhid")
HELPER_PATH = Path("/usr/local/bin/switchdeck-helper")


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""


def _parse_cap_words(raw: str) -> list[int]:
    if not raw:
        return []
    words = [int(chunk, 16) for chunk in raw.split()]
    words.reverse()  # sysfs prints MSB word first; index 0 is LSB word
    return words


def _has_cap_bit(words: list[int], bit: int) -> bool:
    word_idx = bit // BITS_PER_LONG
    if word_idx >= len(words):
        return False
    return bool(words[word_idx] & (1 << (bit % BITS_PER_LONG)))


def _run_cmd(cmd: list[str], env: dict[str, str] | None = None, timeout: float = 2.5) -> tuple[int, str]:
    try:
        merged_env = os.environ.copy()
        if env:
            merged_env.update(env)
        proc = subprocess.run(
            cmd,
            env=merged_env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return proc.returncode, proc.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return 1, ""


class LinuxHardwareBackend:
    """Real SteamOS / Linux sysfs, PipeWire, Gamescope, and steamosctl backend."""

    def __init__(
        self,
        display: str = ":0",
        game_display: str = ":1",
        session: UserSessionContext | None = None,
    ) -> None:
        self.display = display
        self.game_display = game_display
        self.session = session or resolve_user_session()
        self._dongle_wakeup_baseline: dict[str, int] = {}
        self._dongle_active_until: dict[str, float] = {}
        self._dongle_watch_fds: dict[str, int] = {}
        self._paused_starttimes: dict[int, str] = {}

    def _run_helper_or_write(self, action: str, target: str, value: str = "") -> bool:
        if os.geteuid() == 0:
            if action in ("bind-neptune", "unbind-neptune"):
                if not validate_neptune_iface(target):
                    return False
                driver_file = USB_HID_DRIVER / ("bind" if action == "bind-neptune" else "unbind")
                return safe_write_sysfs(driver_file, target)
            if action == "set-wakeup":
                if value not in ("enabled", "disabled"):
                    return False
                wakeup_path = validate_wakeup_path(target)
                if wakeup_path is None:
                    return False
                return safe_write_sysfs(wakeup_path, value)
            return False

        if HELPER_PATH.exists():
            cmd = ["sudo", "-n", str(HELPER_PATH), action, target]
            if value:
                cmd.append(value)
            rc, _ = _run_cmd(cmd)
            return rc == 0
        return False

    def get_deck_model(self) -> DeckModel:
        product = _read_text(Path("/sys/devices/virtual/dmi/id/product_name"))
        if product == DeckModel.JUPITER_LCD.value:
            return DeckModel.JUPITER_LCD
        if product == DeckModel.GALILEO_OLED.value:
            return DeckModel.GALILEO_OLED
        return DeckModel.GENERIC_STEAMOS

    def is_ac_online(self, power_supply_root: Path = Path("/sys/class/power_supply")) -> bool:
        try:
            entries = sorted(power_supply_root.iterdir())
        except OSError:
            return False
        for ps_dir in entries:
            if _read_text(ps_dir / "scope") == "Device":
                continue
            ps_type = _read_text(ps_dir / "type")
            if ps_type not in {"Mains", "USB", "USB_PD", "USB_PD_DRP", "USB_C"}:
                continue
            if _read_text(ps_dir / "online") == "1":
                return True
        return False

    def _query_xrandr_refresh_rates(self) -> dict[tuple[int, int], list[float]]:
        rates: dict[tuple[int, int], list[float]] = {}
        rc, out = self.session.run_user_cmd(["xrandr", "--query"], extra_env={"DISPLAY": self.display})
        if rc != 0:
            return rates
        for line in out.splitlines():
            m = re.match(r"^\s+(\d+)x(\d+)\s+(.+)$", line)
            if not m:
                continue
            w, h = int(m.group(1)), int(m.group(2))
            for tok in re.findall(r"(\d+\.\d+)", m.group(3)):
                rates.setdefault((w, h), []).append(float(tok))
        return rates

    def get_external_displays(self) -> list[DisplayConnector]:
        connectors: list[DisplayConnector] = []
        xrandr_rates = self._query_xrandr_refresh_rates()
        for status_file in sorted(glob.glob("/sys/class/drm/card*-*/status")):
            conn_dir = Path(status_file).parent
            name = conn_dir.name
            if "-eDP-" in name or "-LVDS-" in name or "-DSI-" in name:
                continue
            if _read_text(Path(status_file)) != "connected":
                continue

            modes: list[DisplayMode] = []
            modes_raw = _read_text(conn_dir / "modes")
            for idx, line in enumerate(modes_raw.splitlines()):
                m = re.match(r"^(\d+)x(\d+)", line.strip())
                if not m:
                    continue
                w, h = int(m.group(1)), int(m.group(2))
                hz_list = xrandr_rates.get((w, h)) or [60.0]
                for hz in sorted(set(hz_list), reverse=True):
                    modes.append(DisplayMode(width=w, height=h, refresh_hz=hz, preferred=(idx == 0)))

            edid = None
            try:
                edid_bytes = (conn_dir / "edid").read_bytes()
                edid = parse_edid(edid_bytes)
            except OSError:
                pass

            vrr_capable = _read_text(conn_dir / "vrr_capable") == "1"
            connectors.append(
                DisplayConnector(
                    name=name,
                    connected=True,
                    modes=tuple(modes),
                    edid=edid,
                    vrr_capable=vrr_capable,
                )
            )
        return connectors

    def _classify_transport(self, real_path: str, vendor: str, product: str) -> str:
        if vendor == VALVE_VENDOR and product in PUCK_PRODUCTS:
            return "puck"
        if "/devices/virtual/" in real_path:
            return "uinput"
        if "/uhid/" in real_path or "/bluetooth/" in real_path:
            return "bluetooth"
        if any(tag in real_path.lower() for tag in ("wireless", "dongle", "2.4g", "receiver")):
            return "dongle_24g"
        if "/usb" in real_path:
            return "usb"
        return "other"

    def _close_watcher_fd(self, key: str) -> None:
        fd = self._dongle_watch_fds.pop(key, None)
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass

    def _prune_dongle_watchers(
        self,
        active_keys: set[str] | None = None,
        keep_key: str | None = None,
    ) -> None:
        all_keys = (
            set(self._dongle_watch_fds)
            | set(self._dongle_wakeup_baseline)
            | set(self._dongle_active_until)
        )
        for key in all_keys:
            if keep_key is not None and key == keep_key:
                continue
            if active_keys is not None:
                stale = key not in active_keys
            else:
                stale = not Path(key).exists()
            if stale:
                self._close_watcher_fd(key)
                self._dongle_wakeup_baseline.pop(key, None)
                self._dongle_active_until.pop(key, None)

    def close(self) -> None:
        """Close all open persistent dongle watcher file descriptors."""
        for key in list(self._dongle_watch_fds):
            self._close_watcher_fd(key)

    def _is_dongle_actively_awake(self, input_dir: Path, transport: str) -> tuple[bool, int]:
        wakeup_raw = _read_text(input_dir / "device" / "power" / "wakeup_count")
        wakeup_count = int(wakeup_raw) if wakeup_raw.isdigit() else 0

        if transport not in ("dongle_24g", "puck"):
            return True, wakeup_count

        key = str(input_dir)
        self._prune_dongle_watchers(keep_key=key)
        now = time.monotonic()

        prev = self._dongle_wakeup_baseline.get(key)
        if prev is None:
            self._dongle_wakeup_baseline[key] = wakeup_count
        elif wakeup_count > prev:
            self._dongle_wakeup_baseline[key] = wakeup_count
            self._dongle_active_until[key] = now + 3600.0

        if self._dongle_active_until.get(key, 0.0) > now:
            self._close_watcher_fd(key)
            return True, wakeup_count

        if key not in self._dongle_watch_fds:
            event_nodes = sorted(input_dir.glob("event*"))
            if event_nodes:
                dev_path = f"/dev/input/{event_nodes[0].name}"
                flags = os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_CLOEXEC", 0)
                try:
                    self._dongle_watch_fds[key] = os.open(dev_path, flags)
                except OSError:
                    pass

        fd = self._dongle_watch_fds.get(key)
        if fd is not None:
            try:
                poller = select.poll()
                poller.register(fd, select.POLLIN)
                events = poller.poll(0)
                got_bytes = False
                dead_fd = False
                for _, revents in events:
                    if revents & select.POLLIN:
                        for _ in range(64):
                            try:
                                chunk = os.read(fd, 4096)
                            except BlockingIOError:
                                break
                            if not chunk:
                                dead_fd = True
                                break
                            got_bytes = True
                            if len(chunk) < 4096:
                                break
                    if revents & (select.POLLERR | select.POLLHUP | select.POLLNVAL):
                        dead_fd = True
                if got_bytes:
                    self._dongle_active_until[key] = now + 3600.0
                    self._close_watcher_fd(key)
                    return True, wakeup_count
                if dead_fd:
                    self._close_watcher_fd(key)
            except OSError:
                self._close_watcher_fd(key)

        return False, wakeup_count

    def get_external_controllers(self) -> list[ExternalController]:
        controllers: list[ExternalController] = []
        seen_keys: set[str] = set()
        for input_str in sorted(glob.glob("/sys/class/input/input*")):
            input_dir = Path(input_str)
            try:
                real_path = os.path.realpath(input_dir)
            except OSError:
                continue

            vendor = _read_text(input_dir / "id" / "vendor").lower()
            product = _read_text(input_dir / "id" / "product").lower()
            if vendor == VALVE_VENDOR and product in (NEPTUNE_PRODUCT, STEAM_VIRTUAL_PRODUCT):
                continue

            key_words = _parse_cap_words(_read_text(input_dir / "capabilities" / "key"))
            abs_words = _parse_cap_words(_read_text(input_dir / "capabilities" / "abs"))
            has_gamepad_btn = _has_cap_bit(key_words, BTN_SOUTH_BIT) or _has_cap_bit(key_words, BTN_TRIGGER_BIT)
            has_axes = _has_cap_bit(abs_words, ABS_X_BIT) and _has_cap_bit(abs_words, ABS_Y_BIT)
            if not (has_gamepad_btn and has_axes):
                continue

            name = _read_text(input_dir / "name") or input_dir.name
            transport = self._classify_transport(real_path, vendor, product)
            seen_keys.add(str(input_dir))
            awake, wake_count = self._is_dongle_actively_awake(input_dir, transport)
            event_nodes = sorted(input_dir.glob("event*"))
            event_dev = f"/dev/input/{event_nodes[0].name}" if event_nodes else None

            controllers.append(
                ExternalController(
                    input_name=input_dir.name,
                    name=name,
                    vendor_id=vendor or "0000",
                    product_id=product or "0000",
                    transport=transport,
                    sysfs_path=real_path,
                    event_dev=event_dev,
                    is_actively_awake=awake,
                    wakeup_count=wake_count,
                )
            )
        self._prune_dongle_watchers(active_keys=seen_keys)
        return controllers

    def get_unhandled_dongles(self) -> list[UnhandledDongleWarning]:
        warnings: list[UnhandledDongleWarning] = []
        has_uinput_xbox = any(
            "xbox" in c.name.lower() or "x-box" in c.name.lower()
            for c in self.get_external_controllers()
        )
        for usb_str in sorted(glob.glob("/sys/bus/usb/devices/*")):
            usb_dir = Path(usb_str)
            vid = _read_text(usb_dir / "idVendor").lower()
            pid = _read_text(usb_dir / "idProduct").lower()
            if (vid, pid) not in XBOX_ADAPTER_USB_IDS:
                continue
            # Check if any USB interface has a bound kernel driver (e.g., xone)
            bound = any((iface / "driver").exists() for iface in usb_dir.glob(f"{usb_dir.name}:*"))
            if not bound and not has_uinput_xbox:
                prod_name = _read_text(usb_dir / "product") or "Microsoft Xbox Wireless Adapter"
                warnings.append(
                    UnhandledDongleWarning(
                        usb_id=f"{vid}:{pid}",
                        device_name=prod_name,
                        sysfs_path=str(usb_dir),
                        remediation=(
                            "SteamOS does not include an in-tree driver for the official Xbox 2.4GHz "
                            "adapter (045e:02fe). Install `dlundqvist/xone` (or `medusalix/xow`) or "
                            "switch the Xbox controller to Bluetooth mode."
                        ),
                    )
                )
        return warnings

    def _find_neptune_usb_interfaces(self) -> list[str]:
        interfaces: list[str] = []
        for usb_str in sorted(glob.glob("/sys/bus/usb/devices/*")):
            usb_dir = Path(usb_str)
            if ":" in usb_dir.name:
                continue
            if (
                _read_text(usb_dir / "idVendor").lower() == VALVE_VENDOR
                and _read_text(usb_dir / "idProduct").lower() == NEPTUNE_PRODUCT
            ):
                for iface in sorted(usb_dir.glob(f"{usb_dir.name}:1.*")):
                    interfaces.append(iface.name)
        return interfaces or ["3-3:1.0", "3-3:1.1", "3-3:1.2"]

    def is_builtin_controller_bound(self) -> bool:
        return any((USB_HID_DRIVER / iface).exists() for iface in self._find_neptune_usb_interfaces())

    def set_builtin_controller_bound(self, bound: bool) -> bool:
        interfaces = self._find_neptune_usb_interfaces()
        action = "bind-neptune" if bound else "unbind-neptune"
        ok = True
        for iface in interfaces:
            currently_bound = (USB_HID_DRIVER / iface).exists()
            if bound == currently_bound:
                continue
            if not self._run_helper_or_write(action, iface):
                ok = False
        return ok

    def _find_usb_wakeup_files(self) -> list[Path]:
        nodes: list[Path] = []
        for usb_str in sorted(glob.glob("/sys/bus/usb/devices/*/power/wakeup")):
            wakeup_file = Path(usb_str)
            dev_dir = wakeup_file.parent.parent
            prod = _read_text(dev_dir / "product").lower()
            cls = _read_text(dev_dir / "bDeviceClass").lower()
            # Bluetooth radio class 0xe0 or external wireless/HID receivers
            if cls == "e0" or any(k in prod for k in ("bluetooth", "wireless", "xbox", "receiver")):
                nodes.append(wakeup_file)
        return nodes

    def set_lcd_bluetooth_wakeup(self, enabled: bool) -> bool:
        val = "enabled" if enabled else "disabled"
        ok = True
        for node in self._find_usb_wakeup_files():
            if _read_text(node) != val:
                if not self._run_helper_or_write("set-wakeup", str(node), val):
                    ok = False
        return ok

    def get_lcd_bluetooth_wakeup(self) -> bool:
        return any(_read_text(node) == "enabled" for node in self._find_usb_wakeup_files())

    def _classify_sink_kind(self, text: str) -> str:
        low = text.lower()
        if "bluez" in low:
            return "bluetooth"
        if "hdmi" in low or "displayport" in low or "dp-" in low:
            return "hdmi"
        if "acp5x" in low or "speaker" in low or "vangogh" in low or "nau8821" in low:
            return "speakers"
        if "usb" in low:
            return "usb"
        return "other"

    def get_audio_state(self) -> AudioState:
        rc, out = self.session.run_user_cmd(["wpctl", "status"])
        sinks: list[AudioSink] = []
        default_sink: AudioSink | None = None
        if rc == 0:
            in_audio = False
            in_sinks = False
            for line in out.splitlines():
                if line.startswith("Audio"):
                    in_audio = True
                    continue
                if in_audio and line.startswith("Video"):
                    break
                if in_audio and "Sinks:" in line:
                    in_sinks = True
                    continue
                if in_sinks and ("Sources:" in line or "Filters:" in line or "Streams:" in line):
                    in_sinks = False
                    continue
                if in_sinks:
                    m = re.search(r"(\*)?\s*(\d+)\.\s+(.+?)\s*(?:\[vol:\s*([0-9.]+).*\])?$", line)
                    if not m:
                        continue
                    is_def = m.group(1) == "*"
                    sid = int(m.group(2))
                    desc = m.group(3).strip()
                    sink = AudioSink(
                        sink_id=sid,
                        name=desc,
                        description=desc,
                        kind=self._classify_sink_kind(desc),
                        is_default=is_def,
                    )
                    sinks.append(sink)
                    if is_def:
                        default_sink = sink

        vol = 0.50
        muted = False
        rc_v, v_out = self.session.run_user_cmd(["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"])
        if rc_v == 0:
            vm = re.search(r"Volume:\s*([0-9.]+)", v_out)
            if vm:
                vol = float(vm.group(1))
            muted = "[MUTED]" in v_out
        return AudioState(sinks=tuple(sinks), default_sink=default_sink, volume=vol, muted=muted)

    def ensure_wireplumber_keepalive(self) -> None:
        base_cfg = self.session.home_dir / ".config"
        wp_dir = base_cfg / "wireplumber"
        conf_dir = wp_dir / "wireplumber.conf.d"
        conf_path = conf_dir / "51-switchdeck-keepalive.conf"
        if conf_path.exists() or conf_path.is_symlink():
            return
        created_dirs = [d for d in (base_cfg, wp_dir, conf_dir) if not d.exists()]
        conf_dir.mkdir(parents=True, exist_ok=True)
        conf_path.write_text(
            'monitor.alsa.rules = [\n'
            '  {\n'
            '    matches = [\n'
            '      { node.name = "~alsa_output.pci-0000_04_00.*" }\n'
            '      { node.name = "~alsa_output.platform-acp*" }\n'
            '    ]\n'
            '    actions = {\n'
            '      update-props = {\n'
            '        session.suspend-timeout-seconds = 0\n'
            '        node.pause-on-idle = false\n'
            '      }\n'
            '    }\n'
            '  }\n'
            ']\n',
            encoding="utf-8",
        )
        if self.session.is_root_host:
            for d in created_dirs:
                try:
                    os.chown(d, self.session.uid, self.session.gid)
                except (PermissionError, OSError, AttributeError):
                    pass
            try:
                os.chown(conf_path, self.session.uid, self.session.gid)
            except (PermissionError, OSError, AttributeError):
                pass

    def set_default_audio_sink(self, sink_id: int) -> bool:
        rc, _ = self.session.run_user_cmd(["wpctl", "set-default", str(sink_id)])
        return rc == 0

    def set_sink_volume(self, volume: float) -> bool:
        clamped = max(0.0, min(1.0, volume))
        rc, _ = self.session.run_user_cmd(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{clamped:.2f}"])
        return rc == 0

    def set_tdp_limit(self, watts: int) -> bool:
        rc, _ = self.session.run_user_cmd(["steamosctl", "set-tdp-limit", str(int(watts))])
        return rc == 0

    def set_gpu_performance_auto(self) -> bool:
        rc, _ = self.session.run_user_cmd(["steamosctl", "set-gpu-performance-level", "auto"])
        return rc == 0

    def get_apu_temperature_c(self) -> float | None:
        dev_dir = find_validated_amdgpu_device()
        if dev_dir is None:
            return None
        hwmon = find_validated_amdgpu_hwmon(dev_dir)
        if hwmon is None:
            return None
        raw = _read_text(hwmon / "temp1_input")
        if raw.isdigit():
            return round(int(raw) / 1000.0, 1)
        return None

    def get_max_sustained_tdp_watts(self) -> int:
        dev_dir = find_validated_amdgpu_device()
        if dev_dir is None:
            return 15
        hwmon = find_validated_amdgpu_hwmon(dev_dir)
        if hwmon is None:
            return 15
        raw = _read_text(hwmon / "power1_cap_max")
        if raw.isdigit():
            watts = int(raw) // 1_000_000
            return max(15, min(30, watts))
        return 15

    def apply_docked_overclock(self, watts: int, gpu_max_mhz: int, cpu_boost: bool) -> bool:
        try:
            watts_val, gpu_mhz, boost_flag = validate_overclock_args(watts, gpu_max_mhz, cpu_boost)
        except ValueError:
            return False
        self.session.run_user_cmd(["steamosctl", "set-tdp-limit", str(min(watts_val, 15))])
        if os.geteuid() == 0:
            return apply_runtime_overclock_sysfs(watts_val, gpu_mhz, boost_flag)
        if HELPER_PATH.exists():
            rc, _ = _run_cmd(
                [
                    "sudo",
                    "-n",
                    str(HELPER_PATH),
                    "apply-overclock",
                    str(watts_val),
                    str(gpu_mhz),
                    "1" if boost_flag else "0",
                ]
            )
            return rc == 0
        return False

    def reset_docked_overclock(self, fallback_tdp_watts: int = 15) -> bool:
        safe_watts = max(3, min(15, int(fallback_tdp_watts)))
        sys_ok = False
        if os.geteuid() == 0:
            sys_ok = reset_runtime_overclock_sysfs(safe_watts)
        elif HELPER_PATH.exists():
            rc_help, _ = _run_cmd(["sudo", "-n", str(HELPER_PATH), "reset-overclock", str(safe_watts)])
            sys_ok = rc_help == 0
        rc_tdp, _ = self.session.run_user_cmd(["steamosctl", "set-tdp-limit", str(safe_watts)])
        self.session.run_user_cmd(["steamosctl", "set-gpu-performance-level", "auto"])
        return sys_ok or rc_tdp == 0

    def set_charge_limit(self, percent: int) -> bool:
        rc, _ = self.session.run_user_cmd(["steamosctl", "set-max-charge-level", str(int(percent))])
        return rc == 0

    def get_charge_limit(self) -> int:
        rc, out = self.session.run_user_cmd(["steamosctl", "get-max-charge-level"])
        if rc == 0:
            m = re.search(r"(-?\d+)", out)
            if m:
                return int(m.group(1))
        return -1

    def _read_gpu_busy_percent(self) -> int | None:
        for busy_path in glob.glob("/sys/class/drm/card*/device/gpu_busy_percent"):
            raw = _read_text(Path(busy_path))
            if raw.isdigit():
                return int(raw)
        return None

    def get_active_game_window(self) -> GameWindowState | None:
        rc, prop_out = self.session.run_user_cmd(
            ["xprop", "-root", "GAMESCOPE_FOCUSED_APP", "GAMESCOPE_FOCUSED_WINDOW"],
            extra_env={"DISPLAY": self.display},
        )
        if rc != 0:
            return None

        app_id: int | None = None
        win_id: int | None = None
        m_app = re.search(r"GAMESCOPE_FOCUSED_APP\(CARDINAL\)\s*=\s*(\d+)", prop_out)
        if m_app:
            app_id = int(m_app.group(1))
        m_win = re.search(r"GAMESCOPE_FOCUSED_WINDOW\(CARDINAL\)\s*=\s*(\d+)", prop_out)
        if m_win:
            win_id = int(m_win.group(1))
        if app_id in (None, 0, 769) or not win_id:  # 769 = Steam Big Picture UI
            return None

        pid: int | None = None
        width, height = 0, 0
        title = ""
        rc_w, win_out = self.session.run_user_cmd(
            ["xwininfo", "-id", str(win_id)],
            extra_env={"DISPLAY": self.game_display},
        )
        if rc_w == 0:
            wm = re.search(r"Width:\s*(\d+)\s+Height:\s*(\d+)", win_out)
            if wm:
                width, height = int(wm.group(1)), int(wm.group(2))
            tm = re.search(r'xwininfo:\s*Window id:\s*0x[0-9a-fA-F]+\s*"([^"]*)"', win_out)
            if tm:
                title = tm.group(1)

        rc_p, p_out = self.session.run_user_cmd(
            ["xprop", "-id", str(win_id), "_NET_WM_PID"],
            extra_env={"DISPLAY": self.game_display},
        )
        if rc_p == 0:
            pm = re.search(r"_NET_WM_PID\(CARDINAL\)\s*=\s*(\d+)", p_out)
            if pm:
                pid = int(pm.group(1))

        return GameWindowState(
            pid=pid,
            app_id=app_id,
            window_id=win_id,
            server_idx=1,
            width=width,
            height=height,
            gpu_busy_percent=self._read_gpu_busy_percent(),
            title=title,
        )

    def apply_gamescope_scaling(self, decision: ScalingDecision, server_idx: int = 1) -> bool:
        if not shutil.which("xprop"):
            return False
        env = {"DISPLAY": self.display}
        super_res = 1 if decision.allow_super_res else 0
        cmds = [
            [
                "xprop", "-root", "-f", "GAMESCOPE_XWAYLAND_MODE_CONTROL", "32c",
                "-set", "GAMESCOPE_XWAYLAND_MODE_CONTROL",
                f"{server_idx}, {decision.target_width}, {decision.target_height}, {super_res}",
            ],
            [
                "xprop", "-root", "-f", "GAMESCOPE_NEW_SCALING_FILTER", "32c",
                "-set", "GAMESCOPE_NEW_SCALING_FILTER", str(int(decision.scaling_filter)),
            ],
            [
                "xprop", "-root", "-f", "GAMESCOPE_NEW_SCALING_SCALER", "32c",
                "-set", "GAMESCOPE_NEW_SCALING_SCALER", str(int(decision.scaling_scaler)),
            ],
            [
                "xprop", "-root", "-f", "GAMESCOPE_FSR_SHARPNESS", "32c",
                "-set", "GAMESCOPE_FSR_SHARPNESS", str(max(0, min(20, decision.fsr_sharpness))),
            ],
            [
                "xprop", "-root", "-f", "GAMESCOPE_VRR_ENABLED", "32c",
                "-set", "GAMESCOPE_VRR_ENABLED", "1" if decision.enable_vrr else "0",
            ],
        ]
        all_ok = True
        for cmd in cmds:
            rc, _ = self.session.run_user_cmd(cmd, extra_env=env)
            if rc != 0:
                all_ok = False
        return all_ok

    def nudge_gamescope_display(self) -> bool:
        rc, _ = self.session.run_user_cmd(
            ["xprop", "-root", "-f", "GAMESCOPE_DISPLAY_MODE_NUDGE", "32c", "-set", "GAMESCOPE_DISPLAY_MODE_NUDGE", "1"],
            extra_env={"DISPLAY": self.display},
        )
        return rc == 0

    def trigger_hdmi_cec_wake(self) -> bool:
        rc, _ = self.session.run_user_cmd(["steamosctl", "set-hdmi-cec-state", "control-and-wake"])
        if shutil.which("cec-ctl"):
            _run_cmd(["cec-ctl", "--to", "0", "--image-view-on"])
            _run_cmd(["cec-ctl", "--to", "0", "--active-source", "phys-addr=1.0.0.0"])
        return rc == 0

    def pause_game_process(self, pid: int) -> bool:
        ok, starttime = validate_game_pid(pid)
        if not ok or starttime is None:
            return False
        try:
            os.kill(pid, signal.SIGSTOP)
        except OSError:
            return False
        self._paused_starttimes[pid] = starttime
        return True

    def resume_game_process(self, pid: int) -> bool:
        expected = self._paused_starttimes.pop(pid, None)
        if expected is None:
            return False
        ok, current = validate_game_pid(pid)
        if not ok or current is None or current != expected:
            return False
        try:
            os.kill(pid, signal.SIGCONT)
            return True
        except OSError:
            return False
