export const PROTOCOL_VERSION = 1;
export const INTERFACE_NAME = 'org.snapassist.Shell1';

export function endpointForChannel(channel) {
    if (channel === 'stable')
        return {busName: 'org.snapassist.Shell', objectPath: '/org/snapassist/Shell'};
    if (channel === 'test')
        return {busName: 'org.snapassist.Shell.Test', objectPath: '/org/snapassist/Shell/Test'};
    throw new TypeError(`unsupported channel: ${channel}`);
}

export const {busName: BUS_NAME, objectPath: OBJECT_PATH} = endpointForChannel('test');

export const CAPABILITY_CANDIDATES = Object.freeze([
    'active-window',
    'window-list',
    'window-title',
    'application-id',
    'logical-geometry',
    'monitors',
    'workspaces',
    'focus',
    'move-resize',
    'confirmed-move-resize',
    'maximize',
    'transients',
    'events',
    'work-area',
    'hotplug',
    'scale',
    'shortcut',
    'overlay',
    'native-presentation',
]);

export function protocolInfo(sessionId) {
    return {
        protocolVersion: PROTOCOL_VERSION,
        minimumClientVersion: PROTOCOL_VERSION,
        sessionId,
        interfaceName: INTERFACE_NAME,
        capabilityCandidates: [...CAPABILITY_CANDIDATES],
    };
}

export function normalizeSequence(value) {
    if (!Number.isSafeInteger(value) || value < 0)
        throw new RangeError('sequence must be a non-negative safe integer');
    return value;
}

export function opaqueWindowHandle(id) {
    const value = String(id ?? '').trim();
    if (!value)
        throw new TypeError('window id cannot be empty');
    return `mutter:${value}`;
}

export function toGnomeAccelerator(shortcut) {
    if (typeof shortcut !== 'string' || !shortcut)
        throw new TypeError('shortcut must be a non-empty string');
    const parts = shortcut.toLowerCase().split('+').map(part => part.trim());
    const key = parts.pop();
    const modifiers = {
        super: '<Super>',
        win: '<Super>',
        cmd: '<Super>',
        ctrl: '<Ctrl>',
        control: '<Ctrl>',
        alt: '<Alt>',
        shift: '<Shift>',
    };
    let result = '';
    for (const modifier of parts) {
        if (!modifiers[modifier])
            throw new TypeError(`unknown modifier: ${modifier}`);
        result += modifiers[modifier];
    }
    const keyNames = {
        slash: 'slash', tab: 'Tab', esc: 'Escape', escape: 'Escape',
        space: 'space', enter: 'Return', return: 'Return',
        left: 'Left', right: 'Right', up: 'Up', down: 'Down',
    };
    const functionKey = /^f(?:[1-9]|1[0-2])$/.test(key) ? key.toUpperCase() : null;
    if (!key || (key.length !== 1 && !keyNames[key] && !functionKey))
        throw new TypeError(`invalid key: ${key}`);
    return result + (keyNames[key] ?? functionKey ?? key);
}
