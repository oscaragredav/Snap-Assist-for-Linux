"""
tests/test_phase1.py — Tests de verificación para la Fase 1.

Verifica:
- Importación sin errores de todos los módulos
- Correcta estructura de tipos base (Rect, WindowGeometry, etc.)
- Correcta definición de la interfaz abstracta WindowManager
- Estado global se inicializa vacío
- Operaciones MRU básicas
- Layouts preconfigurados son válidos
"""

import sys
import os

# Agregar el directorio padre al path para imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_imports():
    """Verifica que todos los módulos importan sin errores."""
    print("Test: Importación de módulos...")

    from snapassist.config import (
        Rect, WindowGeometry, ZoneRef, ZoneTemplate, LayoutTemplate,
        SnapGroup, WindowType, WindowState,
        HOTKEY_LAYOUT_MENU, HOTKEY_SNAP_GROUPS, HOTKEY_HELP,
        SNAP_ANIMATION_MS, DRAG_THRESHOLD_PX, QUICKKEY_SEQUENCE,
        OVERLAY_OPACITY, LAYOUT_TEMPLATES,
    )
    from snapassist.wm.backend import WindowManager
    from snapassist.core.state import State
    from snapassist.core.daemon import Daemon

    print("  ✓ Todos los módulos importan correctamente.")


def test_rect():
    """Verifica la estructura y métodos de Rect."""
    print("Test: Rect...")

    from snapassist.config import Rect

    r = Rect(x=100, y=50, w=960, h=540)
    assert r.right == 1060, f"right esperado=1060, obtenido={r.right}"
    assert r.bottom == 590, f"bottom esperado=590, obtenido={r.bottom}"
    assert r.contains_point(500, 300), "Punto (500,300) debería estar dentro"
    assert not r.contains_point(50, 300), "Punto (50,300) no debería estar dentro"

    # Test de intersección
    r2 = Rect(x=500, y=200, w=800, h=600)
    area = r.intersection_area(r2)
    expected_area = (1060 - 500) * (590 - 200)  # 560 * 390 = 218400
    assert area == expected_area, f"Área intersección esperada={expected_area}, obtenida={area}"

    # Test sin intersección
    r3 = Rect(x=2000, y=2000, w=100, h=100)
    assert r.intersection_area(r3) == 0, "No debería haber intersección"

    # Test de dimensiones negativas
    try:
        Rect(x=0, y=0, w=-10, h=100)
        assert False, "Debería lanzar ValueError para dimensiones negativas"
    except ValueError:
        pass

    print("  ✓ Rect funciona correctamente.")


def test_window_geometry():
    """Verifica WindowGeometry."""
    print("Test: WindowGeometry...")

    from snapassist.config import Rect, WindowGeometry

    geom = WindowGeometry(rect=Rect(0, 0, 1920, 1080))
    assert not geom.is_maximized
    assert geom.rect.w == 1920

    geom_max = WindowGeometry(rect=Rect(0, 0, 1920, 1080), is_maximized=True)
    assert geom_max.is_maximized

    print("  ✓ WindowGeometry funciona correctamente.")


def test_enums():
    """Verifica los enums WindowType y WindowState."""
    print("Test: Enums...")

    from snapassist.config import WindowType, WindowState

    assert WindowType.NORMAL.value == "normal"
    assert WindowType.DIALOG.value == "dialog"
    assert WindowType.DOCK.value == "dock"

    assert WindowState.NORMAL.value == "normal"
    assert WindowState.MINIMIZED.value == "minimized"
    assert WindowState.FULLSCREEN.value == "fullscreen"
    assert WindowState.ALWAYS_TOP.value == "always_top"

    print("  ✓ Enums funcionan correctamente.")


def test_state_init():
    """Verifica que State se inicializa vacío."""
    print("Test: State inicialización...")

    from snapassist.core.state import State

    state = State()
    assert state.mru_list == [], f"MRU debería ser vacío, es: {state.mru_list}"
    assert state.saved_geometries == {}
    assert state.snapped_windows == {}
    assert state.active_groups == {}
    assert state.suspended_groups == {}

    print("  ✓ State se inicializa vacío.")


