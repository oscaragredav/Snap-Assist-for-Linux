import {
    BUS_NAME,
    CAPABILITY_CANDIDATES,
    INTERFACE_NAME,
    OBJECT_PATH,
    endpointForChannel,
    normalizeSequence,
    opaqueWindowHandle,
    protocolInfo,
    toGnomeAccelerator,
} from '../lib/protocol.js';

function assert(condition, message) {
    if (!condition)
        throw new Error(message);
}

assert(BUS_NAME === 'org.snapassist.Shell.Test', 'test bus must be isolated');
assert(OBJECT_PATH === '/org/snapassist/Shell/Test', 'unexpected object path');
const stable = endpointForChannel('stable');
assert(stable.busName === 'org.snapassist.Shell', 'unexpected stable bus');
assert(stable.objectPath === '/org/snapassist/Shell', 'unexpected stable object path');
assert(INTERFACE_NAME === 'org.snapassist.Shell1', 'unexpected interface');
assert(CAPABILITY_CANDIDATES.length >= 15, 'capability matrix is incomplete');
assert(new Set(CAPABILITY_CANDIDATES).size === CAPABILITY_CANDIDATES.length, 'duplicate capability');
assert(normalizeSequence(0) === 0, 'zero sequence must be valid');
assert(normalizeSequence(42) === 42, 'positive sequence must be valid');
assert(opaqueWindowHandle(7) === 'mutter:7', 'handle must be opaque');
const info = protocolInfo('session-test');
assert(info.protocolVersion === 1, 'unexpected protocol version');
assert(info.minimumClientVersion === 1, 'unexpected minimum client version');
assert(info.sessionId === 'session-test', 'session id not retained');
assert(info.capabilityCandidates.length === CAPABILITY_CANDIDATES.length,
    'capability candidates not retained');
assert(toGnomeAccelerator('super+z') === '<Super>z', 'Super conversion failed');
assert(toGnomeAccelerator('super+alt+tab') === '<Super><Alt>Tab', 'Tab conversion failed');
assert(toGnomeAccelerator('super+slash') === '<Super>slash', 'slash conversion failed');
assert(toGnomeAccelerator('super+f2') === '<Super>F2', 'function-key conversion failed');
assert(toGnomeAccelerator('ctrl+alt+left') === '<Ctrl><Alt>Left', 'named-key conversion failed');

for (const invalid of [-1, 1.5, Number.MAX_SAFE_INTEGER + 1]) {
    let rejected = false;
    try {
        normalizeSequence(invalid);
    } catch (_error) {
        rejected = true;
    }
    assert(rejected, `invalid sequence accepted: ${invalid}`);
}

print('GNOME protocol module tests passed');
