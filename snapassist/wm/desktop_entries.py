"""Resolución de nombres de aplicaciones mediante entradas XDG desktop."""

from __future__ import annotations

import configparser
import os
from pathlib import Path
from typing import Iterable


def desktop_application_dirs() -> list[Path]:
    data_home = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
    data_dirs = os.environ.get("XDG_DATA_DIRS", "/usr/local/share:/usr/share")
    return [data_home / "applications", *[Path(item) / "applications" for item in data_dirs.split(":") if item]]


class DesktopEntryResolver:
    """Índice pequeño de ``StartupWMClass``/app-id a nombre localizado."""

    def __init__(self, directories: Iterable[Path] | None = None) -> None:
        self._directories = list(directories) if directories is not None else desktop_application_dirs()
        self._names: dict[str, str] | None = None

    def resolve(self, *identifiers: str) -> str:
        if self._names is None:
            self._names = self._load()
        for identifier in identifiers:
            key = identifier.strip().casefold()
            if not key:
                continue
            for candidate in (key, key.removesuffix(".desktop")):
                if candidate in self._names:
                    return self._names[candidate]
        return ""

    def _load(self) -> dict[str, str]:
        names: dict[str, str] = {}
        # Los directorios de usuario tienen precedencia según XDG.
        for directory in reversed(self._directories):
            if not directory.is_dir():
                continue
            for path in directory.glob("*.desktop"):
                parser = configparser.ConfigParser(interpolation=None, strict=False)
                try:
                    parser.read(path, encoding="utf-8")
                    entry = parser["Desktop Entry"]
                    if entry.getboolean("NoDisplay", fallback=False):
                        continue
                    name = entry.get("Name", "").strip()
                    if not name:
                        continue
                    keys = {path.stem, entry.get("StartupWMClass", "").strip()}
                    for key in keys:
                        if key:
                            names[key.casefold()] = name
                except (OSError, configparser.Error, ValueError):
                    continue
        return names
