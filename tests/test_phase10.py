"""Pruebas automatizadas de Fase 10: empaquetado e instalación idempotente."""

import os
import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def test_pointer_listener_is_disabled_during_idle():
    from snapassist.core.hotkeys import HotkeyManager

    manager = HotkeyManager(pointer_event_queue=object())
    assert manager._pointer_listener is None
    # Desactivar el modo idle es un no-op y no importa pynput/X11.
    manager.set_pointer_tracking(False)
    assert manager._pointer_listener is None


def test_dependencies_are_exactly_pinned():
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
    pins = {line for line in requirements if line and not line.startswith("#")}
    assert pins == {"python-xlib==0.33", "pynput==1.8.2", "ewmh==0.1.6"}


def test_service_has_lifecycle_contract():
    unit = (ROOT / "snapassist.service").read_text(encoding="utf-8")
    for required in (
        "After=graphical-session.target",
        "WantedBy=graphical-session.target",
        "Restart=on-failure",
        "RestartSec=3",
        "Conflicts=@CONFLICT_UNIT@",
        "EnvironmentFile=-@ENV_FILE@",
        'Environment="SNAPASSIST_CHANNEL=@CHANNEL@"',
        'Environment="SNAPASSIST_LOG_DIR=@LOG_DIR@"',
        'Environment="SNAPASSIST_CONFIG_FILE=@SETTINGS_FILE@"',
        "@EXEC_START_PRE@",
        "ExecStart=@EXEC_START@",
        "WorkingDirectory=@INSTALL_DIR@",
    ):
        assert required in unit
    assert 'WorkingDirectory="@INSTALL_DIR@"' not in unit
    assert 'EnvironmentFile=-"@ENV_FILE@"' not in unit


def test_stable_install_uses_transactional_channel_activation():
    installer = (ROOT / "install.sh").read_text(encoding="utf-8")
    assert '"${BIN_HOME}/snapassist-channel" stable' in installer
    assert 'systemctl --user restart "${UNIT_NAME}"' not in installer


def test_installer_is_idempotent_in_an_isolated_tree():
    with tempfile.TemporaryDirectory(prefix="snapassist-phase10-") as temp:
        base = Path(temp)
        env = dict(
            os.environ,
            SNAPASSIST_DATA_HOME=str(base / "share"),
            SNAPASSIST_CONFIG_HOME=str(base / "config"),
            SNAPASSIST_BIN_HOME=str(base / "bin"),
            SNAPASSIST_SKIP_PIP="1",
            SNAPASSIST_SKIP_SYSTEMD="1",
        )
        command = ["bash", str(ROOT / "install.sh"), "--promote"]
        subprocess.run(command, cwd=ROOT, env=env, check=True, capture_output=True)
        installed = base / "share" / "snapassist"
        unit = base / "config" / "systemd" / "user" / "snapassist.service"
        assert (installed / "snapassist" / "main.py").is_file()
        assert (installed / "snapassist" / "wait_for_x11.py").is_file()
        assert (installed / "requirements.txt").is_file()
        unit_text = unit.read_text(encoding="utf-8")
        assert str(installed) in unit_text
        assert str(base / "config" / "snapassist" / "environment") in unit_text
        assert "Conflicts=snapassist-test.service" in unit_text
        assert 'Environment="SNAPASSIST_CHANNEL=stable"' in unit_text
        assert str(installed / "logs") in unit_text
        assert str(base / "config" / "snapassist" / "settings.json") in unit_text
        assert "@INSTALL_DIR@" not in unit_text
        manifest = (installed / "install-manifest").read_text(encoding="utf-8")
        assert "channel=stable" in manifest
        assert "version=2.0.0.dev0" in manifest
        assert "source_dirty=" in manifest
        assert "installed_at_utc=" in manifest
        assert (base / "bin" / "snapassist-channel").stat().st_mode & 0o111

        first_main = (installed / "snapassist" / "main.py").read_bytes()
        subprocess.run(command, cwd=ROOT, env=env, check=True, capture_output=True)
        assert (installed / "snapassist" / "main.py").read_bytes() == first_main


