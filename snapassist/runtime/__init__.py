"""Contratos neutrales de plataforma para el core SnapAssist 2.x."""

from snapassist.runtime.contracts import (
    Capability,
    EventKind,
    EventSource,
    LogicalRect,
    MonitorSnapshot,
    OperationResult,
    PlatformEvent,
    PlatformRuntime,
    PresentationPort,
    ShortcutProvider,
    WindowController,
    WindowSnapshot,
)
from snapassist.runtime.gnome_client import (
    GnomeProtocolClient,
    ProtocolDisconnected,
    ProtocolError,
    ProtocolInfo,
    ProtocolVersionError,
    UiAction,
)

__all__ = [
    "Capability",
    "EventKind",
    "EventSource",
    "LogicalRect",
    "MonitorSnapshot",
    "OperationResult",
    "PlatformEvent",
    "PlatformRuntime",
    "PresentationPort",
    "ShortcutProvider",
    "WindowController",
    "WindowSnapshot",
    "GnomeProtocolClient",
    "ProtocolDisconnected",
    "ProtocolError",
    "ProtocolInfo",
    "ProtocolVersionError",
    "UiAction",
]
