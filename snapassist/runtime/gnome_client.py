"""Cliente de protocolo GNOME desacoplado del transporte D-Bus concreto."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable, Protocol

from snapassist.runtime.contracts import (
    Capability,
    DesktopSnapshot,
    EventKind,
    LogicalRect,
    MonitorSnapshot,
    OperationResult,
    PlatformEvent,
    WindowSnapshot,
)


PROTOCOL_VERSION = 1


class ProtocolError(RuntimeError):
    pass


class ProtocolVersionError(ProtocolError):
    pass


class ProtocolDisconnected(ProtocolError):
    pass


class ProtocolTransport(Protocol):
    def connect(self) -> None: ...

    def disconnect(self) -> None: ...

    def call(self, method: str, *args: object) -> str: ...

    def subscribe(
        self,
        signal: str,
        callback: Callable[[str], None],
    ) -> Callable[[], None]: ...


@dataclass(frozen=True)
class ProtocolInfo:
    protocol_version: int
    minimum_client_version: int
    session_id: str
    interface_name: str
    capability_candidates: frozenset[str]


@dataclass(frozen=True)
class UiAction:
    session_id: str
    sequence: int
    flow_id: int
    action: str
    value: object | None = None


class GnomeProtocolClient:
    """Valida sesión/secuencia y reintenta operaciones idempotentes una vez."""

    def __init__(self, transport: ProtocolTransport) -> None:
        self._transport = transport
        self._info: ProtocolInfo | None = None
        self._last_sequence = -1
        self._last_ui_sequence = -1
        self._subscriptions: list[Callable[[], None]] = []
        self._event_callbacks: list[Callable[[PlatformEvent], None]] = []
        self._operation_callbacks: list[Callable[[OperationResult], None]] = []
        self._ui_callbacks: list[Callable[[UiAction], None]] = []

    @property
    def connected(self) -> bool:
        return self._info is not None

    @property
    def info(self) -> ProtocolInfo:
        if self._info is None:
            raise ProtocolDisconnected("el runtime GNOME no está conectado")
        return self._info

    @property
    def capabilities(self) -> frozenset[Capability]:
        supported = {capability.value: capability for capability in Capability}
        return frozenset(
            supported[value]
            for value in self.info.capability_candidates
            if value in supported
        )

    def connect(self) -> ProtocolInfo:
        self.disconnect()
        try:
            self._transport.connect()
            info = _parse_protocol_info(self._transport.call("GetProtocolInfo"))
            _validate_protocol_version(info)
            self._info = info
            self._last_sequence = -1
            self._last_ui_sequence = -1
            self._subscriptions = [
                self._transport.subscribe("PlatformEvent", self._on_platform_event),
                self._transport.subscribe(
                    "OperationCompleted",
                    self._on_operation_completed,
                ),
                self._transport.subscribe("UiAction", self._on_ui_action),
            ]
            return info
        except Exception:
            self._info = None
            self._transport.disconnect()
            raise

    def disconnect(self) -> None:
        for unsubscribe in reversed(self._subscriptions):
            unsubscribe()
        self._subscriptions = []
        self._transport.disconnect()
        self._info = None
        self._last_sequence = -1
        self._last_ui_sequence = -1

    def reconnect(self) -> ProtocolInfo:
        previous_session = self._info.session_id if self._info else None
        info = self.connect()
        if previous_session == info.session_id:
            self._last_sequence = -1
        return info

    def ensure_connected(self) -> DesktopSnapshot:
        """Sonda read-only que recupera conexión y signal matches perdidos."""
        if self._info is None:
            info = self.connect()
            self._emit_runtime_event(EventKind.RUNTIME_RECONNECTED, info.session_id)
        return self.get_snapshot()

    def get_snapshot(self) -> DesktopSnapshot:
        self.info
        raw = self._call_with_reconnect("GetSnapshot")
        snapshot = _parse_snapshot(raw)
        if snapshot.session_id != self.info.session_id:
            raise ProtocolError("snapshot pertenece a otra sesión Shell")
        return snapshot

    def activate(self, operation_id: str, window: str) -> OperationResult:
        return self._operation("Activate", operation_id, window)

    def move_resize(
        self,
        operation_id: str,
        window: str,
        rect: LogicalRect,
    ) -> OperationResult:
        if rect.width <= 0 or rect.height <= 0:
            raise ValueError("move_resize requiere dimensiones positivas")
        return self._operation(
            "MoveResize",
            operation_id,
            window,
            rect.x,
            rect.y,
            rect.width,
            rect.height,
        )

    def set_maximized(
        self,
        operation_id: str,
        window: str,
        maximized: bool,
    ) -> OperationResult:
        return self._operation("SetMaximized", operation_id, window, maximized)

    def move_to_workspace(
        self,
        operation_id: str,
        window: str,
        workspace: str,
    ) -> OperationResult:
        return self._operation(
            "MoveToWorkspace",
            operation_id,
            window,
            workspace,
        )

    def show_layouts(
        self,
        operation_id: str,
        flow_id: int,
        payload: dict[str, object],
    ) -> OperationResult:
        return self._presentation_operation(
            "ShowLayouts",
            operation_id,
            flow_id,
            payload,
        )

    def show_suggestions(
        self,
        operation_id: str,
        flow_id: int,
        payload: dict[str, object],
    ) -> OperationResult:
        return self._presentation_operation(
            "ShowSuggestions",
            operation_id,
            flow_id,
            payload,
        )

    def show_help(
        self,
        operation_id: str,
        flow_id: int,
        payload: dict[str, object],
    ) -> OperationResult:
        return self._presentation_operation(
            "ShowHelp",
            operation_id,
            flow_id,
            payload,
        )

    def hide_presentation(
        self,
        operation_id: str,
        flow_id: int,
    ) -> OperationResult:
        _validate_flow_id(flow_id)
        return self._operation("HidePresentation", operation_id, flow_id)

    def notify(
        self,
        operation_id: str,
        message: str,
        timeout_ms: int = 3000,
    ) -> OperationResult:
        if not message:
            raise ValueError("message no puede estar vacío")
        if not 0 <= timeout_ms <= 60_000:
            raise ValueError("timeout_ms debe estar entre 0 y 60000")
        return self._operation("Notify", operation_id, message, timeout_ms)

    def configure_shortcuts(
        self,
        operation_id: str,
        shortcuts: dict[str, str],
    ) -> OperationResult:
        required = {"layout_menu", "snap_groups", "help"}
        if set(shortcuts) != required:
            raise ValueError("se requieren exactamente los tres atajos públicos")
        if not all(isinstance(value, str) and value for value in shortcuts.values()):
            raise ValueError("todos los atajos deben ser cadenas no vacías")
        payload = json.dumps(shortcuts, ensure_ascii=False, sort_keys=True)
        return self._operation("ConfigureShortcuts", operation_id, payload)

    def subscribe_events(
        self,
        callback: Callable[[PlatformEvent], None],
    ) -> Callable[[], None]:
        self._event_callbacks.append(callback)
        return lambda: _remove_callback(self._event_callbacks, callback)

    def subscribe_operations(
        self,
        callback: Callable[[OperationResult], None],
    ) -> Callable[[], None]:
        self._operation_callbacks.append(callback)
        return lambda: _remove_callback(self._operation_callbacks, callback)

    def subscribe_ui_actions(
        self,
        callback: Callable[[UiAction], None],
    ) -> Callable[[], None]:
        self._ui_callbacks.append(callback)
        return lambda: _remove_callback(self._ui_callbacks, callback)

    def _presentation_operation(
        self,
        method: str,
        operation_id: str,
        flow_id: int,
        payload: dict[str, object],
    ) -> OperationResult:
        _validate_flow_id(flow_id)
        try:
            payload_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        except (TypeError, ValueError) as error:
            raise ValueError(f"payload no serializable: {error}") from error
        return self._operation(method, operation_id, flow_id, payload_json)

    def _operation(self, method: str, operation_id: str, *args: object) -> OperationResult:
        if not operation_id or len(operation_id) > 128:
            raise ValueError("operation_id debe contener entre 1 y 128 caracteres")
        raw = self._call_with_reconnect(method, operation_id, *args)
        result = _parse_operation_result(raw)
        if result.operation_id != operation_id:
            raise ProtocolError("el resultado no corresponde a la operación solicitada")
        if result.session_id != self.info.session_id:
            raise ProtocolError("el resultado pertenece a otra sesión Shell")
        return result

    def _call_with_reconnect(self, method: str, *args: object) -> str:
        self.info
        try:
            return self._transport.call(method, *args)
        except ProtocolDisconnected:
            previous_session = self._info.session_id if self._info else "disconnected"
            self._emit_runtime_event(
                EventKind.RUNTIME_DISCONNECTED,
                previous_session,
            )
            self.reconnect()
            self._emit_runtime_event(
                EventKind.RUNTIME_RECONNECTED,
                self.info.session_id,
            )
            return self._transport.call(method, *args)

    def _emit_runtime_event(self, kind: EventKind, session_id: str) -> None:
        sequence = max(0, self._last_sequence + 1)
        event = PlatformEvent(session_id, sequence, kind)
        for callback in tuple(self._event_callbacks):
            callback(event)

    def _on_platform_event(self, raw: str) -> None:
        try:
            event = _parse_platform_event(raw)
        except (ProtocolError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            return
        if self._info is None or event.session_id != self._info.session_id:
            return
        if event.sequence <= self._last_sequence:
            return
        self._last_sequence = event.sequence
        for callback in tuple(self._event_callbacks):
            callback(event)

    def _on_operation_completed(self, raw: str) -> None:
        try:
            result = _parse_operation_result(raw)
        except (ProtocolError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            return
        if self._info is None or result.session_id != self._info.session_id:
            return
        for callback in tuple(self._operation_callbacks):
            callback(result)

    def _on_ui_action(self, raw: str) -> None:
        try:
            action = _parse_ui_action(raw)
        except (ProtocolError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            return
        if self._info is None or action.session_id != self._info.session_id:
            return
        if action.sequence <= self._last_ui_sequence:
            return
        self._last_ui_sequence = action.sequence
        for callback in tuple(self._ui_callbacks):
            callback(action)


def _parse_protocol_info(raw: str) -> ProtocolInfo:
    value = json.loads(raw)
    try:
        return ProtocolInfo(
            protocol_version=int(value["protocolVersion"]),
            minimum_client_version=int(value["minimumClientVersion"]),
            session_id=_required_string(value, "sessionId"),
            interface_name=_required_string(value, "interfaceName"),
            capability_candidates=frozenset(
                str(item) for item in value["capabilityCandidates"]
            ),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ProtocolError(f"GetProtocolInfo inválido: {error}") from error


def _validate_protocol_version(info: ProtocolInfo) -> None:
    if info.minimum_client_version > PROTOCOL_VERSION:
        raise ProtocolVersionError("la extensión requiere un cliente más reciente")
    if info.protocol_version < PROTOCOL_VERSION:
        raise ProtocolVersionError("la extensión usa un protocolo obsoleto")
    if info.interface_name != "org.snapassist.Shell1":
        raise ProtocolVersionError(f"interfaz inesperada: {info.interface_name}")


def _parse_snapshot(raw: str) -> DesktopSnapshot:
    value = json.loads(raw)
    windows = tuple(
        WindowSnapshot(
            handle=_required_string(item, "handle"),
            title=str(item.get("title", "")),
            app_id=str(item.get("appId", "")),
            app_name=str(item.get("appName", "")),
            geometry=_parse_rect(item["frameRect"]),
            monitor=_required_string(item, "monitor"),
            workspace=_required_string(item, "workspace"),
            minimized=bool(item.get("minimized", False)),
            maximized=bool(
                item.get("maximizedHorizontally", False)
                and item.get("maximizedVertically", False)
            ),
            transient_for=item.get("transientFor"),
            minimum_size=(
                int(item.get("minimumSize", {}).get("width", 0)),
                int(item.get("minimumSize", {}).get("height", 0)),
            ),
            eligible=bool(item.get("eligible", True)),
            client_type=str(item.get("clientType", "unknown")),
            maximized_horizontally=bool(item.get("maximizedHorizontally", False)),
            maximized_vertically=bool(item.get("maximizedVertically", False)),
            minimum_size_known=bool(item.get("minimumSizeKnown", False)),
            maximum_size=(
                int(item.get("maximumSize", {}).get("width", 0)),
                int(item.get("maximumSize", {}).get("height", 0)),
            ),
            maximum_size_known=bool(item.get("maximumSizeKnown", False)),
            fullscreen=bool(item.get("fullscreen", False)),
            above=bool(item.get("above", False)),
            on_all_workspaces=bool(item.get("onAllWorkspaces", False)),
            allows_move=bool(item.get("allowsMove", True)),
            allows_resize=bool(item.get("allowsResize", True)),
            mapped=bool(item.get("mapped", True)),
            tiled=bool(item.get("tiled", False)),
        )
        for item in value["windows"]
    )
    monitors = tuple(
        MonitorSnapshot(
            handle=_required_string(item, "handle"),
            geometry=_parse_rect(item["geometry"]),
            work_area=_parse_rect(item["workArea"]),
            scale=float(item.get("scale", 1.0)),
        )
        for item in value["monitors"]
    )
    return DesktopSnapshot(
        session_id=_required_string(value, "sessionId"),
        sequence=int(value["sequence"]),
        active_window=value.get("activeWindow"),
        active_workspace=_required_string(value, "activeWorkspace"),
        windows=windows,
        monitors=monitors,
    )


def _parse_platform_event(raw: str) -> PlatformEvent:
    value = json.loads(raw)
    return PlatformEvent(
        session_id=_required_string(value, "sessionId"),
        sequence=int(value["sequence"]),
        kind=EventKind(value["kind"]),
        window=value.get("window"),
        operation_id=value.get("operationId"),
        payload=value.get("payload"),
    )


def _parse_operation_result(raw: str) -> OperationResult:
    value = json.loads(raw)
    accepted = bool(value["accepted"])
    return OperationResult(
        operation_id=_required_string(value, "operationId"),
        accepted=accepted,
        error_code=value.get("errorCode"),
        message=str(value.get("message", "")),
        session_id=_required_string(value, "sessionId"),
        status=_optional_string(value, "status") or (
            "confirmed" if accepted else value.get("errorCode")
        ),
        requested_geometry=_optional_rect(value.get("requestedGeometry")),
        observed_geometry=_optional_rect(value.get("observedGeometry")),
        constraint=_optional_string(value, "constraint"),
        attempts=int(value.get("attempts", 0)),
        confirmation_ms=_optional_int(value.get("confirmationMs")),
        restored=bool(value.get("restored", False)),
        observations=tuple(
            dict(item)
            for item in value.get("observations", [])
            if isinstance(item, dict)
        ),
    )


def _parse_ui_action(raw: str) -> UiAction:
    value = json.loads(raw)
    action = UiAction(
        session_id=_required_string(value, "sessionId"),
        sequence=int(value["sequence"]),
        flow_id=int(value["flowId"]),
        action=_required_string(value, "action"),
        value=value.get("value"),
    )
    if action.sequence < 0:
        raise ProtocolError("sequence UI no puede ser negativa")
    _validate_flow_id(action.flow_id)
    return action


def _parse_rect(value: dict[str, object]) -> LogicalRect:
    return LogicalRect(
        int(value["x"]),
        int(value["y"]),
        int(value["width"]),
        int(value["height"]),
    )


def _required_string(value: dict[str, object], key: str) -> str:
    item = value[key]
    if not isinstance(item, str) or not item:
        raise ProtocolError(f"{key} debe ser una cadena no vacía")
    return item


def _optional_string(value: dict[str, object], key: str) -> str | None:
    item = value.get(key)
    if item is None:
        return None
    if not isinstance(item, str):
        raise ProtocolError(f"{key} debe ser una cadena o null")
    return item


def _optional_rect(value: object) -> LogicalRect | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ProtocolError("geometría de operación inválida")
    return _parse_rect(value)


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ProtocolError("valor entero de operación inválido")
    return int(value)


def _remove_callback(callbacks: list[Callable], callback: Callable) -> None:
    if callback in callbacks:
        callbacks.remove(callback)


def _validate_flow_id(flow_id: int) -> None:
    if not isinstance(flow_id, int) or isinstance(flow_id, bool) or flow_id < 0:
        raise ValueError("flow_id debe ser un entero no negativo")
