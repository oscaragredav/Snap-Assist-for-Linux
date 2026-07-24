"""Pruebas unitarias de la Fase 6: filtro, MRU y quickkeys."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Xlib import X

from snapassist.config import QUICKKEY_SEQUENCE, WindowInfo, WindowType
from snapassist.core.state import State
from snapassist.wm.x11_backend import X11Backend


def test_sorted_eligible_uses_mru_and_excludes_active_window():
    state = State()
    for wid in (1, 2, 3, 4, 5, 2):
        state.update_mru(wid)

    windows = [WindowInfo(wid, f"Ventana {wid}") for wid in range(1, 6)]
    result = state.get_sorted_eligible(windows, exclude_wid=2)

    assert [window.window_id for window in result] == [5, 4, 3, 1]
    assert [window.quickkey for window in result] == list(QUICKKEY_SEQUENCE[:4])


def test_quickkeys_are_unique_for_ten_windows():
    state = State()
    windows = [WindowInfo(wid) for wid in range(10)]

    result = state.get_sorted_eligible(windows)

    quickkeys = [window.quickkey for window in result]
    assert len(result) == 10
    assert len(set(quickkeys)) == 10
    assert quickkeys == list(QUICKKEY_SEQUENCE)


def test_minimized_window_remains_eligible():
    class Attributes:
        map_state = X.IsUnmapped

    class Window:
        def get_attributes(self):
            return Attributes()

    class Display:
        def create_resource_object(self, _kind, _wid):
            return Window()

    backend = X11Backend.__new__(X11Backend)
    backend._display = Display()
    backend._atoms = {
        "_NET_WM_STATE_HIDDEN": 1,
        "_NET_WM_STATE_SKIP_TASKBAR": 2,
        "_NET_WM_STATE_FULLSCREEN": 3,
        "_NET_WM_STATE_ABOVE": 4,
    }
    backend._get_wm_states = lambda _wid: [1]
    backend.get_window_type = lambda _wid: WindowType.NORMAL

    assert backend._is_eligible_window(99)


def test_system_and_exclusive_windows_are_not_eligible():
    class Attributes:
        map_state = X.IsViewable

    class Window:
        def get_attributes(self):
            return Attributes()

    class Display:
        def create_resource_object(self, _kind, _wid):
            return Window()

    backend = X11Backend.__new__(X11Backend)
    backend._display = Display()
    backend._atoms = {
        "_NET_WM_STATE_HIDDEN": 1,
        "_NET_WM_STATE_SKIP_TASKBAR": 2,
        "_NET_WM_STATE_FULLSCREEN": 3,
        "_NET_WM_STATE_ABOVE": 4,
    }
    backend.get_window_type = lambda _wid: WindowType.NORMAL

    for excluded_state in (2, 3, 4):
        backend._get_wm_states = lambda _wid, state=excluded_state: [state]
        assert not backend._is_eligible_window(99)

    backend._get_wm_states = lambda _wid: []
    backend.get_window_type = lambda _wid: WindowType.DOCK
    assert not backend._is_eligible_window(99)


def run_all_tests():
    tests = [
        test_sorted_eligible_uses_mru_and_excludes_active_window,
        test_quickkeys_are_unique_for_ten_windows,
        test_minimized_window_remains_eligible,
        test_system_and_exclusive_windows_are_not_eligible,
    ]
    for test in tests:
        test()
        print(f"  ✓ {test.__name__}")


if __name__ == "__main__":
    run_all_tests()
