"""
snap/snap_flow.py — Máquina de estados para el flujo de acoplamiento.
"""

import logging
from typing import List, Optional
from uuid import uuid4

from snapassist.wm.backend import WindowManager
from snapassist.core.state import State
from snapassist.layout.engine import LayoutEngine, Rect
from snapassist.snap.snapper import SnapEngine
from snapassist.snap.group_manager import GroupManager
from snapassist.snap.animation import AnimationEngine
from snapassist.ui.ui_manager import UIManager
from snapassist.ui.notifier import Notifier
from snapassist.config import LAYOUT_TEMPLATES, LayoutTemplate, WindowInfo

logger = logging.getLogger(__name__)

class SnapFlow:
    """
    Controla el flujo interactivo de alto nivel desde que el usuario
    presiona Super+Z hasta que se confirma la animación.
    """
    
    def __init__(
        self,
        wm: WindowManager,
        state: State,
        snap_engine: SnapEngine,
        ui_manager: UIManager,
        group_manager: Optional[GroupManager] = None,
    ):
        self._wm = wm
        self._state = state
        self._snap_engine = snap_engine
        self._ui_manager = ui_manager
        self._group_manager = group_manager
        self._animation_engine = AnimationEngine(fps=60, duration_ms=200)
        self._layout_engine = LayoutEngine(gap_px=0)
        
        self._is_active = False
        self._active_wid = None
        self._monitor_idx = 0
        self._monitor_rect = None
        self._absolute_rects = []
        self._phase = "idle"
        self._flow_token = 0
        self._selected_layout: Optional[LayoutTemplate] = None
        self._selected_layout_index: Optional[int] = None
        self._occupied_zones: List[int] = []
        self._current_zone: Optional[int] = None
        self._eligible_windows: List[WindowInfo] = []
        self._group_id: Optional[str] = None
        self._snapped_map = {}
        self._transaction_state_snapshot = None
        self._transaction_geometries = {}

    def trigger(self) -> None:
        """
        Llamado cuando el usuario presiona Super+Z.
        Si ya está activo, cancela el flujo (toggle).
        """
        if self._is_active:
            logger.info("Super+Z presionado nuevamente. Cancelando menú.")
            self.cancel()
            return
            
        active_wid = self._wm.get_active_window()
        if not active_wid:
            logger.info("No hay ventana activa. Abortando flujo.")
            Notifier.send("Selecciona una ventana primero para acoplarla.")
            return

        # Si el foco está en un diálogo, la unidad de snap es su ventana padre.
        seen = set()
        transient_reader = getattr(self._wm, "get_transient_for", None)
        while transient_reader and active_wid not in seen:
            seen.add(active_wid)
            parent_wid = transient_reader(active_wid)
            if not parent_wid:
                break
            active_wid = parent_wid
            
        self._is_active = True
        self._phase = "layout"
        self._flow_token += 1
        self._active_wid = active_wid
        self._monitor_idx = self._wm.get_monitor_for_window(active_wid)
        self._monitor_rect = self._wm.get_work_area(self._monitor_idx)
        
        logger.info("Iniciando flujo UI para ventana 0x%x en monitor %d", active_wid, self._monitor_idx)
        
        # Pre-calcular rectángulos absolutos
        self._absolute_rects = []
        for layout in LAYOUT_TEMPLATES:
            layout_rects = []
            for zone in layout.zones:
                rect = self._layout_engine.calculate_zone_rect(self._monitor_rect, zone)
                layout_rects.append(rect)
            self._absolute_rects.append(layout_rects)
            
        snappable_count = max(1, len(self._wm.get_all_windows()))
        disabled_layouts = [
            len(layout.zones) > snappable_count
            for layout in LAYOUT_TEMPLATES
        ]
            
        self._ui_manager.send_command({
            "action": "show_menu",
            "flow_id": self._flow_token,
            "layouts": LAYOUT_TEMPLATES,
            "absolute_rects": self._absolute_rects,
            "monitor_rect": self._monitor_rect,
            "disabled_layouts": disabled_layouts
        })

    def cancel(self, flow_id: Optional[int] = None) -> None:
        """Cancela el punto actual y conserva las ventanas ya acopladas."""
        if not self._accepts_callback(flow_id):
            return
        logger.info("Cancelando flujo de acoplamiento.")
        self._ui_manager.send_command({
            "action": "hide_menu", "flow_id": self._flow_token
        })
        self._ui_manager.send_command({
            "action": "hide_snap_assist", "flow_id": self._flow_token
        })
        self._finalize_group()
        self._commit_transaction()
        self._reset()

    def confirm_selection(
        self,
        layout_index: int,
        zone_index: int,
        flow_id: Optional[int] = None,
    ) -> None:
        """
        El usuario seleccionó una zona. Procede con la lógica de animación 
        y acoplamiento a nivel WM.
        """
        if (
            not self._accepts_callback(flow_id)
            or self._phase != "layout"
            or not self._active_wid
        ):
            return
            
        logger.info("Confirmada selección: Layout %d, Zona %d", layout_index, zone_index)
        
        if not (0 <= layout_index < len(self._absolute_rects)) or not (
            0 <= zone_index < len(self._absolute_rects[layout_index])
        ):
            logger.warning("Selección de layout fuera de rango")
            return
        target_rect = self._absolute_rects[layout_index][zone_index]
        start_geom = self._wm.get_window_geometry(self._active_wid)
        start_rect = start_geom.rect
        wid_to_animate = self._active_wid
        token = self._flow_token
        self._begin_transaction()
        self._capture_for_rollback(wid_to_animate)
        if not self._state.get_saved_geometry(wid_to_animate):
            self._state.save_geometry(wid_to_animate, start_geom)

        self._selected_layout = LAYOUT_TEMPLATES[layout_index]
        self._selected_layout_index = layout_index
        self._occupied_zones = []
        self._current_zone = None
        self._group_id = f"phase7-{uuid4()}"
        self._snapped_map = {}
        self._eligible_windows = self._freeze_eligible_windows(wid_to_animate)
        self._phase = "animating"
        
        def update_frame(rect: Rect):
            if self._wm.move_resize_window(wid_to_animate, rect) is False:
                raise RuntimeError(f"falló move/resize de 0x{wid_to_animate:x}")
            
        def on_complete():
            if not self._is_active or token != self._flow_token:
                return
            logger.info("Animación completada para 0x%x", wid_to_animate)
            if self._group_manager:
                self._group_manager.on_window_detached(wid_to_animate)
            if not self._snap_engine.snap_window_to_rect(
                wid_to_animate,
                self._selected_layout,
                zone_index,
                target_rect,
                self._group_id,
            ):
                self._rollback_transaction("falló la primera ventana")
                return
            self._occupied_zones.append(zone_index)
            self._snapped_map[zone_index] = wid_to_animate
            self._show_next_empty_zone()
            
        logger.debug("Iniciando animación: %s -> %s", start_rect, target_rect)
        animation_args = {
            "start_rect": start_rect,
            "end_rect": target_rect,
            "update_callback": update_frame,
            "on_complete": on_complete,
        }
        try:
            self._animation_engine.animate_async(
                **animation_args,
                on_error=lambda error: self._rollback_transaction(str(error)),
            )
        except TypeError as error:
            # Compatibilidad con motores/mocks de fases anteriores.
            if "on_error" not in str(error):
                raise
            self._animation_engine.animate_async(**animation_args)

    def confirm_assist_selection(
        self, wid: Optional[int], flow_id: Optional[int] = None
    ) -> None:
        """Acopla una sugerencia y continúa con la siguiente zona vacía."""
        if not wid or not self._accepts_callback(flow_id) or self._phase != "assist":
            return

        selected = next(
            (info for info in self._eligible_windows if info.window_id == wid),
            None,
        )
        if selected is None or self._current_zone is None:
            logger.warning("Selección de Snap Assist inválida: %s", wid)
            return

        zone_index = self._current_zone
        target_rect = self._absolute_rects[self._selected_layout_index][zone_index]
        self._capture_for_rollback(wid)
        if selected.on_other_workspace:
            self._wm.move_window_to_current_workspace(wid)

        if self._group_manager:
            self._group_manager.on_window_detached(wid)
        if not self._snap_engine.snap_window_to_rect(
            wid,
            self._selected_layout,
            zone_index,
            target_rect,
            self._group_id,
        ):
            self._rollback_transaction(f"falló la ventana sugerida 0x{wid:x}")
            return
        self._occupied_zones.append(zone_index)
        self._snapped_map[zone_index] = wid
        self._eligible_windows = [
            info for info in self._eligible_windows if info.window_id != wid
        ]
        logger.info("Zona %d completada con ventana 0x%x", zone_index, wid)
        self._show_next_empty_zone()

    def cancel_snap_assist(
        self, reason: str = "escape", flow_id: Optional[int] = None
    ) -> None:
        """Finaliza las sugerencias conservando las zonas ya completadas."""
        if not self._accepts_callback(flow_id):
            return
        if reason == "focus_out":
            logger.info("Flujo interrumpido por pérdida de foco")
        else:
            logger.info("Snap Assist cancelado por el usuario")
        self._ui_manager.send_command({
            "action": "hide_snap_assist", "flow_id": self._flow_token
        })
        self._finalize_group()
        self._commit_transaction()
        self._reset()

    def _freeze_eligible_windows(self, exclude_wid: int) -> List[WindowInfo]:
        """Captura una copia inmutable respecto a futuras lecturas del WM."""
        loader = getattr(self._wm, "get_eligible_windows", None)
        if loader:
            candidates = loader()
        else:
            candidates = [
                WindowInfo(wid, self._wm.get_window_title(wid))
                for wid in self._wm.get_all_windows()
            ]
        return list(self._state.get_sorted_eligible(candidates, exclude_wid))

    @staticmethod
    def get_empty_zone_indices(
        template: LayoutTemplate, occupied_zone_indices: List[int]
    ) -> List[int]:
        occupied = set(occupied_zone_indices)
        return [
            index for index in range(len(template.zones))
            if index not in occupied
        ]

    def _show_next_empty_zone(self) -> None:
        empty_zones = self.get_empty_zone_indices(
            self._selected_layout,
            self._occupied_zones,
        )
        if not empty_zones or not self._eligible_windows:
            logger.info(
                "Snap Assist finalizado: %d zona(s) ocupada(s)",
                len(self._occupied_zones),
            )
            self._ui_manager.send_command({
                "action": "hide_snap_assist", "flow_id": self._flow_token
            })
            self._finalize_group()
            self._commit_transaction()
            self._reset()
            return

        self._current_zone = empty_zones[0]
        self._phase = "assist"
        zone_rect = self._absolute_rects[
            self._selected_layout_index
        ][self._current_zone]
        self._ui_manager.send_command({
            "action": "show_snap_assist",
            "flow_id": self._flow_token,
            "eligible_windows": list(self._eligible_windows),
            "zone_rect": zone_rect,
        })

    def on_window_dragged(self, wid: int) -> None:
        """Desacopla una ventana tras superar el umbral de arrastre.

        La geometría se restaura sólo para un drag intencional. Un resize
        manual se trata aparte y conserva el tamaño elegido por el usuario.
        """
        if not self._state.is_snapped(wid):
            return

        previous_geometry = self._state.get_saved_geometry(wid)
        if previous_geometry is None:
            logger.warning("No hay geometría previa para restaurar 0x%x", wid)
            self._state.unmark_snapped(wid)
            return

        logger.info("Desacoplando 0x%x por arrastre y restaurando geometría", wid)
        release = getattr(self._wm, "release_window_from_snap", None)
        if release:
            release(wid)
        self._wm.set_window_maximized(wid, previous_geometry.is_maximized)
        self._wm.move_resize_window(wid, previous_geometry.rect)
        self._state.restore_geometry(wid)
        if self._group_manager:
            self._group_manager.on_window_detached(wid)
        else:
            self._state.unmark_snapped(wid)

    def on_window_resized(self, wid: int) -> None:
        """Desacopla tras un resize externo sin restaurar la geometría."""
        if not self._state.is_snapped(wid):
            return
        logger.info("Desacoplando 0x%x por resize externo", wid)
        release = getattr(self._wm, "release_window_from_snap", None)
        if release:
            release(wid)
        self._state.restore_geometry(wid)
        if self._group_manager:
            self._group_manager.on_window_detached(wid)
        else:
            self._state.unmark_snapped(wid)

    def on_window_destroyed(self, wid: int) -> None:
        release = getattr(self._wm, "release_window_from_snap", None)
        if release:
            release(wid)
        if self._group_manager:
            self._group_manager.on_window_destroyed(wid)
        else:
            self._state.unmark_snapped(wid)
            self._state.restore_geometry(wid)

    def on_monitors_changed(self) -> None:
        """Cierra cualquier selector que haya quedado sobre otra topología."""
        if self._is_active:
            logger.info("Topología de monitores cambió; cerrando flujo activo")
            self.cancel()

    def _begin_transaction(self) -> None:
        if self._transaction_state_snapshot is None:
            self._transaction_state_snapshot = self._state.snapshot_snap_state()
            self._transaction_geometries = {}

    def _capture_for_rollback(self, wid: int) -> None:
        """Guarda geometría física del cliente y de sus modales una sola vez."""
        candidates = [wid]
        loader = getattr(self._wm, "get_transient_children", None)
        if loader:
            candidates.extend(loader(wid))
        for candidate in candidates:
            if candidate not in self._transaction_geometries:
                self._transaction_geometries[candidate] = (
                    self._wm.get_window_geometry(candidate)
                )

    def _commit_transaction(self) -> None:
        self._transaction_state_snapshot = None
        self._transaction_geometries = {}

    def _rollback_transaction(self, reason: str) -> None:
        """Revierte todas las ventanas y el estado si falla una operación."""
        snapshot = self._transaction_state_snapshot
        if snapshot is None:
            self._reset()
            return
        self._ui_manager.send_command({
            "action": "hide_menu", "flow_id": self._flow_token
        })
        self._ui_manager.send_command({
            "action": "hide_snap_assist", "flow_id": self._flow_token
        })
        release = getattr(self._wm, "release_window_from_snap", None)
        exists = getattr(self._wm, "window_exists", None)
        for wid, geometry in reversed(list(self._transaction_geometries.items())):
            if exists and not exists(wid):
                continue
            if release:
                release(wid)
            self._wm.set_window_maximized(wid, geometry.is_maximized)
            if self._wm.move_resize_window(wid, geometry.rect) is False:
                logger.warning("Rollback físico incompleto para 0x%x", wid)
        self._state.restore_snap_state(snapshot)
        prepare = getattr(self._wm, "prepare_window_for_snap", None)
        if prepare:
            for wid in snapshot["snapped_windows"]:
                if not exists or exists(wid):
                    prepare(wid)
        logger.error("Rollback atómico de Snap Assist: %s", reason)
        self._commit_transaction()
        self._reset()

    def _finalize_group(self) -> None:
        if (
            self._group_manager
            and self._selected_layout
            and len(self._snapped_map) >= 2
        ):
            self._group_manager.create_group(
                self._snapped_map,
                self._selected_layout,
                self._monitor_idx,
            )

    def _accepts_callback(self, flow_id: Optional[int]) -> bool:
        """Acepta llamadas directas y callbacks del flujo actualmente visible."""
        accepted = self._is_active and (
            flow_id is None or flow_id == self._flow_token
        )
        if not accepted and flow_id is not None:
            logger.debug(
                "Callback obsoleto ignorado: recibido=%s, activo=%s, estado=%s",
                flow_id,
                self._flow_token,
                self._phase,
            )
        return accepted
        
    def _reset(self) -> None:
        self._flow_token += 1
        self._is_active = False
        self._phase = "idle"
        self._active_wid = None
        self._monitor_idx = 0
        self._monitor_rect = None
        self._absolute_rects = []
        self._selected_layout = None
        self._selected_layout_index = None
        self._occupied_zones = []
        self._current_zone = None
        self._eligible_windows = []
        self._group_id = None
        self._snapped_map = {}
