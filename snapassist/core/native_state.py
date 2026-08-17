"""Estado transaccional neutral para SnapAssist 2.x."""

from __future__ import annotations

import threading
import uuid
from copy import deepcopy
from dataclasses import dataclass

from snapassist.config import LayoutTemplate
from snapassist.runtime.contracts import LogicalRect, MonitorHandle, WindowHandle


@dataclass(frozen=True)
class NativeZoneRef:
    group_id: str | None
    zone_index: int


@dataclass
class NativeSnapGroup:
    group_id: str
    layout: LayoutTemplate
    monitor: MonitorHandle
    zones: dict[int, WindowHandle]


@dataclass(frozen=True)
class NativeStateSnapshot:
    saved_geometries: dict[WindowHandle, LogicalRect]
    saved_maximized: dict[WindowHandle, bool]
    snapped_windows: dict[WindowHandle, NativeZoneRef]
    groups: dict[str, NativeSnapGroup]


class NativeState:
    def __init__(self) -> None:
        self._owner_thread_id: int | None = None
        self.saved_geometries: dict[WindowHandle, LogicalRect] = {}
        self.saved_maximized: dict[WindowHandle, bool] = {}
        self.snapped_windows: dict[WindowHandle, NativeZoneRef] = {}
        self.groups: dict[str, NativeSnapGroup] = {}

    def bind_to_current_thread(self) -> None:
        current = threading.get_ident()
        if self._owner_thread_id not in (None, current):
            raise RuntimeError("NativeState ya pertenece a otro hilo")
        self._owner_thread_id = current

    def save_geometry(
        self,
        window: WindowHandle,
        geometry: LogicalRect,
        maximized: bool = False,
    ) -> None:
        self._assert_owner()
        if window not in self.saved_geometries:
            self.saved_geometries[window] = geometry
            self.saved_maximized[window] = maximized

    def commit_snap(
        self,
        layout: LayoutTemplate,
        monitor: MonitorHandle,
        zones: dict[int, WindowHandle],
    ) -> str | None:
        self._assert_owner()
        if not zones:
            return None
        for window in zones.values():
            self._remove_membership(window, preserve_geometry=True)
        if len(zones) == 1:
            zone_index, window = next(iter(zones.items()))
            self.snapped_windows[window] = NativeZoneRef(None, zone_index)
            return None
        group_id = str(uuid.uuid4())
        group = NativeSnapGroup(group_id, layout, monitor, dict(zones))
        self.groups[group_id] = group
        for zone_index, window in zones.items():
            self.snapped_windows[window] = NativeZoneRef(group_id, zone_index)
        return group_id

    def group_for_window(self, window: WindowHandle) -> NativeSnapGroup | None:
        ref = self.snapped_windows.get(window)
        return self.groups.get(ref.group_id) if ref and ref.group_id else None

    def detach(self, window: WindowHandle) -> LogicalRect | None:
        original = self.detach_with_state(window)
        return original[0] if original else None

    def detach_with_state(
        self,
        window: WindowHandle,
    ) -> tuple[LogicalRect, bool] | None:
        self._assert_owner()
        self._remove_membership(window, preserve_geometry=False)
        geometry = self.saved_geometries.pop(window, None)
        maximized = self.saved_maximized.pop(window, False)
        return (geometry, maximized) if geometry else None

    def forget_window(self, window: WindowHandle) -> None:
        self._assert_owner()
        self._remove_membership(window, preserve_geometry=False)
        self.saved_geometries.pop(window, None)
        self.saved_maximized.pop(window, None)

    def discard_groups_for_missing_monitors(
        self,
        monitor_handles: set[MonitorHandle],
    ) -> int:
        self._assert_owner()
        missing = [
            group
            for group in self.groups.values()
            if group.monitor not in monitor_handles
        ]
        for group in missing:
            self.groups.pop(group.group_id, None)
            for window in group.zones.values():
                self.snapped_windows.pop(window, None)
        return len(missing)

    def snapshot(self) -> NativeStateSnapshot:
        return NativeStateSnapshot(
            deepcopy(self.saved_geometries),
            deepcopy(self.saved_maximized),
            deepcopy(self.snapped_windows),
            deepcopy(self.groups),
        )

    def restore(self, snapshot: NativeStateSnapshot) -> None:
        self._assert_owner()
        self.saved_geometries = deepcopy(snapshot.saved_geometries)
        self.saved_maximized = deepcopy(snapshot.saved_maximized)
        self.snapped_windows = deepcopy(snapshot.snapped_windows)
        self.groups = deepcopy(snapshot.groups)

    def _remove_membership(
        self,
        window: WindowHandle,
        *,
        preserve_geometry: bool,
    ) -> None:
        ref = self.snapped_windows.pop(window, None)
        if ref and ref.group_id:
            group = self.groups.get(ref.group_id)
            if group:
                group.zones = {
                    zone: member
                    for zone, member in group.zones.items()
                    if member != window
                }
                if len(group.zones) < 2:
                    self.groups.pop(group.group_id, None)
                    for member in tuple(group.zones.values()):
                        self.snapped_windows.pop(member, None)
        # La geometría se gestiona por el llamador: commit conserva el primer
        # tamaño original; detach/forget deciden cuándo consumirla.

    def _assert_owner(self) -> None:
        if (
            self._owner_thread_id is not None
            and threading.get_ident() != self._owner_thread_id
        ):
            raise RuntimeError("NativeState solo puede mutarse desde su event loop")
