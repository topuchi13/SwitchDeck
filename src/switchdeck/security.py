"""Security validators, safe sysfs/process helpers, and atomic JSON persistence."""

from __future__ import annotations

import ipaddress
import json
import os
import re
import tempfile
import urllib.parse
from pathlib import Path
from typing import Any

_NEPTUNE_IFACE_RE = re.compile(r"^[0-9]+-[0-9]+(?:\.[0-9]+)*:1\.[0-9]+\Z")
_RFC1123_HOST_RE = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*\Z"
)

_CANONICAL_HDMI_INPUTS: dict[str, str] = {
    "HDMI1": "HDMI1",
    "HDMI2": "HDMI2",
    "HDMI3": "HDMI3",
    "HDMI4": "HDMI4",
    "AV1": "AV1",
    "TUNER": "Tuner",
}

_PROTECTED_PROCESS_COMMS: frozenset[str] = frozenset(
    {
        "steam",
        "steamwebhelper",
        "crbrowsermain",
        "mainthrd",
        "gamescope",
        "gamescope-wl",
        "xwayland",
        "systemd",
        "systemd-udevd",
        "systemd-logind",
        "dbus-broker",
        "dbus-daemon",
        "steamos-manager",
        "pipewire",
        "pipewire-pulse",
        "wireplumber",
        "mangoapp",
        "wineserver",
        "plugin_loader",
        "kwin_wayland",
        "plasmashell",
        "polkitd",
        "bluetoothd",
        "networkmanager",
        "sshd",
        "python",
        "python3",
        "switchdeckd",
        "bash",
        "zsh",
    }
)
_NUMERIC_IPV4_LABEL_RE = re.compile(r"^(?:0[xX][0-9a-fA-F]+|[0-9]+)$")


def validate_neptune_iface(
    iface: str,
    usb_devices_root: Path = Path("/sys/bus/usb/devices"),
) -> bool:
    """Validate a usbhid interface string belongs to Valve Neptune (28de:1205)."""
    if not isinstance(iface, str) or not _NEPTUNE_IFACE_RE.fullmatch(iface):
        return False
    bus_port = iface.split(":", 1)[0]
    dev_dir = usb_devices_root / bus_port
    try:
        vid = (dev_dir / "idVendor").read_text(encoding="utf-8", errors="replace").strip().lower()
        pid = (dev_dir / "idProduct").read_text(encoding="utf-8", errors="replace").strip().lower()
    except OSError:
        return False
    return vid == "28de" and pid == "1205"


def validate_wakeup_path(
    target: str | Path,
    sys_devices_root: str = "/sys/devices/",
) -> Path | None:
    """Resolve and verify a USB sysfs power/wakeup node stays under sys_devices_root."""
    if not target or not sys_devices_root:
        return None
    raw = str(target)
    if "\x00" in raw or "\x00" in sys_devices_root:
        return None
    try:
        real = os.path.realpath(raw)
        root_real = os.path.realpath(sys_devices_root)
        default_sys_real = os.path.realpath("/sys/devices")
    except (OSError, ValueError, TypeError):
        return None
    if not root_real.endswith("/"):
        root_real += "/"
    if root_real == "/":
        return None
    if not real.startswith(root_real) or not real.endswith("/power/wakeup"):
        return None
    resolved = Path(real)
    rel_parts = resolved.relative_to(Path(root_real.rstrip("/"))).parts
    usb_dev_dir = resolved.parent.parent
    has_id_vendor = (usb_dev_dir / "idVendor").is_file()
    if root_real.rstrip("/") == default_sys_real:
        if not has_id_vendor:
            return None
    else:
        has_usb_ancestor = any(part.lower().startswith("usb") for part in rel_parts)
        if not (has_id_vendor or has_usb_ancestor):
            return None
    return resolved


def safe_write_sysfs(path: Path, value: str) -> bool:
    """Write UTF-8 text to an existing sysfs node without following symlinks."""
    flags = os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    fd: int | None = None
    try:
        fd = os.open(os.fspath(path), flags)
        data = value.encode("utf-8")
        view = memoryview(data)
        written = 0
        while written < len(data):
            n = os.write(fd, view[written:])
            if n <= 0:
                return False
            written += n
        return True
    except OSError:
        return False
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass


