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
        "gamescope",
        "gamescope-wl",
        "xwayland",
        "systemd",
        "pipewire",
        "wireplumber",
        "plugin_loader",
        "kwin_wayland",
        "plasmashell",
        "python",
        "python3",
        "switchdeckd",
        "bash",
        "zsh",
    }
)


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
    """Resolve and verify a sysfs power/wakeup node stays under sys_devices_root."""
    if not target or not sys_devices_root:
        return None
    raw = str(target)
    if "\x00" in raw or "\x00" in sys_devices_root:
        return None
    try:
        real = os.path.realpath(raw)
        root_real = os.path.realpath(sys_devices_root)
    except (OSError, ValueError, TypeError):
        return None
    if not root_real.endswith("/"):
        root_real += "/"
    if root_real == "/":
        return None
    if not real.startswith(root_real) or not real.endswith("/power/wakeup"):
        return None
    return Path(real)


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
        ipaddress.ip_address(cleaned)
        return cleaned
    except ValueError:
        pass

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
    """Validate an HTTP/HTTPS webhook URL without control/CRLF characters."""
    if not isinstance(url, str):
        raise ValueError("Webhook URL must be a string")
    if "\r" in url or "\n" in url or any(ord(ch) < 32 or ord(ch) == 127 for ch in url):
        raise ValueError("Webhook URL must not contain CR/LF or control characters")
    cleaned = url.strip()
    if not cleaned or any(ch.isspace() for ch in cleaned):
        raise ValueError(f"Invalid webhook URL: {url!r}")
    parsed = urllib.parse.urlsplit(cleaned)
    if parsed.scheme.lower() not in ("http", "https") or not parsed.hostname:
        raise ValueError(f"Webhook URL must use http/https with a valid hostname: {url!r}")
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


def validate_game_pid(pid: int, proc_root: Path = Path("/proc")) -> tuple[bool, str | None]:
    """Verify a PID is a safe non-system target and return (is_valid, starttime)."""
    if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 100 or pid == os.getpid():
        return False, None
    comm_path = proc_root / str(pid) / "comm"
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
    """Atomically serialize JSON to disk with fsync, mode, and optional ownership."""
    missing_parents: list[Path] = []
    cur = path.parent
    while not cur.exists():
        missing_parents.append(cur)
        parent = cur.parent
        if parent == cur:
            break
        cur = parent

    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if uid is not None and gid is not None:
        for created_dir in reversed(missing_parents):
            try:
                os.chmod(created_dir, 0o700)
                os.chown(created_dir, uid, gid)
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
            os.fsync(tf.fileno())
        os.chmod(tmp_name, mode)
        if uid is not None and gid is not None:
            try:
                os.chown(tmp_name, uid, gid)
            except (PermissionError, OSError, AttributeError):
                pass
        os.replace(tmp_name, path)
        tmp_name = None
    finally:
        if tmp_name is not None:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
