"""Core domain types and enums for SwitchDeck."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from enum import Enum, IntEnum
from typing import Any


def _clamp_int(value: Any, lo: int, hi: int, default: int) -> int:
    """Parse an integer value safely (rejecting bool/NaN/inf) and clamp to [lo, hi]."""
    if isinstance(value, bool) or value is None:
        return default
    if isinstance(value, float):
        if not math.isfinite(value):
            return default
        parsed = int(round(value))
    else:
        try:
            parsed = int(value)
        except (TypeError, ValueError, OverflowError):
            return default
    return max(lo, min(hi, parsed))


def _clamp_float(value: Any, lo: float, hi: float, default: float) -> float:
    """Parse a finite float value safely (rejecting bool/NaN/inf) and clamp to [lo, hi]."""
    if isinstance(value, bool) or value is None:
        return default
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    if not math.isfinite(parsed):
        return default
    return max(lo, min(hi, parsed))


def _clamp_charge_limit(value: Any, default: int = 80) -> int:
    """Allow -1 (disabled/100%) or clamp charge limit into [50, 100]."""
    if isinstance(value, bool) or value is None:
        return default
    if isinstance(value, float):
        if not math.isfinite(value):
            return default
        parsed = int(round(value))
    else:
        try:
            parsed = int(value)
        except (TypeError, ValueError, OverflowError):
            return default
    if parsed == -1:
        return -1
    return max(50, min(100, parsed))


class DeckModel(str, Enum):
    """DMI-detected hardware family."""

    JUPITER_LCD = "Jupiter"
    GALILEO_OLED = "Galileo"
    GENERIC_STEAMOS = "Generic"


class GamescopeFilter(IntEnum):
    """Matches GamescopeUpscaleFilter in ValveSoftware/gamescope/src/main.hpp."""

    LINEAR = 0
    NEAREST = 1
    FSR = 2
    NIS = 3
    PIXEL = 4
    SGSR = 5


class GamescopeScaler(IntEnum):
    """Matches GamescopeUpscaleScaler in ValveSoftware/gamescope/src/main.hpp."""

    AUTO = 0
    INTEGER = 1
    FIT = 2
    FILL = 3
    STRETCH = 4


@dataclass(frozen=True)
class DisplayMode:
    """DRM connector mode candidate."""

    width: int
    height: int
    refresh_hz: float
    preferred: bool = False

    @property
    def label(self) -> str:
        hz = int(round(self.refresh_hz))
        return f"{self.width}x{self.height}@{hz}Hz"


@dataclass(frozen=True)
class EdidInfo:
    """Parsed EDID metadata and stable SHA-256 profile key."""

    manufacturer_id: str
    product_code: int
    monitor_name: str
    native_width: int
    native_height: int
    fingerprint: str
    native_refresh_hz: float = 60.0

    @property
    def profile_id(self) -> str:
        slug = "".join(c if c.isalnum() else "_" for c in self.monitor_name).strip("_") or "Display"
        return f"{self.manufacturer_id}_{slug}_{self.fingerprint}"


@dataclass(frozen=True)
class DisplayConnector:
    """External DRM display connector state."""

    name: str
    connected: bool
    modes: tuple[DisplayMode, ...] = ()
    edid: EdidInfo | None = None
    vrr_capable: bool = False


@dataclass(frozen=True)
class ExternalController:
    """Validated real external gamepad exposed to Linux input."""

    input_name: str
    name: str
    vendor_id: str
    product_id: str
    transport: str  # "usb", "dongle_24g", "bluetooth", "uinput", "puck"
    sysfs_path: str
    event_dev: str | None = None
    is_actively_awake: bool = True
    wakeup_count: int = 0

    @property
    def usb_id(self) -> str:
        return f"{self.vendor_id}:{self.product_id}"


@dataclass(frozen=True)
class UnhandledDongleWarning:
    """USB wireless receiver attached without a bound Linux input driver."""

    usb_id: str
    device_name: str
    sysfs_path: str
    remediation: str


@dataclass(frozen=True)
class AudioSink:
    """PipeWire audio output node."""

    sink_id: int
    name: str
    description: str
    kind: str  # "speakers", "hdmi", "bluetooth", "usb", "other"
    is_default: bool = False


@dataclass(frozen=True)
class AudioState:
    """Current PipeWire routing and volume snapshot."""

    sinks: tuple[AudioSink, ...] = ()
    default_sink: AudioSink | None = None
    volume: float = 0.5
    muted: bool = False


@dataclass(frozen=True)
class GameWindowState:
    """Observed state of the active foreground game inside Gamescope."""

    pid: int | None
    app_id: int | None
    window_id: int | None
    server_idx: int
    width: int
    height: int
    gpu_busy_percent: int | None = None
    title: str = ""


@dataclass(frozen=True)
class ScalingDecision:
    """Runtime Gamescope X11 atom command set produced by scaling engine."""

    target_width: int
    target_height: int
    scaling_filter: GamescopeFilter
    scaling_scaler: GamescopeScaler
    fsr_sharpness: int
    allow_super_res: bool = False
    enable_vrr: bool = False
    reason: str = ""


STOCK_MAX_TDP_WATTS = 15
HARD_MAX_OVERCLOCK_TDP_WATTS = 22
MIN_OVERCLOCK_GPU_MHZ = 1600
MAX_OVERCLOCK_GPU_MHZ = 2000
THERMAL_THROTTLE_TRIGGER_C = 90.0
THERMAL_THROTTLE_RECOVER_C = 80.0


def _clamp_gpu_max_mhz(value: Any, default: int = 0) -> int:
    """Allow 0 (Stock Auto) or clamp manual GPU ceiling into [1600, 2000] MHz."""
    if isinstance(value, bool) or value is None:
        return default
    if isinstance(value, float):
        if not math.isfinite(value):
            return default
        parsed = int(round(value))
    else:
        try:
            parsed = int(value)
        except (TypeError, ValueError, OverflowError):
            return default
    if parsed <= 0:
        return 0
    return max(MIN_OVERCLOCK_GPU_MHZ, min(MAX_OVERCLOCK_GPU_MHZ, parsed))


VALID_TV_DRIVERS: frozenset[str] = frozenset(
    {
        "cec",
        "samsung_tizen",
        "lg_webos",
        "sony_bravia",
        "roku_ecp",
        "wol",
        "webhook",
        "none",
    }
)

DEFAULT_TV_PORTS: dict[str, int] = {
    "cec": 8002,
    "samsung_tizen": 8002,
    "lg_webos": 3001,
    "sony_bravia": 80,
    "roku_ecp": 8060,
    "wol": 9,
    "webhook": 443,
    "none": 8002,
}

_TV_HDMI_INPUT_MAP: dict[str, str] = {
    "HDMI1": "HDMI1",
    "HDMI2": "HDMI2",
    "HDMI3": "HDMI3",
    "HDMI4": "HDMI4",
    "AV1": "AV1",
    "TUNER": "Tuner",
}


def _clean_tv_str(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        return ""
    return value.strip()


@dataclass
class TvDriverConfig:
    """Per-dock TV control settings (supports CEC + LAN Smart TVs)."""

    driver: str = "cec"
    host: str = ""
    port: int = 8002
    mac_address: str = ""
    hdmi_input: str = "HDMI2"
    webhook_url: str = ""
    auto_power_on: bool = True
    auto_switch_input: bool = True

    @classmethod
    def from_dict(cls, raw: Any) -> TvDriverConfig:
        if not isinstance(raw, dict):
            return cls()
        raw_driver = raw.get("driver", cls.driver)
        driver = str(raw_driver if raw_driver is not None else cls.driver).strip().lower()
        if driver not in VALID_TV_DRIVERS:
            driver = cls.driver
        default_port = DEFAULT_TV_PORTS.get(driver, 8002)
        if "port" in raw and raw["port"] is not None:
            port = _clamp_int(raw["port"], 1, 65535, default_port)
        else:
            port = default_port

        raw_hdmi = raw.get("hdmi_input")
        hdmi_key = raw_hdmi.strip().upper() if isinstance(raw_hdmi, str) else ""
        hdmi_input = _TV_HDMI_INPUT_MAP.get(hdmi_key, cls.hdmi_input)

        auto_power_raw = raw.get("auto_power_on")
        auto_power_on = auto_power_raw if isinstance(auto_power_raw, bool) else cls.auto_power_on
        auto_switch_raw = raw.get("auto_switch_input")
        auto_switch_input = (
            auto_switch_raw if isinstance(auto_switch_raw, bool) else cls.auto_switch_input
        )

        return cls(
            driver=driver,
            host=_clean_tv_str(raw.get("host")),
            port=port,
            mac_address=_clean_tv_str(raw.get("mac_address")),
            hdmi_input=hdmi_input,
            webhook_url=_clean_tv_str(raw.get("webhook_url")),
            auto_power_on=auto_power_on,
            auto_switch_input=auto_switch_input,
        )


@dataclass
class DockedOverclockConfig:
    """Volatile runtime-only docked performance tuning (zero BIOS/voltage writes)."""

    risk_acknowledged: bool = False
    enabled: bool = False
    boost_tdp_watts: int = 18
    gpu_max_mhz: int = 0  # 0 = Stock Auto (1600 MHz); >0 clamped to [1600, 2000]
    cpu_boost: bool = True

    @classmethod
    def from_dict(cls, raw: Any) -> DockedOverclockConfig:
        if not isinstance(raw, dict):
            return cls()
        risk_ack = raw.get("risk_acknowledged") is True
        enabled = raw.get("enabled") is True
        cpu_boost_raw = raw.get("cpu_boost")
        cpu_boost = cpu_boost_raw if isinstance(cpu_boost_raw, bool) else cls.cpu_boost
        boost_tdp = _clamp_int(
            raw.get("boost_tdp_watts"),
            STOCK_MAX_TDP_WATTS,
            HARD_MAX_OVERCLOCK_TDP_WATTS,
            cls.boost_tdp_watts,
        )
        gpu_max = _clamp_gpu_max_mhz(raw.get("gpu_max_mhz"), cls.gpu_max_mhz)
        return cls(
            risk_acknowledged=risk_ack,
            enabled=enabled,
            boost_tdp_watts=boost_tdp,
            gpu_max_mhz=gpu_max,
            cpu_boost=cpu_boost,
        )


_INT_CLAMPS: dict[str, tuple[int, int, int]] = {
    "preferred_container_width": (640, 3840, 1920),
    "preferred_container_height": (480, 2160, 1080),
    "fsr_sharpness": (0, 20, 2),
    "docked_tdp_watts": (3, STOCK_MAX_TDP_WATTS, 15),
    "handheld_tdp_watts": (3, 15, 11),
}

_FLOAT_CLAMPS: dict[str, tuple[float, float, float]] = {
    "docked_volume": (0.0, 1.0, 0.65),
    "handheld_volume": (0.0, 1.0, 0.50),
}


@dataclass
class DockProfile:
    """Persisted profile keyed by EDID fingerprint (or 'default')."""

    profile_id: str
    display_name: str = "Generic External Display"
    preferred_container_width: int = 1920
    preferred_container_height: int = 1080
    fsr_sharpness: int = 2
    docked_tdp_watts: int = 15
    handheld_tdp_watts: int = 11
    docked_charge_limit: int = 80
    docked_volume: float = 0.65
    handheld_volume: float = 0.50
    auto_pause_on_undock: bool = True
    adaptive_gpu_downscale: bool = True
    tv: TvDriverConfig = field(default_factory=TvDriverConfig)
    overclock: DockedOverclockConfig = field(default_factory=DockedOverclockConfig)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DockProfile:
        tv = TvDriverConfig.from_dict(data.get("tv"))
        overclock = DockedOverclockConfig.from_dict(data.get("overclock"))
        kwargs: dict[str, Any] = {
            k: v
            for k, v in data.items()
            if k in cls.__dataclass_fields__ and k not in ("tv", "overclock")
        }
        kwargs.setdefault("profile_id", "default")
        for key, (lo, hi, default) in _INT_CLAMPS.items():
            if key in kwargs:
                kwargs[key] = _clamp_int(kwargs[key], lo, hi, default)
        for key, (lo, hi, default) in _FLOAT_CLAMPS.items():
            if key in kwargs:
                kwargs[key] = _clamp_float(kwargs[key], lo, hi, default)
        if "docked_charge_limit" in kwargs:
            kwargs["docked_charge_limit"] = _clamp_charge_limit(
                kwargs["docked_charge_limit"], cls.docked_charge_limit
            )
        return cls(tv=tv, overclock=overclock, **kwargs)


@dataclass
class DaemonStatus:
    """Live snapshot returned by switchdeckctl status / Unix IPC."""

    deck_model: DeckModel
    is_docked: bool
    ac_online: bool
    active_connector: str | None
    active_edid_id: str | None
    selected_output_mode: DisplayMode | None
    builtin_controller_bound: bool
    active_controllers: list[ExternalController] = field(default_factory=list)
    sleeping_controllers: list[ExternalController] = field(default_factory=list)
    unhandled_dongles: list[UnhandledDongleWarning] = field(default_factory=list)
    lcd_bluetooth_wakeup_enabled: bool = False
    charge_limit: int = -1
    tdp_watts: int | None = None
    last_scaling: ScalingDecision | None = None
    audio_sink: str | None = None
    manual_keep_builtin: bool = False
    travel_charge_override: bool = False
    transition_seq: int = 0
    last_transition: dict[str, Any] | None = None
    last_error: str | None = None
    apu_temp_c: float | None = None
    hw_max_tdp_watts: int = STOCK_MAX_TDP_WATTS
    overclock_active: bool = False
    overclock_thermal_throttled: bool = False
    overclock_status_note: str | None = None
    active_app_id: int | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["deck_model"] = self.deck_model.value
        if self.last_scaling is not None:
            data["last_scaling"]["scaling_filter"] = self.last_scaling.scaling_filter.name
            data["last_scaling"]["scaling_scaler"] = self.last_scaling.scaling_scaler.name
        return data
