"""Adaptadores del protocolo GNOME hacia los puertos neutrales del core."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from snapassist.config import LayoutTemplate
from snapassist.runtime.contracts import (
    Capability,
    DesktopSnapshot,
    LogicalRect,
    OperationResult,
    PlatformEvent,
    WindowSnapshot,
)
from snapassist.runtime.gnome_client import GnomeProtocolClient, UiAction


def _operation_id(prefix: str) -> str:
    return f"{prefix}:{uuid.uuid4()}"


def _require_accepted(result: OperationResult) -> None:
    if not result.accepted:
        raise RuntimeError(
            f"{result.error_code or 'operation-failed'}: {result.message}"
        )


def _find_window(snapshot: DesktopSnapshot, handle: str) -> WindowSnapshot | None:
    return next((window for window in snapshot.windows if window.handle == handle), None)


class GnomeWindowController:
    def __init__(self, client: GnomeProtocolClient) -> None:
        self._client = client

    @property
    def capabilities(self) -> frozenset[Capability]:
        return self._client.capabilities

    def get_snapshot(self) -> DesktopSnapshot:
        return self._client.get_snapshot()

    def activate(self, operation_id: str, window: str) -> OperationResult:
        return self._client.activate(operation_id, window)

    def move_resize(
        self,
        operation_id: str,
        window: str,
        rect: LogicalRect,
    ) -> OperationResult:
        capabilities = getattr(self._client, "capabilities", None)
        if capabilities is not None and Capability.CONFIRMED_MOVE_RESIZE not in capabilities:
            return OperationResult(
                operation_id,
                False,
                "unsupported-capability",
                "La extensión GNOME no confirma MoveResize de forma asíncrona.",
            )
        # La extensión espera el configure con temporizadores GLib y solo
        # responde después de confirmar dos muestras consecutivas. La espera
        # D-Bus bloquea al llamador Python, pero nunca el loop de GNOME Shell.
        return self._client.move_resize(operation_id, window, rect)

    def set_maximized(
        self,
        operation_id: str,
        window: str,
        maximized: bool,
    ) -> OperationResult:
        return self._client.set_maximized(operation_id, window, maximized)

    def move_to_workspace(
        self,
        operation_id: str,
        window: str,
        workspace: str,
    ) -> OperationResult:
        return self._client.move_to_workspace(
            operation_id,
            window,
            workspace,
        )


class GnomePresentationPort:
    def __init__(self, client: GnomeProtocolClient) -> None:
        self._client = client

    def show_layouts(
        self,
        flow_id: int,
        layouts: Sequence[object],
        active_window: WindowSnapshot,
    ) -> None:
        serialized = []
        for layout in layouts:
            if not isinstance(layout, LayoutTemplate):
                raise TypeError("GNOME presentation requires LayoutTemplate values")
            serialized.append(
                {
                    "name": layout.name,
                    "disabled": False,
                    "zones": [
                        {"x": zone.x, "y": zone.y, "w": zone.w, "h": zone.h}
                        for zone in layout.zones
                    ],
                }
            )
        result = self._client.show_layouts(
            _operation_id("ui-layouts"),
            flow_id,
            {
                "title": "Elegir layout",
                "subtitle": active_window.app_name or active_window.title,
                "layouts": serialized,
            },
        )
        _require_accepted(result)

    def show_suggestions(
        self,
        flow_id: int,
        zone: LogicalRect,
        candidates: Sequence[WindowSnapshot],
    ) -> None:
        result = self._client.show_suggestions(
            _operation_id("ui-suggestions"),
            flow_id,
            {
                "title": "Completar zona",
                "zone": {
                    "x": zone.x,
                    "y": zone.y,
                    "width": zone.width,
                    "height": zone.height,
                },
                "candidates": [
                    {
                        "handle": candidate.handle,
                        "label": (
                            f"{candidate.app_name} — {candidate.title}"
                            if candidate.app_name and candidate.title
                            else candidate.app_name or candidate.title
                        ),
                    }
                    for candidate in candidates
                ],
            },
        )
        _require_accepted(result)

    def hide(self, flow_id: int) -> None:
        result = self._client.hide_presentation(
            _operation_id("ui-hide"),
            flow_id,
        )
        _require_accepted(result)

    def notify(self, message: str) -> None:
        result = self._client.notify(_operation_id("ui-notify"), message)
        _require_accepted(result)

    def show_help(self, flow_id: int = 0) -> None:
        result = self._client.show_help(
            _operation_id("ui-help"),
            flow_id,
            {
                "title": "Ayuda de SnapAssist",
                "subtitle": "Navegación completamente por teclado",
                "lines": [
                    "Super+Z — elegir layout y zona",
                    "Super+Alt+Tab — enfocar el Snap Group activo",
                    "Flechas o números — cambiar selección",
                    "Enter — confirmar",
                    "Esc — volver o cerrar",
                ],
            },
        )
        _require_accepted(result)


class GnomeShortcutProvider:
    _ACTIONS = frozenset({"layout_menu", "snap_groups", "help"})

    def __init__(self, client: GnomeProtocolClient) -> None:
        self._client = client
        self._shortcuts: dict[str, str] = {}
        self._callbacks: dict[str, Callable[[], None]] = {}
        self._unsubscribe = client.subscribe_ui_actions(self._on_ui_action)

    def register(
        self,
        action: str,
        shortcut: str,
        callback: Callable[[], None],
    ) -> bool:
        if action not in self._ACTIONS or action in self._callbacks:
            return False
        self._shortcuts[action] = shortcut
        self._callbacks[action] = callback
        if set(self._shortcuts) == self._ACTIONS:
            result = self._client.configure_shortcuts(
                _operation_id("shortcuts"),
                self._shortcuts,
            )
            if not result.accepted:
                self._shortcuts.pop(action, None)
                self._callbacks.pop(action, None)
                return False
        return True

    def unregister_all(self) -> None:
        self._shortcuts.clear()
        self._callbacks.clear()

    def update_shortcuts(self, shortcuts: dict[str, str]) -> bool:
        if set(shortcuts) != self._ACTIONS or set(self._callbacks) != self._ACTIONS:
            return False
        result = self._client.configure_shortcuts(
            _operation_id("shortcuts-update"), shortcuts
        )
        if not result.accepted:
            return False
        self._shortcuts = dict(shortcuts)
        return True

    def close(self) -> None:
        self.unregister_all()
        self._unsubscribe()

    def _on_ui_action(self, action: UiAction) -> None:
        if action.action != "shortcut-invoked":
            return
        callback = self._callbacks.get(str(action.value))
        if callback:
            callback()


class GnomeEventSource:
    def __init__(self, client: GnomeProtocolClient) -> None:
        self._client = client

    def subscribe(
        self,
        callback: Callable[[PlatformEvent], None],
    ) -> Callable[[], None]:
        return self._client.subscribe_events(callback)
