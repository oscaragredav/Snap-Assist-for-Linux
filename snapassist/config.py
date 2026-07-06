"""
config.py — Constantes configurables y tipos base del sistema SnapAssist.

Contiene todas las constantes modificables por el usuario sin tocar código de lógica,
así como los dataclasses y enums compartidos por todos los módulos del sistema.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Tipos base
# ---------------------------------------------------------------------------

@dataclass
class Rect:
    """Rectángulo en coordenadas absolutas de pantalla (píxeles)."""
    x: int
    y: int
    w: int
    h: int

    def __post_init__(self) -> None:
        if self.w < 0 or self.h < 0:
            raise ValueError(
                f"Rect no puede tener dimensiones negativas: w={self.w}, h={self.h}"
            )

    @property
    def right(self) -> int:
        return self.x + self.w

    @property
    def bottom(self) -> int:
        return self.y + self.h

    def contains_point(self, px: int, py: int) -> bool:
        """Retorna True si el punto (px, py) está dentro del rectángulo."""
        return self.x <= px < self.right and self.y <= py < self.bottom

    def intersection_area(self, other: "Rect") -> int:
        """Calcula el área de intersección con otro rectángulo."""
        ix = max(self.x, other.x)
        iy = max(self.y, other.y)
        iw = min(self.right, other.right) - ix
        ih = min(self.bottom, other.bottom) - iy
        if iw <= 0 or ih <= 0:
            return 0
        return iw * ih


@dataclass
class WindowGeometry:
    """Geometría completa de una ventana, incluyendo estado de maximización."""
    rect: Rect
    is_maximized: bool = False


@dataclass
class ZoneRef:
    """Referencia de zona: identifica en qué grupo y en qué zona está acoplada una ventana."""
    group_id: str       # UUID del grupo
    zone_index: int     # índice de zona dentro del layout del grupo


@dataclass
class ZoneTemplate:
    """Zona expresada en proporciones relativas (0.0–1.0) respecto al work area."""
    x: float    # fracción del ancho total
    y: float    # fracción del alto total
    w: float    # fracción del ancho total
    h: float    # fracción del alto total


@dataclass
class LayoutTemplate:
    """Plantilla de layout: nombre descriptivo + lista de zonas."""
    name: str
    zones: List[ZoneTemplate] = field(default_factory=list)


@dataclass
class SnapGroup:
    """Grupo de ventanas acopladas a un layout en un monitor."""
    group_id: str
    template: LayoutTemplate
    monitor_index: int
    zones: Dict[int, int] = field(default_factory=dict)
    # zone_index → window_id (solo zonas ocupadas)


class WindowType(Enum):
    """Tipo de ventana según _NET_WM_WINDOW_TYPE."""
    NORMAL = "normal"
    DIALOG = "dialog"
    SPLASH = "splash"
    DOCK   = "dock"
    OTHER  = "other"


class WindowState(Enum):
    """Estado de ventana según _NET_WM_STATE."""
    NORMAL      = "normal"
    MINIMIZED   = "minimized"
    MAXIMIZED   = "maximized"
    FULLSCREEN  = "fullscreen"
    ALWAYS_TOP  = "always_top"


# ---------------------------------------------------------------------------
# Constantes configurables
# ---------------------------------------------------------------------------

# Atajos globales
HOTKEY_LAYOUT_MENU  = "super+z"
HOTKEY_SNAP_GROUPS  = "super+alt+tab"
HOTKEY_HELP         = "super+slash"

# Animación y umbrales
SNAP_ANIMATION_MS   = 200       # duración de transición post-acoplamiento (ms)
DRAG_THRESHOLD_PX   = 8         # umbral de desacoplamiento por mouse (px)

# Teclas de acceso rápido en Snap Assist (orden MRU)
QUICKKEY_SEQUENCE   = "qwertyu"

# Overlay de zona
OVERLAY_OPACITY     = 0.35      # opacidad del overlay (0.0 – 1.0)

# Logging
LOG_DIR             = "~/.local/share/snapassist"
LOG_FILE            = "daemon.log"
LOG_MAX_BYTES       = 5 * 1024 * 1024   # 5 MB por archivo de log
LOG_BACKUP_COUNT    = 7                  # mantener 7 archivos rotados

# ---------------------------------------------------------------------------
# Layouts preconfigurados
# ---------------------------------------------------------------------------

LAYOUT_TEMPLATES: List[LayoutTemplate] = [
    # 1:1 — Dos mitades iguales
    LayoutTemplate("1:1", [
        ZoneTemplate(0.0, 0.0, 0.5, 1.0),
        ZoneTemplate(0.5, 0.0, 0.5, 1.0),
    ]),

    # 2/3 + 1/3
    LayoutTemplate("2/3 + 1/3", [
        ZoneTemplate(0.0,   0.0, 0.667, 1.0),
        ZoneTemplate(0.667, 0.0, 0.333, 1.0),
    ]),

    # 1/3 + 2/3
    LayoutTemplate("1/3 + 2/3", [
        ZoneTemplate(0.0,   0.0, 0.333, 1.0),
        ZoneTemplate(0.333, 0.0, 0.667, 1.0),
    ]),

    # Cuadrícula 2×2
    LayoutTemplate("2×2", [
        ZoneTemplate(0.0, 0.0, 0.5, 0.5),
        ZoneTemplate(0.5, 0.0, 0.5, 0.5),
        ZoneTemplate(0.0, 0.5, 0.5, 0.5),
        ZoneTemplate(0.5, 0.5, 0.5, 0.5),
    ]),

    # 1/2 + 1/4 + 1/4 (columna izquierda completa + dos celdas derechas)
    LayoutTemplate("1/2 + 1/4 + 1/4", [
        ZoneTemplate(0.0, 0.0, 0.5, 1.0),
        ZoneTemplate(0.5, 0.0, 0.5, 0.5),
        ZoneTemplate(0.5, 0.5, 0.5, 0.5),
    ]),

    # Tres columnas iguales
    LayoutTemplate("1/3 + 1/3 + 1/3", [
        ZoneTemplate(0.0,   0.0, 0.333, 1.0),
        ZoneTemplate(0.333, 0.0, 0.334, 1.0),
        ZoneTemplate(0.667, 0.0, 0.333, 1.0),
    ]),
]