def test_state_mru():
    """Verifica operaciones MRU del State."""
    print("Test: State MRU...")

    from snapassist.core.state import State

    state = State()

    # Agregar ventanas
    state.update_mru(100)
    state.update_mru(200)
    state.update_mru(300)
    assert state.get_mru_list() == [300, 200, 100], \
        f"MRU esperado=[300,200,100], obtenido={state.get_mru_list()}"

    # Re-foco en ventana existente la mueve al frente
    state.update_mru(100)
    assert state.get_mru_list() == [100, 300, 200], \
        f"MRU esperado=[100,300,200], obtenido={state.get_mru_list()}"

    # wid=0 se ignora
    state.update_mru(0)
    assert state.get_mru_list() == [100, 300, 200], \
        "MRU no debería cambiar con wid=0"

    # wid=None se ignora
    state.update_mru(None)
    assert state.get_mru_list() == [100, 300, 200], \
        "MRU no debería cambiar con wid=None"

    # Remover ventana de MRU
    state.remove_from_mru(300)
    assert state.get_mru_list() == [100, 200], \
        f"MRU esperado=[100,200], obtenido={state.get_mru_list()}"

    print("  ✓ State MRU funciona correctamente.")


def test_state_geometry():
    """Verifica save/restore de geometría."""
    print("Test: State save/restore geometría...")

    from snapassist.config import Rect, WindowGeometry
    from snapassist.core.state import State

    state = State()
    geom = WindowGeometry(rect=Rect(100, 200, 800, 600), is_maximized=False)

    state.save_geometry(42, geom)
    restored = state.get_saved_geometry(42)
    assert restored is not None
    assert restored.rect.x == 100
    assert restored.rect.w == 800
    assert not restored.is_maximized

    # restore_geometry retorna y elimina
    restored2 = state.restore_geometry(42)
    assert restored2 is not None
    assert state.get_saved_geometry(42) is None, "Geometría debería estar eliminada"

    # restore_geometry de wid sin geometría retorna None
    assert state.restore_geometry(999) is None

    print("  ✓ State save/restore geometría funciona correctamente.")


def test_layout_templates():
    """Verifica que los layouts preconfigurados son válidos."""
    print("Test: Layout templates...")

    from snapassist.config import LAYOUT_TEMPLATES

    assert len(LAYOUT_TEMPLATES) >= 4, \
        f"Esperados al menos 4 layouts, hay {len(LAYOUT_TEMPLATES)}"

    for template in LAYOUT_TEMPLATES:
        assert template.name, f"Template sin nombre"
        assert len(template.zones) >= 2, \
            f"Template '{template.name}' tiene {len(template.zones)} zonas (mínimo 2)"

        # Verificar que las proporciones están en rango [0, 1]
        for zone in template.zones:
            assert 0.0 <= zone.x <= 1.0, \
                f"Template '{template.name}': x={zone.x} fuera de rango"
            assert 0.0 <= zone.y <= 1.0, \
                f"Template '{template.name}': y={zone.y} fuera de rango"
            assert 0.0 < zone.w <= 1.0, \
                f"Template '{template.name}': w={zone.w} fuera de rango"
            assert 0.0 < zone.h <= 1.0, \
                f"Template '{template.name}': h={zone.h} fuera de rango"

    # Verificar el template 1:1 específicamente
    half_half = LAYOUT_TEMPLATES[0]
    assert half_half.name == "1:1"
    assert len(half_half.zones) == 2
    assert half_half.zones[0].w == 0.5
    assert half_half.zones[1].x == 0.5

    print(f"  ✓ {len(LAYOUT_TEMPLATES)} layouts válidos.")


def test_abstract_interface():
    """Verifica que WindowManager no se puede instanciar directamente."""
    print("Test: Interfaz abstracta WindowManager...")

    from snapassist.wm.backend import WindowManager

    try:
        wm = WindowManager()
        assert False, "No debería poder instanciarse WindowManager directamente"
    except TypeError:
        pass  # Correcto: ABC no se puede instanciar

    print("  ✓ WindowManager es abstracta y no instanciable.")


def test_wayland_stub():
    """Verifica que WaylandBackend lanza NotImplementedError."""
    print("Test: WaylandBackend stub...")

    from snapassist.wm.wayland_backend import WaylandBackend

    try:
        backend = WaylandBackend()
        assert False, "WaylandBackend debería lanzar NotImplementedError"
    except NotImplementedError as e:
        assert "v1" in str(e), "Mensaje debería mencionar 'v1'"
        assert "X11" in str(e), "Mensaje debería mencionar 'X11'"

    print("  ✓ WaylandBackend lanza NotImplementedError con mensaje claro.")


def run_all_tests():
    """Ejecuta todos los tests de la Fase 1."""
    print("=" * 60)
    print("SnapAssist — Tests de Fase 1")
    print("=" * 60)
    print()

    tests = [
        test_imports,
        test_rect,
        test_window_geometry,
        test_enums,
        test_state_init,
        test_state_mru,
        test_state_geometry,
        test_layout_templates,
        test_abstract_interface,
        test_wayland_stub,
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
