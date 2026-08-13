"""Pruebas unitarias de la Fase 7: flujo completo de Snap Assist."""

import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from snapassist.config import LAYOUT_TEMPLATES, Rect, WindowGeometry, WindowInfo
from snapassist.core.state import State
from snapassist.layout.engine import LayoutEngine
from snapassist.snap.snap_flow import SnapFlow
from snapassist.snap.snapper import SnapEngine
from snapassist.ui.layout_menu import LayoutMenu


class ImmediateAnimation:
    def animate_async(self, start_rect, end_rect, update_callback, on_complete):
        update_callback(end_rect)
        on_complete()


class MockUI:
    def __init__(self):
        self.commands = []

    def send_command(self, command):
        self.commands.append(command)


class MockBackend:
    def __init__(self):
        self.active = 1
        self.candidates = [
            WindowInfo(1, "Principal"),
            WindowInfo(2, "Terminal", on_other_workspace=True),
            WindowInfo(3, "Editor"),
        ]
        self.moves = []
        self.focuses = []
        self.workspace_moves = []
        self.maximized = []

    def get_active_window(self):
        return self.active

    def get_all_windows(self):
        return [info.window_id for info in self.candidates]

    def get_eligible_windows(self):
        return list(self.candidates)

    def get_window_title(self, wid):
        return next(info.title for info in self.candidates if info.window_id == wid)

    def get_window_app_name(self, wid):
        return "Aplicación principal" if wid == 1 else ""

    def get_window_geometry(self, wid):
        return WindowGeometry(Rect(2000 if wid == 2 else 100, 100, 800, 600))

    def get_monitor_for_window(self, wid):
        return 1 if wid == 2 else 0

    def get_work_area(self, monitor_index=0):
        return Rect(1920, 0, 1920, 1080) if monitor_index == 1 else Rect(0, 0, 1920, 1040)

    def move_resize_window(self, wid, rect):
        self.moves.append((wid, rect))

    def focus_window(self, wid):
        self.focuses.append(wid)

    def set_window_maximized(self, wid, maximized):
        self.maximized.append((wid, maximized))

    def move_window_to_current_workspace(self, wid):
        self.workspace_moves.append(wid)


def make_flow():
    backend = MockBackend()
    state = State()
    ui = MockUI()
    snapper = SnapEngine(backend, state, LayoutEngine(gap_px=0))
    flow = SnapFlow(backend, state, snapper, ui)
    flow._animation_engine = ImmediateAnimation()
    return flow, backend, state, ui


def test_eligible_list_is_frozen_after_first_snap():
    flow, backend, _state, ui = make_flow()
    flow.trigger()
    flow.confirm_selection(0, 0, flow._flow_token)

    command = ui.commands[-1]
    assert command["action"] == "show_snap_assist"
    assert [info.window_id for info in command["eligible_windows"]] == [2, 3]

    backend.candidates.append(WindowInfo(4, "Nueva"))
    assert [info.window_id for info in flow._eligible_windows] == [2, 3]
    assert [info.window_id for info in command["eligible_windows"]] == [2, 3]


def test_layout_menu_identifies_the_active_application():
    flow, _backend, _state, ui = make_flow()
    flow.trigger()
    assert ui.commands[-1]["active_window_name"] == (
        "Aplicación principal - Principal"
    )


def test_window_display_name_includes_application_and_title():
    assert WindowInfo(2, "Wikipedia", app_name="Mozilla Firefox").display_name == (
        "Mozilla Firefox - Wikipedia"
    )
    assert WindowInfo(3, "Descargas", app_name="Archivos").display_name == (
        "Archivos - Descargas"
    )
    assert WindowInfo(4, "Terminal", app_name="Terminal").display_name == "Terminal"

def test_empty_zone_assignment_for_every_template():
    for template in LAYOUT_TEMPLATES:
        for occupied in range(len(template.zones)):
            empty = SnapFlow.get_empty_zone_indices(template, [occupied])
            assert occupied not in empty
            assert len(empty) == len(template.zones) - 1
            assert empty == sorted(empty)


def test_selection_moves_workspace_and_uses_origin_monitor_zones():
    flow, backend, state, ui = make_flow()
    flow.trigger()
    flow.confirm_selection(0, 0, flow._flow_token)
    flow.confirm_assist_selection(2, flow._flow_token)

    assert backend.workspace_moves == [2]
    selected_move = [rect for wid, rect in backend.moves if wid == 2][-1]
    assert selected_move == Rect(960, 0, 960, 1040)
    assert state.is_snapped(1)
    assert state.is_snapped(2)
    assert state.get_zone_ref(1).group_id == state.get_zone_ref(2).group_id
    assert ui.commands[-1]["action"] == "hide_snap_assist"


def test_cancel_preserves_windows_already_snapped():
    flow, _backend, state, _ui = make_flow()
    flow.trigger()
    flow.confirm_selection(4, 0, flow._flow_token)

    assert state.is_snapped(1)
    flow.cancel_snap_assist("escape", flow._flow_token)
    assert state.is_snapped(1)
    assert not flow._is_active


def test_layout_confirmation_cannot_emit_followup_cancel():
    events = []
    menu = LayoutMenu.__new__(LayoutMenu)
    menu._visible = True
    menu._active_layout_idx = 2
    menu._active_zone_idx = 1
    menu._stage = "zone"
    menu.on_selection = lambda layout, zone: events.append(("selected", layout, zone))
    menu.on_cancel = lambda: events.append(("cancelled",))

    menu._confirm()
    menu._cancel()  # Simula el FocusOut que llega después de ocultar el menú.

    assert events == [("selected", 2, 1)]


def test_layout_and_zone_can_be_selected_with_two_number_keys():
    events = []
    menu = LayoutMenu.__new__(LayoutMenu)
    menu._visible = True
    menu._templates = LAYOUT_TEMPLATES
    menu._disabled_layouts = [False] * len(LAYOUT_TEMPLATES)
    menu._active_layout_idx = 0
    menu._active_zone_idx = 0
    menu._stage = "layout"
    menu._update_hover = lambda: None
    menu.on_selection = lambda layout, zone: events.append((layout, zone))

    # Grupo 6 (tres columnas) y posición 3 (derecha).
    menu._handle_key(SimpleNamespace(char="6"))
    assert menu._stage == "zone"
    assert menu._active_layout_idx == 5
    menu._handle_key(SimpleNamespace(char="3"))

    assert events == [(5, 2)]
    assert not menu._visible


def test_zone_names_are_spatially_descriptive():
    three_columns = LAYOUT_TEMPLATES[5]
    assert [
        LayoutMenu._zone_name(zone) for zone in three_columns.zones
    ] == ["Izquierda", "Centro", "Derecha"]


def run_all_tests():
    tests = [
        test_eligible_list_is_frozen_after_first_snap,
        test_layout_menu_identifies_the_active_application,
        test_window_display_name_includes_application_and_title,
        test_empty_zone_assignment_for_every_template,
        test_selection_moves_workspace_and_uses_origin_monitor_zones,
        test_cancel_preserves_windows_already_snapped,
        test_layout_confirmation_cannot_emit_followup_cancel,
        test_layout_and_zone_can_be_selected_with_two_number_keys,
        test_zone_names_are_spatially_descriptive,
    ]
    for test in tests:
        test()
        print(f"  ✓ {test.__name__}")


if __name__ == "__main__":
    run_all_tests()
