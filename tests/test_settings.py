"""Contrato versionado de layouts personalizados y atajos."""

import json
import os
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from snapassist.config import LAYOUT_TEMPLATES
from snapassist.settings import (
    BUILTIN_LAYOUT_IDS,
    DEFAULT_SHORTCUTS,
    RuntimeSettings,
    SettingsEditor,
    SettingsError,
    default_settings_path,
    save_settings_document,
)


def three_column_document():
    return {
        "version": 1,
        "shortcuts": {
            "layout_menu": "super+l",
            "snap_groups": "super+alt+g",
            "help": "super+h",
        },
        "custom_layouts": [
            {
                "id": "custom:three-balanced",
                "name": "Tres equilibradas",
                "zones": [
                    {"x": 0, "y": 0, "w": 0.25, "h": 1},
                    {"x": 0.25, "y": 0, "w": 0.5, "h": 1},
                    {"x": 0.75, "y": 0, "w": 0.25, "h": 1},
                ],
            }
        ],
        "layout_order": ["custom:three-balanced", *BUILTIN_LAYOUT_IDS],
        "disabled_layouts": ["builtin:grid-2x2"],
    }


def test_missing_file_preserves_v11_defaults():
    with tempfile.TemporaryDirectory(prefix="snapassist-settings-") as temp:
        settings = RuntimeSettings.load(Path(temp) / "missing.json")
        assert not settings.loaded_from_file
        assert settings.error is None
        assert settings.shortcuts == DEFAULT_SHORTCUTS
        assert settings.layout_templates == LAYOUT_TEMPLATES


def test_custom_layout_order_disable_and_shortcuts_are_loaded():
    with tempfile.TemporaryDirectory(prefix="snapassist-settings-") as temp:
        path = Path(temp) / "settings.json"
        path.write_text(json.dumps(three_column_document()), encoding="utf-8")
        settings = RuntimeSettings.load(path)
        assert settings.loaded_from_file
        assert settings.error is None
        assert settings.layouts[0].layout_id == "custom:three-balanced"
        assert settings.layouts[0].template.name == "Tres equilibradas"
        assert "builtin:grid-2x2" not in {
            definition.layout_id for definition in settings.layouts
        }
        assert settings.shortcuts["layout_menu"] == "super+l"


def test_invalid_geometry_falls_back_without_rewriting_user_file():
    with tempfile.TemporaryDirectory(prefix="snapassist-settings-") as temp:
        path = Path(temp) / "settings.json"
        document = three_column_document()
        document["custom_layouts"][0]["zones"][1]["x"] = 0.1
        original = json.dumps(document)
        path.write_text(original, encoding="utf-8")
        settings = RuntimeSettings.load(path)
        assert not settings.loaded_from_file
        assert "superpuestas" in settings.error
        assert path.read_text(encoding="utf-8") == original
        assert settings.layout_templates == LAYOUT_TEMPLATES


def test_duplicate_shortcut_falls_back_to_defaults():
    with tempfile.TemporaryDirectory(prefix="snapassist-settings-") as temp:
        path = Path(temp) / "settings.json"
        document = three_column_document()
        document["shortcuts"]["help"] = "super+l"
        path.write_text(json.dumps(document), encoding="utf-8")
        settings = RuntimeSettings.load(path)
        assert "duplicado" in settings.error
        assert settings.shortcuts == DEFAULT_SHORTCUTS


def test_non_finite_geometry_and_unmodified_shortcut_are_rejected():
    with tempfile.TemporaryDirectory(prefix="snapassist-settings-") as temp:
        path = Path(temp) / "settings.json"
        document = three_column_document()
        document["custom_layouts"][0]["zones"][0]["w"] = "NaN"
        path.write_text(json.dumps(document), encoding="utf-8")
        assert "fuera de límites" in RuntimeSettings.load(path).error

        document = three_column_document()
        document["shortcuts"]["help"] = "h"
        path.write_text(json.dumps(document), encoding="utf-8")
        assert "requiere Super" in RuntimeSettings.load(path).error


