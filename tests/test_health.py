"""Health-check GNOME read-only con reintentos deterministas."""

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from snapassist.health import wait_for_gnome
from snapassist.runtime import ProtocolDisconnected


class HealthTransport:
    failures = 0

    def __init__(self):
        self.connected = False

    def connect(self):
        if type(self).failures:
            type(self).failures -= 1
            raise ProtocolDisconnected("todavía sin owner")
        self.connected = True

    def disconnect(self): self.connected = False

    def subscribe(self, _signal, _callback): return lambda: None

    def call(self, method, *_args):
        if method == "GetProtocolInfo":
            return json.dumps({
                "protocolVersion": 1,
                "minimumClientVersion": 1,
                "sessionId": "health-session",
                "interfaceName": "org.snapassist.Shell1",
                "capabilityCandidates": [],
            })
        if method == "GetSnapshot":
            return json.dumps({
                "sessionId": "health-session",
                "sequence": 4,
                "activeWindow": None,
                "activeWorkspace": "workspace:0",
                "windows": [],
                "monitors": [],
            })
        raise AssertionError(f"health ejecutó operación mutante: {method}")


def test_health_retries_and_only_reads_handshake_snapshot():
    HealthTransport.failures = 2
    now = [0.0]

    def clock(): return now[0]
    def sleep(seconds): now[0] += seconds

    report = wait_for_gnome(
        HealthTransport,
        timeout=2,
        interval=0.1,
        clock=clock,
        sleep=sleep,
    )
    assert report["healthy"]
    assert report["attempts"] == 3
    assert report["snapshotSequence"] == 4


def run_all_tests():
    test_health_retries_and_only_reads_handshake_snapshot()
    print("  ✓ test_health_retries_and_only_reads_handshake_snapshot")


if __name__ == "__main__":
    run_all_tests()
