"""Pruebas del adaptador D-Bus sin requerir una sesión Shell real."""

import sys
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from snapassist.adapters import gnome_dbus
from snapassist.runtime.gnome_client import ProtocolDisconnected


class FakeMatch:
    def __init__(self):
        self.removed = False

    def remove(self):
        self.removed = True


class FakeInterface:
    def __init__(self, calls):
        self.calls = calls

    def get_dbus_method(self, method):
        def call(*args, timeout):
            self.calls.append((method, args, timeout))
            return '{"ok": true}'

        return call


class FakeDbusError(RuntimeError):
    def __init__(self, name):
        super().__init__(name)
        self.name = name

    def get_dbus_name(self):
        return self.name


class FailingInterface:
    def __init__(self, error_name):
        self.error_name = error_name

    def get_dbus_method(self, method):
        def call(*args, timeout):
            raise FakeDbusError(self.error_name)

        return call


class FakeProxy:
    def __init__(self):
        self.signal_callback = None
        self.match = FakeMatch()

    def connect_to_signal(self, signal, callback, dbus_interface):
        assert dbus_interface == gnome_dbus.INTERFACE_NAME
        self.signal_callback = (signal, callback)
        return self.match


class FakeBus:
    def __init__(self, proxy, owned=True):
        self.proxy = proxy
        self.owned = owned

    def name_has_owner(self, name):
        assert name == gnome_dbus.TEST_BUS_NAME
        return self.owned

    def get_object(self, name, path, introspect):
        assert name == gnome_dbus.TEST_BUS_NAME
        assert path == gnome_dbus.TEST_OBJECT_PATH
        assert introspect
        return self.proxy


class FakeDbus:
    def __init__(self, owned=True):
        self.proxy = FakeProxy()
        self.bus = FakeBus(self.proxy, owned)
        self.calls = []

    def SessionBus(self):
        return self.bus

    def Interface(self, proxy, interface_name):
        assert proxy is self.proxy
        assert interface_name == gnome_dbus.INTERFACE_NAME
        return FakeInterface(self.calls)


def test_transport_connect_call_signal_and_cleanup():
    fake = FakeDbus()
    original = gnome_dbus._load_dbus
    gnome_dbus._load_dbus = lambda: fake
    try:
        transport = gnome_dbus.GnomeDbusTransport()
        transport.connect()
        assert transport.call("GetProtocolInfo") == '{"ok": true}'
        received = []
        unsubscribe = transport.subscribe("PlatformEvent", received.append)
        signal, callback = fake.proxy.signal_callback
        assert signal == "PlatformEvent"
        callback("payload")
        assert received == ["payload"]
        unsubscribe()
        assert fake.proxy.match.removed
        transport.disconnect()
        assert fake.calls == [("GetProtocolInfo", (), 5.0)]
    finally:
        gnome_dbus._load_dbus = original


def test_missing_bus_owner_is_classified_as_disconnected():
    fake = FakeDbus(owned=False)
    original = gnome_dbus._load_dbus
    gnome_dbus._load_dbus = lambda: fake
    try:
        try:
            gnome_dbus.GnomeDbusTransport().connect()
        except ProtocolDisconnected as error:
            assert "no posee" in str(error)
        else:
            raise AssertionError("se conectó sin owner D-Bus")
    finally:
        gnome_dbus._load_dbus = original


def test_adapter_import_does_not_require_dbus_python():
    transport = gnome_dbus.GnomeDbusTransport()
    try:
        transport.call("GetSnapshot")
    except ProtocolDisconnected:
        pass
    else:
        raise AssertionError("una llamada desconectada fue aceptada")


def test_stable_channel_selects_production_endpoint():
    previous = os.environ.get("SNAPASSIST_CHANNEL")
    try:
        os.environ["SNAPASSIST_CHANNEL"] = "stable"
        transport = gnome_dbus.GnomeDbusTransport()
        assert transport._bus_name == gnome_dbus.STABLE_BUS_NAME
        assert transport._object_path == gnome_dbus.STABLE_OBJECT_PATH
    finally:
        if previous is None:
            os.environ.pop("SNAPASSIST_CHANNEL", None)
        else:
            os.environ["SNAPASSIST_CHANNEL"] = previous


def test_object_removed_during_lock_is_classified_as_disconnected():
    for error_name in (
        "org.freedesktop.DBus.Error.UnknownObject",
        "org.freedesktop.DBus.Error.UnknownMethod",
    ):
        transport = gnome_dbus.GnomeDbusTransport()
        transport._interface = FailingInterface(error_name)
        try:
            transport.call("GetSnapshot")
        except ProtocolDisconnected as error:
            assert error_name in str(error)
        else:
            raise AssertionError(f"{error_name} no se clasificó como desconexión")


def run_all_tests():
    tests = [
        test_transport_connect_call_signal_and_cleanup,
        test_missing_bus_owner_is_classified_as_disconnected,
        test_adapter_import_does_not_require_dbus_python,
        test_stable_channel_selects_production_endpoint,
        test_object_removed_during_lock_is_classified_as_disconnected,
    ]
    for test in tests:
        test()
        print(f"  ✓ {test.__name__}")


if __name__ == "__main__":
    run_all_tests()
