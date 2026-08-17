"""Contract tests del cliente Python para org.snapassist.Shell1."""

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from snapassist.runtime import (
    GnomeProtocolClient,
    LogicalRect,
    ProtocolDisconnected,
    ProtocolError,
    ProtocolVersionError,
)


class FakeTransport:
    def __init__(self):
        self.connected = False
        self.session_id = "shell-session-1"
        self.calls = []
        self.callbacks = {}
        self.fail_next_method = None

    def connect(self):
        self.connected = True

    def disconnect(self):
        self.connected = False

    def call(self, method, *args):
        if not self.connected:
            raise ProtocolDisconnected("bus disconnected")
        self.calls.append((method, args))
        if method == self.fail_next_method:
            self.fail_next_method = None
            self.connected = False
            self.session_id = "shell-session-2"
            raise ProtocolDisconnected("injected disconnect")
        if method == "GetProtocolInfo":
            return json.dumps(
                {
                    "protocolVersion": 1,
                    "minimumClientVersion": 1,
                    "sessionId": self.session_id,
                    "interfaceName": "org.snapassist.Shell1",
                    "capabilityCandidates": ["active-window", "move-resize"],
                }
            )
        if method == "GetSnapshot":
            return snapshot_json(self.session_id, 4)
        operation_id = args[0]
        return json.dumps(
            {
                "operationId": operation_id,
                "accepted": True,
                "errorCode": None,
                "message": "",
                "sessionId": self.session_id,
                "duplicate": False,
            }
        )

    def subscribe(self, signal, callback):
        self.callbacks.setdefault(signal, []).append(callback)

        def unsubscribe():
            if callback in self.callbacks.get(signal, []):
                self.callbacks[signal].remove(callback)

        return unsubscribe

    def emit(self, signal, value):
        for callback in tuple(self.callbacks.get(signal, [])):
            callback(value)


def snapshot_json(session_id, sequence):
    return json.dumps(
        {
            "protocolVersion": 1,
            "sessionId": session_id,
            "sequence": sequence,
            "activeWindow": "mutter:7",
            "activeWorkspace": "workspace:0",
            "windows": [
                {
                    "handle": "mutter:7",
                    "title": "Editor",
                    "appId": "org.example.Editor.desktop",
                    "appName": "Editor",
                    "clientType": "wayland",
                    "frameRect": {"x": -100, "y": 20, "width": 800, "height": 600},
                    "monitor": "monitor:0",
                    "workspace": "workspace:0",
                    "minimized": False,
                    "maximizedHorizontally": True,
                    "maximizedVertically": True,
                    "transientFor": None,
                    "minimumSize": {"width": 640, "height": 480},
                    "minimumSizeKnown": True,
                    "maximumSize": {"width": 1600, "height": 1200},
                    "maximumSizeKnown": True,
                    "fullscreen": False,
                    "above": False,
                    "onAllWorkspaces": False,
                    "allowsMove": True,
                    "allowsResize": True,
                    "mapped": True,
                    "tiled": False,
                }
            ],
            "monitors": [
                {
                    "handle": "monitor:0",
                    "geometry": {"x": -1920, "y": 0, "width": 1920, "height": 1080},
                    "workArea": {"x": -1920, "y": 24, "width": 1920, "height": 1056},
                    "scale": 1.0,
                }
            ],
        }
    )


def event_json(session_id, sequence, kind="window-changed"):
    return json.dumps(
        {
            "sessionId": session_id,
            "sequence": sequence,
            "kind": kind,
            "window": "mutter:7",
            "operationId": None,
            "payload": None,
        }
    )


def ui_action_json(session_id, sequence, flow_id, action, value=None):
    return json.dumps(
        {
            "sessionId": session_id,
            "sequence": sequence,
            "flowId": flow_id,
            "action": action,
            "value": value,
        }
    )


def test_handshake_snapshot_and_operations_use_opaque_contract():
    transport = FakeTransport()
    client = GnomeProtocolClient(transport)
    info = client.connect()
    assert info.session_id == "shell-session-1"
    snapshot = client.get_snapshot()
    assert snapshot.windows[0].handle == "mutter:7"
    assert snapshot.windows[0].geometry.x == -100
    assert snapshot.windows[0].maximized
    assert snapshot.windows[0].maximized_horizontally
    assert snapshot.windows[0].maximized_vertically
    assert snapshot.windows[0].client_type == "wayland"
    assert snapshot.windows[0].minimum_size == (640, 480)
    assert snapshot.windows[0].minimum_size_known
    assert snapshot.windows[0].maximum_size == (1600, 1200)
    assert snapshot.windows[0].maximum_size_known
    assert snapshot.windows[0].allows_move
    assert snapshot.windows[0].allows_resize
    assert snapshot.windows[0].mapped
    assert not snapshot.windows[0].fullscreen
    assert snapshot.monitors[0].work_area.y == 24

    result = client.move_resize(
        "operation:1",
        "mutter:7",
        LogicalRect(-100, 20, 900, 700),
    )
    assert result.operation_id == "operation:1"
    assert result.accepted
    assert transport.calls[-1] == (
        "MoveResize",
        ("operation:1", "mutter:7", -100, 20, 900, 700),
    )