def test_atomic_save_validates_before_replacing_existing_file():
    with tempfile.TemporaryDirectory(prefix="snapassist-settings-") as temp:
        path = Path(temp) / "settings.json"
        settings = save_settings_document(three_column_document(), path)
        assert settings.loaded_from_file
        assert path.stat().st_mode & 0o777 == 0o600
        first = path.read_text(encoding="utf-8")

        invalid = three_column_document()
        invalid["version"] = 999
        try:
            save_settings_document(invalid, path)
        except SettingsError:
            pass
        else:
            raise AssertionError("se aceptó una versión de configuración inválida")
        assert path.read_text(encoding="utf-8") == first


def test_default_path_is_channel_isolated():
    previous_channel = os.environ.get("SNAPASSIST_CHANNEL")
    previous_config = os.environ.get("SNAPASSIST_CONFIG_FILE")
    try:
        os.environ.pop("SNAPASSIST_CONFIG_FILE", None)
        os.environ["SNAPASSIST_CHANNEL"] = "stable"
        stable = default_settings_path()
        os.environ["SNAPASSIST_CHANNEL"] = "test"
        test = default_settings_path()
        assert stable.name == test.name == "settings.json"
        assert stable.parent.name == "snapassist"
        assert test.parent.name == "snapassist-test"
    finally:
        if previous_channel is None:
            os.environ.pop("SNAPASSIST_CHANNEL", None)
        else:
            os.environ["SNAPASSIST_CHANNEL"] = previous_channel
        if previous_config is None:
            os.environ.pop("SNAPASSIST_CONFIG_FILE", None)
        else:
            os.environ["SNAPASSIST_CONFIG_FILE"] = previous_config


def test_editor_create_duplicate_update_reorder_disable_and_delete():
    editor = SettingsEditor()
    zones = three_column_document()["custom_layouts"][0]["zones"]
    editor.create_layout("custom:three", "Tres", zones, position=0)
    assert editor.document["layout_order"][0] == "custom:three"

    editor.duplicate_layout(
        "builtin:half-half",
        "custom:half-copy",
        "Mitades copiadas",
    )
    copy = next(
        layout
        for layout in editor.document["custom_layouts"]
        if layout["id"] == "custom:half-copy"
    )
    assert len(copy["zones"]) == 2

    editor.update_custom_layout("custom:three", name="Tres nuevas", zones=zones)
    editor.set_enabled("builtin:grid-2x2", False)
    order = editor.document["layout_order"]
    editor.reorder(list(reversed(order)))
    assert editor.document["layout_order"] == list(reversed(order))
    editor.delete_custom_layout("custom:half-copy")
    assert "custom:half-copy" not in editor.document["layout_order"]


def test_editor_rejects_builtin_mutation_and_restores_shortcuts():
    editor = SettingsEditor()
    try:
        editor.delete_custom_layout("builtin:half-half")
    except SettingsError:
        pass
    else:
        raise AssertionError("se eliminó un layout predeterminado")
    editor.set_shortcut("layout_menu", "super+l")
    assert editor.document["shortcuts"]["layout_menu"] == "super+l"
    editor.reset_shortcuts()
    assert editor.document["shortcuts"] == DEFAULT_SHORTCUTS


def run_all_tests():
    tests = [
        test_missing_file_preserves_v11_defaults,
        test_custom_layout_order_disable_and_shortcuts_are_loaded,
        test_invalid_geometry_falls_back_without_rewriting_user_file,
        test_duplicate_shortcut_falls_back_to_defaults,
        test_non_finite_geometry_and_unmodified_shortcut_are_rejected,
        test_atomic_save_validates_before_replacing_existing_file,
        test_default_path_is_channel_isolated,
        test_editor_create_duplicate_update_reorder_disable_and_delete,
        test_editor_rejects_builtin_mutation_and_restores_shortcuts,
    ]
    for test in tests:
        test()
        print(f"  ✓ {test.__name__}")


if __name__ == "__main__":
    run_all_tests()
