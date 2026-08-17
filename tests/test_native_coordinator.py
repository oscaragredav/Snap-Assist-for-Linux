"""Flujo neutral layout → zona → sugerencias para GNOME 2.x."""

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from snapassist.config import LAYOUT_TEMPLATES, LayoutTemplate, ZoneTemplate
from snapassist.core.native_coordinator import NativeSnapCoordinator
from snapassist.runtime import (
    EventKind,
    LogicalRect,
    MonitorSnapshot,
    OperationResult,
    PlatformEvent,
    PlatformRuntime,
    UiAction,
    WindowSnapshot,
)
from snapassist.runtime.contracts import DesktopSnapshot


def make_snapshot(active="window:1", include_second=True):
    windows = [
        WindowSnapshot(
            "window:1",
            "Documento",
            "org.example.Editor",
            "Editor",
            LogicalRect(-1500, 100, 800, 600),
            "monitor:left",
            "workspace:0",
        )
    ]
    if include_second:
        windows.append(
            WindowSnapshot(
                "window:2",
                "Web",
                "org.mozilla.firefox",
                "Firefox",
                LogicalRect(100, 100, 900, 700),
                "monitor:right",
                "workspace:0",
            )
        )
    return DesktopSnapshot(
        "session:1",
        1,
        active,
        "workspace:0",
        tuple(windows),
        (
            MonitorSnapshot(
                "monitor:left",
                LogicalRect(-1920, 0, 1920, 1080),
                LogicalRect(-1920, 24, 1920, 1056),
            ),
            MonitorSnapshot(
                "monitor:right",
                LogicalRect(0, 0, 1920, 1080),
                LogicalRect(0, 24, 1920, 1056),
            ),
        ),
    )


class FakeWindows:
    def __init__(self, snapshot):
        self.snapshot = snapshot
        self.moves = []
        self.fail_window = None
        self.fail_error = "window-gone"
        self.fail_restored = False
        self.focused = []
        self.maximized = []

    @property
    def capabilities(self):
        return frozenset()

    def get_snapshot(self):
        return self.snapshot

    def move_resize(self, operation_id, window, rect):
        self.moves.append((operation_id, window, rect))
        if window == self.fail_window:
            return OperationResult(
                operation_id,
                False,
                self.fail_error,
                "rechazada",
                status=self.fail_error,
                restored=self.fail_restored,
            )
        return OperationResult(operation_id, True)

    def activate(self, operation_id, window):
        self.focused.append((operation_id, window))
        return OperationResult(operation_id, True)

    def set_maximized(self, operation_id, window, maximized):
        self.maximized.append((operation_id, window, maximized))
        return OperationResult(operation_id, True)


class FakePresentation:
    def __init__(self):
        self.commands = []
        self.fail_command = None

    def show_layouts(self, flow_id, layouts, active_window):
        if self.fail_command == "layouts":
            raise RuntimeError("fallo UI layouts")
        self.commands.append(("layouts", flow_id, layouts, active_window))

    def show_suggestions(self, flow_id, zone, candidates):
        if self.fail_command == "suggestions":
            raise RuntimeError("fallo UI suggestions")
        self.commands.append(("suggestions", flow_id, zone, list(candidates)))

    def hide(self, flow_id):
        self.commands.append(("hide", flow_id))

    def notify(self, message):
        self.commands.append(("notify", message))


class FakeEvents:
    def __init__(self):
        self.callback = None

    def subscribe(self, callback):
        self.callback = callback
        return lambda: setattr(self, "callback", None)


class FakeShortcuts:
    def register(self, action, shortcut, callback):
        return True

    def unregister_all(self):
        pass


def make_coordinator(snapshot=None):
    windows = FakeWindows(snapshot or make_snapshot())
    presentation = FakePresentation()
    events = FakeEvents()
    runtime = PlatformRuntime(windows, presentation, FakeShortcuts(), events)
    coordinator = NativeSnapCoordinator(runtime, LAYOUT_TEMPLATES)
    return coordinator, windows, presentation, events