def _validate_ip_literal(ip_obj: ipaddress.IPv4Address | ipaddress.IPv6Address, raw_host: str) -> None:
    if ip_obj.is_unspecified or ip_obj.is_multicast:
        raise ValueError(f"Unsupported unspecified/multicast host address: {raw_host!r}")
    if str(ip_obj) == "169.254.169.254":
        raise ValueError(f"Rejected metadata endpoint IP address: {raw_host!r}")


def validate_host(host: str) -> str:
    """Validate an IPv4/IPv6 address or RFC-1123 hostname without URL/CRLF delimiters."""
    if not isinstance(host, str):
        raise ValueError("Host must be a string")
    if "\r" in host or "\n" in host or any(ord(ch) < 32 or ord(ch) == 127 for ch in host):
        raise ValueError(f"Invalid control/newline character in host: {host!r}")
    cleaned = host.strip()
    if not cleaned or len(cleaned) > 253:
        raise ValueError(f"Invalid host length: {host!r}")
    for ch in cleaned:
        if ch.isspace() or ch in ("/", "?", "#", "@"):
            raise ValueError(f"Invalid character in host: {host!r}")

    try:
        ip_obj = ipaddress.ip_address(cleaned)
        _validate_ip_literal(ip_obj, host)
        return cleaned
    except ValueError as exc:
        if "Unsupported" in str(exc) or "Rejected metadata" in str(exc):
            raise

    # Reject decimal integers, hex (0x7f000001), and octal (0177.0.0.1) IPv4 forms
    labels = cleaned.rstrip(".").split(".")
    if labels and all(_NUMERIC_IPV4_LABEL_RE.fullmatch(lbl) for lbl in labels):
        raise ValueError(f"Invalid numeric/hex/octal IPv4 host: {host!r}")

    if ":" in cleaned or not _RFC1123_HOST_RE.fullmatch(cleaned):
        raise ValueError(f"Invalid host format: {host!r}")
    return cleaned


def validate_port(port: int) -> int:
    """Validate a TCP/UDP port integer in [1, 65535]."""
    if isinstance(port, (bool, float)):
        raise ValueError(f"Port must be an integer, got {type(port).__name__}")
    try:
        value = int(port)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid port: {port!r}") from exc
    if value < 1 or value > 65535:
        raise ValueError(f"Port out of range (1..65535): {value}")
    return value


def validate_hdmi_input(hdmi_input: str) -> str:
    """Validate and canonicalize an allowlisted TV input name."""
    if not isinstance(hdmi_input, str):
        raise ValueError("HDMI input must be a string")
    if "\r" in hdmi_input or "\n" in hdmi_input or any(ord(ch) < 32 or ord(ch) == 127 for ch in hdmi_input):
        raise ValueError(f"Invalid control/newline character in HDMI input: {hdmi_input!r}")
    canonical = _CANONICAL_HDMI_INPUTS.get(hdmi_input.strip().upper())
    if canonical is None:
        raise ValueError(f"Unsupported HDMI input: {hdmi_input!r}")
    return canonical


def validate_webhook_url(url: str) -> str:
    """Validate an HTTP/HTTPS webhook URL without control/CRLF/userinfo/SSRFS."""
    if not isinstance(url, str):
        raise ValueError("Webhook URL must be a string")
    if "\r" in url or "\n" in url or any(ord(ch) < 32 or ord(ch) == 127 for ch in url):
        raise ValueError("Webhook URL must not contain CR/LF or control characters")
    cleaned = url.strip()
    if not cleaned or any(ch.isspace() for ch in cleaned):
        raise ValueError("Invalid webhook URL")
    parsed = urllib.parse.urlsplit(cleaned)
    if parsed.scheme.lower() not in ("http", "https") or not parsed.hostname:
        raise ValueError("Webhook URL must use http/https with a valid hostname")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("Webhook URL must not contain userinfo credentials")
    validate_host(parsed.hostname)
    return cleaned


