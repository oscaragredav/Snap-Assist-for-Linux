"""Regresiones del sondeo que recupera GNOME tras bloquear la sesión."""

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from snapassist.gnome_main import heartbeat
from snapassist.runtime.gnome_client import ProtocolDisconnected


class RecoveringClient:
    def __init__(self, error):
        self.error = error
        self.calls = 0

    def ensure_connected(self):
        self.calls += 1
        if self.calls == 1:
            raise self.error
        return object()


def test_heartbeat_survives_disconnect_and_recovers_on_next_probe():
    client = RecoveringClient(ProtocolDisconnected("extensión retirada"))
    assert heartbeat(client) is True
    assert heartbeat(client) is True
    assert client.calls == 2


def test_heartbeat_survives_an_unexpected_transport_exception():
    client = RecoveringClient(RuntimeError("fallo D-Bus no clasificado"))
    assert heartbeat(client) is True
    assert heartbeat(client) is True
    assert client.calls == 2


def run_all_tests():
    tests = [
        test_heartbeat_survives_disconnect_and_recovers_on_next_probe,
        test_heartbeat_survives_an_unexpected_transport_exception,
    ]
    for test in tests:
        test()
        print(f"  ✓ {test.__name__}")


if __name__ == "__main__":
    run_all_tests()