def action(coordinator, name, value=None, flow_id=None, sequence=1):
    return UiAction(
        "session:1",
        sequence,
        coordinator.flow_id if flow_id is None else flow_id,
        name,
        value,
    )


def test_complete_two_zone_flow_uses_negative_monitor_work_area():
    coordinator, windows, presentation, _events = make_coordinator()
    assert coordinator.start()
    assert presentation.commands[-1][0] == "layouts"
    coordinator.handle_ui_action(action(coordinator, "layout-selected", 0))
    assert presentation.commands[-1][0] == "layouts"
    assert presentation.commands[-1][2][0].name.startswith("Zona 1")

    coordinator.handle_ui_action(action(coordinator, "layout-selected", 0, sequence=2))
    first_move = windows.moves[-1]
    assert first_move[1] == "window:1"
    assert first_move[2] == LogicalRect(-1920, 24, 960, 1056)
    assert presentation.commands[-1][0] == "suggestions"
    assert presentation.commands[-1][3][0].handle == "window:2"

    coordinator.handle_ui_action(
        action(coordinator, "suggestion-selected", "window:2", sequence=3)
    )
    assert windows.moves[-1][1] == "window:2"
    assert windows.moves[-1][2] == LogicalRect(-960, 24, 960, 1056)
    assert presentation.commands[-1][0] == "hide"
    assert not coordinator.active
    assert coordinator.state.group_for_window("window:1") is not None

    windows.snapshot = make_snapshot(active="window:2")
    assert coordinator.focus_active_group()
    # El grupo completo se trae al frente inmediatamente; el atajo puede
    # repetir la acción después.
    assert [window for _operation, window in windows.focused] == [
        "window:1",
        "window:2",
        "window:1",
        "window:2",
        "window:1",
        "window:1", "window:2", "window:1",
    ]

    assert coordinator.restore_window("window:1")
    assert windows.moves[-1][2] == LogicalRect(-1500, 100, 800, 600)
    assert not coordinator.state.groups


def test_stale_flow_cancel_and_unknown_actions_do_not_mutate():
    coordinator, windows, presentation, _events = make_coordinator()
    coordinator.start()
    current = coordinator.flow_id
    coordinator.handle_ui_action(action(coordinator, "layout-selected", 0, current - 1))
    coordinator.handle_ui_action(action(coordinator, "unknown", 0))
    assert not windows.moves
    assert coordinator.active
    coordinator.handle_ui_action(action(coordinator, "cancel"))
    assert not coordinator.active
    assert presentation.commands[-1] == ("hide", current)


def test_layouts_can_reload_without_restarting_runtime():
    coordinator, _windows, presentation, _events = make_coordinator()
    replacement = [LAYOUT_TEMPLATES[-1]]
    coordinator.replace_layouts(replacement)
    assert coordinator.start()
    assert presentation.commands[-1][2] == replacement


def test_missing_active_window_and_invalid_work_area_are_safe():
    coordinator, _windows, presentation, _events = make_coordinator(
        make_snapshot(active=None)
    )
    assert not coordinator.start()
    assert presentation.commands[-1][0] == "notify"

    snapshot = make_snapshot()
    bad_monitor = MonitorSnapshot(
        "monitor:left",
        snapshot.monitors[0].geometry,
        LogicalRect(0, 0, 0, 0),
    )
    snapshot = DesktopSnapshot(
        snapshot.session_id,
        snapshot.sequence,
        snapshot.active_window,
        snapshot.active_workspace,
        snapshot.windows,
        (bad_monitor, snapshot.monitors[1]),
    )
    coordinator, _windows, presentation, _events = make_coordinator(snapshot)
    assert not coordinator.start()
    assert "área" in presentation.commands[-1][1]


