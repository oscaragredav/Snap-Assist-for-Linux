"""Flujo SnapAssist 2.x sobre puertos neutrales de plataforma."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from snapassist.config import LayoutTemplate, ZoneTemplate
from snapassist.core.native_state import NativeState
from snapassist.runtime.contracts import (
    DesktopSnapshot,
    EventKind,
    LogicalRect,
    OperationResult,
    PlatformEvent,
    PlatformRuntime,
    WindowSnapshot,
)
from snapassist.runtime.gnome_client import UiAction


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class NativeSnapResult:
    flow_id: int
    snapped: tuple[tuple[str, int], ...]
    completed: bool
    empty_zones: tuple[int, ...] = ()


class NativeSnapCoordinator:
    """Reglas interactivas neutrales sin imports de X11, GJS ni Tkinter."""

    def __init__(
        self,
        runtime: PlatformRuntime,
        layouts: list[LayoutTemplate],
        state: NativeState | None = None,
    ) -> None:
        if not layouts:
            raise ValueError("se requiere al menos un layout")
        self._runtime = runtime
        self._layouts = list(layouts)
        self.state = state or NativeState()
        self.state.bind_to_current_thread()
        self._flow_id = 0
        self._phase = "idle"
        self._snapshot: DesktopSnapshot | None = None
        self._active_window: WindowSnapshot | None = None
        self._layout: LayoutTemplate | None = None
        self._zones: list[LogicalRect] = []
        self._remaining_zones: list[int] = []
        self._snapped: dict[int, str] = {}
        self._empty_zones: set[int] = set()
        self._rejected_windows: set[str] = set()
        self._monitor_handle: str | None = None
        self._state_before_flow = None
        self._flow_originals: dict[str, tuple[LogicalRect, bool]] = {}
        self._pending_restores: list[tuple[str, LogicalRect, bool]] = []
        self._unsubscribe_events = runtime.events.subscribe(self.handle_event)

    @property
    def flow_id(self) -> int:
        return self._flow_id

    @property
    def active(self) -> bool:
        return self._phase != "idle"

    def replace_layouts(self, layouts: list[LayoutTemplate]) -> None:
        if not layouts:
            raise ValueError("se requiere al menos un layout")
        if self.active:
            self.cancel()
        self._layouts = list(layouts)

    def start(self) -> bool:
        if self.active:
            self.cancel()
            return False
        snapshot = self._runtime.windows.get_snapshot()
        active = _find_window(snapshot, snapshot.active_window)
        if active is None:
            self._runtime.presentation.notify(
                "Selecciona una ventana primero para acoplarla."
            )
            return False
        if active.transient_for:
            active = _find_window(snapshot, active.transient_for) or active
        if not active.eligible:
            self._runtime.presentation.notify(
                "La ventana activa no admite el redimensionamiento requerido."
            )
            return False
        monitor = _find_monitor(snapshot, active.monitor)
        if monitor is None or monitor.work_area.width <= 0 or monitor.work_area.height <= 0:
            self._runtime.presentation.notify("No hay área de trabajo disponible.")
            return False

        self._flow_id += 1
        self._phase = "layout"
        self._snapshot = snapshot
        self._active_window = active
        self._layout = None
        self._zones = []
        self._remaining_zones = []
        self._snapped = {}
        self._empty_zones = set()
        self._rejected_windows = set()
        self._monitor_handle = active.monitor
        self._state_before_flow = self.state.snapshot()
        self._flow_originals = {}
        try:
            self._runtime.presentation.show_layouts(
                self._flow_id,
                self._layouts,
                active,
            )
        except Exception as error:
            self._rollback_flow(f"No se pudo mostrar la selección: {error}")
            return False
        return True

    def handle_ui_action(self, action: UiAction) -> None:
        if action.action == "shortcut-invoked":
            return
        if not self.active or action.flow_id != self._flow_id:
            return
        if self._phase == "suggestion":
            self.choose_suggestion(action)
            return
        if action.action == "cancel":
            self.cancel()
            return
        if action.action != "layout-selected":
            return
        try:
            index = int(action.value)
        except (TypeError, ValueError):
            return
        if self._phase == "layout":
            self._choose_layout(index)
        elif self._phase == "zone":
            self._choose_first_zone(index)

    def handle_event(self, event: PlatformEvent) -> None:
        if event.kind == EventKind.WINDOW_CLOSED and event.window:
            if (
                self.active
                and self._active_window
                and event.window == self._active_window.handle
            ):
                self.cancel()
            self.state.forget_window(event.window)
            return
        if event.kind == EventKind.MONITORS_CHANGED:
            if self.active:
                self.cancel()
            snapshot = self._runtime.windows.get_snapshot()
            self.state.discard_groups_for_missing_monitors(
                {monitor.handle for monitor in snapshot.monitors}
            )
            return
        if event.kind == EventKind.WINDOW_DRAGGED and event.window:
            # El usuario ya eligió la nueva posición con el arrastre. Solo se
            # disuelve la pertenencia; no se teletransporta a la geometría
            # anterior al soltar el mouse.
            self.state.detach(event.window)
            return
        if event.kind == EventKind.WINDOW_RESIZED and event.window:
            self.state.detach(event.window)
            return
        if event.kind == EventKind.RUNTIME_DISCONNECTED:
            self._rollback_flow(
                "La integración GNOME se desconectó.",
                defer_restores=True,
            )
            return
        if event.kind == EventKind.RUNTIME_RECONNECTED:
            self._retry_pending_restores()
            return
        if not self.active or self._snapshot is None:
            return

    def choose_suggestion(self, action: UiAction) -> None:
        """Procesa una selección emitida por la lista nativa de sugerencias."""
        if (
            not self.active
            or self._phase != "suggestion"
            or action.flow_id != self._flow_id
        ):
            return
        if action.action == "cancel":
            self.cancel()
            return
        if action.action != "suggestion-selected" or not isinstance(action.value, str):
            return
        if action.value in self._snapped.values() or not self._remaining_zones:
            return
        snapshot = self._runtime.windows.get_snapshot()
        candidate = _find_window(snapshot, action.value)
        if candidate is None:
            self._runtime.presentation.notify("La ventana seleccionada ya no existe.")
            self._show_next_suggestion(snapshot)
            return
        zone_index = self._remaining_zones.pop(0)
        target = self._fit_minimum(candidate, self._zones[zone_index])
        result = self._move(candidate.handle, target)
        if not result.accepted:
            if self._is_recoverable_rejection(result):
                self._reject_zone(candidate, zone_index, result)
                self._show_next_suggestion(self._runtime.windows.get_snapshot())
            else:
                self._rollback_flow(result.message or "No se pudo mover la ventana.")
            return
        self._snapped[zone_index] = candidate.handle
        self._show_next_suggestion(self._runtime.windows.get_snapshot())

    def cancel(self) -> NativeSnapResult:
        result = NativeSnapResult(
            self._flow_id,
            tuple(sorted((window, zone) for zone, window in self._snapped.items())),
            completed=not self._remaining_zones and bool(self._snapped),
            empty_zones=tuple(sorted(self._empty_zones)),
        )
        if self.active:
            try:
                self._runtime.presentation.hide(self._flow_id)
            except Exception as error:
                self._safe_notify(f"No se pudo cerrar la presentación: {error}")
        completed_group_id = None
        if self._snapped and self._layout and self._monitor_handle:
            completed_group_id = self.state.commit_snap(
                self._layout,
                self._monitor_handle,
                self._snapped,
            )
        if completed_group_id:
            self._focus_group(completed_group_id)
        self._reset()
        return result

    def focus_active_group(self) -> bool:
        snapshot = self._runtime.windows.get_snapshot()
        if not snapshot.active_window:
            return False
        group = self.state.group_for_window(snapshot.active_window)
        if group is None:
            return False
        return self._focus_group(group.group_id)

    def _focus_group(self, group_id: str) -> bool:
        group = self.state.groups.get(group_id)
        if group is None:
            return False
        ordered = [window for _zone, window in sorted(group.zones.items())]
        for window in ordered:
            result = self._runtime.windows.activate(
                f"focus-group:{group.group_id}:{uuid.uuid4()}",
                window,
            )
            if not result.accepted:
                self.state.forget_window(window)
        primary = ordered[0] if ordered else None
        if primary and primary in self.state.snapped_windows:
            self._runtime.windows.activate(
                f"focus-group-primary:{group.group_id}:{uuid.uuid4()}",
                primary,
            )
        return group_id in self.state.groups

    def restore_window(self, window: str) -> bool:
        original = self.state.detach_with_state(window)
        if original is None:
            return False
        geometry, maximized = original
        result = self._runtime.windows.move_resize(
            f"restore:{uuid.uuid4()}",
            window,
            geometry,
        )
        if result.accepted and maximized:
            result = self._runtime.windows.set_maximized(
                f"restore-maximized:{uuid.uuid4()}",
                window,
                True,
            )
        return result.accepted

    def close(self) -> None:
        if self.active:
            self.cancel()
        self._unsubscribe_events()

    def _choose_layout(self, index: int) -> None:
        if not 0 <= index < len(self._layouts):
            return
        assert self._snapshot is not None
        assert self._active_window is not None
        monitor = _find_monitor(self._snapshot, self._active_window.monitor)
        if monitor is None:
            self.cancel()
            return
        self._layout = self._layouts[index]
        self._zones = [
            _zone_rect(monitor.work_area, zone)
            for zone in self._layout.zones
        ]
        self._phase = "zone"
        zone_choices = [
            LayoutTemplate(_zone_name(zone, index), [self._layout.zones[index]])
            for index, zone in enumerate(self._zones)
        ]
        try:
            self._runtime.presentation.show_layouts(
                self._flow_id,
                zone_choices,
                self._active_window,
            )
        except Exception as error:
            self._rollback_flow(f"No se pudieron mostrar las zonas: {error}")

    def _choose_first_zone(self, zone_index: int) -> None:
        if not 0 <= zone_index < len(self._zones):
            return
        assert self._active_window is not None
        target = self._fit_minimum(
            self._active_window,
            self._zones[zone_index],
        )
        self._remaining_zones = [
            index for index in range(len(self._zones)) if index != zone_index
        ]
        result = self._move(self._active_window.handle, target)
        if not result.accepted:
            if self._is_recoverable_rejection(result):
                self._reject_zone(self._active_window, zone_index, result)
                self._show_next_suggestion(self._runtime.windows.get_snapshot())
            else:
                self._rollback_flow(result.message or "No se pudo mover la ventana.")
            return
        self._snapped[zone_index] = self._active_window.handle
        self._show_next_suggestion(self._runtime.windows.get_snapshot())

    def _show_next_suggestion(self, snapshot: DesktopSnapshot) -> None:
        candidates: list[WindowSnapshot] = []
        while self._remaining_zones:
            zone_index = self._remaining_zones[0]
            candidates = [
                window
                for window in snapshot.windows
                if (
                    window.eligible
                    and window.workspace == snapshot.active_workspace
                    and window.handle not in self._snapped.values()
                    and window.handle not in self._rejected_windows
                )
            ]
            if candidates:
                break
            # Una zona estrecha sin candidatas no invalida zonas posteriores:
            # otra aplicación todavía puede caber en una zona más grande.
            self._empty_zones.add(self._remaining_zones.pop(0))
        if not self._remaining_zones:
            self.cancel()
            return
        self._phase = "suggestion"
        zone_index = self._remaining_zones[0]
        try:
            self._runtime.presentation.show_suggestions(
                self._flow_id,
                self._zones[zone_index],
                candidates,
            )
        except Exception as error:
            self._rollback_flow(f"No se pudieron mostrar sugerencias: {error}")

    def _move(self, window: str, rect: LogicalRect) -> OperationResult:
        snapshot = self._runtime.windows.get_snapshot()
        current = _find_window(snapshot, window)
        if current and window not in self._flow_originals:
            self._flow_originals[window] = (current.geometry, current.maximized)
        if current and current.maximized:
            unmaximize = self._runtime.windows.set_maximized(
                f"unmaximize:{self._flow_id}:{uuid.uuid4()}",
                window,
                False,
            )
            if not unmaximize.accepted:
                return unmaximize
        result = self._runtime.windows.move_resize(
            f"snap:{self._flow_id}:{uuid.uuid4()}",
            window,
            rect,
        )
        logger.info(
            "Snap solicitado: window=%s app=%s target=%s accepted=%s error=%s",
            window,
            current.app_name if current else "",
            rect,
            result.accepted,
            result.error_code,
        )
        if not result.accepted:
            return result
        if current is not None:
            self.state.save_geometry(
                window,
                current.geometry,
                current.maximized,
            )
            focus = self._runtime.windows.activate(
                f"focus-snapped:{self._flow_id}:{uuid.uuid4()}", window
            )
            if not focus.accepted:
                self._safe_notify(
                    "La ventana se acomodó, pero GNOME no pudo mostrarla en primer plano."
                )
            observed = _find_window(self._runtime.windows.get_snapshot(), window)
            logger.info(
                "Snap observado: window=%s geometry=%s minimized=%s focus=%s",
                window,
                observed.geometry if observed else None,
                observed.minimized if observed else None,
                focus.accepted,
            )
        return result

    @staticmethod
    def _is_recoverable_rejection(result: OperationResult) -> bool:
        status = getattr(result, "status", None)
        return status in {"constraint-rejected", "window-gone"} or result.error_code in {
            "constraint-rejected",
            "geometry-rejected",
            "window-gone",
        }

    def _reject_zone(
        self,
        window: WindowSnapshot,
        zone_index: int,
        result: OperationResult | None,
        *,
        constraint: str | None = None,
    ) -> None:
        """Aísla una ventana incompatible sin deshacer las ya confirmadas."""
        self._empty_zones.add(zone_index)
        self._rejected_windows.add(window.handle)
        original = self._flow_originals.pop(window.handle, None)
        if (
            original is not None
            and getattr(result, "error_code", None) != "window-gone"
            and not getattr(result, "restored", False)
        ):
            geometry, maximized = original
            try:
                restored = self._runtime.windows.move_resize(
                    f"reject-restore:{self._flow_id}:{uuid.uuid4()}",
                    window.handle,
                    geometry,
                )
                if restored.accepted and maximized:
                    self._runtime.windows.set_maximized(
                        f"reject-restore-maximized:{self._flow_id}:{uuid.uuid4()}",
                        window.handle,
                        True,
                    )
                elif not restored.accepted:
                    self._pending_restores.append((window.handle, geometry, maximized))
            except Exception:
                self._pending_restores.append((window.handle, geometry, maximized))
        label = window.app_name or window.app_id or window.title or "La aplicación"
        detected = constraint or getattr(result, "constraint", None)
        detected = {
            "minimum-size": "un tamaño mínimo",
            "client-geometry": "una geometría impuesta por la aplicación",
        }.get(detected, detected)
        if detected:
            message = f"{label} requiere {detected} incompatible; su zona quedó vacía."
        elif getattr(result, "error_code", None) == "window-gone":
            message = f"{label} se cerró mientras se acomodaba; su zona quedó vacía."
        else:
            message = f"{label} no puede cubrir la zona completa; su zona quedó vacía."
        self._safe_notify(message)

    def _rollback_flow(self, reason: str, *, defer_restores: bool = False) -> None:
        """Restaura geometría, maximización y estado si falla una transacción."""
        flow_id = self._flow_id
        for window, (geometry, maximized) in reversed(
            tuple(self._flow_originals.items())
        ):
            if defer_restores:
                self._pending_restores.append((window, geometry, maximized))
                continue
            try:
                result = self._runtime.windows.move_resize(
                    f"rollback:{flow_id}:{uuid.uuid4()}",
                    window,
                    geometry,
                )
                if result.accepted and maximized:
                    self._runtime.windows.set_maximized(
                        f"rollback-maximized:{flow_id}:{uuid.uuid4()}",
                        window,
                        True,
                    )
            except Exception:
                self._pending_restores.append((window, geometry, maximized))
        if self._state_before_flow is not None:
            self.state.restore(self._state_before_flow)
        if self.active and not defer_restores:
            try:
                self._runtime.presentation.hide(flow_id)
            except Exception:
                pass
        self._reset()
        if not defer_restores:
            self._safe_notify(reason)

    def _retry_pending_restores(self) -> None:
        pending = self._pending_restores
        self._pending_restores = []
        for window, geometry, maximized in pending:
            try:
                result = self._runtime.windows.move_resize(
                    f"reconnect-restore:{uuid.uuid4()}", window, geometry
                )
                if result.accepted and maximized:
                    self._runtime.windows.set_maximized(
                        f"reconnect-restore-maximized:{uuid.uuid4()}",
                        window,
                        True,
                    )
            except Exception:
                self._pending_restores.append((window, geometry, maximized))

    def _safe_notify(self, message: str) -> None:
        try:
            self._runtime.presentation.notify(message)
        except Exception:
            pass

    def _fit_minimum(
        self,
        window: WindowSnapshot,
        zone: LogicalRect,
    ) -> LogicalRect:
        if self._snapshot is None:
            return zone
        monitor = _find_monitor(
            self._snapshot,
            self._monitor_handle or window.monitor,
        )
        bounds = monitor.work_area if monitor else zone
        if window.minimum_size_known and window.minimum_size:
            min_w, min_h = window.minimum_size
            width = max(zone.width, min_w)
            height = max(zone.height, min_h)
            width = min(bounds.width, width)
            height = min(bounds.height, height)
            x = zone.x + (zone.width - width) // 2
            y = zone.y + (zone.height - height) // 2
            x = min(max(x, bounds.x), bounds.x + bounds.width - width)
            y = min(max(y, bounds.y), bounds.y + bounds.height - height)
            return LogicalRect(x, y, width, height)

        width = min(bounds.width, zone.width)
        height = min(bounds.height, zone.height)
        x = zone.x + (zone.width - width) // 2
        y = zone.y + (zone.height - height) // 2
        x = min(max(x, bounds.x), bounds.x + bounds.width - width)
        y = min(max(y, bounds.y), bounds.y + bounds.height - height)
        return LogicalRect(x, y, width, height)

    def _reset(self) -> None:
        self._phase = "idle"
        self._snapshot = None
        self._active_window = None
        self._layout = None
        self._zones = []
        self._remaining_zones = []
        self._snapped = {}
        self._empty_zones = set()
        self._rejected_windows = set()
        self._monitor_handle = None
        self._state_before_flow = None
        self._flow_originals = {}


def _zone_rect(work_area: LogicalRect, zone: ZoneTemplate) -> LogicalRect:
    left = work_area.x + round(work_area.width * zone.x)
    top = work_area.y + round(work_area.height * zone.y)
    right = work_area.x + round(work_area.width * (zone.x + zone.w))
    bottom = work_area.y + round(work_area.height * (zone.y + zone.h))
    return LogicalRect(left, top, max(0, right - left), max(0, bottom - top))


def _find_window(
    snapshot: DesktopSnapshot,
    handle: str | None,
) -> WindowSnapshot | None:
    return next((window for window in snapshot.windows if window.handle == handle), None)


def _find_monitor(snapshot: DesktopSnapshot, handle: str):
    return next((monitor for monitor in snapshot.monitors if monitor.handle == handle), None)


def _zone_name(rect: LogicalRect, index: int) -> str:
    return f"Zona {index + 1} — {rect.width}×{rect.height}"
