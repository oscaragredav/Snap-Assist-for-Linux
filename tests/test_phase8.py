"""Pruebas unitarias de Fase 8: Snap Groups y tamaños mínimos."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from snapassist.config import LAYOUT_TEMPLATES, Rect, WindowGeometry
from snapassist.core.state import State
from snapassist.layout.engine import LayoutEngine
from snapassist.snap.group_manager import GroupManager
from snapassist.snap.snapper import SnapEngine
from snapassist.core.hotkeys import parse_hotkey
from snapassist.wm.x11_backend import X11Backend


class MockWM:
    def __init__(self):
        self.windows = {1, 2, 3, 4}
        self.focuses = []

    def window_exists(self, wid):
        return wid in self.windows

    def get_all_windows(self):
        return list(self.windows)

    def focus_window(self, wid):
        self.focuses.append(wid)


def test_exclusive_membership_dissolves_previous_singleton():
    state = State()
    wm = MockWM()
    manager = GroupManager(state, wm)

    first = manager.create_group({0: 1, 1: 2}, LAYOUT_TEMPLATES[0], 0)
    second = manager.create_group({0: 1, 1: 3}, LAYOUT_TEMPLATES[0], 0)

    assert first.group_id not in state.active_groups
    assert second.group_id in state.active_groups
    assert manager.get_group_for_window(1) is second
    assert manager.get_group_for_window(3) is second
    assert not state.is_snapped(2)


def test_destroying_member_of_pair_dissolves_group():
    state = State()
    manager = GroupManager(state, MockWM())
    group = manager.create_group({0: 1, 1: 2}, LAYOUT_TEMPLATES[0], 0)

    manager.on_window_destroyed(1)

    assert group.group_id not in state.active_groups
    assert not state.is_snapped(1)
    assert not state.is_snapped(2)


def test_validate_removes_invalid_references_and_dissolves_when_needed():
    state = State()
    wm = MockWM()
    manager = GroupManager(state, wm)
    group = manager.create_group({0: 1, 1: 2, 2: 3}, LAYOUT_TEMPLATES[4], 0)

    wm.windows.remove(3)
    validated = manager.validate_group(group.group_id)
    assert validated is group
    assert set(group.zones.values()) == {1, 2}

    wm.windows.remove(2)
    assert manager.validate_group(group.group_id) is None
    assert group.group_id not in state.active_groups
    assert not state.is_snapped(1)


def test_group_focus_leaves_primary_zone_active():
    state = State()
    wm = MockWM()
    manager = GroupManager(state, wm)
    group = manager.create_group({0: 1, 1: 2, 2: 3}, LAYOUT_TEMPLATES[4], 0)

    assert manager.focus_group_for_window(2) is group
    assert wm.focuses == [3, 2, 1]


def test_spotify_like_minimum_size_is_centered_but_stays_groupable():
    class SizeWM:
        def __init__(self):
            self.moves = []

        def get_window_geometry(self, _wid):
            return WindowGeometry(Rect(100, 100, 1200, 800))

        def get_window_min_size(self, _wid):
            return (800, 700)

        def set_window_maximized(self, _wid, _maximized):
            pass

        def move_resize_window(self, wid, rect):
            self.moves.append((wid, rect))

        def focus_window(self, _wid):
            pass

    state = State()
    wm = SizeWM()
    snapper = SnapEngine(wm, state, LayoutEngine())
    quarter_zone = Rect(960, 0, 960, 520)

    snapper.snap_window_to_rect(
        99,
        LAYOUT_TEMPLATES[3],
        1,
        quarter_zone,
        "spotify-group",
    )

    assert wm.moves == [(99, Rect(960, -90, 960, 700))]
    assert state.is_snapped(99)
    assert state.get_zone_ref(99).group_id == "spotify-group"


def test_phase8_hotkeys_are_parseable():
    assert parse_hotkey("super+alt+tab") == "<cmd>+<alt>+<tab>"
    assert parse_hotkey("super+slash") == "<cmd>+/"


def test_negative_x11_coordinates_are_encoded_as_card32():
    assert X11Backend._to_card32(-1) == 0xFFFFFFFF
    assert X11Backend._to_card32(-47) == 0xFFFFFFD1
    assert X11Backend._to_card32(960) == 960


def run_all_tests():
    tests = [
        test_exclusive_membership_dissolves_previous_singleton,
        test_destroying_member_of_pair_dissolves_group,
        test_validate_removes_invalid_references_and_dissolves_when_needed,
        test_group_focus_leaves_primary_zone_active,
        test_spotify_like_minimum_size_is_centered_but_stays_groupable,
        test_phase8_hotkeys_are_parseable,
        test_negative_x11_coordinates_are_encoded_as_card32,
    ]
    for test in tests:
        test()
        print(f"  ✓ {test.__name__}")


if __name__ == "__main__":
    run_all_tests()
