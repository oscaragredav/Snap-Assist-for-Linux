"""
core/state.py — Estado global en memoria del sistema SnapAssist.

Es un singleton accesible por todos los módulos. No tiene lógica de negocio;
es exclusivamente almacenamiento y consulta. No persiste nada a disco.
Todo se inicializa vacío al arrancar el daemon.
"""

import logging
from typing import Dict, List, Optional

from snapassist.config import SnapGroup, WindowGeometry, ZoneRef

logger = logging.getLogger(__name__)


class State:
    """
    Estado global en memoria.

    Mantiene la lista MRU, geometrías previas, ventanas acopladas,
    grupos activos y grupos suspendidos. Ningún campo se serializa a disco.
    """

    def __init__(self) -> None:
        # Lista de window_id ordenada por recencia de foco (índice 0 = más reciente)
        self.mru_list: List[int] = []

        # Geometrías previas al acoplamiento, indexadas por window_id
        self.saved_geometries: Dict[int, WindowGeometry] = {}

        # Referencia de zona para cada ventana actualmente acoplada
        self.snapped_windows: Dict[int, ZoneRef] = {}

        # Todos los grupos activos, indexados por group_id
        self.active_groups: Dict[str, SnapGroup] = {}

        # Grupos suspendidos por desconexión de monitor, indexados por monitor_index
        self.suspended_groups: Dict[int, List[SnapGroup]] = {}

        logger.info("Estado global inicializado (vacío).")

    # ------------------------------------------------------------------
    # MRU (Most Recently Used)
    # ------------------------------------------------------------------

    def get_mru_list(self) -> List[int]:
        """Retorna una copia de la lista MRU."""
        return list(self.mru_list)

    def update_mru(self, wid: int) -> None:
        """
        Mueve el window_id al frente de la lista MRU.
        Si no existe, lo inserta al frente.
        Ignora wid=0 o wid=None (significan "sin ventana activa").
        """
        if not wid:
            return

        if wid in self.mru_list:
            self.mru_list.remove(wid)
        self.mru_list.insert(0, wid)
        logger.debug("MRU actualizado: ventana 0x%x al frente. Total: %d", wid, len(self.mru_list))

    def remove_from_mru(self, wid: int) -> None:
        """Remueve un window_id de la lista MRU (e.g., al cerrar ventana)."""
        if wid in self.mru_list:
            self.mru_list.remove(wid)
            logger.debug("Ventana 0x%x removida de MRU. Total: %d", wid, len(self.mru_list))

    # ------------------------------------------------------------------
    # Geometrías previas (Toggle de Memoria)
    # ------------------------------------------------------------------

    def save_geometry(self, wid: int, geom: WindowGeometry) -> None:
        """Guarda la geometría previa de una ventana antes de acoplarla."""
        self.saved_geometries[wid] = geom
        logger.debug(
            "Geometría guardada para 0x%x: Rect(%d, %d, %d, %d), maximized=%s",
            wid, geom.rect.x, geom.rect.y, geom.rect.w, geom.rect.h,
            geom.is_maximized,
        )

    def get_saved_geometry(self, wid: int) -> Optional[WindowGeometry]:
        """Retorna la geometría guardada, o None si no existe."""
        return self.saved_geometries.get(wid)

    def restore_geometry(self, wid: int) -> Optional[WindowGeometry]:
        """
        Retorna y elimina la geometría guardada de una ventana.
        Retorna None si no hay geometría guardada para ese wid.
        """
        geom = self.saved_geometries.pop(wid, None)
        if geom:
            logger.debug("Geometría restaurada para 0x%x", wid)
        return geom

    # ------------------------------------------------------------------
    # Ventanas acopladas
    # ------------------------------------------------------------------

    def is_snapped(self, wid: int) -> bool:
        """Retorna True si la ventana está actualmente acoplada a una zona."""
        return wid in self.snapped_windows

    def get_zone_ref(self, wid: int) -> Optional[ZoneRef]:
        """Retorna la referencia de zona de una ventana acoplada, o None."""
        return self.snapped_windows.get(wid)

    def mark_snapped(self, wid: int, zone_ref: ZoneRef) -> None:
        """Marca una ventana como acoplada a una zona específica."""
        self.snapped_windows[wid] = zone_ref
        logger.debug(
            "Ventana 0x%x acoplada: grupo=%s, zona=%d",
            wid, zone_ref.group_id, zone_ref.zone_index,
        )

    def unmark_snapped(self, wid: int) -> None:
        """Remueve la marca de acoplamiento de una ventana."""
        if wid in self.snapped_windows:
            ref = self.snapped_windows.pop(wid)
            logger.debug(
                "Ventana 0x%x desacoplada: grupo=%s, zona=%d",
                wid, ref.group_id, ref.zone_index,
            )

    # ------------------------------------------------------------------
    # Resumen de estado (para logging y debug)
    # ------------------------------------------------------------------

    def summary(self) -> str:
        """Retorna un resumen legible del estado actual."""
        return (
            f"State: MRU={len(self.mru_list)} ventanas, "
            f"acopladas={len(self.snapped_windows)}, "
            f"grupos={len(self.active_groups)}, "
            f"geometrías_guardadas={len(self.saved_geometries)}"
        )
