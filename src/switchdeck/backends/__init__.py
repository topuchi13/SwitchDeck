"""Hardware backend abstractions for SwitchDeck."""

from .linux import LinuxHardwareBackend
from .mock import MockHardwareBackend
from .protocol import HardwareBackend

__all__ = ["HardwareBackend", "LinuxHardwareBackend", "MockHardwareBackend"]
