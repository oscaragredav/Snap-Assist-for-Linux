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
]


def main() -> None:
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    for test in TESTS:
        print(f"\n== {test} ==")
        subprocess.run([sys.executable, str(ROOT / test)], check=True, env=env)
    print(f"\n✓ Suite completa: {len(TESTS)} archivos ejecutados")


if __name__ == "__main__":
    main()
