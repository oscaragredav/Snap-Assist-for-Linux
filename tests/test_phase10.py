"""Pruebas automatizadas de Fase 10: empaquetado e instalación idempotente."""

import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def test_pointer_listener_is_disabled_during_idle():
    from snapassist.core.hotkeys import HotkeyManager

    manager = HotkeyManager(pointer_event_queue=object())
    assert manager._pointer_listener is None
    # Desactivar el modo idle es un no-op y no importa pynput/X11.
    manager.set_pointer_tracking(False)
    assert manager._pointer_listener is None


def test_dependencies_are_exactly_pinned():
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
    pins = {line for line in requirements if line and not line.startswith("#")}
    assert pins == {"python-xlib==0.33", "pynput==1.8.2", "ewmh==0.1.6"}


def test_service_has_phase10_lifecycle_contract():
    unit = (ROOT / "snapassist.service").read_text(encoding="utf-8")
    for required in (
        "After=graphical-session.target",
        "WantedBy=graphical-session.target",
        "Restart=on-failure",
        "RestartSec=3",
        "EnvironmentFile=-%h/.config/snapassist/environment",
        "ExecStartPre=%h/.local/share/snapassist/venv/bin/python -m snapassist.wait_for_x11",
        "ExecStart=%h/.local/share/snapassist/venv/bin/python -m snapassist.main",
    ):
        assert required in unit


def test_installer_is_idempotent_in_an_isolated_tree():
    with tempfile.TemporaryDirectory(prefix="snapassist-phase10-") as temp:
        base = Path(temp)
        env = dict(
            os.environ,
            SNAPASSIST_DATA_HOME=str(base / "share"),
            SNAPASSIST_CONFIG_HOME=str(base / "config"),
            SNAPASSIST_SKIP_PIP="1",
            SNAPASSIST_SKIP_SYSTEMD="1",
        )
        command = ["bash", str(ROOT / "install.sh")]
        subprocess.run(command, cwd=ROOT, env=env, check=True, capture_output=True)
        installed = base / "share" / "snapassist"
        unit = base / "config" / "systemd" / "user" / "snapassist.service"
        assert (installed / "snapassist" / "main.py").is_file()
        assert (installed / "snapassist" / "wait_for_x11.py").is_file()
        assert (installed / "requirements.txt").is_file()
        assert unit.read_bytes() == (ROOT / "snapassist.service").read_bytes()

        first_main = (installed / "snapassist" / "main.py").read_bytes()
        subprocess.run(command, cwd=ROOT, env=env, check=True, capture_output=True)
        assert (installed / "snapassist" / "main.py").read_bytes() == first_main


def test_readme_documents_user_operations():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for required in (
        "bash install.sh",
        "systemctl --user status snapassist",
        "Super+Z",
        "Super+Alt+Tab",
        "Super+/",
        "journalctl --user -u snapassist",
        "Desinstalación",
        "Privacidad",
    ):
        assert required in readme


def run_all_tests():
    tests = [
        test_pointer_listener_is_disabled_during_idle,
        test_dependencies_are_exactly_pinned,
        test_service_has_phase10_lifecycle_contract,
        test_installer_is_idempotent_in_an_isolated_tree,
        test_readme_documents_user_operations,
    ]
    for test in tests:
        test()
        print(f"  ✓ {test.__name__}")


if __name__ == "__main__":
    run_all_tests()
