"""Pruebas unitarias de la Fase 5: memoria y desacoplamiento."""

import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from snapassist.config import Rect, WindowGeometry, ZoneRef
from snapassist.core.daemon import Daemon
from snapassist.core.state import State
from snapassist.snap.snap_flow import SnapFlow


class MockBackend:
    def __init__(self):
        self.moves = []
        self.maximized = []

    def move_resize_window(self, wid, rect):
        self.moves.append((wid, rect))

    def set_window_maximized(self, wid, maximized):
        self.maximized.append((wid, maximized))


class NullUI:
    def send_command(self, _command):
        pass


def make_flow(state, backend):
    return SnapFlow(backend, state, snap_engine=None, ui_manager=NullUI())


def mark_snapped(state, wid=42):
    state.save_geometry(wid, WindowGeometry(Rect(100, 200, 800, 600), True))
    state.mark_snapped(wid, ZoneRef("test-group", 0))


def test_drag_restores_original_geometry():
    state = State()
    backend = MockBackend()
    mark_snapped(state)

    make_flow(state, backend).on_window_dragged(42)

    assert backend.moves == [(42, Rect(100, 200, 800, 600))]
    assert backend.maximized == [(42, True)]
    assert not state.is_snapped(42)
    assert state.get_saved_geometry(42) is None


def test_external_resize_detaches_without_restoring():
    state = State()
    backend = MockBackend()
    mark_snapped(state)

    make_flow(state, backend).on_window_resized(42)

    assert backend.moves == []
    assert not state.is_snapped(42)
    assert state.get_saved_geometry(42) is None


def test_drag_threshold_and_own_resize_filtering():
    state = State()
    mark_snapped(state)
    detached = []

    class Flow:
        def on_window_dragged(self, wid):
            detached.append(("drag", wid))

        def on_window_resized(self, wid):
            detached.append(("resize", wid))

    class WM:
        def __init__(self):
            self.own_resize = True

        def consume_own_resize(self, _wid):
            result = self.own_resize
            self.own_resize = False
            return result

    daemon = Daemon.__new__(Daemon)
    daemon._state = state
    daemon._snap_flow = Flow()
    daemon._wm = WM()
    daemon._drag_starts = {}
    daemon._drag_distances = {}
    daemon._gesture_modes = {}

    daemon._handle_button_press(SimpleNamespace(window=42, root_x=10, root_y=10))
    daemon._handle_motion_notify(SimpleNamespace(window=42, root_x=15, root_y=10))
    assert detached == []
    daemon._handle_motion_notify(SimpleNamespace(window=42, root_x=19, root_y=10))
    assert detached == [("drag", 42)]

    configure = SimpleNamespace(window=42, x=0, y=0, width=1, height=1)
    daemon._dispatch_event(SimpleNamespace(type=22, **configure.__dict__))
    assert detached == [("drag", 42)]
    daemon._dispatch_event(SimpleNamespace(type=22, **configure.__dict__))
    assert detached == [("drag", 42)]


def test_global_pointer_events_do_not_require_window_event_subscription():
    state = State()
    mark_snapped(state)
    detached = []

    class Flow:
        def on_window_dragged(self, wid):
            detached.append(wid)

    class WM:
        def get_active_window(self):
            return 42

        def get_window_geometry(self, _wid):
            return WindowGeometry(Rect(0, 0, 800, 600))

    daemon = Daemon.__new__(Daemon)
    daemon._state = state
    daemon._snap_flow = Flow()
    daemon._wm = WM()
    daemon._drag_starts = {}
    daemon._drag_distances = {}
    daemon._gesture_modes = {}

    daemon._handle_pointer_event({"event": "pointer_press", "x": 100, "y": 30})
    daemon._handle_pointer_event({"event": "pointer_move", "x": 105, "y": 30})
    assert detached == []
    daemon._handle_pointer_event({"event": "pointer_move", "x": 109, "y": 30})
    assert detached == [42]


def test_pointer_edge_resize_detaches_without_restore():
    state = State()
    mark_snapped(state)
    detached = []

    class Flow:
        def on_window_dragged(self, wid):
            detached.append(("drag", wid))

        def on_window_resized(self, wid):
            detached.append(("resize", wid))

    class WM:
        def get_active_window(self):
            return 42

        def get_window_geometry(self, _wid):
            return WindowGeometry(Rect(100, 100, 800, 600))

    daemon = Daemon.__new__(Daemon)
    daemon._state = state
    daemon._snap_flow = Flow()
    daemon._wm = WM()
    daemon._drag_starts = {}
    daemon._drag_distances = {}
    daemon._gesture_modes = {}

    daemon._handle_pointer_event({"event": "pointer_press", "x": 900, "y": 400})
    daemon._handle_pointer_event({"event": "pointer_move", "x": 910, "y": 400})
    assert detached == [("resize", 42)]


def test_repeated_own_geometry_does_not_detach_group():
    class WM:
        def consume_own_resize(self, _wid, event):
            return (
                event.x,
                event.y,
                event.width,
                event.height,
            ) == (10, 20, 800, 600)

    daemon = Daemon.__new__(Daemon)
    daemon._wm = WM()
    event = SimpleNamespace(x=10, y=20, width=800, height=600)

    assert daemon._consume_own_resize(42, event)
    assert daemon._consume_own_resize(42, event)


def run_all_tests():
    tests = [
        test_drag_restores_original_geometry,
        test_external_resize_detaches_without_restoring,
        test_drag_threshold_and_own_resize_filtering,
        test_global_pointer_events_do_not_require_window_event_subscription,
        test_pointer_edge_resize_detaches_without_restore,
        test_repeated_own_geometry_does_not_detach_group,
    ]
    for test in tests:
        test()
        print(f"  ✓ {test.__name__}")


if __name__ == "__main__":
    run_all_tests()