def test_window_failure_is_reported_and_monitor_change_cancels():
    coordinator, windows, presentation, events = make_coordinator()
    coordinator.start()
    coordinator.handle_ui_action(action(coordinator, "layout-selected", 0))
    windows.fail_window = "window:1"
    coordinator.handle_ui_action(action(coordinator, "layout-selected", 0, sequence=2))
    assert coordinator.active
    assert any(command[0] == "notify" for command in presentation.commands)
    events.callback(
        PlatformEvent("session:1", 5, EventKind.MONITORS_CHANGED)
    )
    assert not coordinator.active
    assert presentation.commands[-1][0] == "hide"


def test_drag_and_resize_detach_without_moving_user_window():
    coordinator, windows, _presentation, events = make_coordinator()
    coordinator.start()
    coordinator.handle_ui_action(action(coordinator, "layout-selected", 0))
    coordinator.handle_ui_action(action(coordinator, "layout-selected", 0, sequence=2))
    coordinator.handle_ui_action(
        action(coordinator, "suggestion-selected", "window:2", sequence=3)
    )
    move_count = len(windows.moves)
    events.callback(
        PlatformEvent(
            "session:1",
            10,
            EventKind.WINDOW_DRAGGED,
            window="window:1",
        )
    )
    assert len(windows.moves) == move_count
    assert "window:1" not in coordinator.state.snapped_windows

    coordinator.start()
    coordinator.handle_ui_action(action(coordinator, "layout-selected", 0))
    coordinator.handle_ui_action(action(coordinator, "layout-selected", 0, sequence=2))
    coordinator.handle_ui_action(
        action(coordinator, "suggestion-selected", "window:2", sequence=3)
    )
    move_count = len(windows.moves)
    events.callback(
        PlatformEvent(
            "session:1",
            11,
            EventKind.WINDOW_RESIZED,
            window="window:1",
        )
    )
    assert len(windows.moves) == move_count
    assert "window:1" not in coordinator.state.snapped_windows


def test_minimum_hint_never_preempts_real_move_confirmation():
    snapshot = make_snapshot(include_second=False)
    large = WindowSnapshot(
        "window:1",
        "Grande",
        "org.example.Large",
        "Grande",
        snapshot.windows[0].geometry,
        "monitor:left",
        "workspace:0",
        minimum_size=(1400, 1200),
    )
    snapshot = DesktopSnapshot(
        snapshot.session_id,
        snapshot.sequence,
        snapshot.active_window,
        snapshot.active_workspace,
        (large,),
        snapshot.monitors,
    )
    coordinator, windows, presentation, _events = make_coordinator(snapshot)
    coordinator.start()
    coordinator.handle_ui_action(action(coordinator, "layout-selected", 0))
    coordinator.handle_ui_action(action(coordinator, "layout-selected", 0, sequence=2))
    assert windows.moves
    assert windows.moves[0][2] == LogicalRect(-1920, 24, 960, 1056)
    assert not coordinator.active
    assert not any(command[0] == "notify" for command in presentation.commands)


def test_cancel_result_reports_incompatible_zone_as_empty():
    snapshot = make_snapshot()
    large = WindowSnapshot(
        "window:1", "Grande", "org.example.Large", "Grande",
        snapshot.windows[0].geometry, "monitor:left", "workspace:0",
        minimum_size=(1400, 1200),
    )
    snapshot = DesktopSnapshot(
        snapshot.session_id, snapshot.sequence, snapshot.active_window,
        snapshot.active_workspace, (large, snapshot.windows[1]), snapshot.monitors,
    )
    coordinator, windows, _presentation, _events = make_coordinator(snapshot)
    windows.fail_window = "window:1"
    windows.fail_error = "constraint-rejected"
    coordinator.start()
    coordinator.handle_ui_action(action(coordinator, "layout-selected", 0))
    coordinator.handle_ui_action(action(coordinator, "layout-selected", 0, sequence=2))

    result = coordinator.cancel()

    assert result.empty_zones == (0,)
    assert not result.snapped
    assert not result.completed


