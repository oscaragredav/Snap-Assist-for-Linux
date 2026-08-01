"""
snap/snapper.py — Motor central de lógica de Snap Assist.

Coordina las tres capas:
1. Lee geometría original del WM.
2. Usa LayoutEngine para calcular destino.
3. Guarda estado original y ordena al WM mover la ventana.
"""

import logging
from typing import Optional

from snapassist.config import LayoutTemplate, Rect, ZoneRef
from snapassist.core.state import State
from snapassist.layout.engine import LayoutEngine
from snapassist.wm.backend import WindowManager

logger = logging.getLogger(__name__)


class SnapEngine:
    """
    Orquestador de operaciones de acoplamiento.
    """

    def __init__(
        self,
        wm_backend: WindowManager,
        state: State,
        layout_engine: LayoutEngine,
    ) -> None:
        self._wm = wm_backend
        self._state = state
        self._layout = layout_engine

    def snap_window_to_zone(
        self,
        wid: int,
        layout: LayoutTemplate,
        zone_index: int,
        group_id: Optional[str] = None,
    ) -> None:
        """
        Ancla una ventana a la zona especificada de un layout.

        Flujo:
        1. Rescata la geometría original (para poder hacer "unsnap" después).
        2. Remueve el estado maximizado si lo tiene.
        3. Calcula las coordenadas exactas de la zona en el monitor.
        4. Mueve y redimensiona la ventana.
        5. Actualiza el estado (snapped_windows).
        """
        monitor_idx = self._wm.get_monitor_for_window(wid)
        work_area = self._wm.get_work_area(monitor_idx)
        target_rect = self._layout.calculate_zone_rect(
            work_area=work_area,
            zone=layout.zones[zone_index],
        )
        return self.snap_window_to_rect(
            wid, layout, zone_index, target_rect, group_id, bounds=work_area
        )

    def snap_window_to_rect(
        self,
        wid: int,
        layout: LayoutTemplate,
        zone_index: int,
        target_rect: Rect,
        group_id: Optional[str],
        bounds: Optional[Rect] = None,
    ) -> bool:
        """Acopla una ventana a un rectángulo ya calculado.

        Esta variante permite que Snap Assist coloque ventanas procedentes de
        otro monitor en las zonas del monitor donde comenzó el flujo.
        """
        saved_here = not self._state.get_saved_geometry(wid)
        if saved_here:
            current_geom = self._wm.get_window_geometry(wid)
            self._state.save_geometry(wid, current_geom)
            logger.debug(
                "snap_window_to_zone: guardada geometría original de 0x%x", wid
            )

        min_size_reader = getattr(self._wm, "get_window_min_size", None)
        min_size = min_size_reader(wid) if min_size_reader else (1, 1)
        adjusted_rect = self._layout.center_minimum_size(
            min_size, target_rect, bounds=bounds
        )
        if adjusted_rect != target_rect:
            logger.warning(
                "Ignorar y Centrar: 0x%x requiere mínimo %dx%d; "
                "zona=%dx%d, resultado=%dx%d",
                wid,
                min_size[0],
                min_size[1],
                target_rect.w,
                target_rect.h,
                adjusted_rect.w,
                adjusted_rect.h,
            )

        prepare = getattr(self._wm, "prepare_window_for_snap", None)
        if prepare:
            prepare(wid)
        self._wm.set_window_maximized(wid, False)
        logger.info(
            "Acoplando ventana 0x%x a zona %d de layout '%s'",
            wid, zone_index, layout.name,
        )
        if self._wm.move_resize_window(wid, adjusted_rect) is False:
            if saved_here:
                self._state.restore_geometry(wid)
            release = getattr(self._wm, "release_window_from_snap", None)
            if release:
                release(wid)
            return False

        reconcile = getattr(self._wm, "reconcile_window_geometry", None)
        if reconcile and not reconcile(wid, adjusted_rect):
            logger.warning(
                "La geometría final de 0x%x difiere de la zona solicitada %s",
                wid, adjusted_rect,
            )

        transient_loader = getattr(self._wm, "get_transient_children", None)
        for child_wid in (transient_loader(wid) if transient_loader else []):
            child_rect = self._wm.get_window_geometry(child_wid).rect
            centered = Rect(
                adjusted_rect.x + (adjusted_rect.w - child_rect.w) // 2,
                adjusted_rect.y + (adjusted_rect.h - child_rect.h) // 2,
                child_rect.w,
                child_rect.h,
            )
            if self._wm.move_resize_window(child_wid, centered) is False:
                return False
        self._wm.focus_window(wid)
        self._state.mark_snapped(
            wid,
            ZoneRef(group_id=group_id, zone_index=zone_index),
        )
        return True
