"""Pruebas de Fase 9: tolerancia a fallos, XRandR y ventanas modales."""

import os
import queue
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Xlib.error import BadWindow

from snapassist.config import LAYOUT_TEMPLATES, Rect, WindowGeometry, WindowInfo
from snapassist.core.daemon import Daemon
from snapassist.core.hotkeys import HotkeyManager
from snapassist.core.state import State
from snapassist.layout.engine import LayoutEngine
from snapassist.snap.group_manager import GroupManager
from snapassist.snap.snap_flow import SnapFlow
from snapassist.snap.snapper import SnapEngine
from snapassist.wm.x11_backend import X11Backend
from snapassist.snap.animation import AnimationEngine
from snapassist.ui.ui_manager import UIManager


class UIRecorder:
    def __init__(self):
        self.commands = []

    def send_command(self, command):
        self.commands.append(command)


class ImmediateAnimation:
    def animate_async(self, start_rect, end_rect, update_callback,
                      on_complete=None, on_error=None):
        try:
            update_callback(end_rect)
        except Exception as error:
            if on_error:
                on_error(error)
        else:
            if on_complete:
                on_complete()


class TransactionWM:
    def __init__(self):
        self.rects = {
            1: Rect(10, 10, 700, 500),
            2: Rect(30, 30, 600, 400),
            3: Rect(50, 50, 500, 300),
        }
        self.original = dict(self.rects)
        self.fail_wid = None

    def get_active_window(self): return 1
    def get_all_windows(self): return [1, 2, 3]
    def get_eligible_windows(self):
        return [WindowInfo(wid, str(wid)) for wid in self.rects]
    def get_window_title(self, wid): return str(wid)
    def get_window_geometry(self, wid): return WindowGeometry(self.rects[wid])
    def get_window_min_size(self, wid): return (1, 1)
    def get_monitor_for_window(self, wid): return 0
    def get_work_area(self, monitor=0): return Rect(0, 0, 1200, 900)
    def get_transient_for(self, wid): return None
    def get_transient_children(self, wid): return []
    def set_window_maximized(self, wid, maximized): pass
    def prepare_window_for_snap(self, wid): pass
    def release_window_from_snap(self, wid): pass
    def focus_window(self, wid): pass
    def move_window_to_current_workspace(self, wid): pass
    def window_exists(self, wid): return wid in self.rects

    def move_resize_window(self, wid, rect):
        if wid == self.fail_wid and rect != self.original[wid]:
            return False
        self.rects[wid] = rect
        return True


def test_third_window_failure_rolls_back_geometry_and_state():
    wm = TransactionWM()
    state = State()
    engine = SnapEngine(wm, state, LayoutEngine(gap_px=0))
    flow = SnapFlow(wm, state, engine, UIRecorder(), GroupManager(state, wm))
    flow._animation_engine = ImmediateAnimation()

    flow.trigger()
    flow.confirm_selection(4, 0)
    flow.confirm_assist_selection(2)
    wm.fail_wid = 3
    flow.confirm_assist_selection(3)

    assert wm.rects == wm.original
    assert state.saved_geometries == {}
    assert state.snapped_windows == {}
    assert state.active_groups == {}
    assert not flow._is_active


def test_modal_is_centered_over_snapped_parent():
    wm = TransactionWM()
    wm.rects = {1: Rect(0, 0, 600, 500), 9: Rect(20, 20, 300, 200)}
    wm.get_transient_children = lambda wid: [9] if wid == 1 else []
    state = State()
    engine = SnapEngine(wm, state, LayoutEngine(gap_px=0))

    assert engine.snap_window_to_rect(
        1, LAYOUT_TEMPLATES[0], 0, Rect(0, 0, 1000, 800), "modal-test"
    )
    assert wm.rects[1] == Rect(0, 0, 1000, 800)
    assert wm.rects[9] == Rect(350, 300, 300, 200)


def test_badwindow_returns_false_from_x11_backend():
    class VanishedDisplay:
        def create_resource_object(self, _kind, _wid):
            raise BadWindow.__new__(BadWindow)

    backend = X11Backend.__new__(X11Backend)
    backend._display = VanishedDisplay()
    backend._pending_own_resizes = set()
    backend._own_resize_geometries = {}
    assert backend.move_resize_window(0xDEAD, Rect(0, 0, 100, 100)) is False


