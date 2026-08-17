import {OperationStore, validateOperationId} from '../lib/operation-store.js';

function assert(condition, message) {
    if (!condition)
        throw new Error(message);
}

const store = new OperationStore(2);
let calls = 0;
const first = store.execute('operation:1', 'activate:1', () => ++calls);
const duplicate = store.execute('operation:1', 'activate:1', () => ++calls);
assert(first.accepted && first.value === 1, 'first operation failed');
assert(duplicate.accepted && duplicate.duplicate, 'duplicate not replayed');
assert(calls === 1, 'duplicate operation was executed twice');

const conflict = store.execute('operation:1', 'activate:2', () => ++calls);
assert(!conflict.accepted && conflict.errorCode === 'operation-id-conflict',
    'operation id conflict not rejected');
assert(calls === 1, 'conflicting operation was executed');

store.remember('operation:async', 'move:async', {
    accepted: true,
    errorCode: null,
    message: '',
    value: null,
    duplicate: false,
});
const asyncDuplicate = store.lookup('operation:async', 'move:async');
assert(asyncDuplicate?.accepted && asyncDuplicate.duplicate,
    'async operation result was not replayed');

assert(store.reserve('operation:pending', 'move:pending') === null,
    'async operation ID was not reserved');
const pendingConflict = store.execute('operation:pending', 'activate:pending', () => ++calls);
assert(!pendingConflict.accepted && pendingConflict.errorCode === 'operation-id-conflict',
    'sync operation reused a pending async ID');
assert(store.pendingSize === 1, 'pending operation was not retained');
store.remember('operation:pending', 'move:pending', {
    accepted: true,
    errorCode: null,
    message: '',
    value: null,
    duplicate: false,
});
assert(store.pendingSize === 0, 'completed operation kept its pending reservation');

const missing = store.execute('operation:2', 'activate:missing', () => {
    const error = new Error('window disappeared');
    error.code = 'window-gone';
    throw error;
});
assert(!missing.accepted && missing.errorCode === 'window-gone', 'error not classified');
assert(store.execute('operation:2', 'activate:missing', () => true).duplicate, 'error replay missing');

store.execute('operation:3', 'activate:3', () => true);
const evicted = store.execute('operation:1', 'activate:1', () => ++calls);
assert(!evicted.duplicate && calls === 2, 'bounded cache did not evict oldest');

const stress = new OperationStore();
for (let index = 0; index < 10000; index++)
    stress.execute(`stress:${index}`, `move:${index}`, () => index);
assert(stress.size === 256, 'operation cache grew beyond its bound');
stress.clear();
assert(stress.size === 0, 'operation cache was not cleared on teardown');

let invalidRejected = false;
try {
    validateOperationId('');
} catch (_error) {
    invalidRejected = true;
}
assert(invalidRejected, 'empty operation id accepted');

print('GNOME operation store tests passed');
