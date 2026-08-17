#!/usr/bin/env python3
"""Diagnóstico real y autocontenido de geometría para GNOME Terminal."""

from __future__ import annotations

import argparse
import json
import subprocess
import time
import uuid

from snapassist.adapters.gnome_dbus import GnomeDbusTransport
from snapassist.runtime import LogicalRect
from snapassist.runtime.gnome_client import GnomeProtocolClient


TITLE = f"SnapAssist QA Terminal {uuid.uuid4().hex[:8]}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot-only", action="store_true")
    parser.add_argument(
        "--maximize-before-move",
        action="store_true",
        help="maximiza la Terminal temporal antes de MoveResize para verificar la transición real",
    )
    args = parser.parse_args()
    if args.snapshot_only:
        client = GnomeProtocolClient(GnomeDbusTransport())
        try:
            client.connect()
            snapshot = client.get_snapshot()
            terminals = [item for item in snapshot.windows if "terminal" in (
                f"{item.app_id} {item.app_name} {item.title}".lower()
            )]
            print(json.dumps({
                "activeWindow": snapshot.active_window,
                "activeWorkspace": snapshot.active_workspace,
                "terminals": [
                    {
                        "handle": item.handle,
                        "title": item.title,
                        "appId": item.app_id,
                        "appName": item.app_name,
                        "geometry": item.geometry.__dict__,
                        "workspace": item.workspace,
                        "monitor": item.monitor,
                        "minimized": item.minimized,
                        "maximized": item.maximized,
                        "maximizedHorizontally": item.maximized_horizontally,
                        "maximizedVertically": item.maximized_vertically,
                        "clientType": item.client_type,
                        "minimumSize": item.minimum_size,
                        "eligible": item.eligible,
                    }
                    for item in terminals
                ],
            }, ensure_ascii=False, indent=2))
        finally:
            client.disconnect()
        return
    terminal = subprocess.Popen(
        ["gnome-terminal", "--wait", f"--title={TITLE}", "--", "bash", "-c", "sleep 12"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    client = GnomeProtocolClient(GnomeDbusTransport())
    try:
        client.connect()
        window = None
        snapshot = None
        for _attempt in range(50):
            snapshot = client.get_snapshot()
            window = next((item for item in snapshot.windows if item.title == TITLE), None)
            if window:
                break
            time.sleep(0.1)
        if window is None or snapshot is None:
            raise RuntimeError("GNOME Terminal temporal no apareció en el snapshot")
        monitor = next(item for item in snapshot.monitors if item.handle == window.monitor)
        area = monitor.work_area
        target = LogicalRect(area.x, area.y, area.width // 2, area.height)
        before_move = []
        if args.maximize_before_move:
            client.set_maximized(
                f"terminal-qa-maximize:{uuid.uuid4()}",
                window.handle,
                True,
            )
            for _attempt in range(20):
                current_snapshot = client.get_snapshot()
                current = next(
                    item for item in current_snapshot.windows
                    if item.handle == window.handle
                )
                before_move.append({
                    "geometry": current.geometry.__dict__,
                    "maximizedHorizontally": current.maximized_horizontally,
                    "maximizedVertically": current.maximized_vertically,
                    "active": current_snapshot.active_window == window.handle,
                })
                if current.maximized_horizontally and current.maximized_vertically:
                    break
                time.sleep(0.05)
        result = client.move_resize(f"terminal-qa:{uuid.uuid4()}", window.handle, target)
        samples = []
        for delay in (0.05, 0.2, 0.5, 1.0):
            time.sleep(delay)
            current_snapshot = client.get_snapshot()
            current = next(
                item for item in current_snapshot.windows if item.handle == window.handle
            )
            samples.append({
                "afterSeconds": delay,
                "geometry": current.geometry.__dict__,
                "maximizedHorizontally": current.maximized_horizontally,
                "maximizedVertically": current.maximized_vertically,
                "active": current_snapshot.active_window == window.handle,
            })
        print(json.dumps({
            "accepted": result.accepted,
            "status": result.status,
            "error": result.error_code,
            "constraint": result.constraint,
            "requestedGeometry": (
                result.requested_geometry.__dict__
                if result.requested_geometry else None
            ),
            "observedGeometry": (
                result.observed_geometry.__dict__
                if result.observed_geometry else None
            ),
            "attempts": result.attempts,
            "confirmationMs": result.confirmation_ms,
            "confirmationObservations": list(result.observations),
            "clientType": window.client_type,
            "monitorScale": monitor.scale,
            "minimumSize": window.minimum_size,
            "original": window.geometry.__dict__,
            "beforeMove": before_move,
            "target": target.__dict__,
            "samples": samples,
        }, ensure_ascii=False, indent=2))
    finally:
        client.disconnect()
        try:
            terminal.wait(timeout=13)
        except subprocess.TimeoutExpired:
            terminal.terminate()


if __name__ == "__main__":
    main()
