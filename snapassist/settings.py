"""Configuración versionada de layouts y atajos de SnapAssist."""

from __future__ import annotations

import json
import logging
import math
import os
import re
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from snapassist.config import (
    HOTKEY_HELP,
    HOTKEY_LAYOUT_MENU,
    HOTKEY_SNAP_GROUPS,
    LAYOUT_TEMPLATES,
    LayoutTemplate,
    ZoneTemplate,
)
from snapassist.core.hotkeys import parse_hotkey


logger = logging.getLogger(__name__)
SETTINGS_VERSION = 1
CUSTOM_ID_PATTERN = re.compile(r"^custom:[a-z0-9][a-z0-9._-]{0,63}$")
BUILTIN_LAYOUT_IDS = (
    "builtin:half-half",
    "builtin:two-thirds-left",
    "builtin:two-thirds-right",
    "builtin:grid-2x2",
    "builtin:main-left",
    "builtin:three-columns",
)
DEFAULT_SHORTCUTS = {
    "layout_menu": HOTKEY_LAYOUT_MENU,
    "snap_groups": HOTKEY_SNAP_GROUPS,
    "help": HOTKEY_HELP,
}


def default_settings_document() -> dict[str, Any]:
    return {
        "version": SETTINGS_VERSION,
        "shortcuts": dict(DEFAULT_SHORTCUTS),
        "custom_layouts": [],
        "layout_order": list(BUILTIN_LAYOUT_IDS),
        "disabled_layouts": [],
    }


class SettingsError(ValueError):
    """La configuración no cumple el contrato versionado."""


@dataclass(frozen=True)
class LayoutDefinition:
    layout_id: str
    template: LayoutTemplate
    builtin: bool


@dataclass(frozen=True)
class RuntimeSettings:
    layouts: tuple[LayoutDefinition, ...]
    shortcuts: dict[str, str]
    source_path: Path
    loaded_from_file: bool = False
    error: str | None = None

    @property
    def layout_templates(self) -> list[LayoutTemplate]:
        return [definition.template for definition in self.layouts]

    @classmethod
    def defaults(cls, source_path: Path | None = None) -> "RuntimeSettings":
        path = source_path or default_settings_path()
        layouts = tuple(
            LayoutDefinition(layout_id, template, True)
            for layout_id, template in zip(
                BUILTIN_LAYOUT_IDS,
                LAYOUT_TEMPLATES,
                strict=True,
            )
        )
        return cls(layouts, dict(DEFAULT_SHORTCUTS), path)

    @classmethod
    def load(cls, source_path: Path | None = None) -> "RuntimeSettings":
        path = source_path or default_settings_path()
        if not path.exists():
            return cls.defaults(path)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            return _parse_settings(raw, path)
        except (OSError, json.JSONDecodeError, SettingsError, TypeError) as error:
            message = str(error)
            logger.error(
                "Configuración inválida en %s; se usarán defaults: %s",
                path,
                message,
            )
            defaults = cls.defaults(path)
            return cls(
                defaults.layouts,
                defaults.shortcuts,
                path,
                loaded_from_file=False,
                error=message,
            )


