"""El entrypoint GNOME permanece importable sin inicializar D-Bus/X11."""

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def test_gnome_entrypoint_import_is_side_effect_free():
    from snapassist import gnome_main

    assert callable(gnome_main.main)
    assert callable(gnome_main.setup_logging)


def test_gnome_runner_uses_system_python_and_isolated_paths():
    runner = (ROOT / "scripts" / "run-gnome-test.sh").read_text(encoding="utf-8")
    for required in (
        "SNAPASSIST_CHANNEL=test",
        "snapassist-test/settings.json",
        "snapassist-test/logs",
        "/usr/bin/python3 -m snapassist.gnome_main",
    ):
        assert required in runner


def run_all_tests():
    tests = [
        test_gnome_entrypoint_import_is_side_effect_free,
        test_gnome_runner_uses_system_python_and_isolated_paths,
    ]
    for test in tests:
        test()
        print(f"  ✓ {test.__name__}")


if __name__ == "__main__":
    run_all_tests()
