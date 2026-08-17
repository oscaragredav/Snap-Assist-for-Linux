"""Estado neutral: grupos, geometrías y rollback."""

import sys
import threading
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from snapassist.config import LAYOUT_TEMPLATES
from snapassist.core.native_state import NativeState
from snapassist.runtime import LogicalRect


def test_singleton_and_group_membership_are_exclusive():
    state = NativeState()
    state.save_geometry("window:1", LogicalRect(10, 20, 800, 600))
    assert state.commit_snap(
        LAYOUT_TEMPLATES[0], "monitor:0", {0: "window:1"}
    ) is None
    assert state.snapped_windows["window:1"].group_id is None

    group_id = state.commit_snap(
        LAYOUT_TEMPLATES[0],
        "monitor:0",
        {0: "window:1", 1: "window:2"},
    )
    assert group_id
    assert state.group_for_window("window:1").group_id == group_id
    assert state.group_for_window("window:2").group_id == group_id


def test_detach_dissolves_pair_and_returns_original_geometry():
    state = NativeState()
    original = LogicalRect(10, 20, 800, 600)
    state.save_geometry("window:1", original)
    state.save_geometry("window:2", LogicalRect(30, 40, 900, 700))
    state.commit_snap(
        LAYOUT_TEMPLATES[0],
        "monitor:0",
        {0: "window:1", 1: "window:2"},
    )
    assert state.detach("window:1") == original
    assert not state.groups
    assert "window:1" not in state.snapped_windows
    assert "window:2" not in state.snapped_windows
    assert "window:2" in state.saved_geometries


def test_snapshot_restore_is_deep_and_atomic():
    state = NativeState()
    state.save_geometry("window:1", LogicalRect(0, 0, 100, 100))
    snapshot = state.snapshot()
    state.commit_snap(LAYOUT_TEMPLATES[0], "monitor:0", {0: "window:1"})
    state.save_geometry("window:2", LogicalRect(1, 1, 200, 200))
    state.restore(snapshot)
    assert state.saved_geometries == {
        "window:1": LogicalRect(0, 0, 100, 100)
    }
    assert not state.snapped_windows
    assert state.saved_maximized == {"window:1": False}


def test_mutation_from_foreign_thread_is_rejected():
    state = NativeState()
    state.bind_to_current_thread()
    errors = []

    def mutate():
        try:
            state.save_geometry("window:1", LogicalRect(0, 0, 1, 1))
        except RuntimeError as error:
            errors.append(str(error))

    thread = threading.Thread(target=mutate)
    thread.start()
    thread.join()
    assert errors == ["NativeState solo puede mutarse desde su event loop"]


def test_missing_monitor_discards_only_affected_groups():
    state = NativeState()
    left = state.commit_snap(
        LAYOUT_TEMPLATES[0],
        "monitor:left",
        {0: "window:1", 1: "window:2"},
    )
    right = state.commit_snap(
        LAYOUT_TEMPLATES[0],
        "monitor:right",
        {0: "window:3", 1: "window:4"},
    )
    assert state.discard_groups_for_missing_monitors({"monitor:right"}) == 1
    assert left not in state.groups
    assert right in state.groups
    assert "window:1" not in state.snapped_windows
    assert "window:3" in state.snapped_windows


def run_all_tests():
    tests = [
        test_singleton_and_group_membership_are_exclusive,
        test_detach_dissolves_pair_and_returns_original_geometry,
        test_snapshot_restore_is_deep_and_atomic,
        test_mutation_from_foreign_thread_is_rejected,
        test_missing_monitor_discards_only_affected_groups,
    ]
    for test in tests:
        test()
        print(f"  ✓ {test.__name__}")


if __name__ == "__main__":
    run_all_tests()