class SettingsEditor:
    """Operaciones puras compartidas con el editor gráfico nativo."""

    def __init__(self, document: dict[str, Any] | None = None) -> None:
        self._document = deepcopy(document or default_settings_document())
        _parse_settings(self._document, Path("<memory>"))

    @classmethod
    def load(cls, source_path: Path | None = None) -> "SettingsEditor":
        path = source_path or default_settings_path()
        if not path.exists():
            return cls()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise SettingsError(f"no se puede editar configuración inválida: {error}") from error
        return cls(raw)

    @property
    def document(self) -> dict[str, Any]:
        return deepcopy(self._document)

    def create_layout(
        self,
        layout_id: str,
        name: str,
        zones: list[dict[str, float]],
        position: int | None = None,
    ) -> None:
        candidate = self.document
        candidate["custom_layouts"].append(
            {"id": layout_id, "name": name, "zones": deepcopy(zones)}
        )
        order = candidate["layout_order"]
        if position is None:
            order.append(layout_id)
        elif 0 <= position <= len(order):
            order.insert(position, layout_id)
        else:
            raise SettingsError(f"posición de layout inválida: {position}")
        self._replace(candidate)

    def duplicate_layout(
        self,
        source_id: str,
        new_id: str,
        new_name: str,
        position: int | None = None,
    ) -> None:
        source = self._layout_payload(source_id)
        self.create_layout(new_id, new_name, source["zones"], position)

    def update_custom_layout(
        self,
        layout_id: str,
        *,
        name: str,
        zones: list[dict[str, float]],
    ) -> None:
        candidate = self.document
        for layout in candidate["custom_layouts"]:
            if layout["id"] == layout_id:
                layout["name"] = name
                layout["zones"] = deepcopy(zones)
                self._replace(candidate)
                return
        raise SettingsError(f"solo se pueden modificar layouts personalizados: {layout_id}")

    def delete_custom_layout(self, layout_id: str) -> None:
        if layout_id in BUILTIN_LAYOUT_IDS:
            raise SettingsError("los layouts predeterminados no se pueden eliminar")
        candidate = self.document
        original_count = len(candidate["custom_layouts"])
        candidate["custom_layouts"] = [
            layout
            for layout in candidate["custom_layouts"]
            if layout["id"] != layout_id
        ]
        if len(candidate["custom_layouts"]) == original_count:
            raise SettingsError(f"layout desconocido: {layout_id}")
        candidate["layout_order"] = [
            item for item in candidate["layout_order"] if item != layout_id
        ]
        candidate["disabled_layouts"] = [
            item for item in candidate["disabled_layouts"] if item != layout_id
        ]
        self._replace(candidate)

    def reorder(self, ordered_ids: list[str]) -> None:
        candidate = self.document
        known = set(BUILTIN_LAYOUT_IDS) | {
            layout["id"] for layout in candidate["custom_layouts"]
        }
        if len(ordered_ids) != len(set(ordered_ids)) or set(ordered_ids) != known:
            raise SettingsError("el nuevo orden debe contener cada layout exactamente una vez")
        candidate["layout_order"] = list(ordered_ids)
        self._replace(candidate)

    def set_enabled(self, layout_id: str, enabled: bool) -> None:
        candidate = self.document
        known = set(candidate["layout_order"])
        if layout_id not in known:
            raise SettingsError(f"layout desconocido: {layout_id}")
        disabled = set(candidate["disabled_layouts"])
        if enabled:
            disabled.discard(layout_id)
        else:
            disabled.add(layout_id)
        candidate["disabled_layouts"] = [
            item for item in candidate["layout_order"] if item in disabled
        ]
        self._replace(candidate)

    def set_shortcut(self, action: str, shortcut: str) -> None:
        candidate = self.document
        if action not in DEFAULT_SHORTCUTS:
            raise SettingsError(f"acción de atajo desconocida: {action}")
        candidate["shortcuts"][action] = shortcut
        self._replace(candidate)

    def reset_shortcuts(self) -> None:
        candidate = self.document
        candidate["shortcuts"] = dict(DEFAULT_SHORTCUTS)
        self._replace(candidate)

    def save(self, destination: Path | None = None) -> RuntimeSettings:
        return save_settings_document(self._document, destination)

    def _replace(self, candidate: dict[str, Any]) -> None:
        _parse_settings(candidate, Path("<memory>"))
        self._document = candidate

    def _layout_payload(self, layout_id: str) -> dict[str, Any]:
        for layout in self._document["custom_layouts"]:
            if layout["id"] == layout_id:
                return deepcopy(layout)
        if layout_id in BUILTIN_LAYOUT_IDS:
            template = LAYOUT_TEMPLATES[BUILTIN_LAYOUT_IDS.index(layout_id)]
            return {
                "id": layout_id,
                "name": template.name,
                "zones": [
                    {"x": zone.x, "y": zone.y, "w": zone.w, "h": zone.h}
                    for zone in template.zones
                ],
            }
        raise SettingsError(f"layout desconocido: {layout_id}")


def default_settings_path() -> Path:
    explicit = os.environ.get("SNAPASSIST_CONFIG_FILE")
    if explicit:
        return Path(explicit).expanduser()
    channel = os.environ.get("SNAPASSIST_CHANNEL", "stable")
    app_name = "snapassist-test" if channel == "test" else "snapassist"
    config_home = Path(
        os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")
    ).expanduser()
    return config_home / app_name / "settings.json"


