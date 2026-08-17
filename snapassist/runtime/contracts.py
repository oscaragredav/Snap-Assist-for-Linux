"""Puertos y snapshots inmutables sin conceptos X11, Mutter, GJS o Tkinter."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Mapping, Protocol, Sequence, TypeAlias

WindowHandle: TypeAlias = str
MonitorHandle: TypeAlias = str
WorkspaceHandle: TypeAlias = str
OperationId: TypeAlias = str


@dataclass(frozen=True)
class LogicalRect:
    x: int
    y: int
    width: int
    height: int

    def __post_init__(self) -> None:
        if self.width < 0 or self.height < 0:
            raise ValueError("LogicalRect no admite dimensiones negativas")


class Capability(str, Enum):
    ACTIVE_WINDOW = "active-window"
    WINDOW_LIST = "window-list"
    LOGICAL_GEOMETRY = "logical-geometry"
    MONITORS = "monitors"
    WORKSPACES = "workspaces"
    FOCUS = "focus"
    MOVE_RESIZE = "move-resize"
    CONFIRMED_MOVE_RESIZE = "confirmed-move-resize"
    MAXIMIZE = "maximize"
    TRANSIENTS = "transients"
    EVENTS = "events"
    WORK_AREA = "work-area"
    HOTPLUG = "hotplug"
    SCALE = "scale"
    SHORTCUTS = "shortcuts"
    PRESENTATION = "presentation"


@dataclass(frozen=True)
class WindowSnapshot:
    handle: WindowHandle
    title: str
    app_id: str
    app_name: str
    geometry: LogicalRect
    monitor: MonitorHandle
    workspace: WorkspaceHandle
    minimized: bool = False
    maximized: bool = False
    transient_for: WindowHandle | None = None
    minimum_size: tuple[int, int] = (0, 0)
    eligible: bool = True
    client_type: str = "unknown"
    maximized_horizontally: bool = False
    maximized_vertically: bool = False
    minimum_size_known: bool = False
    maximum_size: tuple[int, int] = (0, 0)
    maximum_size_known: bool = False
    fullscreen: bool = False
    above: bool = False
    on_all_workspaces: bool = False
    allows_move: bool = True
    allows_resize: bool = True
    mapped: bool = True
    tiled: bool = False


@dataclass(frozen=True)
class MonitorSnapshot:
    handle: MonitorHandle
    geometry: LogicalRect
    work_area: LogicalRect
    scale: float = 1.0


@dataclass(frozen=True)
class DesktopSnapshot:
    session_id: str
    sequence: int
    active_window: WindowHandle | None
    active_workspace: WorkspaceHandle
    windows: tuple[WindowSnapshot, ...]
    monitors: tuple[MonitorSnapshot, ...]

    def __post_init__(self) -> None:
        if self.sequence < 0:
            raise ValueError("sequence no puede ser negativa")
        window_handles = [window.handle for window in self.windows]
        monitor_handles = [monitor.handle for monitor in self.monitors]
        if len(window_handles) != len(set(window_handles)):
            raise ValueError("snapshot contiene handles de ventana duplicados")
        if len(monitor_handles) != len(set(monitor_handles)):
            raise ValueError("snapshot contiene handles de monitor duplicados")


class EventKind(str, Enum):
    ACTIVE_WINDOW_CHANGED = "active-window-changed"
    WINDOW_OPENED = "window-opened"
    WINDOW_CLOSED = "window-closed"
    WINDOW_CHANGED = "window-changed"
    WINDOW_DRAGGED = "window-dragged"
    WINDOW_RESIZED = "window-resized"
    MONITORS_CHANGED = "monitors-changed"
    WORKSPACE_CHANGED = "workspace-changed"
    OPERATION_COMPLETED = "operation-completed"
    RUNTIME_DISCONNECTED = "runtime-disconnected"
    RUNTIME_RECONNECTED = "runtime-reconnected"


@dataclass(frozen=True)
class PlatformEvent:
    session_id: str
    sequence: int
    kind: EventKind
    window: WindowHandle | None = None
    operation_id: OperationId | None = None
    payload: Mapping[str, object] | None = None

    def __post_init__(self) -> None:
        if self.sequence < 0:
            raise ValueError("sequence no puede ser negativa")


@dataclass(frozen=True)
class OperationResult:
    operation_id: OperationId
    accepted: bool
    error_code: str | None = None
    message: str = ""
    session_id: str | None = None
    status: str | None = None
    requested_geometry: LogicalRect | None = None
    observed_geometry: LogicalRect | None = None
    constraint: str | None = None
    attempts: int = 0
    confirmation_ms: int | None = None
    restored: bool = False
    observations: tuple[Mapping[str, object], ...] = ()


class WindowController(Protocol):
    @property
    def capabilities(self) -> frozenset[Capability]: ...

    def get_snapshot(self) -> DesktopSnapshot: ...

    def activate(self, operation_id: OperationId, window: WindowHandle) -> OperationResult: ...

    def move_resize(
        self,
        operation_id: OperationId,
        window: WindowHandle,
        rect: LogicalRect,
    ) -> OperationResult: ...

    def set_maximized(
        self,
        operation_id: OperationId,
        window: WindowHandle,
        maximized: bool,
    ) -> OperationResult: ...

    def move_to_workspace(
        self,
        operation_id: OperationId,
        window: WindowHandle,
        workspace: WorkspaceHandle,
    ) -> OperationResult: ...


class PresentationPort(Protocol):
    def show_layouts(
        self,
        flow_id: int,
        layouts: Sequence[object],
        active_window: WindowSnapshot,
    ) -> None: ...

    def show_suggestions(
        self,
        flow_id: int,
        zone: LogicalRect,
        candidates: Sequence[WindowSnapshot],
    ) -> None: ...

    def hide(self, flow_id: int) -> None: ...

    def notify(self, message: str) -> None: ...


class ShortcutProvider(Protocol):
    def register(self, action: str, shortcut: str, callback: Callable[[], None]) -> bool: ...

    def unregister_all(self) -> None: ...


class EventSource(Protocol):
    def subscribe(self, callback: Callable[[PlatformEvent], None]) -> Callable[[], None]: ...


@dataclass(frozen=True)
class PlatformRuntime:
    windows: WindowController
    presentation: PresentationPort
    shortcuts: ShortcutProvider
    events: EventSource
