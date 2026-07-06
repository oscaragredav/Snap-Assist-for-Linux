"""
ui/overlay.py — Overlay semitransparente.
"""

import tkinter as tk
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class Overlay:
    """
    Ventana Tkinter sin bordes y semitransparente que resalta
    la zona en la pantalla real durante la navegación del menú.
    """

    def __init__(self, root: tk.Tk):
        self._window = tk.Toplevel(root)
        self._window.withdraw()
        
        # Usar -type splash para que el WM lo maneje (sin bordes)
        # Esto permite que respete el Z-index respecto a ventanas topmost
        self._window.attributes("-type", "splash")
        
        # En la mayoría de WMs compositivos (GNOME/Mutter), esto aplica
        # opacidad al fondo de la ventana entera.
        self._window.attributes("-alpha", 0.3)
        
        # Color azul semitransparente característico de resaltado de zonas
        self._window.configure(bg="#3498db")

    def show(self, rect) -> None:
        """
        Muestra y posiciona el overlay en la pantalla real.
        El objeto rect debe tener propiedades x, y, w, h.
        """
        # Geometría de Tkinter: ancho x alto + x + y
        geom = f"{rect.w}x{rect.h}+{rect.x}+{rect.y}"
        self._window.geometry(geom)
        self._window.deiconify()
        # Aseguramos que quede por encima de otras apps, pero por debajo de topmost
        self._window.lift()
        
    def hide(self) -> None:
        """Oculta el overlay."""
        self._window.withdraw()
