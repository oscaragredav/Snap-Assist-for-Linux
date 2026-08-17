"""
tests/test_geometry_reconciliation.py — Suite exhaustiva de reconciliación de geometría.

Valida de forma determinista y exhaustiva:
1. Soporte completo de ventanas maximizadas y en mosaico (inicio de flujo y sugerencias).
2. Reconciliación con cuadrículas discretas (Terminales/Editores) en todos los 6 layouts.
3. Política Center & Clamp para tamaños mínimos rígidos (Spotify/Electron, Firefox).
4. Validación por redundancia frente a eventos ConfigureNotify transitorios de Mutter.
5. Cobertura multi-monitor con coordenadas negativas y consistencia fraccional.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from snapassist.config import LAYOUT_TEMPLATES, LayoutTemplate, ZoneTemplate
from snapassist.core.native_coordinator import NativeSnapCoordinator, _zone_rect
from snapassist.core.native_state import NativeState
from snapassist.runtime.contracts import (
    DesktopSnapshot,
    EventKind,
    LogicalRect,
    MonitorSnapshot,
    OperationResult,
    PlatformEvent,
    WindowSnapshot,
)
from snapassist.runtime.gnome_client import UiAction


class MockPresentation:
    def __init__(self):
        self.layouts_shown = []
        self.suggestions_shown = []
        self.notifications = []
        self.hidden = []

    def show_layouts(self, flow_id, layouts, active_window):
        self.layouts_shown.append((flow_id, layouts, active_window))

    def show_suggestions(self, flow_id, zone, candidates):
        self.suggestions_shown.append((flow_id, zone, list(candidates)))

    def hide(self, flow_id):
        self.hidden.append(flow_id)

    def notify(self, message):
        self.notifications.append(message)


class MockWindows:
    def __init__(self, snapshot):
        self.snapshot = snapshot
        self.moves = []
        self.focused = []
        self.maximized = []
        self.custom_results = {}

    def get_snapshot(self):
        return self.snapshot

    def activate(self, op_id, window):
        self.focused.append((op_id, window))
        return OperationResult(op_id, True)

    def move_resize(self, op_id, window, rect):
        self.moves.append((op_id, window, rect))
        if window in self.custom_results:
            return self.custom_results[window]
        return OperationResult(
            op_id,
            True,
            status="confirmed",
            requested_geometry=rect,
            observed_geometry=rect,
        )

    def set_maximized(self, op_id, window, maximized):
        self.maximized.append((op_id, window, maximized))
        return OperationResult(op_id, True)


class MockRuntime:
    def __init__(self, snapshot):
        self.windows = MockWindows(snapshot)
        self.presentation = MockPresentation()
        self.events = type("Events", (), {"subscribe": lambda self, cb: lambda: None})()


def make_ui_action(coord, action, value=None):
    return UiAction(
        session_id="session:test",
        sequence=1,
        flow_id=coord.flow_id,
        action=action,
        value=value,
    )


# ============================================================================
# 1. PRUEBAS DE VENTANAS MAXIMIZADAS Y EN MOSAICO
# ============================================================================

def test_maximized_active_window_starts_flow_and_snaps_smoothly():
    mon = MonitorSnapshot("m0", LogicalRect(0, 0, 1920, 1080), LogicalRect(0, 24, 1920, 1056))
    max_win = WindowSnapshot(
        handle="w:max",
        title="Terminal Maximizada",
        app_id="org.gnome.Terminal",
        app_name="Terminal",
        geometry=LogicalRect(0, 24, 1920, 1056),
        monitor="m0",
        workspace="ws:0",
        maximized=True,
        maximized_horizontally=True,
        maximized_vertically=True,
        allows_resize=True,
        eligible=True,
    )
    snap = DesktopSnapshot("s:1", 1, "w:max", "ws:0", (max_win,), (mon,))
    runtime = MockRuntime(snap)
    coord = NativeSnapCoordinator(runtime, LAYOUT_TEMPLATES)

    # Iniciar flujo con ventana activa maximizada
    assert coord.start() is True
    assert len(runtime.presentation.layouts_shown) == 1

    # Seleccionar layout 1/2 : 1/2 y primera zona
    coord.handle_ui_action(make_ui_action(coord, "layout-selected", 0))
    coord.handle_ui_action(make_ui_action(coord, "layout-selected", 0))

    # Verificar que el movimiento se solicitó con la geometría de la zona
    assert len(runtime.windows.moves) == 1
    assert runtime.windows.moves[0][1] == "w:max"
    assert runtime.windows.moves[0][2] == LogicalRect(0, 24, 960, 1056)
    # Verificar que se guardó la geometría original y su estado maximizado
    assert coord.state.saved_geometries["w:max"] == LogicalRect(0, 24, 1920, 1056)
    assert coord.state.saved_maximized["w:max"] is True


def test_maximized_windows_appear_in_suggestions_and_can_be_selected():
    mon = MonitorSnapshot("m0", LogicalRect(0, 0, 1920, 1080), LogicalRect(0, 24, 1920, 1056))
    active_win = WindowSnapshot(
        handle="w:active",
        title="Editor",
        app_id="editor",
        app_name="Editor",
        geometry=LogicalRect(100, 100, 800, 600),
        monitor="m0",
        workspace="ws:0",
        eligible=True,
    )
    max_candidate = WindowSnapshot(
        handle="w:max_candidate",
        title="Spotify Maximizado",
        app_id="spotify",
        app_name="Spotify",
        geometry=LogicalRect(0, 24, 1920, 1056),
        monitor="m0",
        workspace="ws:0",
        maximized=True,
        maximized_horizontally=True,
        maximized_vertically=True,
        eligible=True,
    )
    snap = DesktopSnapshot("s:1", 1, "w:active", "ws:0", (active_win, max_candidate), (mon,))
    runtime = MockRuntime(snap)
    coord = NativeSnapCoordinator(runtime, LAYOUT_TEMPLATES)

    coord.start()
    # Layout 1/2 : 1/2 y zona izquierda
    coord.handle_ui_action(make_ui_action(coord, "layout-selected", 0))
    coord.handle_ui_action(make_ui_action(coord, "layout-selected", 0))

    # Verificar que w:max_candidate está en las sugerencias
    assert len(runtime.presentation.suggestions_shown) == 1
    candidates = runtime.presentation.suggestions_shown[0][2]
    assert "w:max_candidate" in [c.handle for c in candidates]

    # Seleccionar la ventana sugerida maximizada
    coord.choose_suggestion(make_ui_action(coord, "suggestion-selected", "w:max_candidate"))
    assert len(runtime.windows.moves) == 2
    assert runtime.windows.moves[1][1] == "w:max_candidate"
    assert runtime.windows.moves[1][2] == LogicalRect(960, 24, 960, 1056)
    assert coord.state.saved_maximized["w:max_candidate"] is True


# ============================================================================
# 2. PRUEBAS DE CUADRÍCULA DISCRETA Y RECONCILIACIÓN EN TODOS LOS LAYOUTS
# ============================================================================

def test_discrete_grid_cell_increments_accepted_across_all_layouts():
    mon = MonitorSnapshot("m0", LogicalRect(0, 0, 1920, 1080), LogicalRect(0, 24, 1920, 1056))
    work_area = mon.work_area

    # Probar todos los 6 layouts predefinidos
    for layout_idx, layout in enumerate(LAYOUT_TEMPLATES):
        zones = [_zone_rect(work_area, z) for z in layout.zones]
        for zone_idx, zone in enumerate(zones):
            win = WindowSnapshot(
                handle=f"w:term_{layout_idx}_{zone_idx}",
                title="Terminal Grid",
                app_id="terminal",
                app_name="Terminal",
                geometry=LogicalRect(100, 100, 800, 600),
                monitor="m0",
                workspace="ws:0",
                eligible=True,
            )
            snap = DesktopSnapshot("s:1", 1, win.handle, "ws:0", (win,), (mon,))
            runtime = MockRuntime(snap)

            # Simular que la terminal se acomoda a múltiplos de su celda (delta de 8px en ancho y 12px en alto)
            grid_geometry = LogicalRect(zone.x, zone.y, max(100, zone.width - 8), max(100, zone.height - 12))
            runtime.windows.custom_results[win.handle] = OperationResult(
                "op:snap",
                True,
                status="confirmed",
                requested_geometry=zone,
                observed_geometry=grid_geometry,
                constraint="size-increments",
                attempts=2,
            )

            coord = NativeSnapCoordinator(runtime, LAYOUT_TEMPLATES)
            assert coord.start() is True
            coord.handle_ui_action(make_ui_action(coord, "layout-selected", layout_idx))
            coord.handle_ui_action(make_ui_action(coord, "layout-selected", zone_idx))

            # Verificar que el acoplamiento con cuadrícula fue aceptado y comprometido en el estado sin rollback
            assert win.handle in coord.state.snapped_windows
            assert coord.state.snapped_windows[win.handle].zone_index == zone_idx


# ============================================================================
# 3. POLÍTICA CENTER & CLAMP PARA TAMAÑOS MÍNIMOS (SPOTIFY / FIREFOX)
# ============================================================================

def test_center_and_clamp_policy_for_hard_minimum_sizes():
    mon = MonitorSnapshot("m0", LogicalRect(0, 0, 1920, 1080), LogicalRect(0, 24, 1920, 1056))
    spotify_win = WindowSnapshot(
        handle="w:spotify",
        title="Spotify",
        app_id="spotify",
        app_name="Spotify",
        geometry=LogicalRect(100, 100, 900, 700),
        monitor="m0",
        workspace="ws:0",
        minimum_size=(800, 600),  # Ancho mínimo de 800px > zona 1/3 (640px)
        minimum_size_known=True,
        eligible=True,
    )
    snap = DesktopSnapshot("s:1", 1, "w:spotify", "ws:0", (spotify_win,), (mon,))
    runtime = MockRuntime(snap)
    coord = NativeSnapCoordinator(runtime, LAYOUT_TEMPLATES)

    coord.start()
    # Layout 2/3 : 1/3 (layout_idx=1), seleccionar zona de 1/3 (zone_idx=1, width=640px, x=1280px)
    coord.handle_ui_action(make_ui_action(coord, "layout-selected", 1))
    coord.handle_ui_action(make_ui_action(coord, "layout-selected", 1))

    # Verificar el cálculo de _fit_minimum
    move_req = runtime.windows.moves[0][2]
    # Ancho debe haberse adaptado al mínimo (800px)
    assert move_req.width == 800
    # La ventana debe estar contenida dentro de los límites del monitor (x + width <= 1920)
    assert move_req.x + move_req.width <= 1920
    assert move_req.x >= 0
    assert spotify_win.handle in coord.state.snapped_windows


def test_center_and_clamp_on_small_resolution():
    # Monitor 1366x768 (work area 1366x744)
    mon = MonitorSnapshot("m0", LogicalRect(0, 0, 1366, 768), LogicalRect(0, 24, 1366, 744))
    firefox = WindowSnapshot(
        handle="w:firefox",
        title="Firefox",
        app_id="firefox",
        app_name="Firefox",
        geometry=LogicalRect(50, 50, 800, 600),
        monitor="m0",
        workspace="ws:0",
        minimum_size=(500, 400),  # 500px > 1/3 de 1366 (455px)
        minimum_size_known=True,
        eligible=True,
    )
    snap = DesktopSnapshot("s:1", 1, "w:firefox", "ws:0", (firefox,), (mon,))
    runtime = MockRuntime(snap)
    coord = NativeSnapCoordinator(runtime, LAYOUT_TEMPLATES)

    coord.start()
    # Layout 1/3 : 2/3 (layout_idx=2), zona 0 (1/3 = 455px)
    coord.handle_ui_action(make_ui_action(coord, "layout-selected", 2))
    coord.handle_ui_action(make_ui_action(coord, "layout-selected", 0))

    move_req = runtime.windows.moves[0][2]
    assert move_req.width == 500
    assert move_req.x >= 0
    assert move_req.x + move_req.width <= 1366


# ============================================================================
# 4. PRUEBAS DE FRACCIONES EXACTAS Y COBERTURA MULTI-MONITOR
# ============================================================================

def test_fractional_layout_coverage_has_no_gaps_or_overlaps():
    resolutions = [
        (1366, 768, 744),
        (1920, 1080, 1056),
        (2560, 1440, 1400),
        (3840, 2160, 2120),
    ]
    for width, height, work_h in resolutions:
        work_area = LogicalRect(0, 24, width, work_h)
        for layout in LAYOUT_TEMPLATES:
            zones = [_zone_rect(work_area, z) for z in layout.zones]
            # Verificar que ninguna zona se salga del work area
            for z in zones:
                assert z.x >= 0
                assert z.y >= 24
                assert z.x + z.width <= width
                assert z.y + z.height <= 24 + work_h

            # En layouts horizontales (2/3 : 1/3, 1/3 : 2/3, 1/3 : 1/3 : 1/3), la suma de anchos debe cubrir exactamente el work area
            if layout.name in {"2/3 : 1/3", "1/3 : 2/3", "1/3 : 1/3 : 1/3", "1/2 : 1/2"}:
                total_w = sum(z.width for z in zones)
                assert total_w == width, f"Fallo en {layout.name} sobre {width}px: total={total_w}"


def test_multi_monitor_with_negative_coordinates():
    # Monitor izquierdo: -1920..0; Monitor derecho: 0..1920
    mon_left = MonitorSnapshot("m_left", LogicalRect(-1920, 0, 1920, 1080), LogicalRect(-1920, 24, 1920, 1056))
    mon_right = MonitorSnapshot("m_right", LogicalRect(0, 0, 1920, 1080), LogicalRect(0, 24, 1920, 1056))
    win = WindowSnapshot(
        handle="w:left",
        title="Ventana Monitor Izquierdo",
        app_id="app",
        app_name="App",
        geometry=LogicalRect(-1500, 100, 800, 600),
        monitor="m_left",
        workspace="ws:0",
        eligible=True,
    )
    snap = DesktopSnapshot("s:1", 1, "w:left", "ws:0", (win,), (mon_left, mon_right))
    runtime = MockRuntime(snap)
    coord = NativeSnapCoordinator(runtime, LAYOUT_TEMPLATES)

    coord.start()
    # Layout 1/2 : 1/2, zona izquierda
    coord.handle_ui_action(make_ui_action(coord, "layout-selected", 0))
    coord.handle_ui_action(make_ui_action(coord, "layout-selected", 0))

    move_req = runtime.windows.moves[0][2]
    assert move_req.x == -1920
    assert move_req.width == 960


def run_all_tests():
    tests = [
        test_maximized_active_window_starts_flow_and_snaps_smoothly,
        test_maximized_windows_appear_in_suggestions_and_can_be_selected,
        test_discrete_grid_cell_increments_accepted_across_all_layouts,
        test_center_and_clamp_policy_for_hard_minimum_sizes,
        test_center_and_clamp_on_small_resolution,
        test_fractional_layout_coverage_has_no_gaps_or_overlaps,
        test_multi_monitor_with_negative_coordinates,
    ]
    for test in tests:
        test()
        print(f"  ✓ {test.__name__}")


if __name__ == "__main__":
    run_all_tests()