def validate_mac_address(mac: str) -> str:
    """Validate and canonicalize an optional Ethernet/Wi-Fi MAC address (AA:BB:CC:DD:EE:FF)."""
    if not isinstance(mac, str):
        raise ValueError("MAC address must be a string")
    if "\r" in mac or "\n" in mac or any(ord(ch) < 32 or ord(ch) == 127 for ch in mac):
        raise ValueError(f"Invalid control/newline character in MAC address: {mac!r}")
    cleaned = mac.strip()
    if not cleaned:
        return ""
    if any(ch not in "0123456789abcdefABCDEF:-." for ch in cleaned):
        raise ValueError(f"Invalid MAC address format: {mac!r}")
    hex_digits = "".join(ch for ch in cleaned if ch not in ":-.")
    if len(hex_digits) != 12:
        raise ValueError(f"MAC address must contain 12 hex digits: {mac!r}")
    return ":".join(hex_digits[i : i + 2].upper() for i in range(0, 12, 2))


def validate_tv_secret(secret: str) -> str:
    """Validate a TV auth token/PSK without CR/LF/NUL/control characters."""
    if not isinstance(secret, str):
        raise ValueError("TV secret/PSK must be a string")
    if "\r" in secret or "\n" in secret or any(ord(ch) < 32 or ord(ch) == 127 for ch in secret):
        raise ValueError("TV secret/PSK must not contain CR/LF or control characters")
    cleaned = secret.strip()
    if not cleaned or len(cleaned) > 256:
        raise ValueError("TV secret/PSK must be 1..256 non-whitespace characters")
    return cleaned


def capture_process_starttime(pid: int, proc_root: Path = Path("/proc")) -> str | None:
    """Read field 22 (starttime) from /proc/<pid>/stat, or 'nonproc' when /proc is absent."""
    if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
        return None
    if not proc_root.exists():
        if pid > 100 and pid != os.getpid():
            return "nonproc"
        return None
    stat_path = proc_root / str(pid) / "stat"
    try:
        raw = stat_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    rparen = raw.rfind(")")
    if rparen == -1:
        return None
    fields = raw[rparen + 1 :].split()
    if len(fields) <= 19:
        return None
    return fields[19]


def validate_game_pid(
    pid: int,
    proc_root: Path = Path("/proc"),
    expected_uid: int | None = None,
) -> tuple[bool, str | None]:
    """Verify a PID is a safe non-system target and return (is_valid, starttime)."""
    if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 100 or pid == os.getpid():
        return False, None
    proc_dir = proc_root / str(pid)
    if proc_dir.exists():
        try:
            st = proc_dir.stat()
        except OSError:
            return False, None
        if expected_uid is not None and expected_uid > 0 and st.st_uid != expected_uid:
            return False, None
        if proc_root == Path("/proc") and st.st_uid == 0:
            return False, None
        exe_path = proc_dir / "exe"
        try:
            if exe_path.is_symlink():
                exe_name = os.path.basename(os.readlink(exe_path)).lower()
                if exe_name in _PROTECTED_PROCESS_COMMS:
                    return False, None
        except OSError:
            pass
    comm_path = proc_dir / "comm"
    if comm_path.exists():
        try:
            comm = comm_path.read_text(encoding="utf-8", errors="replace").strip().lower()
        except OSError:
            return False, None
        if comm in _PROTECTED_PROCESS_COMMS:
            return False, None
    starttime = capture_process_starttime(pid, proc_root=proc_root)
    if not starttime:
        return False, None
    return True, starttime


