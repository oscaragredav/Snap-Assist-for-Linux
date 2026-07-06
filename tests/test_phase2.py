"""
tests/test_phase2.py — Tests de verificación para la Fase 2 (pynput version).

Verifica:
- Parseo de cadenas de atajos (hotkey strings) para pynput
- HotkeyManager: registro e interfaz básica
- State.update_mru con ventana nueva, existente, y wid=0
- Importación sin errores de los módulos modificados
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_parse_hotkey():
    """Verifica el parseo de cadenas de atajos hacia formato pynput."""
    print("Test: parse_hotkey...")

    from snapassist.core.hotkeys import parse_hotkey

    # super+z
    assert parse_hotkey("super+z") == "<cmd>+z"
    assert parse_hotkey("win+z") == "<cmd>+z"
    
    # ctrl+shift+a
    assert parse_hotkey("ctrl+shift+a") == "<ctrl>+<shift>+a"
    assert parse_hotkey("control+shift+a") == "<ctrl>+<shift>+a"

    # super+alt+tab
    assert parse_hotkey("super+alt+tab") == "<cmd>+<alt>+<tab>"

    # escape / esc
    assert parse_hotkey("super+esc") == "<cmd>+<esc>"
    assert parse_hotkey("super+escape") == "<cmd>+<esc>"

    print("  ✓ parse_hotkey funciona correctamente.")


def test_parse_hotkey_errors():
    """Verifica que parse_hotkey lanza ValueError en casos inválidos."""
    print("Test: parse_hotkey errores...")

    from snapassist.core.hotkeys import parse_hotkey

    # Modificador desconocido
    try:
        parse_hotkey("mega+z")
        assert False, "Debería lanzar ValueError para modificador 'mega'"
    except ValueError:
        pass

    print("  ✓ parse_hotkey valida errores correctamente.")


def test_state_update_mru_phase2():
    """Verifica update_mru con los escenarios de Fase 2."""
    print("Test: State.update_mru (Fase 2)...")

    from snapassist.core.state import State

    state = State()

    # Caso 1: ventana nueva
    state.update_mru(100)
    assert state.get_mru_list() == [100], \
        f"MRU tras nueva: {state.get_mru_list()}"

    # Caso 2: más ventanas
    state.update_mru(200)
    state.update_mru(300)
    assert state.get_mru_list() == [300, 200, 100], \
        f"MRU tras 3 ventanas: {state.get_mru_list()}"

    # Caso 3: ventana ya existente se mueve al frente
    state.update_mru(100)
    assert state.get_mru_list() == [100, 300, 200], \
        f"MRU tras re-foco: {state.get_mru_list()}"

    # Caso 4: wid=0 se ignora
    state.update_mru(0)
    assert state.get_mru_list() == [100, 300, 200], \
        "MRU no debería cambiar con wid=0"

    # Caso 5: wid=None se ignora
    state.update_mru(None)
    assert state.get_mru_list() == [100, 300, 200], \
        "MRU no debería cambiar con wid=None"

    # Caso 6: remove_from_mru
    state.remove_from_mru(300)
    assert state.get_mru_list() == [100, 200], \
        f"MRU tras remove: {state.get_mru_list()}"

    # Caso 7: remove de ventana inexistente no crashea
    state.remove_from_mru(999)
    assert state.get_mru_list() == [100, 200]

    print("  ✓ State.update_mru funciona correctamente.")


def test_hotkey_manager_init():
    """Verifica que HotkeyManager se puede importar y tiene la interfaz esperada."""
    print("Test: HotkeyManager importación e interfaz...")

    from snapassist.core.hotkeys import HotkeyManager
    hm = HotkeyManager()
    
    assert hasattr(hm, 'register')
    assert hasattr(hm, 'start')
    assert hasattr(hm, 'unregister_all')
    assert hasattr(hm, 'get_registered_hotkeys')

    # Probar registro
    def dummy(): pass
    hm.register("super+z", dummy)
    assert hm.registered_count == 1
    assert hm.get_registered_hotkeys() == ["super+z"]

    print("  ✓ HotkeyManager tiene la interfaz correcta.")


def test_daemon_init():
    """Verifica que Daemon acepta los nuevos parámetros de Fase 2."""
    print("Test: Daemon constructor (Fase 2)...")

    from snapassist.core.daemon import Daemon
    import inspect

    # Verificar que el constructor acepta hotkey_manager
    sig = inspect.signature(Daemon.__init__)
    params = list(sig.parameters.keys())
    assert "hotkey_manager" in params, \
        f"Daemon.__init__ no tiene parámetro hotkey_manager. Params: {params}"
    assert "wm_backend" in params
    assert "state" in params

    print("  ✓ Daemon acepta hotkey_manager en constructor.")


def test_imports_phase2():
    """Verifica que los módulos modificados importan sin errores."""
    print("Test: Importaciones Fase 2...")

    from snapassist.core.hotkeys import HotkeyManager, parse_hotkey
    from snapassist.core.daemon import Daemon
    from snapassist.core.state import State
    from snapassist.main import (
        setup_logging, detect_and_create_backend,
        log_system_state, create_super_z_callback, main,
    )

    print("  ✓ Todos los módulos de Fase 2 importan correctamente.")


def run_all_tests():
    """Ejecuta todos los tests de la Fase 2."""
    print("=" * 60)
    print("SnapAssist — Tests de Fase 2 (pynput)")
    print("=" * 60)
    print()

    tests = [
        test_imports_phase2,
        test_parse_hotkey,
        test_parse_hotkey_errors,
        test_state_update_mru_phase2,
        test_hotkey_manager_init,
        test_daemon_init,
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
