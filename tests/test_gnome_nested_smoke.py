"""Contrato estático del smoke GNOME anidado, ejecutado opcionalmente en CI."""

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def test_nested_smoke_isolated_and_checks_lifecycle():
    runner = (ROOT / "scripts/run-gnome-nested-smoke.sh").read_text()
    session = (ROOT / "scripts/gnome-nested-session.sh").read_text()
    for required in (
        "mktemp -d /tmp/snapassist-gnome-nested.",
        "XDG_RUNTIME_DIR",
        "GSETTINGS_BACKEND=keyfile",
        "--headless",
        "--virtual-monitor 1280x720",
        "GetProtocolInfo",
        "GetSnapshot",
        'gsettings set org.gnome.shell enabled-extensions "[]"',
        'gsettings set org.gnome.shell enabled-extensions "[\'${UUID}\']"',
        "reconnected_protocol",
        "reconnected_snapshot",
        "wait_for_owner absent",
        "for _attempt in $(seq 1 50)",
    ):
        assert required in runner + session
    assert "gnome-extensions enable" not in runner + session


def run_all_tests():
    test_nested_smoke_isolated_and_checks_lifecycle()
    print("  ✓ test_nested_smoke_isolated_and_checks_lifecycle")


if __name__ == "__main__":
    run_all_tests()
