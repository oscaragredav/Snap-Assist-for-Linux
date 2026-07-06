"""
wm/backend.py — Interfaz abstracta WindowManager.

Define el contrato que debe cumplir cualquier backend de gestión de ventanas
(X11, Wayland futuro). Todos los módulos del sistema que necesiten interactuar
con ventanas importan esta interfaz, nunca la implementación concreta.
"""

from abc import ABC, abstractmethod
from typing import Callable, List, Optional

from snapassist.config import Rect, WindowGeometry, WindowState, WindowType


class WindowManager(ABC):
    """
    Interfaz abstracta para interactuar con el servidor de display.

    Cada método abstracto tiene una implementación concreta en x11_backend.py
    (y futuramente en wayland_backend.py). Los módulos de lógica de negocio
    (snap/, layout/, core/) dependen exclusivamente de esta interfaz.
    """

    @abstractmethod
    def get_active_window(self) -> Optional[int]:
        """
        Retorna el window_id de la ventana actualmente enfocada,
        o None si no hay ventana activa (foco en el escritorio).
        """
        ...

    @abstractmethod
    def get_all_windows(self) -> List[int]:
        """
        Retorna la lista de window_id de todas las ventanas del cliente
        según _NET_CLIENT_LIST. No aplica filtros de elegibilidad en esta fase.
        """
        ...

    @abstractmethod
    def get_window_geometry(self, wid: int) -> WindowGeometry:
        """
        Retorna la geometría de la ventana en coordenadas absolutas de pantalla,
        incluyendo estado de maximización.
        """
        ...

    @abstractmethod
    def get_window_title(self, wid: int) -> str:
        """
        Retorna el título de la ventana (preferencia: _NET_WM_NAME,
        fallback: WM_NAME). Retorna cadena vacía si no se puede obtener.
        """
        ...

    @abstractmethod
    def get_window_type(self, wid: int) -> WindowType:
        """
        Retorna el tipo de la ventana según _NET_WM_WINDOW_TYPE.
        """
        ...

    @abstractmethod
    def get_window_state(self, wid: int) -> WindowState:
        """
        Retorna el estado de la ventana según _NET_WM_STATE.
        """
        ...

    @abstractmethod
    def get_work_area(self, monitor_index: int = 0) -> Rect:
        """
        Retorna el work area del monitor indicado: el rectángulo que excluye
        paneles, docks y barras de tareas. Usa _NET_WORKAREA.
        """
        ...

    @abstractmethod
    def get_monitor_for_window(self, wid: int) -> int:
        """
        Retorna el índice del monitor donde reside la ventana,
        calculado por intersección de geometrías.
        """
        ...

    @abstractmethod
    def move_resize_window(self, wid: int, rect: Rect) -> None:
        """
        Mueve y redimensiona la ventana a la geometría especificada.
        Usa _NET_MOVERESIZE_WINDOW con fallback a XMoveResizeWindow.
        """
        ...

    @abstractmethod
    def focus_window(self, wid: int) -> None:
        """Pide el foco para la ventana dada."""
        pass

    @abstractmethod
    def set_window_maximized(self, wid: int, maximized: bool) -> None:
        """Modifica el estado de maximización de una ventana."""
        pass

    @abstractmethod
    def get_transient_for(self, wid: int) -> Optional[int]:
        """
        Retorna el window_id del padre transitorio (WM_TRANSIENT_FOR),
        o None si la ventana no es transitoria.
        """
        ...

    @abstractmethod
    def get_display(self) -> object:
        """
        Retorna el objeto de conexión al display (Display para X11).
        Necesario para que el daemon opere el event loop.
        """
        ...
