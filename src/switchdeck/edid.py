"""Binary EDID parser and HDMI 2.0/2.1 display mode scorer."""

from __future__ import annotations

import hashlib
import math
import struct
from typing import Iterable

from .domain import DisplayMode, EdidInfo

EDID_MAGIC = b"\x00\xff\xff\xff\xff\xff\xff\x00"


def _decode_pnp_id(raw_two_bytes: bytes) -> str:
    word = struct.unpack(">H", raw_two_bytes)[0]
    chars = []
    for shift in (10, 5, 0):
        code = (word >> shift) & 0x1F
        chars.append(chr(code + 64) if 1 <= code <= 26 else "?")
    return "".join(chars)


def _encode_pnp_id(pnp: str) -> bytes:
    cleaned = (pnp.upper() + "AAA")[:3]
    vals = [max(1, min(26, ord(ch) - 64)) for ch in cleaned]
    word = (vals[0] << 10) | (vals[1] << 5) | vals[2]
    return struct.pack(">H", word)


def parse_edid(raw: bytes) -> EdidInfo | None:
    """Parse and checksum-verify a 128+ byte binary EDID blob from `/sys/class/drm/.../edid`."""
    if len(raw) < 128 or raw[:8] != EDID_MAGIC:
        return None
    if (sum(raw[:128]) % 256) != 0:
        return None

    manufacturer_id = _decode_pnp_id(raw[8:10])
    product_code = struct.unpack("<H", raw[10:12])[0]
    fingerprint = hashlib.sha256(raw[:128]).hexdigest()[:12]

    native_width = 0
    native_height = 0
    native_refresh_hz = 60.0
    monitor_name = ""

    # Detailed timing descriptor 1 sits at bytes 54..71
    dtd0 = raw[54:72]
    pclk_10khz = struct.unpack("<H", dtd0[0:2])[0]
    if pclk_10khz != 0:
        native_width = dtd0[2] | ((dtd0[4] >> 4) << 8)
        native_height = dtd0[5] | ((dtd0[7] >> 4) << 8)
        h_blank = dtd0[3] | ((dtd0[4] & 0x0F) << 8)
        v_blank = dtd0[6] | ((dtd0[7] & 0x0F) << 8)
        h_total = native_width + h_blank
        v_total = native_height + v_blank
        if h_total > 0 and v_total > 0:
            calc_hz = (pclk_10khz * 10_000.0) / (h_total * v_total)
            if math.isfinite(calc_hz) and 20.0 <= calc_hz <= 360.0:
                native_refresh_hz = round(calc_hz, 2)

    # Scan the four 18-byte descriptor slots for monitor name (tag 0xFC)
    for offset in (54, 72, 90, 108):
        slot = raw[offset : offset + 18]
        if slot[:3] == b"\x00\x00\x00" and slot[3] == 0xFC:
            raw_name = slot[5:18].split(b"\n", 1)[0]
            decoded = raw_name.decode("ascii", errors="ignore")
            monitor_name = "".join(ch for ch in decoded if 32 <= ord(ch) <= 126).strip()
            break

    if not monitor_name:
        monitor_name = f"{manufacturer_id}-{product_code:04X}"

    return EdidInfo(
        manufacturer_id=manufacturer_id,
        product_code=product_code,
        monitor_name=monitor_name,
        native_width=native_width,
        native_height=native_height,
        fingerprint=fingerprint,
        native_refresh_hz=native_refresh_hz,
    )


def make_synthetic_edid(
    manufacturer_id: str = "SAM",
    product_code: int = 0x7341,
    monitor_name: str = "SAMSUNG S90C",
    native_width: int = 3840,
    native_height: int = 2160,
    native_refresh_hz: float = 60.0,
) -> bytes:
    """Build a valid 128-byte EDID block for simulation and testing."""
    buf = bytearray(128)
    buf[0:8] = EDID_MAGIC
    buf[8:10] = _encode_pnp_id(manufacturer_id)
    buf[10:12] = struct.pack("<H", product_code & 0xFFFF)
    buf[18] = 1
    buf[19] = 4  # EDID 1.4

    # Detailed timing descriptor 0 with realistic pixel clock + blanking
    h_blank = 160
    v_blank = 45
    h_total = max(1, native_width) + h_blank
    v_total = max(1, native_height) + v_blank
    pclk_10khz = max(1, min(65535, int(round((h_total * v_total * native_refresh_hz) / 10_000.0))))
    buf[54:56] = struct.pack("<H", pclk_10khz)
    buf[56] = native_width & 0xFF
    buf[57] = h_blank & 0xFF
    buf[58] = (((native_width >> 8) & 0x0F) << 4) | ((h_blank >> 8) & 0x0F)
    buf[59] = native_height & 0xFF
    buf[60] = v_blank & 0xFF
    buf[61] = (((native_height >> 8) & 0x0F) << 4) | ((v_blank >> 8) & 0x0F)

    # Monitor name descriptor in slot 1 (bytes 72..89)
    buf[72:77] = b"\x00\x00\x00\xfc\x00"
    name_bytes = monitor_name.encode("ascii", errors="ignore")[:13]
    if len(name_bytes) < 13:
        name_bytes = name_bytes + b"\n" + b" " * (12 - len(name_bytes))
    buf[77:90] = name_bytes[:13]

    checksum = (256 - (sum(buf[:127]) % 256)) % 256
    buf[127] = checksum
    return bytes(buf)


def select_best_output_mode(
    modes: Iterable[DisplayMode],
    prefer_max_height: int = 2160,
    min_refresh_hz: float = 50.0,
) -> DisplayMode | None:
    """Score DRM modes to avoid budget HDMI-hub traps (e.g. 4K@30Hz).

    Prioritizes smooth 60–120Hz 16:9 modes suitable for Steam Deck TV/monitor output:
    1. Modes >= min_refresh_hz strictly beat < 50Hz modes.
    2. Among smooth modes, rewards 120Hz (for 1080p/1440p VRR/low-latency) and
       clean 16:9 resolutions up to prefer_max_height, preferring 1080p@120Hz or
       1440p@60/120Hz or 4K@60Hz over 4K@30Hz.
    """
    candidates = [
        m
        for m in modes
        if m.width > 0 and m.height > 0 and math.isfinite(m.refresh_hz) and m.refresh_hz > 0.0
    ]
    if not candidates:
        return None

    def score(mode: DisplayMode) -> tuple[int, int, float, int, int]:
        smooth = 1 if mode.refresh_hz >= min_refresh_hz else 0
        within_cap = 1 if mode.height <= prefer_max_height else 0
        is_16_9 = 1 if abs((mode.width / mode.height) - (16 / 9)) < 0.05 else 0

        # Tier resolution nicely: 1080p@120Hz / 1440p@120Hz / 4K@60+Hz
        res_tier = 0
        if mode.height >= 2160:
            res_tier = 3 if smooth else 0
        elif mode.height >= 1440:
            res_tier = 3 if mode.refresh_hz >= 100 else 2
        elif mode.height >= 1080:
            res_tier = 3 if mode.refresh_hz >= 100 else 2
        elif mode.height >= 720:
            res_tier = 1

        hz_capped = min(mode.refresh_hz, 120.0)
        return (smooth, within_cap, res_tier * 100.0 + hz_capped + (20.0 if is_16_9 else 0.0), mode.width * mode.height, 1 if mode.preferred else 0)

    return max(candidates, key=score)
