"""Contratos neutrales y snapshots inmutables de alpha.2."""

import ast
import sys
from dataclasses import FrozenInstanceError
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from snapassist.runtime import (
    EventKind,
    LogicalRect,
    MonitorSnapshot,
    OperationResult,
    PlatformEvent,
    WindowSnapshot,
)
from snapassist.runtime.contracts import DesktopSnapshot


def test_runtime_package_has_no_platform_or_ui_imports():
    forbidden = ("Xlib", "pynput", "tkinter", "gi")
    for path in (ROOT / "snapassist" / "runtime").glob("*.py"):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.append(node.module)
        for module in imported:
            assert not module.startswith(forbidden), (
                f"{path.name} importa plataforma/UI: {module}"
            )


def test_snapshots_are_immutable_and_use_opaque_handles():
    window = WindowSnapshot(
        handle="x11:opaque-1",
        title="Editor",
        app_id="org.example.Editor",
        app_name="Editor",
        geometry=LogicalRect(-100, 20, 800, 600),
        monitor="monitor:left",
        workspace="workspace:1",
    )
    monitor = MonitorSnapshot(
        "monitor:left",
        LogicalRect(-1920, 0, 1920, 1080),
        LogicalRect(-1920, 24, 1920, 1056),
        1.0,
    )
    snapshot = DesktopSnapshot(
        "session-test",
        1,
        window.handle,
        "workspace:1",
        (window,),
        (monitor,),
    )
    assert snapshot.active_window == "x11:opaque-1"
    try:
        snapshot.sequence = 2
    except FrozenInstanceError:
        pass
    else:
        raise AssertionError("DesktopSnapshot es mutable")


def test_duplicate_handles_and_negative_sequences_are_rejected():
    window = WindowSnapshot(
        "window:1",
        "",
        "",
        "",
        LogicalRect(0, 0, 1, 1),
        "monitor:1",
        "workspace:1",
    )
    monitor = MonitorSnapshot(
        "monitor:1",
        LogicalRect(0, 0, 1, 1),
        LogicalRect(0, 0, 1, 1),
    )
    for kwargs in (
        {"sequence": -1, "windows": (window,), "monitors": (monitor,)},
        {"sequence": 0, "windows": (window, window), "monitors": (monitor,)},
        {"sequence": 0, "windows": (window,), "monitors": (monitor, monitor)},
    ):
        try:
            DesktopSnapshot(
                "session",
                kwargs["sequence"],
                None,
                "workspace:1",
                kwargs["windows"],
                kwargs["monitors"],
            )
        except ValueError:
            pass
        else:
            raise AssertionError("snapshot inválido aceptado")


def test_semantic_events_and_operation_results_do_not_expose_native_ids():
    event = PlatformEvent(
        "session",
        3,
        EventKind.WINDOW_CHANGED,
        window="mutter:opaque",
    )
    result = OperationResult(
        "operation:7",
        False,
        "window-gone",
        "desapareció",
        "session:1",
    )
    assert event.window == "mutter:opaque"
    assert result.error_code == "window-gone"
    assert result.session_id == "session:1"


def run_all_tests():
    tests = [
        test_runtime_package_has_no_platform_or_ui_imports,
        test_snapshots_are_immutable_and_use_opaque_handles,
        test_duplicate_handles_and_negative_sequences_are_rejected,
        test_semantic_events_and_operation_results_do_not_expose_native_ids,
    ]
    for test in tests:
        test()
        print(f"  ✓ {test.__name__}")


if __name__ == "__main__":
    run_all_tests()