def save_settings_document(
    document: dict[str, Any],
    destination: Path | None = None,
) -> RuntimeSettings:
    """Valida y guarda configuración de forma atómica.

    El archivo existente nunca se reemplaza si el documento nuevo es inválido
    o si falla la escritura previa al ``os.replace``.
    """
    path = destination or default_settings_path()
    parsed = _parse_settings(document, path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    try:
        temporary.write_text(
            json.dumps(document, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.chmod(0o600)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()
    return parsed


def _parse_settings(raw: Any, source_path: Path) -> RuntimeSettings:
    if not isinstance(raw, dict):
        raise SettingsError("la raíz debe ser un objeto JSON")
    if raw.get("version") != SETTINGS_VERSION:
        raise SettingsError(f"version debe ser {SETTINGS_VERSION}")

    shortcuts = _parse_shortcuts(raw.get("shortcuts", {}))
    definitions = {
        layout_id: LayoutDefinition(layout_id, template, True)
        for layout_id, template in zip(
            BUILTIN_LAYOUT_IDS,
            LAYOUT_TEMPLATES,
            strict=True,
        )
    }
    custom_ids: list[str] = []
    custom_layouts = raw.get("custom_layouts", [])
    if not isinstance(custom_layouts, list):
        raise SettingsError("custom_layouts debe ser una lista")
    for item in custom_layouts:
        definition = _parse_custom_layout(item)
        if definition.layout_id in definitions:
            raise SettingsError(f"layout duplicado: {definition.layout_id}")
        definitions[definition.layout_id] = definition
        custom_ids.append(definition.layout_id)

    disabled = raw.get("disabled_layouts", [])
    if not isinstance(disabled, list) or not all(isinstance(item, str) for item in disabled):
        raise SettingsError("disabled_layouts debe ser una lista de IDs")
    unknown_disabled = set(disabled) - set(definitions)
    if unknown_disabled:
        raise SettingsError(
            f"layouts deshabilitados desconocidos: {sorted(unknown_disabled)}"
        )

    default_order = [*BUILTIN_LAYOUT_IDS, *custom_ids]
    order = raw.get("layout_order", default_order)
    if not isinstance(order, list) or not all(isinstance(item, str) for item in order):
        raise SettingsError("layout_order debe ser una lista de IDs")
    if len(order) != len(set(order)):
        raise SettingsError("layout_order contiene IDs duplicados")
    unknown_order = set(order) - set(definitions)
    if unknown_order:
        raise SettingsError(f"layout_order contiene IDs desconocidos: {sorted(unknown_order)}")
    order = [*order, *(item for item in default_order if item not in order)]
    enabled = tuple(definitions[item] for item in order if item not in disabled)
    if not enabled:
        raise SettingsError("debe existir al menos un layout habilitado")
    return RuntimeSettings(enabled, shortcuts, source_path, loaded_from_file=True)


def _parse_shortcuts(raw: Any) -> dict[str, str]:
    if not isinstance(raw, dict):
        raise SettingsError("shortcuts debe ser un objeto")
    unknown = set(raw) - set(DEFAULT_SHORTCUTS)
    if unknown:
        raise SettingsError(f"acciones de atajo desconocidas: {sorted(unknown)}")
    shortcuts = dict(DEFAULT_SHORTCUTS)
    shortcuts.update(raw)
    normalized: dict[str, str] = {}
    for action, shortcut in shortcuts.items():
        if not isinstance(shortcut, str) or not shortcut.strip():
            raise SettingsError(f"atajo inválido para {action}")
        parts = {part.strip().lower() for part in shortcut.split("+")}
        if not parts.intersection({"super", "win", "cmd", "ctrl", "control", "alt"}):
            raise SettingsError(
                f"atajo inválido para {action}: requiere Super, Ctrl o Alt"
            )
        try:
            parsed = parse_hotkey(shortcut)
        except (ValueError, IndexError) as error:
            raise SettingsError(f"atajo inválido para {action}: {error}") from error
        if parsed in normalized:
            raise SettingsError(
                f"atajo duplicado para {action} y {normalized[parsed]}: {shortcut}"
            )
        normalized[parsed] = action
        shortcuts[action] = shortcut.strip().lower()
    return shortcuts


def _parse_custom_layout(raw: Any) -> LayoutDefinition:
    if not isinstance(raw, dict):
        raise SettingsError("cada layout personalizado debe ser un objeto")
    layout_id = raw.get("id")
    name = raw.get("name")
    zones = raw.get("zones")
    if not isinstance(layout_id, str) or not CUSTOM_ID_PATTERN.fullmatch(layout_id):
        raise SettingsError(f"ID personalizado inválido: {layout_id!r}")
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 80:
        raise SettingsError(f"nombre inválido para {layout_id}")
    if not isinstance(zones, list) or not 1 <= len(zones) <= 10:
        raise SettingsError(f"{layout_id} debe tener entre 1 y 10 zonas")
    parsed_zones = tuple(_parse_zone(layout_id, zone) for zone in zones)
    _validate_zone_geometry(layout_id, parsed_zones)
    return LayoutDefinition(
        layout_id,
        LayoutTemplate(name.strip(), list(parsed_zones)),
        False,
    )


def _parse_zone(layout_id: str, raw: Any) -> ZoneTemplate:
    if not isinstance(raw, dict):
        raise SettingsError(f"zona inválida en {layout_id}")
    try:
        values = tuple(float(raw[key]) for key in ("x", "y", "w", "h"))
    except (KeyError, TypeError, ValueError) as error:
        raise SettingsError(f"zona incompleta en {layout_id}") from error
    x, y, width, height = values
    tolerance = 1e-9
    if (
        not all(math.isfinite(value) for value in values)
        or x < 0
        or y < 0
        or width <= 0
        or height <= 0
        or x + width > 1 + tolerance
        or y + height > 1 + tolerance
    ):
        raise SettingsError(f"zona fuera de límites en {layout_id}: {values}")
    return ZoneTemplate(x, y, width, height)


def _validate_zone_geometry(
    layout_id: str,
    zones: tuple[ZoneTemplate, ...],
) -> None:
    for index, first in enumerate(zones):
        for second in zones[index + 1 :]:
            overlap_width = min(first.x + first.w, second.x + second.w) - max(
                first.x, second.x
            )
            overlap_height = min(first.y + first.h, second.y + second.h) - max(
                first.y, second.y
            )
            if overlap_width > 1e-9 and overlap_height > 1e-9:
                raise SettingsError(f"zonas superpuestas en {layout_id}")
    area = sum(zone.w * zone.h for zone in zones)
    if abs(area - 1.0) > 1e-6:
        raise SettingsError(
            f"las zonas de {layout_id} deben cubrir el área completa (área={area})"
        )
