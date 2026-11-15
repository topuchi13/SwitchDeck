"""Protocol defining hardware/OS interactions so coordinator tests cleanly."""

from __future__ import annotations

from typing import Protocol

from ..domain import (
    AudioState,
    DeckModel,
    DisplayConnector,
    ExternalController,
    GameWindowState,
    ScalingDecision,
    UnhandledDongleWarning,
)


class HardwareBackend(Protocol):
    """Boundary between SwitchDeck state machine and SteamOS / mock hardware."""

    def get_deck_model(self) -> DeckModel:
        ...

    def is_ac_online(self) -> bool:
        ...

    def get_external_displays(self) -> list[DisplayConnector]:
        ...

    def get_external_controllers(self) -> list[ExternalController]:
        ...

    def get_unhandled_dongles(self) -> list[UnhandledDongleWarning]:
        ...

    def is_builtin_controller_bound(self) -> bool:
        ...

    def set_builtin_controller_bound(self, bound: bool) -> bool:
        ...

    def set_lcd_bluetooth_wakeup(self, enabled: bool) -> bool:
        ...

    def get_lcd_bluetooth_wakeup(self) -> bool:
        ...

    def get_audio_state(self) -> AudioState:
        ...

    def ensure_wireplumber_keepalive(self) -> None:
        ...

    def set_default_audio_sink(self, sink_id: int) -> bool:
        ...

    def set_sink_volume(self, volume: float) -> bool:
        ...

    def set_tdp_limit(self, watts: int) -> bool:
        ...

    def set_gpu_performance_auto(self) -> bool:
        ...

    def set_charge_limit(self, percent: int) -> bool:
        ...

    def get_charge_limit(self) -> int:
        ...

    def get_active_game_window(self) -> GameWindowState | None:
        ...

    def apply_gamescope_scaling(self, decision: ScalingDecision, server_idx: int = 1) -> bool:
        ...

    def nudge_gamescope_display(self) -> bool:
        ...

    def trigger_hdmi_cec_wake(self) -> bool:
        ...

    def pause_game_process(self, pid: int) -> bool:
        ...

    def resume_game_process(self, pid: int) -> bool:
        ...
