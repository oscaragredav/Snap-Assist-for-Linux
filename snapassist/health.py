"""Health-check read-only para la integración GNOME instalada."""

from __future__ import annotations

import argparse
import json
import time
from collections.abc import Callable

from snapassist.adapters.gnome_dbus import DbusUnavailable, GnomeDbusTransport
from snapassist.runtime.gnome_client import GnomeProtocolClient, ProtocolError


def wait_for_gnome(
    transport_factory: Callable[[], object] = GnomeDbusTransport,
    *,
    timeout: float = 3.0,
    interval: float = 0.2,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, object]:
    """Espera handshake+snapshot sin ejecutar operaciones sobre ventanas."""
    deadline = clock() + timeout
    last_error: Exception | None = None
    attempts = 0
    while True:
        attempts += 1
        client = GnomeProtocolClient(transport_factory())
        try:
            info = client.connect()
            snapshot = client.get_snapshot()
            return {
                "healthy": True,
                "attempts": attempts,
                "protocolVersion": info.protocol_version,
                "sessionId": info.session_id,
                "snapshotSequence": snapshot.sequence,
            }
        except (DbusUnavailable, ProtocolError, OSError) as error:
            last_error = error
        finally:
            client.disconnect()
        now = clock()
        if now >= deadline:
            raise RuntimeError(
                f"runtime GNOME no saludable tras {attempts} intentos: {last_error}"
            ) from last_error
        sleep(min(interval, max(0.0, deadline - now)))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout", type=float, default=3.0)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout debe ser positivo")
    try:
        report = wait_for_gnome(timeout=args.timeout)
    except RuntimeError as error:
        raise SystemExit(str(error)) from error
    if args.json:
        print(json.dumps(report, sort_keys=True))
    else:
        print(
            "GNOME saludable: "
            f"protocolo={report['protocolVersion']} sesión={report['sessionId']}"
        )


if __name__ == "__main__":
    main()
