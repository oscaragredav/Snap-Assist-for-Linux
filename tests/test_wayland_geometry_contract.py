"""Regresiones del contrato de geometría confirmado en GNOME/Wayland.

Estas pruebas no dependen de una aplicación concreta. El adaptador Python no
sondea Mutter: conserva el resultado final que la extensión obtuvo de forma
asíncrona después de recibir los configures Wayland.
"""

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from snapassist.adapters.gnome_runtime import GnomeWindowController  # noqa: E402
from snapassist.config import LAYOUT_TEMPLATES  # noqa: E402
from snapassist.core.native_state import NativeState  # noqa: E402
from snapassist.runtime import (  # noqa: E402
    LogicalRect,
    OperationResult,
)


TARGET = LogicalRect(-960, 24, 960, 1056)


class ConfirmationClient:
    """Cliente mínimo que entrega el resultado final de la extensión."""

    def __init__(self, result):
        self.result = result
        self.moves = []

    def move_resize(self, operation_id, window, rect):
        self.moves.append((operation_id, window, rect))
        return self.result


def test_geometry_match_allows_at_most_one_logical_pixel():
    observed = LogicalRect(
        TARGET.x + 1,
        TARGET.y - 1,
        TARGET.width,
        TARGET.height,
    )
    client = ConfirmationClient(
        OperationResult(
            "snap:one-pixel",
            True,
            session_id="session:test",
            status="confirmed",
            requested_geometry=TARGET,
            observed_geometry=observed,
            attempts=1,
        )
    )
    result = GnomeWindowController(client).move_resize(
        "snap:one-pixel",
        "window:test",
        TARGET,
    )
    assert result.accepted
    assert result.observed_geometry == observed
    assert len(client.moves) == 1


def test_wayland_controller_does_not_accept_visible_two_pixel_error():
    # La extensión nunca confirma un frame dos píxeles fuera de la zona.
    observed = LogicalRect(TARGET.x + 2, TARGET.y, TARGET.width, TARGET.height)
    client = ConfirmationClient(
        OperationResult(
            "snap:test",
            False,
            "constraint-rejected",
            "La aplicación no puede mantener la zona solicitada.",
            "session:test",
            "constraint-rejected",
            TARGET,
            observed,
            "client-geometry",
            1,
            1_000,
        )
    )
    controller = GnomeWindowController(client)

    result = controller.move_resize("snap:test", "window:test", TARGET)

    assert not result.accepted
    assert result.error_code == "constraint-rejected"
    assert result.observed_geometry == observed
    assert len(client.moves) == 1


def test_wayland_controller_requires_two_consecutive_stable_samples():
    client = ConfirmationClient(
        OperationResult(
            "snap:stable",
            True,
            session_id="session:test",
            status="confirmed",
            requested_geometry=TARGET,
            observed_geometry=TARGET,
            attempts=2,
            confirmation_ms=100,
        )
    )
    controller = GnomeWindowController(client)

    result = controller.move_resize("snap:stable", "window:test", TARGET)

    assert result.accepted
    assert result.status == "confirmed"
    assert result.attempts == 2
    assert len(client.moves) == 1


def test_wayland_controller_reports_window_closed_during_confirmation():
    client = ConfirmationClient(
        OperationResult(
            "snap:gone",
            False,
            "window-gone",
            "La ventana desapareció mientras se acomodaba.",
            "session:test",
            "window-gone",
            TARGET,
        )
    )
    controller = GnomeWindowController(client)
    result = controller.move_resize("snap:gone", "window:test", TARGET)

    assert not result.accepted
    assert result.error_code == "window-gone"


def test_partial_confirmation_group_contains_only_confirmed_windows():
    state = NativeState()
    state.bind_to_current_thread()
    state.save_geometry("window:compatible-1", LogicalRect(10, 10, 800, 600))
    state.save_geometry("window:compatible-2", LogicalRect(20, 20, 900, 700))

    # La zona 0 pertenece a la aplicación incompatible y queda vacía. Las
    # zonas 1 y 2 son las únicas confirmadas y sí pueden formar un grupo.
    group_id = state.commit_snap(
        LAYOUT_TEMPLATES[4],
        "monitor:left",
        {1: "window:compatible-1", 2: "window:compatible-2"},
    )

    assert group_id is not None
    group = state.groups[group_id]
    assert group.zones == {
        1: "window:compatible-1",
        2: "window:compatible-2",
    }
    assert state.group_for_window("window:compatible-1") is group
    assert state.group_for_window("window:compatible-2") is group
    assert state.group_for_window("window:failed") is None


def test_one_confirmed_window_is_not_promoted_to_group():
    state = NativeState()
    state.bind_to_current_thread()
    state.save_geometry("window:only", LogicalRect(10, 10, 800, 600))

    group_id = state.commit_snap(
        LAYOUT_TEMPLATES[0],
        "monitor:left",
        {0: "window:only"},
    )

    assert group_id is None
    assert not state.groups
    assert state.group_for_window("window:only") is None
    assert state.snapped_windows["window:only"].zone_index == 0


def test_wayland_controller_accepts_grid_and_min_size_constraints():
    # El controlador acepta frames estables con restricciones de cuadrícula o tamaño mínimo
    grid_observed = LogicalRect(TARGET.x, TARGET.y, TARGET.width - 8, TARGET.height - 12)
    client_grid = ConfirmationClient(
        OperationResult(
            "snap:grid",
            True,
            session_id="session:test",
            status="confirmed",
            requested_geometry=TARGET,
            observed_geometry=grid_observed,
            constraint="size-increments",
            attempts=2,
        )
    )
    result_grid = GnomeWindowController(client_grid).move_resize("snap:grid", "window:term", TARGET)
    assert result_grid.accepted
    assert result_grid.constraint == "size-increments"
    assert result_grid.observed_geometry == grid_observed

    min_observed = LogicalRect(TARGET.x, TARGET.y, TARGET.width + 160, TARGET.height)
    client_min = ConfirmationClient(
        OperationResult(
            "snap:min",
            True,
            session_id="session:test",
            status="confirmed",
            requested_geometry=TARGET,
            observed_geometry=min_observed,
            constraint="minimum-size",
            attempts=2,
        )
    )
    result_min = GnomeWindowController(client_min).move_resize("snap:min", "window:spotify", TARGET)
    assert result_min.accepted
    assert result_min.constraint == "minimum-size"
    assert result_min.observed_geometry == min_observed


def run_all_tests():
    tests = [
        test_geometry_match_allows_at_most_one_logical_pixel,
        test_wayland_controller_does_not_accept_visible_two_pixel_error,
        test_wayland_controller_requires_two_consecutive_stable_samples,
        test_wayland_controller_reports_window_closed_during_confirmation,
        test_wayland_controller_accepts_grid_and_min_size_constraints,
        test_partial_confirmation_group_contains_only_confirmed_windows,
        test_one_confirmed_window_is_not_promoted_to_group,
    ]
    for test in tests:
        test()
        print(f"  ✓ {test.__name__}")


if __name__ == "__main__":
    run_all_tests()
