"""Adaptadores del backend X11 heredado a los contratos neutrales 2.x."""

from __future__ import annotations

import uuid
from collections.abc import Callable, Sequence

from snapassist.config import LayoutTemplate, Rect, WindowState
from snapassist.runtime.contracts import (
    Capability,
    DesktopSnapshot,
    LogicalRect,
    MonitorSnapshot,
    OperationResult,
    PlatformEvent,
    WindowSnapshot,
)
from snapassist.wm.backend import WindowManager


def _window_handle(wid: int) -> str:
    return f"x11:{wid:x}"


def _parse_window_handle(handle: str) -> int:
    if not isinstance(handle, str) or not handle.startswith("x11:"):
        raise ValueError(f"handle X11 inválido: {handle!r}")
    try:
        wid = int(handle[4:], 16)
    except ValueError as error:
        raise ValueError(f"handle X11 inválido: {handle!r}") from error
    if wid <= 0:
        raise ValueError(f"handle X11 inválido: {handle!r}")
    return wid


class X11WindowController:
    """Convierte IDs/Rect/errores X11 en snapshots y resultados neutrales."""

    def __init__(self, backend: WindowManager, session_id: str | None = None) -> None:
        self._backend = backend
        self._session_id = session_id or f"x11-session:{uuid.uuid4()}"
        self._sequence = 0

    @property
    def capabilities(self) -> frozenset[Capability]:
        return frozenset({
            Capability.ACTIVE_WINDOW, Capability.WINDOW_LIST,
            Capability.LOGICAL_GEOMETRY, Capability.MONITORS,
            Capability.WORKSPACES, Capability.FOCUS, Capability.MOVE_RESIZE,
            Capability.MAXIMIZE, Capability.TRANSIENTS, Capability.WORK_AREA,
        })

    def get_snapshot(self) -> DesktopSnapshot:
        self._sequence += 1
        monitors = self._backend.get_monitors()
        monitor_snapshots = tuple(
            MonitorSnapshot(
                f"monitor:{index}",
                _logical(rect),
                _logical(self._backend.get_work_area(index)),
                1.0,
            )
            for index, rect in enumerate(monitors)
        )
        current_workspace = self._backend.get_current_workspace()
        windows = []
        eligible_windows = set(self._backend.get_all_windows())
        for wid in self._backend.get_snapshot_windows():
            geometry = self._backend.get_window_geometry(wid)
            state = self._backend.get_window_state(wid)
            parent = self._backend.get_transient_for(wid)
            windows.append(WindowSnapshot(
                _window_handle(wid),
                self._backend.get_window_title(wid),
                "",
                self._backend.get_window_app_name(wid),
                _logical(geometry.rect),
                f"monitor:{self._backend.get_monitor_for_window(wid)}",
                f"workspace:{self._backend.get_window_workspace(wid)}",
                minimized=state == WindowState.MINIMIZED,
                maximized=geometry.is_maximized or state == WindowState.MAXIMIZED,
                transient_for=_window_handle(parent) if parent else None,
                minimum_size=self._backend.get_window_min_size(wid),
                eligible=wid in eligible_windows,
            ))
        active = self._backend.get_active_window()
        return DesktopSnapshot(
            self._session_id,
            self._sequence,
            _window_handle(active) if active else None,
            f"workspace:{current_workspace}",
            tuple(windows),
            monitor_snapshots,
        )

    def activate(self, operation_id: str, window: str) -> OperationResult:
        return self._mutate(operation_id, window, self._backend.focus_window)

    def move_resize(
        self, operation_id: str, window: str, rect: LogicalRect
    ) -> OperationResult:
        wid = self._resolve(operation_id, window)
        if isinstance(wid, OperationResult):
            return wid
        accepted = self._backend.move_resize_window(wid, _legacy(rect))
        return self._result(
            operation_id, accepted, None if accepted else "operation-failed",
            "" if accepted else "X11 rechazó move/resize",
        )

    def set_maximized(
        self, operation_id: str, window: str, maximized: bool
    ) -> OperationResult:
        return self._mutate(
            operation_id, window,
            lambda wid: self._backend.set_window_maximized(wid, maximized),
        )

    def move_to_workspace(
        self, operation_id: str, window: str, workspace: str
    ) -> OperationResult:
        expected = f"workspace:{self._backend.get_current_workspace()}"
        if workspace != expected:
            return self._result(
                operation_id, False, "unsupported-workspace",
                "X11 heredado solo mueve al workspace activo",
            )
        return self._mutate(
            operation_id, window, self._backend.move_window_to_current_workspace
        )

    def _mutate(self, operation_id, window, callback) -> OperationResult:
        wid = self._resolve(operation_id, window)
        if isinstance(wid, OperationResult):
            return wid
        try:
            value = callback(wid)
            accepted = value is not False
            return self._result(
                operation_id, accepted, None if accepted else "operation-failed"
            )
        except Exception as error:
            return self._result(operation_id, False, "operation-failed", str(error))

    def _resolve(self, operation_id, window):
        try:
            wid = _parse_window_handle(window)
        except ValueError as error:
            return self._result(operation_id, False, "invalid-handle", str(error))
        if not self._backend.window_exists(wid):
            return self._result(operation_id, False, "window-gone", "ventana desaparecida")
        return wid

    def _result(self, operation_id, accepted, error_code=None, message=""):
        return OperationResult(
            operation_id, accepted, error_code, message, self._session_id
        )


class X11EventSource:
    """Puente observable; el event loop X11 publica eventos semánticos aquí."""

    def __init__(self) -> None:
        self._callbacks: list[Callable[[PlatformEvent], None]] = []

    def subscribe(self, callback):
        self._callbacks.append(callback)
        return lambda: self._callbacks.remove(callback) if callback in self._callbacks else None

    def publish(self, event: PlatformEvent) -> None:
        for callback in tuple(self._callbacks):
            callback(event)


class X11ShortcutProvider:
    def __init__(self, hotkeys) -> None:
        self._hotkeys = hotkeys

    def register(self, _action: str, shortcut: str, callback) -> bool:
        return bool(self._hotkeys.register(shortcut, callback))

    def unregister_all(self) -> None:
        self._hotkeys.unregister_all()


class X11PresentationPort:
    """Callbacks explícitos evitan importar Tkinter desde el core neutral."""

    def __init__(self, show_layouts, show_suggestions, hide, notify) -> None:
        self._show_layouts = show_layouts
        self._show_suggestions = show_suggestions
        self._hide = hide
        self._notify = notify

    def show_layouts(
        self, flow_id: int, layouts: Sequence[LayoutTemplate], active_window
    ) -> None:
        self._show_layouts(flow_id, layouts, active_window)

    def show_suggestions(self, flow_id, zone, candidates) -> None:
        self._show_suggestions(flow_id, zone, candidates)

    def hide(self, flow_id: int) -> None:
        self._hide(flow_id)

    def notify(self, message: str) -> None:
        self._notify(message)


def _logical(rect: Rect) -> LogicalRect:
    return LogicalRect(rect.x, rect.y, rect.w, rect.h)


def _legacy(rect: LogicalRect) -> Rect:
    return Rect(rect.x, rect.y, rect.width, rect.height)
