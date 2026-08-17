"""Puerta única, sin dependencias externas, para la suite de regresión."""

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
TESTS = [
    "test_phase1.py", "test_phase2.py", "test_phase3.py", "test_phase4.py",
    "test_phase5.py", "test_phase6.py", "test_phase7.py", "test_phase8.py",
    "test_phase9.py", "test_phase10.py", "test_qa_regressions.py",
    "test_release_contract.py",
    "test_gnome_extension.py",
    "test_settings.py",
    "test_runtime_contracts.py",
    "test_gnome_protocol_client.py",
    "test_gnome_dbus_adapter.py",
    "test_gnome_heartbeat.py",
    "test_gnome_runtime_adapters.py",
    "test_wayland_geometry_contract.py",
    "test_native_coordinator.py",
    "test_gnome_main.py",
    "test_native_state.py",
    "test_soak.py",
    "test_release_artifacts.py",
    "test_x11_runtime_adapter.py",
    "test_health.py",
    "test_roadmap_validator.py",
    "test_gnome_nested_smoke.py",
    "test_geometry_reconciliation.py",
]


def main() -> None:
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    for test in TESTS:
        print(f"\n== {test} ==")
        subprocess.run([sys.executable, str(ROOT / test)], check=True, env=env)
    print(f"\n✓ Suite completa: {len(TESTS)} archivos ejecutados")


if __name__ == "__main__":
    main()
