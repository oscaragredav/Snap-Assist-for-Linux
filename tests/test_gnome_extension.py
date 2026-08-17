"""Contratos estáticos y módulos puros del spike GNOME Shell 46."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
EXTENSION = ROOT / "gnome-extension"


def test_metadata_targets_isolated_gnome_46_test_extension():
    metadata = json.loads((EXTENSION / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["uuid"] == "snapassist-test@oscaragredav"
    assert metadata["shell-version"] == ["46"]
    assert metadata["settings-schema"] == "org.snapassist.shell.test"
    assert metadata["version"] == 1


def test_extension_has_cleanup_and_test_only_ipc_contract():
    extension = (EXTENSION / "extension.js").read_text(encoding="utf-8")
    presentation = (EXTENSION / "lib" / "native-presentation.js").read_text(
        encoding="utf-8"
    )
    protocol = (EXTENSION / "lib" / "protocol.js").read_text(encoding="utf-8")
    confirmation = (EXTENSION / "lib" / "move-resize-confirmation.js").read_text(
        encoding="utf-8"
    )
    for required in (
        "Main.wm.addKeybinding",
        "Main.wm.removeKeybinding",
        "Gio.DBusExportedObject.wrapJSObject",
        "this._dbusObject?.unexport()",
        "Gio.bus_unown_name",
        "notify::focus-window",
        "window-created",
        "active-workspace-changed",
        "window-closed",
        "window-changed",
        "grab-op-end",
        "window-dragged",
        "window-resized",
        "removeChrome",
        "OperationStore",
        "PlatformEvent",
        "OperationCompleted",
        "UiAction",
        "NativePresentation",
        "animateWindow",
        "enable_animations",
        "window.unminimize()",
        "window.unmaximize(Meta.MaximizeFlags.BOTH)",
        "monitorForRect(x, y, width, height)",
        "window.move_to_monitor(targetMonitor)",
        "window.move_resize_frame(false, target.x, target.y, target.width, target.height)",
        "window.move_frame(false, target.x, target.y)",
        "Main.activateWindow(window, global.get_current_time())",
        "MoveResizeAsync(params, invocation)",
        "GLib.timeout_add",
        "requiredStableSamples = 2",
        "tolerance = 1",
        "constraint-rejected",
        "requestedGeometry",
        "observedGeometry",
        "this._pendingMoveResizes",
        "cancelPendingMoveResizes",
        "this._dbusService?.destroy()",
        "!sample.maximizedHorizontally",
        "!sample.maximizedVertically",
        "restored",
    ):
        assert required in extension + presentation + confirmation
    assert "org.snapassist.Shell.Test" in protocol
    assert "org.snapassist.Shell1" in protocol
    assert "endpointForChannel('test')" in protocol
    assert "endpointForChannel('stable')" not in protocol
    assert "move_resize_frame(true" not in extension
    assert "_SETTLE_DELAYS" not in (ROOT / "snapassist" / "adapters" / "gnome_runtime.py").read_text(encoding="utf-8")


def test_canonical_dbus_contract_matches_extension_copy():
    canonical = ROOT / "protocol" / "org.snapassist.Shell1.xml"
    extension_copy = EXTENSION / "protocol" / "org.snapassist.Shell1.xml"
    canonical_root = ET.parse(canonical).getroot()
    extension_root = ET.parse(extension_copy).getroot()

    def signature(root):
        interface = root.find("interface")
        return (
            interface.attrib["name"],
            [
                (
                    child.tag,
                    child.attrib["name"],
                    [
                        (arg.attrib.get("name"), arg.attrib["type"], arg.attrib.get("direction"))
                        for arg in child.findall("arg")
                    ],
                )
                for child in interface
                if child.tag in {"method", "signal"}
            ],
        )

    assert signature(canonical_root) == signature(extension_root)


def test_protocol_module_with_gjs_when_available():
    gjs = shutil.which("gjs")
    if not gjs:
        print("  - gjs no disponible; módulo puro validado por CI GNOME")
        return
    result = subprocess.run(
        [gjs, "-m", str(EXTENSION / "tests" / "protocol.test.js")],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "GNOME protocol module tests passed" in result.stdout

    result = subprocess.run(
        [gjs, "-m", str(EXTENSION / "tests" / "operation-store.test.js")],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "GNOME operation store tests passed" in result.stdout

    result = subprocess.run(
        [gjs, "-m", str(EXTENSION / "tests" / "move-resize-confirmation.test.js")],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "GNOME move-resize confirmation tests passed" in result.stdout

    result = subprocess.run(
        [gjs, "-m", str(EXTENSION / "tests" / "settings-document.test.js")],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "GNOME settings document tests passed" in result.stdout

    env = dict(os.environ, SNAPASSIST_DBUS_XML=str(ROOT / "protocol" / "org.snapassist.Shell1.xml"))
    result = subprocess.run(
        [gjs, "-m", str(EXTENSION / "tests" / "introspection.test.js")],
        cwd=ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "GNOME D-Bus introspection tests passed" in result.stdout


def test_gsettings_schema_compiles_strictly_when_tool_is_available():
    compiler = shutil.which("glib-compile-schemas")
    if not compiler:
        print("  - glib-compile-schemas no disponible; schema validado por CI GNOME")
        return
    with tempfile.TemporaryDirectory(prefix="snapassist-schema-") as temp:
        destination = Path(temp)
        shutil.copy2(
            EXTENSION / "schemas" / "org.snapassist.shell.test.gschema.xml",
            destination,
        )
        subprocess.run(
            [compiler, "--strict", str(destination)],
            cwd=ROOT,
            check=True,
            capture_output=True,
        )
        assert (destination / "gschemas.compiled").is_file()
        gsettings = shutil.which("gsettings")
        if gsettings:
            result = subprocess.run(
                [
                    gsettings,
                    "--schemadir",
                    str(destination),
                    "list-keys",
                    "org.snapassist.shell.test",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            assert set(result.stdout.split()) == {
                "show-layouts",
                "show-snap-groups",
                "show-help",
            }


def test_extension_bundle_contains_runtime_sources_when_packager_is_available():
    packager = shutil.which("gnome-extensions")
    if not packager:
        print("  - gnome-extensions no disponible; bundle validado por CI GNOME")
        return
    with tempfile.TemporaryDirectory(prefix="snapassist-extension-") as temp:
        subprocess.run(
            ["bash", str(ROOT / "scripts" / "build-gnome-extension.sh"), temp],
            cwd=ROOT,
            check=True,
            capture_output=True,
        )
        archive = Path(temp) / "snapassist-test@oscaragredav.shell-extension.zip"
        with zipfile.ZipFile(archive) as bundle:
            names = set(bundle.namelist())
        for required in (
            "metadata.json",
            "extension.js",
            "prefs.js",
            "stylesheet.css",
            "lib/protocol.js",
            "lib/snapshot.js",
            "lib/operation-store.js",
            "lib/settings-document.js",
            "protocol/org.snapassist.Shell1.xml",
            "schemas/org.snapassist.shell.test.gschema.xml",
        ):
            assert required in names


def test_preferences_are_visual_and_creation_is_null_safe():
    prefs = (EXTENSION / "prefs.js").read_text(encoding="utf-8")
    presentation = (EXTENSION / "lib/native-presentation.js").read_text(
        encoding="utf-8"
    )
    for required in (
        "Gtk.GestureClick",
        "presetZones",
        "Dividir lado a lado",
        "Dividir arriba y abajo",
        "source !== null",
        "nextCustomId",
        "Cambios guardados y enviados a SnapAssist",
    ):
        assert required in prefs
    assert "Gtk.TextView" not in prefs
    assert "Gtk.SpinButton" not in prefs
    assert "Gtk.Scale" not in prefs
    assert "Proporción" not in prefs
    assert "description:" not in prefs
    assert "captured-event" in presentation
    assert "global.stage.connect('captured-event'" in presentation
    assert "event.get_coords()" in presentation
    assert "get_transformed_position()" in presentation
    assert "global.stage.disconnect(this._stageCaptureId)" in presentation
    assert "ensureVisibleInScrollView" in presentation


def run_all_tests():
    tests = [
        test_metadata_targets_isolated_gnome_46_test_extension,
        test_extension_has_cleanup_and_test_only_ipc_contract,
        test_canonical_dbus_contract_matches_extension_copy,
        test_protocol_module_with_gjs_when_available,
        test_gsettings_schema_compiles_strictly_when_tool_is_available,
        test_extension_bundle_contains_runtime_sources_when_packager_is_available,
        test_preferences_are_visual_and_creation_is_null_safe,
    ]
    for test in tests:
        test()
        print(f"  ✓ {test.__name__}")


if __name__ == "__main__":
    run_all_tests()
