"""Contrato del bundle conjunto y su reproducibilidad binaria."""

import hashlib
import io
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def build_python():
    for candidate in (sys.executable, "/usr/bin/python3"):
        result = subprocess.run(
            [candidate, "-c", "import pip, setuptools"],
            capture_output=True,
        )
        if result.returncode == 0:
            return candidate
    return None


def test_release_bundle_is_joint_checksummed_and_reproducible():
    if not shutil.which("gnome-extensions") or not build_python():
        print("  - toolchain de release no disponible; validada en CI GNOME")
        return
    with tempfile.TemporaryDirectory(prefix="snapassist-release-test-") as temp:
        first = Path(temp) / "first"
        second = Path(temp) / "second"
        env = {**__import__("os").environ, "SNAPASSIST_BUILD_PYTHON": build_python()}
        for output in (first, second):
            subprocess.run(
                ["bash", str(ROOT / "scripts/build-release.sh"), str(output)],
                cwd=ROOT,
                env=env,
                check=True,
                capture_output=True,
            )
        bundle_name = "snapassist-2.0.0.dev0-bundle.tar.gz"
        first_bytes = (first / bundle_name).read_bytes()
        assert first_bytes == (second / bundle_name).read_bytes()
        with tarfile.open(fileobj=io.BytesIO(first_bytes), mode="r:gz") as bundle:
            members = {
                member.name.removeprefix("./"): bundle.extractfile(member).read()
                for member in bundle.getmembers()
                if member.isfile()
            }
        required = {
            "release-manifest.json",
            "SHA256SUMS",
            "snapassist-2.0.0.dev0-py3-none-any.whl",
            "snapassist-2.0.0.dev0-source.tar.gz",
            "snapassist-test@oscaragredav.shell-extension.zip",
            "snapassist@oscaragredav.shell-extension.zip",
        }
        assert required <= set(members)
        manifest = json.loads(members["release-manifest.json"])
        assert manifest["version"] == "2.0.0.dev0"
        assert manifest["baselineCommit"] == "77a6e66"
        for line in members["SHA256SUMS"].decode().splitlines():
            expected, name = line.split(None, 1)
            assert hashlib.sha256(members[name]).hexdigest() == expected
        with zipfile.ZipFile(io.BytesIO(members["snapassist@oscaragredav.shell-extension.zip"])) as extension:
            metadata = json.loads(extension.read("metadata.json"))
            assert metadata["snapassist-channel"] == "stable"
            assert "schemas/org.snapassist.shell.gschema.xml" in extension.namelist()


def run_all_tests():
    test_release_bundle_is_joint_checksummed_and_reproducible()
    print("  ✓ test_release_bundle_is_joint_checksummed_and_reproducible")


if __name__ == "__main__":
    run_all_tests()