def atomic_write_json(
    path: Path,
    data: Any,
    mode: int = 0o600,
    uid: int | None = None,
    gid: int | None = None,
) -> None:
    """Atomically serialize JSON to disk with symlink rejection, fchmod/fchown, fsync, and os.replace."""
    if os.path.lexists(path) and os.path.islink(path):
        raise OSError(f"Refusing to overwrite symlink: {path}")

    missing_parents: list[Path] = []
    cur = path.parent
    while not cur.exists():
        if os.path.lexists(cur) and cur.is_symlink():
            raise OSError(f"Refusing to traverse symlink parent: {cur}")
        missing_parents.append(cur)
        parent = cur.parent
        if parent == cur:
            break
        cur = parent

    if path.parent.exists() and path.parent.is_symlink():
        raise OSError(f"Refusing to write inside symlink directory: {path.parent}")

    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.parent.is_symlink():
        raise OSError(f"Refusing to write inside symlink directory: {path.parent}")

    if uid is not None and gid is not None:
        for created_dir in reversed(missing_parents):
            try:
                os.chmod(created_dir, 0o700)
                os.chown(created_dir, uid, gid, follow_symlinks=False)
            except (PermissionError, OSError, AttributeError):
                pass

    payload = json.dumps(data, indent=2) + "\n"
    tmp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=str(path.parent),
            prefix=f".{path.name}.",
            delete=False,
        ) as tf:
            tmp_name = tf.name
            tf.write(payload)
            tf.flush()
            fd = tf.fileno()
            os.fchmod(fd, mode)
            if uid is not None and gid is not None:
                try:
                    os.fchown(fd, uid, gid)
                except (PermissionError, OSError, AttributeError):
                    pass
            os.fsync(fd)
        if os.path.lexists(path) and os.path.islink(path):
            raise OSError(f"Refusing to replace symlink target: {path}")
        os.replace(tmp_name, path)
        tmp_name = None
        dir_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
        try:
            dir_fd = os.open(os.fspath(path.parent), dir_flags)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except OSError:
            pass
    finally:
        if tmp_name is not None:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass


def _resolve_under_root(target: str | Path, root_real: str) -> Path | None:
    """Resolve target via realpath and verify strict confinement under root_real."""
    if not target or "\x00" in str(target):
        return None
    try:
        real = os.path.realpath(str(target))
    except (OSError, ValueError, TypeError):
        return None
    if real != root_real.rstrip("/") and not real.startswith(root_real):
        return None
    return Path(real)


def _normalized_sys_root(sys_devices_root: str) -> str | None:
    if not sys_devices_root or "\x00" in sys_devices_root:
        return None
    try:
        root_real = os.path.realpath(sys_devices_root)
    except (OSError, ValueError, TypeError):
        return None
    if not root_real.endswith("/"):
        root_real += "/"
    if root_real == "/":
        return None
    return root_real


def find_validated_amdgpu_device(
    drm_root: Path = Path("/sys/class/drm"),
    sys_devices_root: str = "/sys/devices/",
) -> Path | None:
    """Locate AMD GPU sysfs device directory (vendor 0x1002) confined under sys_devices_root."""
    root_real = _normalized_sys_root(sys_devices_root)
    if root_real is None:
        return None
    try:
        candidates = sorted(drm_root.glob("card*/device"))
    except OSError:
        return None
    for candidate in candidates:
        real_dev = _resolve_under_root(candidate, root_real)
        if real_dev is None:
            continue
        try:
            vendor = (real_dev / "vendor").read_text(encoding="utf-8", errors="replace").strip().lower()
        except OSError:
            continue
        if vendor == "0x1002":
            return real_dev
    return None


def find_validated_amdgpu_hwmon(
    dev_dir: Path,
    sys_devices_root: str = "/sys/devices/",
) -> Path | None:
    """Locate validated amdgpu hwmon directory strictly inside dev_dir and sys_devices_root."""
    root_real = _normalized_sys_root(sys_devices_root)
    if root_real is None:
        return None
    real_dev = _resolve_under_root(dev_dir, root_real)
    if real_dev is None:
        return None
    dev_prefix = os.fspath(real_dev).rstrip("/") + "/"
    try:
        hwmons = sorted((real_dev / "hwmon").glob("hwmon*"))
    except OSError:
        return None
    for candidate in hwmons:
        real_hw = _resolve_under_root(candidate, dev_prefix)
        if real_hw is None or not os.fspath(real_hw).startswith(root_real):
            continue
        name_path = real_hw / "name"
        if name_path.exists():
            try:
                name_val = name_path.read_text(encoding="utf-8", errors="replace").strip().lower()
            except OSError:
                continue
            if name_val != "amdgpu":
                continue
        return real_hw
    return None


