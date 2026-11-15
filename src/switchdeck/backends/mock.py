"""Deterministic in-memory HardwareBackend simulator for local macOS dev & tests."""

from __future__ import annotations

from dataclasses import dataclass, field

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
from ..edid import make_synthetic_edid, parse_edid


@dataclass
class MockHardwareBackend:
    """Simulates Steam Deck (LCD/OLED), USB-C hubs, 2.4GHz dongles, PipeWire, and Gamescope."""

    deck_model: DeckModel = DeckModel.JUPITER_LCD
    ac_online: bool = False
    displays: list[DisplayConnector] = field(default_factory=list)
    controllers: list[ExternalController] = field(default_factory=list)
    unhandled_dongles: list[UnhandledDongleWarning] = field(default_factory=list)
    builtin_bound: bool = True
    lcd_bt_wakeup: bool = False
    sinks: list[AudioSink] = field(default_factory=list)
    volume: float = 0.50
    tdp_watts: int = 11
    gpu_level: str = "auto"
    charge_limit: int = -1
    active_game: GameWindowState | None = None
    wireplumber_keepalive_written: bool = False
    paused_pids: set[int] = field(default_factory=set)
    events_log: list[str] = field(default_factory=list)
    applied_scaling: list[tuple[int, ScalingDecision]] = field(default_factory=list)
    cec_wake_count: int = 0
    mode_nudge_count: int = 0

    def __post_init__(self) -> None:
        if not self.sinks:
            self.sinks = [
                AudioSink(
                    sink_id=10,
                    name="alsa_output.platform-acp5x.HiFi__hw_acp5x_1__sink",
                    description="Speaker",
                    kind="speakers",
                    is_default=True,
                )
            ]

    def attach_samsung_s90c_hub(self, include_24g_xbox_dongle: bool = True, pad_awake: bool = False) -> None:
        """Simulate plugging into a generic USB-C hub connected to a Samsung S90C OLED."""
        edid = parse_edid(
            make_synthetic_edid(
                manufacturer_id="SAM",
                product_code=0x7341,
                monitor_name="SAMSUNG S90C",
                native_width=3840,
                native_height=2160,
            )
        )
        self.ac_online = True
        self.displays = [
            DisplayConnector(
                name="card0-DP-1",
                connected=True,
                modes=(
                    DisplayMode(3840, 2160, 30.0, preferred=False),
                    DisplayMode(3840, 2160, 60.0, preferred=True),
                    DisplayMode(2560, 1440, 120.0, preferred=False),
                    DisplayMode(1920, 1080, 120.0, preferred=False),
                ),
                edid=edid,
                vrr_capable=True,
            )
        ]
        if not any(s.kind == "hdmi" for s in self.sinks):
            self.sinks.append(
                AudioSink(
                    sink_id=42,
                    name="alsa_output.pci-0000_04_00.1.hdmi-stereo",
                    description="SAMSUNG S90C (HDMI)",
                    kind="hdmi",
                    is_default=False,
                )
            )
        if include_24g_xbox_dongle:
            self.controllers = [
                ExternalController(
                    input_name="input19",
                    name="Microsoft X-Box One pad (2.4GHz)",
                    vendor_id="045e",
                    product_id="02ea",
                    transport="dongle_24g",
                    sysfs_path="/sys/devices/pci0000:00/usb3/3-1/input/input19",
                    is_actively_awake=pad_awake,
                    wakeup_count=1 if pad_awake else 0,
                )
            ]
        self.events_log.append("mock: attached USB-C hub -> SAMSUNG S90C")

    def detach_hub(self, keep_wireless_controller: bool = True) -> None:
        """Simulate pulling the USB-C hub out of the Deck."""
        self.ac_online = False
        self.displays = []
        self.sinks = [s for s in self.sinks if s.kind != "hdmi"]
        if self.sinks and not any(s.is_default for s in self.sinks):
            first = self.sinks[0]
            self.sinks[0] = AudioSink(first.sink_id, first.name, first.description, first.kind, is_default=True)
        if not keep_wireless_controller:
            self.controllers = []
        self.events_log.append("mock: detached USB-C hub")

    def wake_wireless_controller(self) -> None:
        """Simulate pressing the Xbox Guide button on a sleeping 2.4GHz or BT pad."""
        updated = []
        for ctrl in self.controllers:
            updated.append(
                ExternalController(
                    input_name=ctrl.input_name,
                    name=ctrl.name,
                    vendor_id=ctrl.vendor_id,
                    product_id=ctrl.product_id,
                    transport=ctrl.transport,
                    sysfs_path=ctrl.sysfs_path,
                    event_dev=ctrl.event_dev,
                    is_actively_awake=True,
                    wakeup_count=ctrl.wakeup_count + 1,
                )
            )
        self.controllers = updated
        self.events_log.append("mock: wireless controller woke up")

    # HardwareBackend Protocol methods
    def get_deck_model(self) -> DeckModel:
        return self.deck_model

    def is_ac_online(self) -> bool:
        return self.ac_online

    def get_external_displays(self) -> list[DisplayConnector]:
        return list(self.displays)

    def get_external_controllers(self) -> list[ExternalController]:
        return list(self.controllers)

    def get_unhandled_dongles(self) -> list[UnhandledDongleWarning]:
        return list(self.unhandled_dongles)

    def is_builtin_controller_bound(self) -> bool:
        return self.builtin_bound

    def set_builtin_controller_bound(self, bound: bool) -> bool:
        if self.builtin_bound != bound:
            self.builtin_bound = bound
            self.events_log.append(f"usbhid:{'bind' if bound else 'unbind'} 28de:1205")
        return True

    def set_lcd_bluetooth_wakeup(self, enabled: bool) -> bool:
        if self.lcd_bt_wakeup != enabled:
            self.lcd_bt_wakeup = enabled
            self.events_log.append(f"power/wakeup:{'enabled' if enabled else 'disabled'}")
        return True

    def get_lcd_bluetooth_wakeup(self) -> bool:
        return self.lcd_bt_wakeup

    def get_audio_state(self) -> AudioState:
        default_sink = next((s for s in self.sinks if s.is_default), self.sinks[0] if self.sinks else None)
        return AudioState(sinks=tuple(self.sinks), default_sink=default_sink, volume=self.volume, muted=False)

    def ensure_wireplumber_keepalive(self) -> None:
        self.wireplumber_keepalive_written = True

    def set_default_audio_sink(self, sink_id: int) -> bool:
        found = False
        new_sinks: list[AudioSink] = []
        for s in self.sinks:
            is_def = s.sink_id == sink_id
            if is_def:
                found = True
            new_sinks.append(AudioSink(s.sink_id, s.name, s.description, s.kind, is_default=is_def))
        if found:
            self.sinks = new_sinks
            self.events_log.append(f"wpctl:set-default {sink_id}")
        return found

    def set_sink_volume(self, volume: float) -> bool:
        self.volume = max(0.0, min(1.0, round(volume, 2)))
        self.events_log.append(f"wpctl:set-volume {self.volume:.2f}")
        return True

    def set_tdp_limit(self, watts: int) -> bool:
        self.tdp_watts = watts
        self.events_log.append(f"steamosctl:set-tdp-limit {watts}W")
        return True

    def set_gpu_performance_auto(self) -> bool:
        self.gpu_level = "auto"
        self.events_log.append("steamosctl:set-gpu-performance-level auto")
        return True

    def set_charge_limit(self, percent: int) -> bool:
        self.charge_limit = percent
        self.events_log.append(f"steamosctl:set-max-charge-level {percent}")
        return True

    def get_charge_limit(self) -> int:
        return self.charge_limit

    def get_active_game_window(self) -> GameWindowState | None:
        return self.active_game

    def apply_gamescope_scaling(self, decision: ScalingDecision, server_idx: int = 1) -> bool:
        self.applied_scaling.append((server_idx, decision))
        self.events_log.append(
            f"gamescope:mode({server_idx},{decision.target_width}x{decision.target_height}) "
            f"filter={decision.scaling_filter.name} scaler={decision.scaling_scaler.name}"
        )
        return True

    def nudge_gamescope_display(self) -> bool:
        self.mode_nudge_count += 1
        self.events_log.append("gamescope:GAMESCOPE_DISPLAY_MODE_NUDGE=1")
        return True

    def trigger_hdmi_cec_wake(self) -> bool:
        self.cec_wake_count += 1
        self.events_log.append("cec:wake")
        return True

    def pause_game_process(self, pid: int) -> bool:
        self.paused_pids.add(pid)
        self.events_log.append(f"kill:SIGSTOP pid={pid}")
        return True

    def resume_game_process(self, pid: int) -> bool:
        self.paused_pids.discard(pid)
        self.events_log.append(f"kill:SIGCONT pid={pid}")
        return True
