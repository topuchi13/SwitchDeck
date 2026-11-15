"""SwitchDeck: Universal Switch-like docking daemon for Steam Deck & SteamOS."""

from .domain import (
    AudioSink,
    AudioState,
    DaemonStatus,
    DeckModel,
    DisplayConnector,
    DisplayMode,
    DockProfile,
    EdidInfo,
    ExternalController,
    GameWindowState,
    GamescopeFilter,
    GamescopeScaler,
    ScalingDecision,
    TvDriverConfig,
    UnhandledDongleWarning,
)

__all__ = [
    "AudioSink",
    "AudioState",
    "DaemonStatus",
    "DeckModel",
    "DisplayConnector",
    "DisplayMode",
    "DockProfile",
    "EdidInfo",
    "ExternalController",
    "GameWindowState",
    "GamescopeFilter",
    "GamescopeScaler",
    "ScalingDecision",
    "TvDriverConfig",
    "UnhandledDongleWarning",
]
__version__ = "0.1.0"