def test_development_tree_cannot_overwrite_stable_without_promotion():
    with tempfile.TemporaryDirectory(prefix="snapassist-no-promote-") as temp:
        base = Path(temp)
        env = dict(
            os.environ,
            SNAPASSIST_DATA_HOME=str(base / "share"),
            SNAPASSIST_CONFIG_HOME=str(base / "config"),
            SNAPASSIST_BIN_HOME=str(base / "bin"),
            SNAPASSIST_SKIP_PIP="1",
            SNAPASSIST_SKIP_SYSTEMD="1",
        )
        result = subprocess.run(
            ["bash", str(ROOT / "install.sh"), "--channel", "stable"],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1
        assert "no se sobrescribirá stable" in result.stderr
        assert not (base / "share/snapassist").exists()


def test_test_channel_is_fully_isolated_from_stable():
    with tempfile.TemporaryDirectory(prefix="snapassist-channels-") as temp:
        base = Path(temp)
        env = dict(
            os.environ,
            SNAPASSIST_DATA_HOME=str(base / "share"),
            SNAPASSIST_CONFIG_HOME=str(base / "config"),
            SNAPASSIST_BIN_HOME=str(base / "bin"),
            SNAPASSIST_SKIP_PIP="1",
            SNAPASSIST_SKIP_SYSTEMD="1",
        )
        stable_command = [
            "bash", str(ROOT / "install.sh"), "--channel", "stable", "--promote"
        ]
        test_command = ["bash", str(ROOT / "install.sh"), "--channel", "test"]
        subprocess.run(stable_command, cwd=ROOT, env=env, check=True, capture_output=True)
        stable_main = base / "share" / "snapassist" / "snapassist" / "main.py"
        stable_bytes = stable_main.read_bytes()

        subprocess.run(test_command, cwd=ROOT, env=env, check=True, capture_output=True)

        test_root = base / "share" / "snapassist-test"
        test_unit = (
            base / "config" / "systemd" / "user" / "snapassist-test.service"
        ).read_text(encoding="utf-8")
        assert stable_main.read_bytes() == stable_bytes
        assert (test_root / "snapassist" / "main.py").is_file()
        assert "Conflicts=snapassist.service" in test_unit
        assert 'Environment="SNAPASSIST_CHANNEL=test"' in test_unit
        assert str(test_root / "logs") in test_unit
        manifest = (test_root / "install-manifest").read_text(encoding="utf-8")
        assert "channel=test" in manifest
        assert "service=snapassist-test.service" in manifest
        assert "extension_uuid=snapassist-test@oscaragredav" in manifest
        assert "runtime=x11" in manifest
        extension = (
            base
            / "share"
            / "gnome-shell"
            / "extensions"
            / "snapassist-test@oscaragredav"
        )
        assert (extension / "metadata.json").is_file()
        assert (extension / "extension.js").is_file()
        assert (extension / "prefs.js").is_file()


def test_test_channel_can_install_gnome_runtime_without_touching_stable():
    with tempfile.TemporaryDirectory(prefix="snapassist-gnome-channel-") as temp:
        base = Path(temp)
        env = dict(
            os.environ,
            SNAPASSIST_DATA_HOME=str(base / "share"),
            SNAPASSIST_CONFIG_HOME=str(base / "config"),
            SNAPASSIST_BIN_HOME=str(base / "bin"),
            SNAPASSIST_SKIP_PIP="1",
            SNAPASSIST_SKIP_SYSTEMD="1",
            SNAPASSIST_RUNTIME="gnome",
        )
        subprocess.run(
            ["bash", str(ROOT / "install.sh"), "--channel", "test"],
            cwd=ROOT,
            env=env,
            check=True,
            capture_output=True,
        )
        unit = (base / "config/systemd/user/snapassist-test.service").read_text()
        assert "ExecStart=/usr/bin/python3 -m snapassist.gnome_main" in unit
        assert f"WorkingDirectory={base}/share/snapassist-test" in unit
        assert 'WorkingDirectory="' not in unit
        assert "wait_for_x11" not in unit
        manifest = (base / "share/snapassist-test/install-manifest").read_text()
        assert "runtime=gnome" in manifest


def test_promoted_stable_gnome_uses_production_extension_identity():
    with tempfile.TemporaryDirectory(prefix="snapassist-stable-gnome-") as temp:
        base = Path(temp)
        env = dict(
            os.environ,
            SNAPASSIST_DATA_HOME=str(base / "share"),
            SNAPASSIST_CONFIG_HOME=str(base / "config"),
            SNAPASSIST_BIN_HOME=str(base / "bin"),
            SNAPASSIST_SKIP_PIP="1",
            SNAPASSIST_SKIP_SYSTEMD="1",
            SNAPASSIST_RUNTIME="gnome",
        )
        subprocess.run(
            ["bash", str(ROOT / "install.sh"), "--channel", "stable", "--promote"],
            cwd=ROOT, env=env, check=True, capture_output=True,
        )
        extension = base / "share/gnome-shell/extensions/snapassist@oscaragredav"
        metadata = json.loads((extension / "metadata.json").read_text())
        assert metadata["snapassist-channel"] == "stable"
        assert metadata["settings-schema"] == "org.snapassist.shell"
        assert (extension / "schemas/org.snapassist.shell.gschema.xml").is_file()
        assert not (extension / "schemas/org.snapassist.shell.test.gschema.xml").exists()
        manifest = (base / "share/snapassist/install-manifest").read_text()
        assert "extension_uuid=snapassist@oscaragredav" in manifest


def test_update_backup_rollback_migration_and_uninstall_are_isolated():
    with tempfile.TemporaryDirectory(prefix="snapassist-lifecycle-") as temp:
        base = Path(temp)
        env = dict(
            os.environ,
            SNAPASSIST_DATA_HOME=str(base / "share"),
            SNAPASSIST_CONFIG_HOME=str(base / "config"),
            SNAPASSIST_BIN_HOME=str(base / "bin"),
            SNAPASSIST_SKIP_PIP="1",
            SNAPASSIST_SKIP_SYSTEMD="1",
        )
        stable_install = ["bash", str(ROOT / "install.sh"), "--promote"]
        test_install = ["bash", str(ROOT / "install.sh"), "--channel", "test"]
        subprocess.run(stable_install, cwd=ROOT, env=env, check=True, capture_output=True)
        subprocess.run(test_install, cwd=ROOT, env=env, check=True, capture_output=True)

        test_main = base / "share/snapassist-test/snapassist/main.py"
        previous = test_main.read_text(encoding="utf-8") + "\n# previous-candidate\n"
        test_main.write_text(previous, encoding="utf-8")
        subprocess.run(test_install, cwd=ROOT, env=env, check=True, capture_output=True)
        assert test_main.read_text(encoding="utf-8") != previous
        subprocess.run(
            ["bash", str(ROOT / "snapassist-manage"), "rollback", "test"],
            cwd=ROOT, env=env, check=True, capture_output=True,
        )
        assert test_main.read_text(encoding="utf-8") == previous

        stable_config = base / "config/snapassist/settings.json"
        stable_config.parent.mkdir(parents=True, exist_ok=True)
        stable_config.write_text(json.dumps({
            "version": 1,
            "shortcuts": {
                "layout_menu": "super+l",
                "snap_groups": "super+alt+tab",
                "help": "super+slash",
            },
            "custom_layouts": [],
            "layout_order": [
                "builtin:half-half", "builtin:two-thirds-left",
                "builtin:two-thirds-right", "builtin:grid-2x2",
                "builtin:main-left", "builtin:three-columns",
            ],
            "disabled_layouts": [],
        }), encoding="utf-8")
        subprocess.run(
            ["bash", str(ROOT / "snapassist-manage"), "migrate", "stable", "test"],
            cwd=ROOT, env=env, check=True, capture_output=True,
        )
        test_config = base / "config/snapassist-test/settings.json"
        assert json.loads(test_config.read_text())["shortcuts"]["layout_menu"] == "super+l"
        subprocess.run(
            ["bash", str(ROOT / "snapassist-manage"), "uninstall", "test"],
            cwd=ROOT, env=env, check=True, capture_output=True,
        )
        assert not (base / "share/snapassist-test").exists()
        assert test_config.exists()
        assert (base / "share/snapassist").exists()


def test_channel_selector_restores_previous_channel_on_failure():
    script = (ROOT / "snapassist-channel").read_text(encoding="utf-8")
    for required in (
        'systemctl --user disable --now "${other_unit}"',
        'systemctl --user enable --now "${target_unit}"',
        'systemctl --user enable --now "${other_unit}"',
        "other_was_active=1",
    ):
        assert required in script

    with tempfile.TemporaryDirectory(prefix="snapassist-selector-") as temp:
        base = Path(temp)
        fake_bin = base / "bin"
        fake_bin.mkdir()
        state_dir = base / "state"
        state_dir.mkdir()
        (state_dir / "snapassist.service.active").touch()
        fake_systemctl = fake_bin / "systemctl"
        fake_systemctl.write_text(
            """#!/usr/bin/env bash
set -euo pipefail
[[ "$1" == "--user" ]] && shift
command="$1"; shift
case "$command" in
  cat) exit 0 ;;
  is-active)
    [[ "${1:-}" == "--quiet" ]] && shift
    [[ -f "$FAKE_STATE_DIR/$1.active" ]]
    ;;
  disable)
    [[ "${1:-}" == "--now" ]] && shift
    rm -f "$FAKE_STATE_DIR/$1.active"
    ;;
  enable)
    [[ "${1:-}" == "--now" ]] && shift
    [[ "$1" != "${FAKE_FAIL_UNIT:-}" ]] || exit 1
    touch "$FAKE_STATE_DIR/$1.active"
    ;;
  *) exit 2 ;;
esac
""",
            encoding="utf-8",
        )
        fake_systemctl.chmod(0o755)
        env = dict(
            os.environ,
            PATH=f"{fake_bin}:{os.environ.get('PATH', '')}",
            FAKE_STATE_DIR=str(state_dir),
            FAKE_FAIL_UNIT="snapassist-test.service",
        )
        result = subprocess.run(
            ["bash", str(ROOT / "snapassist-channel"), "test"],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1
        assert (state_dir / "snapassist.service.active").is_file()
        assert not (state_dir / "snapassist-test.service.active").exists()


def test_channel_selector_rolls_back_service_and_extension_on_unhealthy_gnome():
    with tempfile.TemporaryDirectory(prefix="snapassist-selector-gnome-") as temp:
        base = Path(temp)
        fake_bin = base / "bin"
        state = base / "state"
        data = base / "share"
        fake_bin.mkdir(); state.mkdir()
        (state / "snapassist.service.active").touch()
        (state / "snapassist@oscaragredav.enabled").touch()
        for instance, unit, uuid in (
            ("snapassist", "snapassist.service", "snapassist@oscaragredav"),
            ("snapassist-test", "snapassist-test.service", "snapassist-test@oscaragredav"),
        ):
            root = data / instance
            root.mkdir(parents=True)
            (root / "install-manifest").write_text(
                f"channel={'stable' if instance == 'snapassist' else 'test'}\n"
                "version=2.0.0.dev0\nruntime=gnome\n"
                f"service={unit}\ninstall_dir={root}\nextension_uuid={uuid}\n",
                encoding="utf-8",
            )
        (fake_bin / "systemctl").write_text(
            """#!/usr/bin/env bash
set -euo pipefail
[[ "$1" == "--user" ]] && shift
command="$1"; shift
case "$command" in
  cat) exit 0 ;;
  is-active) [[ "${1:-}" == "--quiet" ]] && shift; [[ -f "$FAKE_STATE_DIR/$1.active" ]] ;;
  disable) [[ "${1:-}" == "--now" ]] && shift; rm -f "$FAKE_STATE_DIR/$1.active" ;;
  enable) [[ "${1:-}" == "--now" ]] && shift; touch "$FAKE_STATE_DIR/$1.active" ;;
  *) exit 2 ;;
esac
""", encoding="utf-8",
        )
        (fake_bin / "gnome-extensions").write_text(
            """#!/usr/bin/env bash
set -euo pipefail
case "$1" in
  list) for file in "$FAKE_STATE_DIR"/*.enabled; do [[ -e "$file" ]] && basename "$file" .enabled; done ;;
  enable) touch "$FAKE_STATE_DIR/$2.enabled" ;;
  disable) rm -f "$FAKE_STATE_DIR/$2.enabled" ;;
  *) exit 2 ;;
esac
""", encoding="utf-8",
        )
        (fake_bin / "health").write_text(
            '#!/usr/bin/env bash\n[[ "$1" != "test" ]]\n',
            encoding="utf-8",
        )
        for executable in ("systemctl", "gnome-extensions", "health"):
            (fake_bin / executable).chmod(0o755)
        env = dict(
            os.environ,
            PATH=f"{fake_bin}:{os.environ.get('PATH', '')}",
            FAKE_STATE_DIR=str(state),
            SNAPASSIST_DATA_HOME=str(data),
            SNAPASSIST_HEALTH_COMMAND=str(fake_bin / "health"),
        )
        result = subprocess.run(
            ["bash", str(ROOT / "snapassist-channel"), "test"],
            cwd=ROOT, env=env, capture_output=True, text=True,
        )
        assert result.returncode == 1
        assert (state / "snapassist.service.active").exists()
        assert not (state / "snapassist-test.service.active").exists()
        assert (state / "snapassist@oscaragredav.enabled").exists()
        assert not (state / "snapassist-test@oscaragredav.enabled").exists()


def test_readme_documents_user_operations():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for required in (
        "bash install.sh",
        "systemctl --user status snapassist",
        "Super+Z",
        "Super+Alt+Tab",
        "Super+/",
        "journalctl --user -u snapassist",
        "Desinstalación",
        "Privacidad",
    ):
        assert required in readme


def run_all_tests():
    tests = [
        test_pointer_listener_is_disabled_during_idle,
        test_dependencies_are_exactly_pinned,
        test_service_has_lifecycle_contract,
        test_stable_install_uses_transactional_channel_activation,
        test_installer_is_idempotent_in_an_isolated_tree,
        test_development_tree_cannot_overwrite_stable_without_promotion,
        test_test_channel_is_fully_isolated_from_stable,
        test_test_channel_can_install_gnome_runtime_without_touching_stable,
        test_promoted_stable_gnome_uses_production_extension_identity,
        test_update_backup_rollback_migration_and_uninstall_are_isolated,
        test_channel_selector_restores_previous_channel_on_failure,
        test_channel_selector_rolls_back_service_and_extension_on_unhealthy_gnome,
        test_readme_documents_user_operations,
    ]
    for test in tests:
        test()
        print(f"  ✓ {test.__name__}")


if __name__ == "__main__":
    run_all_tests()
