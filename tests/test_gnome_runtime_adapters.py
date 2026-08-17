"""Adaptación del protocolo GNOME a puertos de core."""

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from snapassist.adapters.gnome_runtime import (
    GnomePresentationPort,
    GnomeShortcutProvider,
    GnomeWindowController,
)
from snapassist.config import LAYOUT_TEMPLATES
from snapassist.runtime import (
    Capability,
    LogicalRect,
    MonitorSnapshot,
    OperationResult,
    UiAction,
    WindowSnapshot,
)
from snapassist.runtime.contracts import DesktopSnapshot


class FakeClient:
    def __init__(self):
        self.calls = []
        self.ui_callback = None

    def subscribe_ui_actions(self, callback):
        self.ui_callback = callback
        return lambda: setattr(self, "ui_callback", None)

    def show_layouts(self, operation_id, flow_id, payload):
        self.calls.append(("show_layouts", operation_id, flow_id, payload))
        return OperationResult(operation_id, True)

    def show_suggestions(self, operation_id, flow_id, payload):
        self.calls.append(("show_suggestions", operation_id, flow_id, payload))
        return OperationResult(operation_id, True)

    def show_help(self, operation_id, flow_id, payload):
        self.calls.append(("show_help", operation_id, flow_id, payload))
        return OperationResult(operation_id, True)

    def hide_presentation(self, operation_id, flow_id):
        self.calls.append(("hide", operation_id, flow_id))
        return OperationResult(operation_id, True)

    def notify(self, operation_id, message):
        self.calls.append(("notify", operation_id, message))
        return OperationResult(operation_id, True)

    def configure_shortcuts(self, operation_id, shortcuts):
        self.calls.append(("shortcuts", operation_id, dict(shortcuts)))
        return OperationResult(operation_id, True)


class GeometryClient:
    def __init__(self, result):
        self.result = result
        self.moves = []

    def move_resize(self, operation_id, handle, rect):
        self.moves.append((operation_id, handle, rect))
        return self.result


def window(handle="window:1"):
    return WindowSnapshot(
        handle,
        "Documento",
        "org.example.Editor",
        "Editor",
        LogicalRect(0, 0, 800, 600),
        "monitor:0",
        "workspace:0",
    )


def test_native_presentation_payloads_preserve_flow_and_handles():
    client = FakeClient()
    presentation = GnomePresentationPort(client)
    presentation.show_layouts(7, LAYOUT_TEMPLATES[:2], window())
    method, operation_id, flow_id, payload = client.calls[-1]
    assert method == "show_layouts"
    assert operation_id.startswith("ui-layouts:")
    assert flow_id == 7
    assert payload["subtitle"] == "Editor"
    assert len(payload["layouts"]) == 2

    presentation.show_suggestions(
        7,
        LogicalRect(0, 0, 960, 1080),
        [window("window:2")],
    )
    payload = client.calls[-1][3]
    assert payload["candidates"][0]["handle"] == "window:2"
    presentation.hide(7)
    presentation.notify("Listo")
    assert client.calls[-2][0] == "hide"
    assert client.calls[-1][0] == "notify"
    presentation.show_help()
    assert client.calls[-1][0] == "show_help"
    assert "Super+Z" in client.calls[-1][3]["lines"][0]


def test_shortcuts_are_applied_together_and_dispatch_native_actions():
    client = FakeClient()
    provider = GnomeShortcutProvider(client)
    invoked = []
    assert provider.register("layout_menu", "super+z", lambda: invoked.append("layout"))
    assert provider.register("snap_groups", "super+alt+tab", lambda: invoked.append("groups"))
    assert not any(call[0] == "shortcuts" for call in client.calls)
    assert provider.register("help", "super+slash", lambda: invoked.append("help"))
    shortcut_call = client.calls[-1]
    assert shortcut_call[0] == "shortcuts"
    assert shortcut_call[2]["layout_menu"] == "super+z"

    client.ui_callback(UiAction("session", 1, 0, "shortcut-invoked", "help"))
    client.ui_callback(UiAction("session", 2, 0, "layout-selected", 1))
    assert invoked == ["help"]
    assert provider.update_shortcuts({
        "layout_menu": "super+l",
        "snap_groups": "super+alt+g",
        "help": "super+h",
    })
    assert client.calls[-1][0] == "shortcuts"
    assert client.calls[-1][2]["layout_menu"] == "super+l"
    provider.close()
    assert client.ui_callback is None


def test_wayland_move_uses_extension_confirmation_without_daemon_polling():
    target = LogicalRect(960, 0, 960, 1040)
    client = GeometryClient(
        OperationResult(
            "snap:1",
            True,
            session_id="session:1",
            status="confirmed",
            requested_geometry=target,
            observed_geometry=target,
            attempts=2,
            confirmation_ms=100,
        )
    )
    controller = GnomeWindowController(client)
    result = controller.move_resize("snap:1", "window:1", target)
    assert result.accepted
    assert result.status == "confirmed"
    assert result.observed_geometry == target
    assert client.moves == [("snap:1", "window:1", target)]


def test_wayland_move_preserves_extension_constraint_result():
    target = LogicalRect(1280, 0, 640, 1040)
    previous_tile = LogicalRect(960, 0, 960, 1040)
    client = GeometryClient(
        OperationResult(
            "snap:2",
            False,
            "constraint-rejected",
            "La aplicación no puede mantener la zona solicitada.",
            "session:1",
            "constraint-rejected",
            target,
            previous_tile,
            "minimum-size",
            2,
            1_000,
        )
    )
    controller = GnomeWindowController(client)
    result = controller.move_resize("snap:2", "window:1", target)
    assert not result.accepted
    assert result.error_code == "constraint-rejected"
    assert result.constraint == "minimum-size"
    assert result.observed_geometry == previous_tile
    assert len(client.moves) == 1


def test_real_extension_without_confirmation_capability_is_rejected():
    class LegacyClient:
        capabilities = frozenset({Capability.MOVE_RESIZE})

        def move_resize(self, *_args):
            raise AssertionError("no debe invocarse una extensión no confirmada")

    result = GnomeWindowController(LegacyClient()).move_resize(
        "snap:legacy",
        "window:1",
        LogicalRect(0, 0, 800, 600),
    )
    assert not result.accepted
    assert result.error_code == "unsupported-capability"


def run_all_tests():
    tests = [
        test_native_presentation_payloads_preserve_flow_and_handles,
        test_shortcuts_are_applied_together_and_dispatch_native_actions,
        test_wayland_move_uses_extension_confirmation_without_daemon_polling,
        test_wayland_move_preserves_extension_constraint_result,
        test_real_extension_without_confirmation_capability_is_rejected,
    ]
    for test in tests:
        test()
        print(f"  ✓ {test.__name__}")


if __name__ == "__main__":
    run_all_tests()
