#!/usr/bin/env python3
"""Stress reproducible del cliente IPC sin necesitar una sesión gráfica."""

from __future__ import annotations

import argparse
import gc
import json
import sys
import tracemalloc
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from snapassist.runtime import GnomeProtocolClient, ProtocolDisconnected


class SoakTransport:
    def __init__(self) -> None:
        self.connected = False
        self.generation = 0
        self.callbacks: dict[str, list] = {}
        self.disconnect_next = False

    @property
    def session_id(self) -> str:
        return f"soak-session:{self.generation}"

    def connect(self) -> None:
        self.connected = True

    def disconnect(self) -> None:
        self.connected = False

    def subscribe(self, signal, callback):
        self.callbacks.setdefault(signal, []).append(callback)

        def unsubscribe():
            callbacks = self.callbacks.get(signal, [])
            if callback in callbacks:
                callbacks.remove(callback)

        return unsubscribe

    def call(self, method, *args):
        if not self.connected:
            raise ProtocolDisconnected("soak disconnect")
        if self.disconnect_next and method != "GetProtocolInfo":
            self.disconnect_next = False
            self.connected = False
            self.generation += 1
            raise ProtocolDisconnected("soak injected reconnect")
        if method == "GetProtocolInfo":
            return json.dumps({
                "protocolVersion": 1,
                "minimumClientVersion": 1,
                "sessionId": self.session_id,
                "interfaceName": "org.snapassist.Shell1",
                "capabilityCandidates": ["active-window", "move-resize"],
            })
        operation_id = str(args[0])
        return json.dumps({
            "operationId": operation_id,
            "accepted": True,
            "errorCode": None,
            "message": "",
            "sessionId": self.session_id,
        })


def run(cycles: int, reconnect_every: int) -> dict[str, int]:
    transport = SoakTransport()
    client = GnomeProtocolClient(transport)
    received = []
    unsubscribe = client.subscribe_operations(received.append)
    client.connect()
    tracemalloc.start()
    baseline, _peak = tracemalloc.get_traced_memory()
    reconnects = 0
    for index in range(cycles):
        if reconnect_every and index and index % reconnect_every == 0:
            transport.disconnect_next = True
            reconnects += 1
        result = client.activate(f"soak:{index}", "mutter:1")
        if not result.accepted:
            raise RuntimeError(f"operación rechazada en ciclo {index}")
        if index % 100 == 0:
            gc.collect()
    unsubscribe()
    client.disconnect()
    gc.collect()
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    residues = sum(len(items) for items in transport.callbacks.values())
    if residues:
        raise RuntimeError(f"quedaron {residues} suscripciones IPC")
    return {
        "cycles": cycles,
        "reconnects": reconnects,
        "subscriptions_after_disconnect": residues,
        "retained_bytes": max(0, current - baseline),
        "peak_bytes": peak,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cycles", type=int, default=10_000)
    parser.add_argument("--reconnect-every", type=int, default=17)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.cycles < 1 or args.reconnect_every < 0:
        parser.error("los ciclos deben ser positivos y reconnect-every no negativo")
    report = run(args.cycles, args.reconnect_every)
    if args.json:
        print(json.dumps(report, sort_keys=True))
    else:
        for key, value in report.items():
            print(f"{key}: {value}")


if __name__ == "__main__":
    main()
