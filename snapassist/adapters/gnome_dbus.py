"""Transporte D-Bus concreto para la extensión GNOME del canal de prueba."""

from __future__ import annotations

import logging
import os
from collections.abc import Callable

from snapassist.runtime.gnome_client import ProtocolDisconnected


logger = logging.getLogger(__name__)
TEST_BUS_NAME = "org.snapassist.Shell.Test"
TEST_OBJECT_PATH = "/org/snapassist/Shell/Test"
INTERFACE_NAME = "org.snapassist.Shell1"
STABLE_BUS_NAME = "org.snapassist.Shell"
STABLE_OBJECT_PATH = "/org/snapassist/Shell"


class DbusUnavailable(RuntimeError):
    pass


class GnomeDbusTransport:
    """Adaptador fino de dbus-python; no contiene decisiones del core."""

    def __init__(
        self,
        bus_name: str | None = None,
        object_path: str | None = None,
    ) -> None:
        channel = os.environ.get("SNAPASSIST_CHANNEL", "test")
        default_bus, default_path = (
            (STABLE_BUS_NAME, STABLE_OBJECT_PATH)
            if channel == "stable"
            else (TEST_BUS_NAME, TEST_OBJECT_PATH)
        )
        self._bus_name = bus_name or default_bus
        self._object_path = object_path or default_path
        self._bus = None
        self._proxy = None
        self._interface = None
        self._signal_matches = []

    def connect(self) -> None:
        self.disconnect()
        dbus = _load_dbus()
        try:
            self._bus = dbus.SessionBus()
            if not self._bus.name_has_owner(self._bus_name):
                raise ProtocolDisconnected(
                    f"la extensión GNOME no posee {self._bus_name}"
                )
            self._proxy = self._bus.get_object(
                self._bus_name,
                self._object_path,
                introspect=True,
            )
            self._interface = dbus.Interface(self._proxy, INTERFACE_NAME)
        except ProtocolDisconnected:
            self.disconnect()
            raise
        except Exception as error:
            self.disconnect()
            raise ProtocolDisconnected(f"no se pudo conectar a GNOME: {error}") from error

    def disconnect(self) -> None:
        for match in reversed(self._signal_matches):
            try:
                match.remove()
            except Exception:
                logger.debug("No se pudo retirar un signal match D-Bus", exc_info=True)
        self._signal_matches = []
        self._interface = None
        self._proxy = None
        self._bus = None

    def call(self, method: str, *args: object) -> str:
        if self._interface is None:
            raise ProtocolDisconnected("transporte D-Bus desconectado")
        try:
            remote_method = self._interface.get_dbus_method(method)
            return str(remote_method(*args, timeout=5.0))
        except Exception as error:
            if _is_disconnect_error(error):
                raise ProtocolDisconnected(str(error)) from error
            raise

    def subscribe(
        self,
        signal: str,
        callback: Callable[[str], None],
    ) -> Callable[[], None]:
        if self._proxy is None:
            raise ProtocolDisconnected("transporte D-Bus desconectado")

        def receive(value) -> None:
            callback(str(value))

        try:
            match = self._proxy.connect_to_signal(
                signal,
                receive,
                dbus_interface=INTERFACE_NAME,
            )
        except Exception as error:
            raise ProtocolDisconnected(
                f"no se pudo suscribir a {signal}: {error}"
            ) from error
        self._signal_matches.append(match)

        def unsubscribe() -> None:
            if match not in self._signal_matches:
                return
            self._signal_matches.remove(match)
            match.remove()

        return unsubscribe


def _load_dbus():
    try:
        import dbus
        from dbus.mainloop.glib import DBusGMainLoop
    except ImportError as error:
        raise DbusUnavailable(
            "Falta dbus-python. En Zorin/Ubuntu instala python3-dbus y crea "
            "el entorno virtual con acceso a paquetes del sistema."
        ) from error
    DBusGMainLoop(set_as_default=True)
    return dbus


def _is_disconnect_error(error: Exception) -> bool:
    name_reader = getattr(error, "get_dbus_name", None)
    name = name_reader() if name_reader else ""
    return name in {
        "org.freedesktop.DBus.Error.Disconnected",
        "org.freedesktop.DBus.Error.NameHasNoOwner",
        "org.freedesktop.DBus.Error.ServiceUnknown",
        # GNOME deshabilita temporalmente las extensiones al bloquear la
        # sesión. Durante esa transición el nombre puede seguir teniendo
        # owner aunque el objeto o sus métodos ya no estén exportados.
        "org.freedesktop.DBus.Error.UnknownObject",
        "org.freedesktop.DBus.Error.UnknownMethod",
        "org.freedesktop.DBus.Error.NoReply",
    }
