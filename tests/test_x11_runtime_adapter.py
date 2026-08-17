"""Contrato neutral sobre un doble del backend X11 heredado."""

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from snapassist.adapters.x11_runtime import X11EventSource, X11WindowController
from snapassist.config import Rect, WindowGeometry, WindowState
from snapassist.runtime import EventKind, LogicalRect, PlatformEvent


class FakeX11Backend:
    def __init__(self):
        self.existing = {0x10, 0x20}
        self.moves = []
        self.focused = []
        self.maximized = []
        self.workspace_moves = []

    def get_monitors(self): return [Rect(-1920, 0, 1920, 1080), Rect(0, 0, 1920, 1080)]
    def get_work_area(self, index=0): return [Rect(-1920, 24, 1920, 1056), Rect(0, 24, 1920, 1056)][index]
    def get_current_workspace(self): return 2
    def get_all_windows(self): return [0x10, 0x20]
    def get_snapshot_windows(self): return [0x10, 0x20]
    def get_active_window(self): return 0x10
    def get_window_geometry(self, wid): return WindowGeometry(Rect(-1800 if wid == 0x10 else 100, 40, 800, 600), wid == 0x10)
    def get_window_state(self, wid): return WindowState.MAXIMIZED if wid == 0x10 else WindowState.MINIMIZED
    def get_transient_for(self, wid): return None
    def get_window_title(self, wid): return f"Window {wid:x}"
    def get_window_app_name(self, wid): return "Editor" if wid == 0x10 else "Browser"
    def get_monitor_for_window(self, wid): return 0 if wid == 0x10 else 1
    def get_window_workspace(self, wid): return 2 if wid == 0x10 else 3
    def get_window_min_size(self, wid): return (640, 480)
    def window_exists(self, wid): return wid in self.existing
    def move_resize_window(self, wid, rect): self.moves.append((wid, rect)); return True
    def focus_window(self, wid): self.focused.append(wid)
    def set_window_maximized(self, wid, value): self.maximized.append((wid, value))
    def move_window_to_current_workspace(self, wid): self.workspace_moves.append(wid)


def test_x11_snapshot_uses_opaque_handles_and_logical_coordinates():
    controller = X11WindowController(FakeX11Backend(), "x11-session:test")
    snapshot = controller.get_snapshot()
    assert snapshot.session_id == "x11-session:test"
    assert snapshot.active_window == "x11:10"
    assert snapshot.active_workspace == "workspace:2"
    assert snapshot.monitors[0].geometry.x == -1920
    assert snapshot.monitors[0].work_area.y == 24
    assert snapshot.windows[0].maximized
    assert snapshot.windows[1].minimized
    assert snapshot.windows[1].workspace == "workspace:3"


def test_x11_operations_classify_handles_missing_windows_and_workspace_limits():
    backend = FakeX11Backend()
    controller = X11WindowController(backend, "x11-session:test")
    assert controller.move_resize("op:1", "x11:10", LogicalRect(-100, 20, 900, 700)).accepted
    assert backend.moves[0][0] == 0x10
    assert backend.moves[0][1] == Rect(-100, 20, 900, 700)
    assert controller.activate("op:2", "native:10").error_code == "invalid-handle"
    assert controller.activate("op:3", "x11:dead").error_code == "window-gone"
    assert controller.move_to_workspace("op:4", "x11:10", "workspace:3").error_code == "unsupported-workspace"
    assert controller.move_to_workspace("op:5", "x11:10", "workspace:2").accepted
    assert backend.workspace_moves == [0x10]


def test_x11_semantic_event_source_unsubscribes_cleanly():
    source = X11EventSource()
    received = []
    unsubscribe = source.subscribe(received.append)
    event = PlatformEvent("x11-session:test", 1, EventKind.WINDOW_CLOSED, "x11:10")
    source.publish(event)
    unsubscribe()
    source.publish(PlatformEvent("x11-session:test", 2, EventKind.WINDOW_OPENED, "x11:20"))
    assert received == [event]


def run_all_tests():
    tests = [
        test_x11_snapshot_uses_opaque_handles_and_logical_coordinates,
        test_x11_operations_classify_handles_missing_windows_and_workspace_limits,
        test_x11_semantic_event_source_unsubscribes_cleanly,
    ]
    for test in tests:
        test()
        print(f"  ✓ {test.__name__}")


if __name__ == "__main__":
    run_all_tests()