def test_move_resize_result_parses_confirmation_contract():
    transport = FakeTransport()
    original_call = transport.call

    def enriched_result(method, *args):
        if method != "MoveResize":
            return original_call(method, *args)
        return json.dumps(
            {
                "operationId": args[0],
                "accepted": False,
                "errorCode": "constraint-rejected",
                "message": "minimum size exceeds zone",
                "sessionId": transport.session_id,
                "status": "constraint-rejected",
                "requestedGeometry": {"x": -100, "y": 20, "width": 500, "height": 300},
                "observedGeometry": {"x": -100, "y": 20, "width": 640, "height": 480},
                "constraint": "minimum-size",
                "attempts": 2,
                "confirmationMs": 1000,
                "restored": True,
                "observations": [
                    {
                        "elapsedMs": 50,
                        "geometry": {"x": -100, "y": 20, "width": 640, "height": 480},
                        "monitor": 0,
                        "scale": 1.25,
                    }
                ],
            }
        )

    transport.call = enriched_result
    client = GnomeProtocolClient(transport)
    client.connect()
    result = client.move_resize(
        "operation:constraint", "mutter:7", LogicalRect(-100, 20, 500, 300)
    )
    assert result.status == "constraint-rejected"
    assert result.requested_geometry == LogicalRect(-100, 20, 500, 300)
    assert result.observed_geometry == LogicalRect(-100, 20, 640, 480)
    assert result.constraint == "minimum-size"
    assert result.attempts == 2
    assert result.confirmation_ms == 1000
    assert result.restored
    assert result.observations[0]["elapsedMs"] == 50
    assert result.observations[0]["scale"] == 1.25


def test_disconnect_reconnects_and_retries_same_operation_id_once():
    transport = FakeTransport()
    client = GnomeProtocolClient(transport)
    client.connect()
    transport.fail_next_method = "Activate"
    result = client.activate("operation:retry", "mutter:7")
    assert result.accepted
    activate_calls = [call for call in transport.calls if call[0] == "Activate"]
    assert activate_calls == [
        ("Activate", ("operation:retry", "mutter:7")),
        ("Activate", ("operation:retry", "mutter:7")),
    ]
    assert client.info.session_id == "shell-session-2"


def test_reconnect_emits_lifecycle_events_and_probe_recovers_idle_client():
    transport = FakeTransport()
    client = GnomeProtocolClient(transport)
    client.connect()
    received = []
    client.subscribe_events(received.append)
    transport.fail_next_method = "Activate"
    client.activate("operation:lifecycle", "mutter:7")
    assert [event.kind.value for event in received] == [
        "runtime-disconnected",
        "runtime-reconnected",
    ]
    client.disconnect()
    snapshot = client.ensure_connected()
    assert snapshot.session_id == client.info.session_id
    assert received[-1].kind.value == "runtime-reconnected"


def test_stale_out_of_order_and_foreign_session_events_are_ignored():
    transport = FakeTransport()
    client = GnomeProtocolClient(transport)
    client.connect()
    received = []
    unsubscribe = client.subscribe_events(received.append)
    transport.emit("PlatformEvent", event_json("shell-session-1", 2))
    transport.emit("PlatformEvent", event_json("shell-session-1", 1))
    transport.emit("PlatformEvent", event_json("shell-session-1", 2))
    transport.emit("PlatformEvent", event_json("foreign-session", 99))
    transport.emit("PlatformEvent", event_json("shell-session-1", 3))
    assert [event.sequence for event in received] == [2, 3]
    unsubscribe()
    transport.emit("PlatformEvent", event_json("shell-session-1", 4))
    assert [event.sequence for event in received] == [2, 3]


def test_malformed_signals_are_isolated_and_valid_completion_is_delivered():
    transport = FakeTransport()
    client = GnomeProtocolClient(transport)
    client.connect()
    results = []
    client.subscribe_operations(results.append)
    transport.emit("PlatformEvent", "not-json")
    transport.emit("OperationCompleted", "not-json")
    transport.emit(
        "OperationCompleted",
        json.dumps(
            {
                "operationId": "operation:done",
                "accepted": False,
                "errorCode": "window-gone",
                "message": "window disappeared",
                "sessionId": "shell-session-1",
            }
        ),
    )
    assert len(results) == 1
    assert results[0].error_code == "window-gone"

    transport.emit(
        "OperationCompleted",
        json.dumps(
            {
                "operationId": "operation:foreign",
                "accepted": True,
                "errorCode": None,
                "message": "",
                "sessionId": "foreign-session",
            }
        ),
    )
    assert len(results) == 1