def test_suggestions_use_runtime_eligibility_not_unverified_minimum_hints():
    snapshot = make_snapshot()
    other_workspace = WindowSnapshot(
        "window:other", "Otro", "org.example.Other", "Otro",
        LogicalRect(10, 10, 600, 500), "monitor:right", "workspace:1",
    )
    too_large = WindowSnapshot(
        "window:large", "Grande", "org.example.Large", "Grande",
        LogicalRect(10, 10, 600, 500), "monitor:right", "workspace:0",
        minimum_size=(1200, 500),
    )
    snapshot = DesktopSnapshot(
        snapshot.session_id, snapshot.sequence, snapshot.active_window,
        snapshot.active_workspace, (*snapshot.windows, other_workspace, too_large),
        snapshot.monitors,
    )
    coordinator, _windows, presentation, _events = make_coordinator(snapshot)
    coordinator.start()
    coordinator.handle_ui_action(action(coordinator, "layout-selected", 0))
    coordinator.handle_ui_action(action(coordinator, "layout-selected", 0, sequence=2))
    assert [item.handle for item in presentation.commands[-1][3]] == [
        "window:2",
        "window:large",
    ]


def test_unverified_minimum_hint_does_not_skip_narrow_zone():
    snapshot = make_snapshot()
    candidate = WindowSnapshot(
        "window:2", "Ancha", "org.example.Wide", "Ancha",
        snapshot.windows[1].geometry, "monitor:right", "workspace:0",
        minimum_size=(700, 400),
    )
    snapshot = DesktopSnapshot(
        snapshot.session_id, snapshot.sequence, snapshot.active_window,
        snapshot.active_workspace, (snapshot.windows[0], candidate), snapshot.monitors,
    )
    windows = FakeWindows(snapshot)
    presentation = FakePresentation()
    events = FakeEvents()
    runtime = PlatformRuntime(windows, presentation, FakeShortcuts(), events)
    layout = LayoutTemplate("activa : estrecha : ancha", [
        ZoneTemplate(0.0, 0.0, 0.25, 1.0),
        ZoneTemplate(0.25, 0.0, 0.25, 1.0),
        ZoneTemplate(0.5, 0.0, 0.5, 1.0),
    ])
    coordinator = NativeSnapCoordinator(runtime, [layout])
    coordinator.start()
    coordinator.handle_ui_action(action(coordinator, "layout-selected", 0))
    coordinator.handle_ui_action(action(coordinator, "layout-selected", 0, sequence=2))

    assert coordinator.active
    assert presentation.commands[-1][0] == "suggestions"
    assert presentation.commands[-1][2] == LogicalRect(-1440, 24, 480, 1056)
    assert [item.handle for item in presentation.commands[-1][3]] == ["window:2"]
    result = coordinator.cancel()
    assert result.empty_zones == ()


def test_ineligible_active_window_does_not_start_native_flow():
    snapshot = make_snapshot(include_second=False)
    blocked = WindowSnapshot(
        "window:1", "Pantalla completa", "org.example.Player", "Player",
        snapshot.windows[0].geometry, "monitor:left", "workspace:0",
        eligible=False, fullscreen=True,
    )
    snapshot = DesktopSnapshot(
        snapshot.session_id, snapshot.sequence, blocked.handle,
        snapshot.active_workspace, (blocked,), snapshot.monitors,
    )
    coordinator, windows, presentation, _events = make_coordinator(snapshot)

    assert not coordinator.start()
    assert not windows.moves
    assert presentation.commands == [
        ("notify", "La ventana activa no admite el redimensionamiento requerido.")
    ]


