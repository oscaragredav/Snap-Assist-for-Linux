"""
wm/wayland_backend.py — Stub para futura implementación Wayland.

Implementa la interfaz WindowManager con métodos que lanzan NotImplementedError.
Su propósito en v1 es documentar el punto de extensión futuro y permitir que
el sistema arranque bajo Wayland con un error explícito y legible.

En una versión futura, esta implementación usará:
- wlr-foreign-toplevel-management para compositores wlroots (Hyprland, Sway)
- API D-Bus de KWin para KDE Plasma en Wayland
- XDG Portals para atajos globales (org.freedesktop.portal.GlobalShortcuts)
"""

import logging
from typing import List, Optional

from snapassist.config import Rect, WindowGeometry, WindowState, WindowType
from snapassist.wm.backend import WindowManager

logger = logging.getLogger(__name__)

_WAYLAND_MSG = (
    "El backend Wayland no está implementado en la v1 de SnapAssist. "
    "Por favor, utilice una sesión X11. "
    "Wayland requiere protocolos específicos del compositor "
    "(wlr-foreign-toplevel-management, KWin D-Bus, XDG Portals) "
    "que serán implementados en una versión futura."
)


class WaylandBackend(WindowManager):
    """
    Stub Wayland: todos los métodos lanzan NotImplementedError con un mensaje
    claro indicando que el backend no está disponible en v1.
    """

    def __init__(self) -> None:
        logger.critical(_WAYLAND_MSG)
        raise NotImplementedError(_WAYLAND_MSG)

    def get_active_window(self) -> Optional[int]:
        raise NotImplementedError(_WAYLAND_MSG)

    def get_all_windows(self) -> List[int]:
        raise NotImplementedError(_WAYLAND_MSG)

    def get_window_geometry(self, wid: int) -> WindowGeometry:
        raise NotImplementedError(_WAYLAND_MSG)

    def get_window_title(self, wid: int) -> str:
        raise NotImplementedError(_WAYLAND_MSG)

    def get_window_type(self, wid: int) -> WindowType:
        raise NotImplementedError(_WAYLAND_MSG)

    def get_window_state(self, wid: int) -> WindowState:
        raise NotImplementedError(_WAYLAND_MSG)

    def get_work_area(self, monitor_index: int = 0) -> Rect:
        raise NotImplementedError(_WAYLAND_MSG)

    def get_monitor_for_window(self, wid: int) -> int:
        raise NotImplementedError(_WAYLAND_MSG)

    def move_resize_window(self, wid: int, rect: Rect) -> None:
        raise NotImplementedError(_WAYLAND_MSG)

    def focus_window(self, wid: int) -> None:
        raise NotImplementedError(_WAYLAND_MSG)

    def get_transient_for(self, wid: int) -> Optional[int]:
        raise NotImplementedError(_WAYLAND_MSG)

    def get_display(self) -> object:
        raise NotImplementedError(_WAYLAND_MSG)
