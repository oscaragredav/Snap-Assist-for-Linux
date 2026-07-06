"""
tests/test_phase3.py — Tests de verificación para la Fase 3.

Verifica:
- LayoutEngine: cálculo de coordenadas absolutas y gaps.
- SnapEngine: orquestación de llamadas al backend (guardado de estado, des-maximizado, resize).
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import Optional
from snapassist.config import Rect, ZoneTemplate, LayoutTemplate, ZoneRef


class MockBackend:
    def __init__(self):
        self.moves = []
        self.focuses = []
        self.maximized_states = []
        
    def get_window_geometry(self, wid: int) -> 'WindowGeometry':
        from snapassist.config import WindowGeometry
        return WindowGeometry(rect=Rect(0, 0, 800, 600))
        
    def get_monitor_for_window(self, wid: int) -> int:
        return 0
        
    def get_work_area(self, monitor_idx: int = 0) -> Rect:
        return Rect(0, 0, 1920, 1080)
        
    def set_window_maximized(self, wid: int, maximized: bool) -> None:
        self.maximized_states.append((wid, maximized))
        
    def move_resize_window(self, wid: int, rect: Rect) -> None:
        self.moves.append((wid, rect))
        
    def focus_window(self, wid: int) -> None:
        self.focuses.append(wid)


def test_layout_engine_math():
    """Verifica las matemáticas del cálculo de zonas."""
    from snapassist.layout.engine import LayoutEngine
    
    print("Test: LayoutEngine matemáticas...")
    
    engine = LayoutEngine(gap_px=0)
    
    # Monitor 1080p estándar
    work_area = Rect(0, 0, 1920, 1080)
    
    # 1. Mitad izquierda exacta
    zone_left = ZoneTemplate(x=0.0, y=0.0, w=0.5, h=1.0)
    rect_left = engine.calculate_zone_rect(work_area, zone_left)
    assert rect_left.x == 0
    assert rect_left.y == 0
    assert rect_left.w == 960
    assert rect_left.h == 1080
    
    # 2. Mitad derecha exacta
    zone_right = ZoneTemplate(x=0.5, y=0.0, w=0.5, h=1.0)
    rect_right = engine.calculate_zone_rect(work_area, zone_right)
    assert rect_right.x == 960
    assert rect_right.y == 0
    assert rect_right.w == 960
    assert rect_right.h == 1080
    
    # 3. Monitor desplazado (ej. secundario a la derecha)
    work_area_2 = Rect(1920, 0, 1920, 1080)
    rect_left_2 = engine.calculate_zone_rect(work_area_2, zone_left)
    assert rect_left_2.x == 1920
    assert rect_left_2.y == 0
    assert rect_left_2.w == 960
    assert rect_left_2.h == 1080
    
    print("  ✓ Matemáticas de zonas correctas sin gap.")


def test_layout_engine_gaps():
    """Verifica la aplicación de gaps."""
    from snapassist.layout.engine import LayoutEngine
    print("Test: LayoutEngine gaps...")
    
    engine = LayoutEngine(gap_px=10)
    work_area = Rect(0, 0, 1920, 1080)
    
    # Mitad izquierda con gap
    zone_left = ZoneTemplate(x=0.0, y=0.0, w=0.5, h=1.0)
    rect_left = engine.calculate_zone_rect(work_area, zone_left)
    
    assert rect_left.x == 10
    assert rect_left.y == 10
    # Ancho base 960, menos gap izquierdo (10) y derecho (10) = 940
    assert rect_left.w == 940 
    assert rect_left.h == 1060
    
    print("  ✓ Aplicación de gaps correcta.")


def test_snap_engine_workflow():
    """Verifica el flujo del orquestador SnapEngine."""
    from snapassist.snap.snapper import SnapEngine
    from snapassist.core.state import State
    from snapassist.layout.engine import LayoutEngine
    print("Test: SnapEngine workflow...")
    
    backend = MockBackend()
    state = State()
    layout = LayoutEngine(gap_px=0)
    snapper = SnapEngine(backend, state, layout)
    
    # Simular un layout 1:1
    template = LayoutTemplate(
        name="1:1",
        zones=[
            ZoneTemplate(x=0.0, y=0.0, w=0.5, h=1.0),
            ZoneTemplate(x=0.5, y=0.0, w=0.5, h=1.0)
        ]
    )
    
    wid = 0x1234
    snapper.snap_window_to_zone(wid, template, 0)
    
    # Verificaciones:
    # 1. ¿Se guardó el estado original?
    assert state.get_saved_geometry(wid) is not None, "El estado original debe guardarse"
    
    # 2. ¿Se des-maximizó la ventana?
    assert (wid, False) in backend.maximized_states, "La ventana debe ser des-maximizada"
    
    # 3. ¿Se movió la ventana a la coordenada correcta?
    assert len(backend.moves) == 1
    moved_wid, target_rect = backend.moves[0]
    assert moved_wid == wid
    assert target_rect.x == 0
    assert target_rect.y == 0
    assert target_rect.w == 960
    assert target_rect.h == 1080
    
    # 4. ¿Se pidió el foco?
    assert wid in backend.focuses
    
    # 5. ¿Se registró en el estado?
    assert wid in state.snapped_windows
    assert state.snapped_windows[wid].group_id == "dummy-phase3-group"
    assert state.snapped_windows[wid].zone_index == 0
    
    print("  ✓ Flujo del SnapEngine correcto.")


def run_all_tests():
    print("=" * 60)
    print("SnapAssist — Tests de Fase 3")
    print("=" * 60)
    print()

    tests = [
        test_layout_engine_math,
        test_layout_engine_gaps,
        test_snap_engine_workflow,
    ]

    passed = 0
    failed = 0

    for test_fn in tests:
        try:
            test_fn()
            passed += 1
        except Exception as e:
            print(f"  ✗ FALLÓ: {e}")
            failed += 1

    print()
    print("=" * 60)
    print(f"Resultados: {passed} pasados, {failed} fallidos de {len(tests)} tests")
    print("=" * 60)

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    run_all_tests()
