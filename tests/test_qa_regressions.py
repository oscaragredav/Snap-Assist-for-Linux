"""Regresiones automatizadas para los hallazgos de QA_REPORT.md."""

import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from snapassist.config import LAYOUT_TEMPLATES, Rect, WindowGeometry, WindowInfo, ZoneRef
from snapassist.core.daemon import Daemon
from snapassist.core.state import State
from snapassist.layout.engine import LayoutEngine
from snapassist.main import build_help_message
from snapassist.snap.group_manager import GroupManager
from snapassist.snap.snap_flow import SnapFlow
from snapassist.snap.snapper import SnapEngine
from snapassist.ui.notifier import Notifier
from snapassist.wm.x11_backend import X11Backend


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


class FlowWM:
    def __init__(self, active=1, candidates=None, work_area=None):
        self.active = active
        self.candidates = candidates or [WindowInfo(1, "Principal"), WindowInfo(2, "Editor")]
        self.work_area = work_area or Rect(0, 0, 1920, 1040)
        self.rects = {
            info.window_id: WindowGeometry(Rect(50 * info.window_id, 20, 500, 400))
            for info in self.candidates
        }
        self.moves = []

    def get_active_window(self): return self.active
    def get_all_windows(self): return [info.window_id for info in self.candidates]
    def get_eligible_windows(self): return list(self.candidates)
    def get_window_title(self, wid): return f"W{wid}"
    def get_window_geometry(self, wid): return self.rects[wid]
    def get_window_min_size(self, wid): return (1, 1)
    def get_monitor_for_window(self, wid): return 0
    def get_work_area(self, monitor=0): return self.work_area
    def get_transient_for(self, wid): return None
    def get_transient_children(self, wid): return []
    def set_window_maximized(self, wid, maximized): pass
    def prepare_window_for_snap(self, wid): pass
    def release_window_from_snap(self, wid): pass
    def focus_window(self, wid): pass
    def move_window_to_current_workspace(self, wid): pass
    def window_exists(self, wid): return wid in self.rects

    def move_resize_window(self, wid, rect):
        self.moves.append((wid, rect))
        self.rects[wid] = WindowGeometry(rect)
        return True


def make_flow(wm):
    state = State()
    ui = UIRecorder()
    groups = GroupManager(state, wm)
    flow = SnapFlow(wm, state, SnapEngine(wm, state, LayoutEngine()), ui, groups)
    flow._animation_engine = ImmediateAnimation()
    return flow, state, ui


def no_notifications():
    original = Notifier.send
    Notifier.send = staticmethod(lambda *_args, **_kwargs: None)
    return original


def test_ssd_geometry_conversion_is_reversible():
    client = Rect(2100, 216, 700, 500)
    extents = (0, 0, 36, 0)
    outer = X11Backend._outer_rect_from_client(client, extents)
    assert outer == Rect(2100, 180, 700, 536)
    assert X11Backend._client_rect_from_outer(outer, extents) == Rect(2100, 180, 700, 500)
    assert X11Backend._compensate_csd_rect(
        Rect(0, 0, 960, 1036), (47, 47, 37, 57)
    ) == Rect(-47, -37, 1054, 1130)


def test_all_candidates_are_retained_after_quickkeys_end():
    state = State()
    candidates = [WindowInfo(index, f"W{index}") for index in range(12)]
    result = state.get_sorted_eligible(candidates)
    assert [info.window_id for info in result] == list(range(12))
    assert [info.quickkey for info in result[:10]] == list("qwertyuiop")
    assert [info.quickkey for info in result[10:]] == [None, None]


def test_ineligible_active_window_and_empty_workarea_do_not_start_flow():
    original = no_notifications()
    try:
        flow, _state, ui = make_flow(FlowWM(active=99))
        flow.rects = {}  # active is deliberately absent from candidates
        flow.trigger()
        assert not flow._is_active
        assert not ui.commands

        flow, _state, ui = make_flow(FlowWM(work_area=Rect(0, 0, 0, 0)))
        flow.trigger()
        assert not flow._is_active
        assert not ui.commands
    finally:
        Notifier.send = original


def test_partial_cancel_uses_independent_zone_ref():
    flow, state, _ui = make_flow(FlowWM(candidates=[WindowInfo(1, "A"), WindowInfo(2, "B")]))
    flow.trigger()
    flow.confirm_selection(0, 0, flow._flow_token)
    flow.cancel_snap_assist("escape", flow._flow_token)
    ref = state.get_zone_ref(1)
    assert ref is not None and ref.group_id is None
    assert not state.active_groups


