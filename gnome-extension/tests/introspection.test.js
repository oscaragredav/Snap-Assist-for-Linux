import Gio from 'gi://Gio';
import GLib from 'gi://GLib';

const path = GLib.getenv('SNAPASSIST_DBUS_XML');
if (!path)
    throw new Error('SNAPASSIST_DBUS_XML is required');
const [ok, bytes] = GLib.file_get_contents(path);
if (!ok)
    throw new Error(`cannot read ${path}`);
const xml = new TextDecoder().decode(bytes);
const node = Gio.DBusNodeInfo.new_for_xml(xml);
if (node.interfaces.length !== 1)
    throw new Error('expected exactly one D-Bus interface');
const iface = node.interfaces[0];
if (iface.name !== 'org.snapassist.Shell1')
    throw new Error(`unexpected interface: ${iface.name}`);
const methods = new Set(iface.methods.map(method => method.name));
for (const method of [
    'GetProtocolInfo',
    'GetSnapshot',
    'Activate',
    'MoveResize',
    'SetMaximized',
    'MoveToWorkspace',
    'ShowLayouts',
    'ShowSuggestions',
    'HidePresentation',
    'Notify',
    'ConfigureShortcuts',
]) {
    if (!methods.has(method))
        throw new Error(`missing method: ${method}`);
}
const signals = new Set(iface.signals.map(signal => signal.name));
if (!signals.has('PlatformEvent') || !signals.has('OperationCompleted'))
    throw new Error('missing protocol signals');
if (!signals.has('UiAction'))
    throw new Error('missing UI action signal');
print('GNOME D-Bus introspection tests passed');
