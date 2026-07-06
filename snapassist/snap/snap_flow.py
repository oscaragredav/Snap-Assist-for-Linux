"""
snap/snap_flow.py — Máquina de estados para el flujo de acoplamiento.
"""

import logging
from typing import Optional, List
from snapassist.wm.backend import WindowManager
from snapassist.core.state import State
from snapassist.layout.engine import LayoutEngine, Rect
from snapassist.snap.snapper import SnapEngine
from snapassist.snap.animation import AnimationEngine
from snapassist.ui.ui_manager import UIManager
from snapassist.ui.notifier import Notifier
from snapassist.config import LAYOUT_TEMPLATES, WindowType

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
        ui_manager: UIManager
    ):
        self._wm = wm
        self._state = state
        self._snap_engine = snap_engine
        self._ui_manager = ui_manager
        self._animation_engine = AnimationEngine(fps=60, duration_ms=200)
        self._layout_engine = LayoutEngine(gap_px=0)
        
        self._is_active = False
        self._active_wid = None
        self._monitor_idx = 0
        self._monitor_rect = None
        self._absolute_rects = []

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
            
        self._is_active = True
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
            
        # Calcular layouts deshabilitados según cantidad de ventanas
        # Contamos cuántas ventanas "normales" hay en el sistema.
        windows = self._wm.get_all_windows()
        snappable_count = 0
        for w in windows:
            if self._wm.get_window_type(w) == WindowType.NORMAL:
                snappable_count += 1
                
        # Asegurarnos de que al menos contamos con 1 (la activa)
        snappable_count = max(1, snappable_count)
        
        disabled_layouts = []
        for layout in LAYOUT_TEMPLATES:
            # Un layout se deshabilita solo si tiene 3 o más zonas y no hay suficientes ventanas.
            if len(layout.zones) >= 3 and len(layout.zones) > snappable_count:
                disabled_layouts.append(True)
            else:
                disabled_layouts.append(False)
            
        self._ui_manager.send_command({
            "action": "show_menu",
            "layouts": LAYOUT_TEMPLATES,
            "absolute_rects": self._absolute_rects,
            "monitor_rect": self._monitor_rect,
            "disabled_layouts": disabled_layouts
        })

    def cancel(self) -> None:
        """Cancela el flujo y oculta la UI sin modificar ventanas."""
        if not self._is_active:
            return
        logger.info("Cancelando flujo de acoplamiento.")
        self._ui_manager.send_command({"action": "hide_menu"})
        self._reset()

    def confirm_selection(self, layout_index: int, zone_index: int) -> None:
        """
        El usuario seleccionó una zona. Procede con la lógica de animación 
        y acoplamiento a nivel WM.
        """
        if not self._is_active or not self._active_wid:
            return
            
        logger.info("Confirmada selección: Layout %d, Zona %d", layout_index, zone_index)
        
        target_rect = self._absolute_rects[layout_index][zone_index]
        start_geom = self._wm.get_window_geometry(self._active_wid)
        start_rect = start_geom.rect
        
        wid_to_animate = self._active_wid
        
        def update_frame(rect: Rect):
            self._wm.move_resize_window(wid_to_animate, rect)
            
        def on_complete():
            logger.info("Animación completada para 0x%x", wid_to_animate)
            # Acoplamiento real
            self._snap_engine.snap_window_to_zone(wid_to_animate, LAYOUT_TEMPLATES[layout_index], zone_index)
            # Asegurar foco tras animar
            self._wm.focus_window(wid_to_animate)
            
        logger.debug("Iniciando animación: %s -> %s", start_rect, target_rect)
        self._animation_engine.animate_async(
            start_rect=start_rect,
            end_rect=target_rect,
            update_callback=update_frame,
            on_complete=on_complete
        )
        
        self._reset()
        
    def _reset(self) -> None:
        self._is_active = False
        self._active_wid = None
        self._monitor_idx = 0
        self._monitor_rect = None
        self._absolute_rects = []