def test_ui_error_cancels_or_rolls_back_the_active_flow():
    flow, state, ui = make_flow(FlowWM())
    flow.trigger()
    token = flow._flow_token
    flow.on_ui_command_failed("show_menu", "fallo inyectado", token)
    assert not flow._is_active
    assert state.snapped_windows == {}

    flow, state, ui = make_flow(FlowWM())
    flow.trigger()
    token = flow._flow_token
    flow.confirm_selection(0, 0, token)
    assert flow._is_active
    flow.on_ui_command_failed("show_snap_assist", "fallo inyectado", token)
    assert not flow._is_active
    assert state.snapped_windows == {}
    assert state.saved_geometries == {}


def test_minimum_size_is_clamped_to_work_area():
    bounds = Rect(0, 0, 1920, 1036)
    result = LayoutEngine.center_minimum_size((850, 700), Rect(960, 0, 960, 518), bounds)
    assert result == Rect(960, 0, 960, 700)


def test_content_drag_needs_real_window_geometry_change():
    state = State()
    state.mark_snapped(42, ZoneRef(None, 0))
    detached = []

    class Flow:
        def on_window_dragged(self, wid): detached.append(("drag", wid))
        def on_window_resized(self, wid): detached.append(("resize", wid))

    class WM:
        def __init__(self): self.rect = Rect(100, 100, 800, 600)
        def get_active_window(self): return 42
        def get_window_geometry(self, wid): return WindowGeometry(self.rect)

    daemon = Daemon.__new__(Daemon)
    daemon._state = state
    daemon._snap_flow = Flow()
    daemon._wm = WM()
    daemon._drag_starts = {}
    daemon._drag_distances = {}
    daemon._gesture_modes = {}
    daemon._gesture_geometries = {}
    daemon._handle_pointer_event({"event": "pointer_press", "x": 500, "y": 150})
    daemon._handle_pointer_event({"event": "pointer_move", "x": 530, "y": 150})
    assert detached == []
    daemon._wm.rect = Rect(130, 100, 800, 600)
    daemon._handle_pointer_event({"event": "pointer_move", "x": 540, "y": 150})
    assert detached == [("drag", 42)]


def test_help_reports_daemon_state():
    class WM:
        def get_all_windows(self): return [1, 2]
        def get_window_title(self, wid): return f"W{wid}"

    state = State()
    manager = GroupManager(state, WM())
    assert "Daemon: activo" in build_help_message(WM(), state, manager, None)


def test_struts_are_applied_only_to_the_affected_monitor():
    class Prop:
        def __init__(self, values): self.value = values

    class Dock:
        def get_full_property(self, atom, _type):
            return Prop([0, 0, 0, 40, 0, 1079, 0, 1079, 0, 3839, 1920, 3839])

    class Screen:
        width_in_pixels = 3840
        height_in_pixels = 1080

    class Display:
        def screen(self): return Screen()
        def create_resource_object(self, _kind, _wid): return Dock()

    backend = X11Backend.__new__(X11Backend)
    backend._display = Display()
    backend._atoms = {"_NET_WM_STRUT_PARTIAL": 1, "_NET_WM_STRUT": 2}
    backend._get_raw_client_windows = lambda: [1]
    assert backend._work_area_from_struts(Rect(0, 0, 1920, 1080)) == Rect(0, 0, 1920, 1080)
    assert backend._work_area_from_struts(Rect(1920, 0, 1920, 1080)) == Rect(1920, 0, 1920, 1040)


def run_all_tests():
    tests = [
        test_ssd_geometry_conversion_is_reversible,
        test_all_candidates_are_retained_after_quickkeys_end,
        test_ineligible_active_window_and_empty_workarea_do_not_start_flow,
        test_partial_cancel_uses_independent_zone_ref,
        test_ui_error_cancels_or_rolls_back_the_active_flow,
        test_minimum_size_is_clamped_to_work_area,
        test_content_drag_needs_real_window_geometry_change,
        test_help_reports_daemon_state,
        test_struts_are_applied_only_to_the_affected_monitor,
    ]
    for test in tests:
        test()
        print(f"  ✓ {test.__name__}")


if __name__ == "__main__":
    run_all_tests()
