#!/usr/bin/env python3
"""Crea y valida evidencia estructurada de las puertas manuales U0-U8."""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
VALID_GATES = tuple(f"U{index}" for index in range(9))
VALID_RESULTS = ("approved", "rejected")


def current_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True,
        capture_output=True, check=False,
    )
    return result.stdout.strip() or "unknown"


def validate_evidence(payload: object, gate: str) -> list[str]:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return ["la evidencia debe ser un objeto JSON"]
    required_strings = ("gate", "result", "date", "commit", "session", "tester", "notes")
    for field in required_strings:
        if not isinstance(payload.get(field), str) or not payload[field].strip():
            errors.append(f"campo requerido vacío: {field}")
    if payload.get("gate") != gate:
        errors.append(f"gate debe ser {gate}")
    if payload.get("result") not in VALID_RESULTS:
        errors.append("result debe ser approved o rejected")
    checks = payload.get("checks")
    if not isinstance(checks, list) or not checks:
        errors.append("checks debe contener al menos una comprobación")
    elif any(not isinstance(item, dict) or not isinstance(item.get("name"), str)
             or not isinstance(item.get("passed"), bool) for item in checks):
        errors.append("cada check requiere name (texto) y passed (booleano)")
    elif payload.get("result") == "approved" and not all(item["passed"] for item in checks):
        errors.append("una puerta aprobada no puede contener checks fallidos")
    evidence = payload.get("evidence")
    if not isinstance(evidence, list) or not evidence or not all(
        isinstance(item, str) and item.strip() for item in evidence
    ):
        errors.append("evidence debe contener al menos una referencia no vacía")
    return errors


def load_status(directory: Path, gate: str) -> dict[str, object]:
    path = directory / f"{gate}.json"
    if not path.is_file():
        return {"status": "pending", "path": str(path), "errors": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return {"status": "invalid", "path": str(path), "errors": [str(error)]}
    errors = validate_evidence(payload, gate)
    return {
        "status": "invalid" if errors else payload["result"],
        "path": str(path),
        "errors": errors,
        "evidence": payload if not errors else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("gate", choices=VALID_GATES)
    parser.add_argument("--directory", type=Path, default=Path("artifacts/manual-validation"))
    parser.add_argument("--init", action="store_true", help="crear plantilla sin aprobarla")
    parser.add_argument("--check", action="store_true", help="validar evidencia existente")
    args = parser.parse_args()
    directory = args.directory if args.directory.is_absolute() else ROOT / args.directory
    path = directory / f"{args.gate}.json"
    if args.init:
        if path.exists():
            raise SystemExit(f"No se sobrescribe evidencia existente: {path}")
        directory.mkdir(parents=True, exist_ok=True)
        payload = {
            "schemaVersion": 1,
            "gate": args.gate,
            "result": "rejected",
            "date": datetime.now(timezone.utc).isoformat(),
            "commit": current_commit(),
            "session": "X11 o Wayland",
            "tester": "nombre",
            "checks": [{"name": "describir comprobación", "passed": False}],
            "evidence": ["ruta a log, captura o informe"],
            "notes": "editar y cambiar result a approved solo tras completar la guía",
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(path)
        return
    status = load_status(directory, args.gate)
    print(json.dumps(status, ensure_ascii=False, indent=2))
    raise SystemExit(0 if status["status"] in VALID_RESULTS else 1)


if __name__ == "__main__":
    main()
