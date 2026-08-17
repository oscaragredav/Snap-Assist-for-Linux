#!/usr/bin/env python3
"""Smoke read-only del protocolo GNOME en una sesión real."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from snapassist.adapters.gnome_dbus import DbusUnavailable, GnomeDbusTransport
from snapassist.runtime.gnome_client import GnomeProtocolClient, ProtocolError


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--json",
        action="store_true",
        help="imprime un resumen JSON apto para adjuntar a U2/U4",
    )
    args = parser.parse_args()

    client = GnomeProtocolClient(GnomeDbusTransport())
    try:
        info = client.connect()
        snapshot = client.get_snapshot()
    except (DbusUnavailable, ProtocolError, OSError) as error:
        print(f"SnapAssist GNOME: {error}", file=sys.stderr)
        return 1
    finally:
        if client.connected:
            client.disconnect()

    result = {
        "protocol_version": info.protocol_version,
        "session_id": info.session_id,
        "interface": info.interface_name,
        "snapshot_sequence": snapshot.sequence,
        "windows": len(snapshot.windows),
        "monitors": len(snapshot.monitors),
        "active_window": snapshot.active_window,
        "active_workspace": snapshot.active_workspace,
        "capability_candidates": sorted(info.capability_candidates),
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(
            "SnapAssist GNOME conectado: "
            f"protocolo={info.protocol_version} "
            f"ventanas={len(snapshot.windows)} "
            f"monitores={len(snapshot.monitors)}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