def test_monitor_disconnect_suspends_and_reconnect_discards_group():
    wm = TransactionWM()
    state = State()
    manager = GroupManager(state, wm)
    group = manager.create_group({0: 1, 1: 2}, LAYOUT_TEMPLATES[0], 1)
    monitors = [Rect(0, 0, 1200, 900), Rect(1200, 0, 1200, 900)]

    manager.on_monitors_changed(monitors, monitors[:1])
    assert group.group_id not in state.active_groups
    assert state.suspended_groups[1][0].group_id == group.group_id
    assert not state.is_snapped(1) and not state.is_snapped(2)

    manager.on_monitors_changed(monitors[:1], monitors)
    assert state.suspended_groups == {}


def test_randr_dispatch_updates_topology_and_event_errors_are_isolated():
    class WM:
        def get_monitors(self): return [Rect(0, 0, 800, 600)]
    class Groups:
        def __init__(self): self.calls = []
        def on_monitors_changed(self, old, new): self.calls.append((old, new))
    class Flow:
        def __init__(self): self.calls = 0
        def on_monitors_changed(self): self.calls += 1

    daemon = Daemon.__new__(Daemon)
    daemon._wm = WM()
    daemon._monitors = [Rect(0, 0, 1600, 900), Rect(1600, 0, 1600, 900)]
    daemon._group_manager = Groups()
    daemon._snap_flow = Flow()
    event = type("Event", (), {"_snapassist_randr_screen_change": True})()
    daemon._dispatch_event(event)
    assert len(daemon._group_manager.calls) == 1
    assert daemon._snap_flow.calls == 1

    daemon._dispatch_event = lambda _event: (_ for _ in ()).throw(RuntimeError("boom"))
    assert daemon._safe_dispatch_event(object()) is False
    daemon._dispatch_event = lambda _event: None
    assert daemon._safe_dispatch_event(object()) is True


def test_stale_cancel_cannot_cancel_a_new_flow():
    wm = TransactionWM()
    state = State()
    flow = SnapFlow(
        wm,
        state,
        SnapEngine(wm, state, LayoutEngine(gap_px=0)),
        UIRecorder(),
    )
    flow.trigger()
    old_flow_id = flow._flow_token
    flow.cancel(old_flow_id)
    flow.trigger()
    new_flow_id = flow._flow_token

    flow.cancel(old_flow_id)

    assert new_flow_id != old_flow_id
    assert flow._is_active
    assert flow._flow_token == new_flow_id


def test_hotkey_callback_is_serialized_through_daemon_queue():
    callback_queue = queue.Queue()
    calls = []
    hotkeys = HotkeyManager(callback_queue=callback_queue)
    assert hotkeys.register("super+z", lambda: calls.append(threading.get_ident()))
    wrapped = next(iter(hotkeys._bindings.values()))

    wrapped()
    assert calls == []
    callback_queue.get_nowait()()
    assert calls == [threading.get_ident()]


def test_animation_updates_run_on_calling_thread():
    caller = threading.get_ident()
    update_threads = []
    AnimationEngine(fps=1, duration_ms=0).animate_async(
        Rect(0, 0, 10, 10),
        Rect(10, 10, 20, 20),
        lambda _rect: update_threads.append(threading.get_ident()),
    )
    assert update_threads == [caller]


def test_ui_quit_is_processed_before_polling_stops():
    class Root:
        def __init__(self): self.quit_calls = 0
        def quit(self): self.quit_calls += 1

    manager = UIManager(queue.Queue())
    manager._running = True
    manager._root = Root()
    manager.stop()
    assert manager._running
    manager._process_command(manager._cmd_queue.get_nowait())
    assert not manager._running
    assert manager._root.quit_calls == 1


def run_all_tests():
    tests = [
        test_third_window_failure_rolls_back_geometry_and_state,
        test_modal_is_centered_over_snapped_parent,
        test_badwindow_returns_false_from_x11_backend,
        test_monitor_disconnect_suspends_and_reconnect_discards_group,
        test_randr_dispatch_updates_topology_and_event_errors_are_isolated,
        test_stale_cancel_cannot_cancel_a_new_flow,
        test_hotkey_callback_is_serialized_through_daemon_queue,
        test_animation_updates_run_on_calling_thread,
        test_ui_quit_is_processed_before_polling_stops,
    ]
    for test in tests:
        test()
        print(f"  ✓ {test.__name__}")


if __name__ == "__main__":
    run_all_tests()