def validate_overclock_args(watts: Any, gpu_max_mhz: Any, cpu_boost: Any) -> tuple[int, int, bool]:
    """Validate volatile runtime overclock bounds: 3..22W, GPU 0|1600..2000MHz, bool boost."""
    if isinstance(watts, (bool, float)):
        raise ValueError(f"Invalid watts type: {type(watts).__name__}")
    try:
        watts_val = int(watts)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid watts value: {watts!r}") from exc
    if watts_val < 3 or watts_val > 22:
        raise ValueError(f"Watts out of safe bounds (3..22): {watts_val}")

    if isinstance(gpu_max_mhz, (bool, float)):
        raise ValueError(f"Invalid gpu_max_mhz type: {type(gpu_max_mhz).__name__}")
    try:
        gpu_val = int(gpu_max_mhz)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid gpu_max_mhz value: {gpu_max_mhz!r}") from exc
    if gpu_val != 0 and (gpu_val < 1600 or gpu_val > 2000):
        raise ValueError(f"gpu_max_mhz must be 0 or 1600..2000: {gpu_val}")

    if isinstance(cpu_boost, bool):
        boost_val = cpu_boost
    elif isinstance(cpu_boost, int) and cpu_boost in (0, 1):
        boost_val = bool(cpu_boost)
    elif isinstance(cpu_boost, str) and cpu_boost in ("0", "1"):
        boost_val = cpu_boost == "1"
    else:
        raise ValueError(f"cpu_boost must be boolean or 0/1, got: {cpu_boost!r}")

    return watts_val, gpu_val, boost_val


def _read_sysfs_int(path: Path) -> int | None:
    try:
        raw = path.read_text(encoding="utf-8", errors="replace").strip()
        return int(raw) if raw.isdigit() else None
    except OSError:
        return None


def _write_cpufreq_controls(
    cpu_root: Path,
    root_real: str,
    boost_enabled: bool,
    target_governor: str,
) -> None:
    real_cpu = _resolve_under_root(cpu_root, root_real)
    if real_cpu is None:
        return
    boost_file = _resolve_under_root(real_cpu / "cpufreq" / "boost", root_real)
    if boost_file is not None and boost_file.exists():
        safe_write_sysfs(boost_file, "1\n" if boost_enabled else "0\n")
    try:
        gov_nodes = sorted(real_cpu.glob("cpu[0-9]*/cpufreq/scaling_governor"))
    except OSError:
        return
    for gov_node in gov_nodes:
        real_gov = _resolve_under_root(gov_node, root_real)
        if real_gov is None or not real_gov.exists():
            continue
        avail_path = real_gov.parent / "scaling_available_governors"
        chosen = target_governor
        if avail_path.exists():
            try:
                avail = avail_path.read_text(encoding="utf-8", errors="replace").split()
            except OSError:
                avail = []
            if avail and chosen not in avail:
                if "schedutil" in avail:
                    chosen = "schedutil"
                elif "powersave" in avail:
                    chosen = "powersave"
                else:
                    continue
        safe_write_sysfs(real_gov, f"{chosen}\n")


