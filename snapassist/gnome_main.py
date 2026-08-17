"""Daemon SnapAssist 2.x para GNOME Shell/Mutter."""

from __future__ import annotations

import logging
import logging.handlers
import os
import signal
import sys
from pathlib import Path

from snapassist.adapters.gnome_dbus import (
    DbusUnavailable,
    GnomeDbusTransport,
)
from snapassist.adapters.gnome_runtime import (
    GnomeEventSource,
    GnomePresentationPort,
    GnomeShortcutProvider,
    GnomeWindowController,
)
from snapassist.core.native_coordinator import NativeSnapCoordinator
from snapassist.runtime import PlatformRuntime
from snapassist.runtime.gnome_client import GnomeProtocolClient, ProtocolError
from snapassist.settings import RuntimeSettings


logger = logging.getLogger(__name__)


def heartbeat(client: GnomeProtocolClient) -> bool:
    """Mantiene viva la recuperación aunque GNOME retire la extensión."""
    try:
        client.ensure_connected()
    except (DbusUnavailable, ProtocolError) as error:
        logger.warning("Heartbeat GNOME pendiente: %s", error)
    except Exception:
        # Un callback de GLib que propaga una excepción queda eliminado. El
        # sondeo debe sobrevivir para poder recuperarse tras desbloquear.
        logger.exception("Fallo inesperado en heartbeat GNOME; se reintentará")
    return True


def setup_logging() -> None:
    log_dir = Path(
        os.environ.get(
            "SNAPASSIST_LOG_DIR",
            "~/.local/share/snapassist-test/logs",
        )
    ).expanduser()
    log_dir.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)-8s] %(name)s | %(message)s",
        "%Y-%m-%d %H:%M:%S",
    )
    handler = logging.handlers.RotatingFileHandler(
        log_dir / "gnome-daemon.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=7,
        encoding="utf-8",
    )
    handler.setFormatter(formatter)
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    logging.basicConfig(level=logging.INFO, handlers=[handler, console])


def main() -> None:
    setup_logging()
    try:
        from gi.repository import GLib
    except ImportError as error:
        raise SystemExit(
            "SnapAssist GNOME requiere PyGObject (python3-gi)."
        ) from error

    client = GnomeProtocolClient(GnomeDbusTransport())
    shortcut_provider = None
    coordinator = None
    unsubscribe_ui = None
    heartbeat_id = None
    settings_reload_id = None
    try:
        info = client.connect()
        settings = RuntimeSettings.load()
        windows = GnomeWindowController(client)
        presentation = GnomePresentationPort(client)
        shortcut_provider = GnomeShortcutProvider(client)
        events = GnomeEventSource(client)
        runtime = PlatformRuntime(windows, presentation, shortcut_provider, events)
        coordinator = NativeSnapCoordinator(
            runtime,
            settings.layout_templates,
        )
        unsubscribe_ui = client.subscribe_ui_actions(coordinator.handle_ui_action)

        registered = [shortcut_provider.register(
            "layout_menu",
            settings.shortcuts["layout_menu"],
            coordinator.start,
        )]
        registered.append(shortcut_provider.register(
            "snap_groups",
            settings.shortcuts["snap_groups"],
            lambda: (
                None
                if coordinator.focus_active_group()
                else presentation.notify(
                    "La ventana activa no pertenece a un Snap Group."
                )
            ),
        ))
        registered.append(shortcut_provider.register(
            "help",
            settings.shortcuts["help"],
            presentation.show_help,
        ))
        if not all(registered):
            raise ProtocolError(
                "GNOME rechazó la configuración inicial de atajos."
            )
        logger.info(
            "GNOME runtime conectado: protocolo=%d sesión=%s layouts=%d",
            info.protocol_version,
            info.session_id,
            len(settings.layouts),
        )

        loop = GLib.MainLoop()

        heartbeat_id = GLib.timeout_add_seconds(2, heartbeat, client)

        settings_path = settings.source_path
        settings_stamp = [
            settings_path.stat().st_mtime_ns if settings_path.exists() else None
        ]

        def reload_settings():
            try:
                stamp = settings_path.stat().st_mtime_ns if settings_path.exists() else None
                if stamp == settings_stamp[0]:
                    return GLib.SOURCE_CONTINUE
                candidate = RuntimeSettings.load(settings_path)
                if candidate.error:
                    presentation.notify(
                        "La configuración no se aplicó porque contiene errores."
                    )
                    settings_stamp[0] = stamp
                    return GLib.SOURCE_CONTINUE
                if not shortcut_provider.update_shortcuts(candidate.shortcuts):
                    presentation.notify("No se pudieron aplicar los nuevos atajos.")
                    return GLib.SOURCE_CONTINUE
                coordinator.replace_layouts(candidate.layout_templates)
                settings_stamp[0] = stamp
                presentation.notify("Configuración de SnapAssist aplicada.")
                logger.info("Configuración recargada: layouts=%d", len(candidate.layouts))
            except OSError as error:
                logger.warning("Configuración pendiente de recarga: %s", error)
            return GLib.SOURCE_CONTINUE

        settings_reload_id = GLib.timeout_add_seconds(1, reload_settings)

        def shutdown(*_args):
            loop.quit()
            return GLib.SOURCE_REMOVE

        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, shutdown)
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT, shutdown)
        loop.run()
    except (DbusUnavailable, ProtocolError) as error:
        logger.error("No se pudo iniciar el runtime GNOME: %s", error)
        raise SystemExit(str(error)) from error
    finally:
        if heartbeat_id:
            try:
                GLib.source_remove(heartbeat_id)
            except (NameError, RuntimeError):
                pass
        if settings_reload_id:
            try:
                GLib.source_remove(settings_reload_id)
            except (NameError, RuntimeError):
                pass
        if unsubscribe_ui:
            unsubscribe_ui()
        if coordinator:
            coordinator.close()
        if shortcut_provider:
            shortcut_provider.close()
        client.disconnect()
        logger.info("Runtime GNOME finalizado")


if __name__ == "__main__":
    main()