def test_incompatible_version_and_session_mismatch_are_rejected():
    transport = FakeTransport()
    original_call = transport.call

    def incompatible(method, *args):
        if method == "GetProtocolInfo":
            value = json.loads(original_call(method, *args))
            value["minimumClientVersion"] = 2
            return json.dumps(value)
        return original_call(method, *args)

    transport.call = incompatible
    try:
        GnomeProtocolClient(transport).connect()
    except ProtocolVersionError:
        pass
    else:
        raise AssertionError("se aceptó una versión incompatible")

    transport = FakeTransport()
    client = GnomeProtocolClient(transport)
    client.connect()
    original_call = transport.call

    def wrong_snapshot(method, *args):
        if method == "GetSnapshot":
            return snapshot_json("foreign-session", 1)
        return original_call(method, *args)

    transport.call = wrong_snapshot
    try:
        client.get_snapshot()
    except ProtocolError:
        pass
    else:
        raise AssertionError("se aceptó snapshot de otra sesión")


def test_presentation_operations_and_ui_actions_preserve_flow_id():
    transport = FakeTransport()
    client = GnomeProtocolClient(transport)
    client.connect()
    result = client.show_layouts(
        "operation:ui:1",
        17,
        {"title": "Layouts", "layouts": [{"name": "1:1"}]},
    )
    assert result.accepted
    method, args = transport.calls[-1]
    assert method == "ShowLayouts"
    assert args[0:2] == ("operation:ui:1", 17)
    assert json.loads(args[2])["layouts"][0]["name"] == "1:1"

    client.show_help(
        "operation:ui:help",
        18,
        {"title": "Ayuda", "lines": ["Super+Z"]},
    )
    method, args = transport.calls[-1]
    assert method == "ShowHelp"
    assert args[0:2] == ("operation:ui:help", 18)

    received = []
    client.subscribe_ui_actions(received.append)
    transport.emit(
        "UiAction",
        ui_action_json("shell-session-1", 2, 17, "layout-selected", 0),
    )
    transport.emit(
        "UiAction",
        ui_action_json("shell-session-1", 1, 17, "cancel"),
    )
    transport.emit(
        "UiAction",
        ui_action_json("foreign", 3, 17, "cancel"),
    )
    assert len(received) == 1
    assert received[0].flow_id == 17
    assert received[0].value == 0

    client.hide_presentation("operation:ui:2", 17)
    assert transport.calls[-1] == (
        "HidePresentation",
        ("operation:ui:2", 17),
    )


def test_invalid_presentation_input_is_rejected_locally():
    transport = FakeTransport()
    client = GnomeProtocolClient(transport)
    client.connect()
    invalid_calls = (
        lambda: client.show_layouts("operation:1", -1, {}),
        lambda: client.show_layouts("operation:1", 1, {"bad": object()}),
        lambda: client.notify("operation:1", "", 100),
        lambda: client.notify("operation:1", "message", 60_001),
        lambda: client.configure_shortcuts(
            "operation:1",
            {"layout_menu": "super+l"},
        ),
    )
    for call in invalid_calls:
        try:
            call()
        except ValueError:
            pass
        else:
            raise AssertionError("entrada UI inválida aceptada")


def test_shortcuts_are_sent_as_complete_versioned_action_map():
    transport = FakeTransport()
    client = GnomeProtocolClient(transport)
    client.connect()
    shortcuts = {
        "layout_menu": "super+l",
        "snap_groups": "super+alt+g",
        "help": "super+h",
    }
    result = client.configure_shortcuts("operation:shortcuts", shortcuts)
    assert result.accepted
    method, args = transport.calls[-1]
    assert method == "ConfigureShortcuts"
    assert args[0] == "operation:shortcuts"
    assert json.loads(args[1]) == shortcuts


def run_all_tests():
    tests = [
        test_handshake_snapshot_and_operations_use_opaque_contract,
        test_move_resize_result_parses_confirmation_contract,
        test_disconnect_reconnects_and_retries_same_operation_id_once,
        test_reconnect_emits_lifecycle_events_and_probe_recovers_idle_client,
        test_stale_out_of_order_and_foreign_session_events_are_ignored,
        test_malformed_signals_are_isolated_and_valid_completion_is_delivered,
        test_incompatible_version_and_session_mismatch_are_rejected,
        test_presentation_operations_and_ui_actions_preserve_flow_id,
        test_invalid_presentation_input_is_rejected_locally,
        test_shortcuts_are_sent_as_complete_versioned_action_map,
    ]
    for test in tests:
        test()
        print(f"  ✓ {test.__name__}")


if __name__ == "__main__":
    run_all_tests()