def test_maximized_window_is_unmaximized_and_restored():
    snapshot = make_snapshot(include_second=False)
    maximized = WindowSnapshot(
        "window:1",
        "Max",
        "org.example.Max",
        "Max",
        snapshot.windows[0].geometry,
        "monitor:left",
        "workspace:0",
        maximized=True,
    )
    snapshot = DesktopSnapshot(
        snapshot.session_id,
        snapshot.sequence,
        snapshot.active_window,
        snapshot.active_workspace,
        (maximized,),
        snapshot.monitors,
    )
    coordinator, windows, _presentation, _events = make_coordinator(snapshot)
    coordinator.start()
    coordinator.handle_ui_action(action(coordinator, "layout-selected", 0))
    coordinator.handle_ui_action(action(coordinator, "layout-selected", 0, sequence=2))
    assert windows.maximized[-1][1:] == ("window:1", False)
    assert coordinator.restore_window("window:1")
    assert windows.maximized[-1][1:] == ("window:1", True)


def test_second_window_constraint_keeps_first_and_leaves_zone_empty():
    coordinator, windows, presentation, _events = make_coordinator()
    assert coordinator.start()
    coordinator.handle_ui_action(action(coordinator, "layout-selected", 0))
    coordinator.handle_ui_action(action(coordinator, "layout-selected", 0, sequence=2))
    windows.fail_window = "window:2"
    windows.fail_error = "constraint-rejected"
    coordinator.handle_ui_action(
        action(coordinator, "suggestion-selected", "window:2", sequence=3)
    )
    assert not coordinator.active
    assert coordinator.state.snapped_windows["window:1"].group_id is None
    assert "window:2" not in coordinator.state.snapped_windows
    assert not coordinator.state.groups
    assert coordinator.state.saved_geometries["window:1"] == LogicalRect(
        -1500, 100, 800, 600
    )
    assert any(command[0] == "notify" for command in presentation.commands)


def test_extension_owned_restore_is_not_repeated_by_coordinator():
    coordinator, windows, _presentation, _events = make_coordinator()
    coordinator.start()
    coordinator.handle_ui_action(action(coordinator, "layout-selected", 0))
    coordinator.handle_ui_action(action(coordinator, "layout-selected", 0, sequence=2))
    windows.fail_window = "window:2"
    windows.fail_error = "constraint-rejected"
    windows.fail_restored = True
    before = len(windows.moves)
    coordinator.handle_ui_action(
        action(coordinator, "suggestion-selected", "window:2", sequence=3)
    )

    assert len(windows.moves) == before + 1
    assert windows.moves[-1][1] == "window:2"


def test_partial_flow_groups_two_confirmed_windows_and_excludes_rejected_one():
    snapshot = make_snapshot()
    third = WindowSnapshot(
        "window:3", "Terminal", "org.example.Terminal", "Terminal",
        LogicalRect(300, 120, 700, 600), "monitor:right", "workspace:0",
    )
    snapshot = DesktopSnapshot(
        snapshot.session_id, snapshot.sequence, snapshot.active_window,
        snapshot.active_workspace, (*snapshot.windows, third), snapshot.monitors,
    )
    coordinator, windows, presentation, _events = make_coordinator(snapshot)
    coordinator.start()
    coordinator.handle_ui_action(action(coordinator, "layout-selected", 4))
    coordinator.handle_ui_action(action(coordinator, "layout-selected", 0, sequence=2))
    coordinator.handle_ui_action(
        action(coordinator, "suggestion-selected", "window:2", sequence=3)
    )
    windows.fail_window = "window:3"
    windows.fail_error = "constraint-rejected"
    coordinator.handle_ui_action(
        action(coordinator, "suggestion-selected", "window:3", sequence=4)
    )

    assert not coordinator.active
    group = coordinator.state.group_for_window("window:1")
    assert group is not None
    assert set(group.zones.values()) == {"window:1", "window:2"}
    assert coordinator.state.group_for_window("window:3") is None
    assert any(
        command[0] == "notify" and "zona quedó vacía" in command[1]
        for command in presentation.commands
    )


