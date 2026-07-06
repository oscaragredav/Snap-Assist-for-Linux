"""
snap/snapper.py — Motor central de lógica de Snap Assist.

Coordina las tres capas:
1. Lee geometría original del WM.
2. Usa LayoutEngine para calcular destino.
3. Guarda estado original y ordena al WM mover la ventana.
"""

import logging

from snapassist.config import LayoutTemplate, ZoneRef
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

    def snap_window_to_zone(self, wid: int, layout: LayoutTemplate, zone_index: int) -> None:
        """
        Ancla una ventana a la zona especificada de un layout.

        Flujo:
        1. Rescata la geometría original (para poder hacer "unsnap" después).
        2. Remueve el estado maximizado si lo tiene.
        3. Calcula las coordenadas exactas de la zona en el monitor.
        4. Mueve y redimensiona la ventana.
        5. Actualiza el estado (snapped_windows).
        """
        # 1. Guardar estado original si es la primera vez que se acopla
        if not self._state.get_saved_geometry(wid):
            current_geom = self._wm.get_window_geometry(wid)
            self._state.save_geometry(wid, current_geom)
            logger.debug(
                "snap_window_to_zone: guardada geometría original de 0x%x", wid
            )

        # 2. Des-maximizar antes de mover
        self._wm.set_window_maximized(wid, False)

        # 3. Calcular destino
        # Obtener monitor donde reside actualmente la ventana
        monitor_idx = self._wm.get_monitor_for_window(wid)
        work_area = self._wm.get_work_area(monitor_idx)

        zone_template = layout.zones[zone_index]
        
        target_rect = self._layout.calculate_zone_rect(
            work_area=work_area,
            zone=zone_template
        )

        # 4. Mover ventana
        logger.info(
            "Acoplando ventana 0x%x a zona %d de layout '%s' en monitor %d",
            wid, zone_index, layout.name, monitor_idx
        )
        self._wm.move_resize_window(wid, target_rect)
        
        # Opcionalmente, enfocar la ventana asegurando que suba
        self._wm.focus_window(wid)

        # 5. Registrar en el estado
        # En la Fase 3, usamos un group_id dummy ya que la gestión de grupos
        # se implementará en la Fase 4.
        dummy_zone_ref = ZoneRef(group_id="dummy-phase3-group", zone_index=zone_index)
        self._state.mark_snapped(wid, dummy_zone_ref)