def apply_runtime_overclock_sysfs(
    watts: int,
    gpu_max_mhz: int = 0,
    cpu_boost: bool = True,
    *,
    drm_root: Path = Path("/sys/class/drm"),
    cpu_root: Path = Path("/sys/devices/system/cpu"),
    sys_devices_root: str = "/sys/devices/",
) -> bool:
    """Apply volatile Linux sysfs PPT caps, optional GPU OD range, and cpufreq state."""
    watts_val, gpu_mhz, boost_flag = validate_overclock_args(watts, gpu_max_mhz, cpu_boost)
    root_real = _normalized_sys_root(sys_devices_root)
    if root_real is None:
        return False

    dev_dir = find_validated_amdgpu_device(drm_root=drm_root, sys_devices_root=sys_devices_root)
    if dev_dir is None:
        return False
    hwmon_dir = find_validated_amdgpu_hwmon(dev_dir, sys_devices_root=sys_devices_root)
    if hwmon_dir is None:
        return False

    p2_path = _resolve_under_root(hwmon_dir / "power2_cap", root_real)
    if p2_path is not None and p2_path.exists():
        p2_max_uw = _read_sysfs_int(hwmon_dir / "power2_cap_max") or 24_000_000
        target_p2_uw = min((watts_val + 2) * 1_000_000, p2_max_uw, 24_000_000)
        safe_write_sysfs(p2_path, f"{target_p2_uw}\n")

    p1_max_uw = _read_sysfs_int(hwmon_dir / "power1_cap_max") or 22_000_000
    target_p1_uw = min(watts_val * 1_000_000, p1_max_uw)
    p1_path = _resolve_under_root(hwmon_dir / "power1_cap", root_real)
    if p1_path is None or not p1_path.exists() or not safe_write_sysfs(p1_path, f"{target_p1_uw}\n"):
        return False

    dpm_level = _resolve_under_root(dev_dir / "power_dpm_force_performance_level", root_real)
    pp_od = _resolve_under_root(dev_dir / "pp_od_clk_voltage", root_real)
    if gpu_mhz >= 1600:
        if dpm_level is not None and dpm_level.exists() and pp_od is not None and pp_od.exists():
            if safe_write_sysfs(dpm_level, "manual\n"):
                safe_write_sysfs(pp_od, "s 0 400\n")
                safe_write_sysfs(pp_od, f"s 1 {gpu_mhz}\n")
                safe_write_sysfs(pp_od, "c\n")
    elif gpu_mhz == 0:
        if pp_od is not None and pp_od.exists():
            safe_write_sysfs(pp_od, "r\n")
            safe_write_sysfs(pp_od, "c\n")
        if dpm_level is not None and dpm_level.exists():
            safe_write_sysfs(dpm_level, "auto\n")

    _write_cpufreq_controls(
        cpu_root=cpu_root,
        root_real=root_real,
        boost_enabled=boost_flag,
        target_governor="schedutil",
    )
    return True


def reset_runtime_overclock_sysfs(
    watts: int = 15,
    *,
    drm_root: Path = Path("/sys/class/drm"),
    cpu_root: Path = Path("/sys/devices/system/cpu"),
    sys_devices_root: str = "/sys/devices/",
) -> bool:
    """Restore stock PPT cap (clamped <= 15W), GPU DPM auto, CPU boost enabled, and schedutil."""
    if isinstance(watts, (bool, float)):
        safe_watts = 15
    else:
        try:
            safe_watts = max(3, min(15, int(watts)))
        except (TypeError, ValueError):
            safe_watts = 15

    root_real = _normalized_sys_root(sys_devices_root)
    if root_real is None:
        return False

    dev_dir = find_validated_amdgpu_device(drm_root=drm_root, sys_devices_root=sys_devices_root)
    if dev_dir is None:
        return False
    hwmon_dir = find_validated_amdgpu_hwmon(dev_dir, sys_devices_root=sys_devices_root)
    if hwmon_dir is None:
        return False

    p1_max_uw = _read_sysfs_int(hwmon_dir / "power1_cap_max") or 15_000_000
    target_p1_uw = min(safe_watts * 1_000_000, p1_max_uw)
    p1_path = _resolve_under_root(hwmon_dir / "power1_cap", root_real)
    ok = p1_path is not None and p1_path.exists() and safe_write_sysfs(p1_path, f"{target_p1_uw}\n")

    p2_path = _resolve_under_root(hwmon_dir / "power2_cap", root_real)
    if p2_path is not None and p2_path.exists():
        p2_max_uw = _read_sysfs_int(hwmon_dir / "power2_cap_max") or 15_000_000
        target_p2_uw = min(safe_watts * 1_000_000, p2_max_uw)
        safe_write_sysfs(p2_path, f"{target_p2_uw}\n")

    pp_od = _resolve_under_root(dev_dir / "pp_od_clk_voltage", root_real)
    if pp_od is not None and pp_od.exists():
        safe_write_sysfs(pp_od, "r\n")
        safe_write_sysfs(pp_od, "c\n")

    dpm_level = _resolve_under_root(dev_dir / "power_dpm_force_performance_level", root_real)
    if dpm_level is not None and dpm_level.exists():
        safe_write_sysfs(dpm_level, "auto\n")

    _write_cpufreq_controls(
        cpu_root=cpu_root,
        root_real=root_real,
        boost_enabled=True,
        target_governor="schedutil",
    )
    return ok
