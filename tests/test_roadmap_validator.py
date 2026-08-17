"""El validador cubre todas las etapas y conserva puertas manuales separadas."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def test_validator_lists_e0_to_e8_with_distinct_manual_gates():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/validate-roadmap.py"), "--list"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    stages = json.loads(result.stdout)
    assert [item["stage"] for item in stages] == [f"E{index}" for index in range(9)]
    assert [item["manualGate"] for item in stages] == [f"U{index}" for index in range(9)]


def test_manual_evidence_is_validated_and_never_self_approves():
    with tempfile.TemporaryDirectory() as temp:
        directory = Path(temp)
        init = subprocess.run(
            [sys.executable, str(ROOT / "scripts/manual-gate.py"), "U3", "--init",
             "--directory", str(directory)],
            cwd=ROOT, check=True, capture_output=True, text=True,
        )
        path = Path(init.stdout.strip())
        template = json.loads(path.read_text(encoding="utf-8"))
        assert template["result"] == "rejected"
        invalid = subprocess.run(
            [sys.executable, str(ROOT / "scripts/manual-gate.py"), "U3", "--check",
             "--directory", str(directory)],
            cwd=ROOT, capture_output=True, text=True,
        )
        assert invalid.returncode == 0
        assert json.loads(invalid.stdout)["status"] == "rejected"
        template["result"] = "approved"
        path.write_text(json.dumps(template), encoding="utf-8")
        failed = subprocess.run(
            [sys.executable, str(ROOT / "scripts/manual-gate.py"), "U3", "--check",
             "--directory", str(directory)],
            cwd=ROOT, capture_output=True, text=True,
        )
        assert failed.returncode == 1
        assert json.loads(failed.stdout)["status"] == "invalid"


def run_all_tests():
    test_validator_lists_e0_to_e8_with_distinct_manual_gates()
    test_manual_evidence_is_validated_and_never_self_approves()
    print("  ✓ test_validator_lists_e0_to_e8_with_distinct_manual_gates")
    print("  ✓ test_manual_evidence_is_validated_and_never_self_approves")


if __name__ == "__main__":
    run_all_tests()
