#!/usr/bin/env python3
"""Puerta automática E0–E8; no modifica servicios ni la sesión gráfica."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
_MANUAL_SPEC = importlib.util.spec_from_file_location(
    "snapassist_manual_gate", ROOT / "scripts" / "manual-gate.py"
)
if _MANUAL_SPEC is None or _MANUAL_SPEC.loader is None:
    raise RuntimeError("no se pudo cargar scripts/manual-gate.py")
_MANUAL_MODULE = importlib.util.module_from_spec(_MANUAL_SPEC)
_MANUAL_SPEC.loader.exec_module(_MANUAL_MODULE)
load_status = _MANUAL_MODULE.load_status


@dataclass(frozen=True)
class Stage:
    stage: str
    description: str
    commands: tuple[tuple[str, ...], ...]
    manual_gate: str


def stage_plan(python: str, *, full: bool) -> tuple[Stage, ...]:
    soak_cycles = "10000" if full else "500"
    gnome_checks = [(python, "tests/test_gnome_extension.py")]
    if full:
        gnome_checks.append(("bash", "scripts/run-gnome-nested-smoke.sh"))
    return (
        Stage("E0", "aislamiento stable/test", ((python, "tests/test_phase10.py"),), "U0"),
        Stage("E1", "regresión y release X11", (
            (python, "tests/test_release_contract.py"),
            (python, "tests/test_qa_regressions.py"),
        ), "U1"),
        Stage("E2", "extensión GNOME", tuple(gnome_checks), "U2"),
        Stage("E3", "core, adapters y configuración", (
            (python, "tests/test_runtime_contracts.py"),
            (python, "tests/test_x11_runtime_adapter.py"),
            (python, "tests/test_settings.py"),
        ), "U3"),
        Stage("E4", "IPC y recuperación", (
            (python, "tests/test_gnome_protocol_client.py"),
            (python, "tests/test_gnome_dbus_adapter.py"),
            (python, "tests/test_health.py"),
        ), "U4"),
        Stage("E5", "flujo, UI y personalización", (
            (python, "tests/test_native_coordinator.py"),
            (python, "tests/test_gnome_runtime_adapters.py"),
        ), "U5"),
        Stage("E6", "soak y residuos", (
            (python, "scripts/run-soak.py", "--cycles", soak_cycles, "--reconnect-every", "17", "--json"),
        ), "U6"),
        Stage("E7", "suite RC", (
            (python, "tests/run_all.py"),
            (python, "-m", "compileall", "-q", "snapassist", "tests", "scripts"),
            ("bash", "-n", "install.sh", "snapassist-channel", "snapassist-manage",
             "scripts/build-release.sh", "scripts/build-gnome-extension.sh"),
            ("git", "diff", "--check"),
        ), "U7"),
        Stage("E8", "bundle conjunto reproducible", (), "U8"),
    )


def run_command(command: tuple[str, ...], env: dict[str, str]) -> dict[str, object]:
    started = time.monotonic()
    result = subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
    )
    return {
        "command": list(command),
        "passed": result.returncode == 0,
        "returnCode": result.returncode,
        "durationSeconds": round(time.monotonic() - started, 3),
        "stdoutTail": result.stdout[-4000:],
        "stderrTail": result.stderr[-4000:],
    }


def validate_bundle(env: dict[str, str]) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="snapassist-roadmap-release-") as temp:
        first = Path(temp) / "first"
        second = Path(temp) / "second"
        commands = []
        for output in (first, second):
            result = run_command(("bash", "scripts/build-release.sh", str(output)), env)
            commands.append(result)
            if not result["passed"]:
                return {"passed": False, "commands": commands}
        bundles = sorted(first.glob("*-bundle.tar.gz"))
        other = second / bundles[0].name if bundles else None
        identical = bool(bundles and other and other.is_file() and bundles[0].read_bytes() == other.read_bytes())
        digest = hashlib.sha256(bundles[0].read_bytes()).hexdigest() if bundles else None
        return {
            "passed": identical,
            "commands": commands,
            "binaryReproducible": identical,
            "sha256": digest,
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--full", action="store_true", help="soak largo de 10000 ciclos")
    parser.add_argument("--output", type=Path, help="guardar informe JSON")
    parser.add_argument("--list", action="store_true", help="listar etapas sin ejecutarlas")
    parser.add_argument(
        "--manual-dir", type=Path, default=Path("artifacts/manual-validation"),
        help="directorio con evidencia U0-U8; no cambia el resultado automático",
    )
    args = parser.parse_args()
    python = sys.executable
    stages = stage_plan(python, full=args.full)
    if args.list:
        print(json.dumps([
            {"stage": item.stage, "description": item.description, "manualGate": item.manual_gate}
            for item in stages
        ], ensure_ascii=False, indent=2))
        return
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    manual_dir = args.manual_dir if args.manual_dir.is_absolute() else ROOT / args.manual_dir
    if "SNAPASSIST_BUILD_PYTHON" not in env:
        for candidate in (python, "/usr/bin/python3"):
            available = subprocess.run(
                [candidate, "-c", "import pip, setuptools"],
                capture_output=True,
            ).returncode == 0
            if available:
                env["SNAPASSIST_BUILD_PYTHON"] = candidate
                break
    report = {
        "schemaVersion": 1,
        "mode": "full" if args.full else "quick",
        "sourceCommit": subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True,
            capture_output=True, check=False,
        ).stdout.strip() or "unknown",
        "stages": [],
    }
    all_passed = True
    for stage in stages:
        if stage.stage == "E8":
            result = validate_bundle(env)
            checks = result.pop("commands", [])
            stage_passed = bool(result["passed"])
            extra = result
        else:
            checks = [run_command(command, env) for command in stage.commands]
            stage_passed = all(check["passed"] for check in checks)
            extra = {}
        manual = load_status(manual_dir, stage.manual_gate)
        report["stages"].append({
            "stage": stage.stage,
            "description": stage.description,
            "automatic": "passed" if stage_passed else "failed",
            "manualGate": stage.manual_gate,
            "manualStatus": manual["status"],
            "manualEvidence": manual,
            "checks": checks,
            **extra,
        })
        all_passed &= stage_passed
        print(f"{stage.stage}: {'PASS' if stage_passed else 'FAIL'} — {stage.description}")
        if not stage_passed:
            break
    report["automaticPassed"] = all_passed
    report["manualPassed"] = len(report["stages"]) == len(stages) and all(
        item["manualStatus"] == "approved" for item in report["stages"]
    )
    payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(payload)
    raise SystemExit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
