"""Soak corto de CI; el recorrido largo vive en scripts/run-soak.py."""

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from importlib.util import module_from_spec, spec_from_file_location


def load_soak_module():
    spec = spec_from_file_location("snapassist_soak", ROOT / "scripts/run-soak.py")
    module = module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_reconnect_soak_releases_every_subscription():
    report = load_soak_module().run(500, 7)
    assert report["cycles"] == 500
    assert report["reconnects"] == 71
    assert report["subscriptions_after_disconnect"] == 0
    assert report["peak_bytes"] >= report["retained_bytes"]


def run_all_tests():
    test_reconnect_soak_releases_every_subscription()
    print("  ✓ test_reconnect_soak_releases_every_subscription")


if __name__ == "__main__":
    run_all_tests()
