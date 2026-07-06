"""
layout/engine.py — Motor de cálculo de geometría de zonas.

Traduce las proporciones lógicas de las plantillas (0.0 a 1.0) 
a coordenadas absolutas (píxeles) del monitor, tomando en cuenta 
el work area y un margen opcional.
"""

from typing import List

from snapassist.config import LayoutTemplate, Rect, ZoneRef, ZoneTemplate


class LayoutEngine:
    """
    Motor matemático puro para cálculo de áreas en pantalla.
    No interactúa con X11 ni con el estado, solo hace transformaciones de Rect.
    """

    def __init__(self, gap_px: int = 0) -> None:
        """
        Args:
            gap_px: Separación en píxeles entre zonas y bordes.
                    Por defecto 0 para probar la funcionalidad cruda.
        """
        self.gap_px = gap_px

    def calculate_zone_rect(self, work_area: Rect, zone: ZoneTemplate) -> Rect:
        """
        Calcula el rectángulo absoluto de una zona específica dentro de un área de trabajo.
        
        Aplica los márgenes (gaps) configurados, asegurando que las zonas adyacentes 
        tengan una separación uniforme y no se salgan del monitor.

        Args:
            work_area: Rectángulo disponible del monitor (excluyendo paneles).
            zone: Plantilla con proporciones normalizadas [0.0, 1.0].

        Returns:
            Rect: Geometría absoluta (píxeles enteros) donde debe ir la ventana.
        """
        # Calcular dimensiones absolutas base (sin gap)
        abs_x = work_area.x + (work_area.w * zone.x)
        abs_y = work_area.y + (work_area.h * zone.y)
        abs_w = work_area.w * zone.w
        abs_h = work_area.h * zone.h

        # Aplicar el gap. 
        # Reducimos el ancho y alto, e incrementamos x, y
        final_x = int(round(abs_x + self.gap_px))
        final_y = int(round(abs_y + self.gap_px))
        
        # Para evitar problemas de redondeo que dejan huecos entre zonas, 
        # calculamos el right/bottom base y aplicamos el gap allí, 
        # luego obtenemos w/h finales.
        abs_right = abs_x + abs_w
        abs_bottom = abs_y + abs_h
        
        final_right = int(round(abs_right - self.gap_px))
        final_bottom = int(round(abs_bottom - self.gap_px))
        
        final_w = max(1, final_right - final_x)
        final_h = max(1, final_bottom - final_y)

        return Rect(x=final_x, y=final_y, w=final_w, h=final_h)

    def calculate_layout(self, work_area: Rect, template: LayoutTemplate) -> List[Rect]:
        """
        Calcula todos los rectángulos de un layout completo.
        
        Útil para el overlay visual (Fase 4).
        """
        return [
            self.calculate_zone_rect(work_area, zone)
            for zone in template.zones
        ]
