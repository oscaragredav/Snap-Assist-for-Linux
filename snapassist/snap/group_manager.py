"""Gestión del ciclo de vida de Snap Groups."""

import logging
from typing import Dict, List, Optional
from uuid import uuid4

from snapassist.config import LayoutTemplate, SnapGroup, ZoneRef
from snapassist.core.state import State
from snapassist.wm.backend import WindowManager

logger = logging.getLogger(__name__)


class GroupManager:
    """Crea, valida, enfoca y disuelve grupos de ventanas acopladas."""

    def __init__(self, state: State, wm: WindowManager) -> None:
        self._state = state
        self._wm = wm

    def create_group(
        self,
        snapped_map: Dict[int, int],
        template: LayoutTemplate,
        monitor: int,
    ) -> Optional[SnapGroup]:
        """Crea un grupo aplicando pertenencia exclusiva."""
        members = {
            int(zone): int(wid)
            for zone, wid in snapped_map.items()
            if wid
        }
        if len(members) < 2:
            return None

        for wid in members.values():
            old_group = self.get_group_for_window(wid)
            if old_group:
                self._remove_member(old_group, wid, preserve_member_state=True)

        group_id = str(uuid4())
        group = SnapGroup(
            group_id=group_id,
            template=template,
            monitor_index=monitor,
            zones=dict(members),
        )
        self._state.active_groups[group_id] = group
        for zone_index, wid in members.items():
            self._state.mark_snapped(wid, ZoneRef(group_id, zone_index))

        logger.info(
            "Snap Group creado: %s (%d ventanas, layout '%s')",
            group_id,
            len(members),
            template.name,
        )
        return group

    def get_group_for_window(self, wid: int) -> Optional[SnapGroup]:
        ref = self._state.get_zone_ref(wid)
        if not ref:
            return None
        group = self._state.active_groups.get(ref.group_id)
        if group and wid in group.zones.values():
            return group
        return None

    def get_all_windows_in_group(self, group_id: str) -> List[int]:
        group = self._state.active_groups.get(group_id)
        if not group:
            return []
        return [wid for _, wid in sorted(group.zones.items())]

    def on_window_destroyed(self, wid: int) -> None:
        self._release_snap_constraints(wid)
        group = self.get_group_for_window(wid)
        if group:
            self._remove_member(group, wid)
        self._state.unmark_snapped(wid)
        self._state.restore_geometry(wid)

    def on_window_detached(self, wid: int) -> None:
        self._release_snap_constraints(wid)
        group = self.get_group_for_window(wid)
        if group:
            self._remove_member(group, wid)
        self._state.unmark_snapped(wid)

    def validate_group(self, group_id: str) -> Optional[SnapGroup]:
        group = self._state.active_groups.get(group_id)
        if not group:
            return None

        exists = getattr(self._wm, "window_exists", None)
        known_windows = None if exists else set(self._wm.get_all_windows())
        invalid = [
            wid
            for wid in group.zones.values()
            if not (exists(wid) if exists else wid in known_windows)
        ]
        for wid in invalid:
            self._remove_member(group, wid)
            if group_id not in self._state.active_groups:
                return None

        return self._state.active_groups.get(group_id)

    def focus_group_for_window(self, wid: int) -> Optional[SnapGroup]:
        group = self.get_group_for_window(wid)
        if not group:
            return None
        group = self.validate_group(group.group_id)
        if not group:
            return None

        # Enfocar en orden inverso deja la zona principal (índice menor)
        # arriba y con el foco al terminar.
        for _, member_wid in sorted(group.zones.items(), reverse=True):
            self._wm.focus_window(member_wid)
        logger.info("Snap Group %s traído al frente", group.group_id)
        return group

    def dissolve_group(self, group_id: str) -> None:
        group = self._state.active_groups.pop(group_id, None)
        if not group:
            return
        for wid in group.zones.values():
            ref = self._state.get_zone_ref(wid)
            if ref and ref.group_id == group_id:
                self._state.unmark_snapped(wid)
                # La ventana conserva su geometría actual, pero deja de tener
                # una geometría flotante pendiente al convertirse en independiente.
                self._state.restore_geometry(wid)
                self._release_snap_constraints(wid)
        logger.info("Snap Group disuelto: %s", group_id)

    def _release_snap_constraints(self, wid: int) -> None:
        release = getattr(self._wm, "release_window_from_snap", None)
        if release:
            release(wid)

    def _remove_member(
        self,
        group: SnapGroup,
        wid: int,
        preserve_member_state: bool = False,
    ) -> None:
        for zone_index, member_wid in list(group.zones.items()):
            if member_wid == wid:
                del group.zones[zone_index]
                break

        if not preserve_member_state:
            self._state.unmark_snapped(wid)

        if len(group.zones) <= 1:
            self.dissolve_group(group.group_id)