def test_presentation_failure_aborts_without_leaving_active_flow():
    coordinator, _windows, presentation, _events = make_coordinator()
    presentation.fail_command = "layouts"
    assert not coordinator.start()
    assert not coordinator.active
    assert presentation.commands[-1][0] == "notify"


def test_disconnect_defers_geometry_restore_until_reconnected():
    coordinator, windows, _presentation, events = make_coordinator()
    coordinator.start()
    coordinator.handle_ui_action(action(coordinator, "layout-selected", 0))
    coordinator.handle_ui_action(action(coordinator, "layout-selected", 0, sequence=2))
    move_count = len(windows.moves)
    events.callback(PlatformEvent("session:1", 20, EventKind.RUNTIME_DISCONNECTED))
    assert not coordinator.active
    assert len(windows.moves) == move_count
    events.callback(PlatformEvent("session:2", 0, EventKind.RUNTIME_RECONNECTED))
    assert windows.moves[-1][1:] == (
        "window:1",
        LogicalRect(-1500, 100, 800, 600),
    )


def test_transient_active_resolves_parent_and_ineligible_windows_are_not_suggested():
    snapshot = make_snapshot()
    dialog = WindowSnapshot(
        "window:dialog",
        "Guardar",
        "org.example.Editor",
        "Editor",
        LogicalRect(-1400, 200, 400, 300),
        "monitor:left",
        "workspace:0",
        transient_for="window:1",
        eligible=False,
    )
    utility = WindowSnapshot(
        "window:utility",
        "Panel",
        "org.example.Utility",
        "Utility",
        LogicalRect(200, 200, 400, 300),
        "monitor:right",
        "workspace:0",
        eligible=False,
    )
    snapshot = DesktopSnapshot(
        snapshot.session_id,
        snapshot.sequence,
        dialog.handle,
        snapshot.active_workspace,
        (*snapshot.windows, dialog, utility),
        snapshot.monitors,
    )
    coordinator, _windows, presentation, _events = make_coordinator(snapshot)
    assert coordinator.start()
    assert presentation.commands[-1][3].handle == "window:1"
    coordinator.handle_ui_action(action(coordinator, "layout-selected", 0))
    coordinator.handle_ui_action(action(coordinator, "layout-selected", 0, sequence=2))
    candidates = presentation.commands[-1][3]
    assert [candidate.handle for candidate in candidates] == ["window:2"]


def run_all_tests():
    tests = [
        test_complete_two_zone_flow_uses_negative_monitor_work_area,
        test_stale_flow_cancel_and_unknown_actions_do_not_mutate,
        test_layouts_can_reload_without_restarting_runtime,
        test_missing_active_window_and_invalid_work_area_are_safe,
        test_window_failure_is_reported_and_monitor_change_cancels,
        test_drag_and_resize_detach_without_moving_user_window,
        test_minimum_hint_never_preempts_real_move_confirmation,
        test_cancel_result_reports_incompatible_zone_as_empty,
        test_suggestions_use_runtime_eligibility_not_unverified_minimum_hints,
        test_unverified_minimum_hint_does_not_skip_narrow_zone,
        test_ineligible_active_window_does_not_start_native_flow,
        test_maximized_window_is_unmaximized_and_restored,
        test_second_window_constraint_keeps_first_and_leaves_zone_empty,
        test_extension_owned_restore_is_not_repeated_by_coordinator,
        test_partial_flow_groups_two_confirmed_windows_and_excludes_rejected_one,
        test_presentation_failure_aborts_without_leaving_active_flow,
        test_disconnect_defers_geometry_restore_until_reconnected,
        test_transient_active_resolves_parent_and_ineligible_windows_are_not_suggested,
    ]
    for test in tests:
        test()
        print(f"  ✓ {test.__name__}")


if __name__ == "__main__":
    run_all_tests()
