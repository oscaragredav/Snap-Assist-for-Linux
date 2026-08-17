import {
    ConfirmationAction,
    MoveResizeConfirmation,
    rectMatches,
} from '../lib/move-resize-confirmation.js';

function assert(condition, message) {
    if (!condition)
        throw new Error(message);
}

const target = {x: -960, y: 24, width: 960, height: 1056};
const originalRect = {x: 0, y: 24, width: 1920, height: 1056};
const sample = (geometry, overrides = {}) => ({
    geometry,
    monitor: 1,
    maximizedHorizontally: false,
    maximizedVertically: false,
    tiled: false,
    windowGone: false,
    ...overrides,
});
const machine = () => new MoveResizeConfirmation({
    target,
    originalRect,
    targetMonitor: 1,
});

assert(rectMatches({...target, x: target.x + 1}, target), 'one pixel must match');
assert(!rectMatches({...target, x: target.x + 2}, target), 'two pixels must fail');

let confirmation = machine();
assert(confirmation.observe(sample(target), 50).action === ConfirmationAction.WAIT,
    'first stable sample confirmed too early');
assert(confirmation.observe(sample(target), 100).status === 'confirmed',
    'second stable sample did not confirm');

confirmation = machine();
assert(confirmation.observe(sample(originalRect), 50).action === ConfirmationAction.RETRY,
    'return to previous tile did not request retry');
assert(confirmation.observe(sample(originalRect), 100).action === ConfirmationAction.WAIT,
    'previous tile retried more than once');
assert(confirmation.observe(sample(target), 150).action === ConfirmationAction.WAIT,
    'late configure confirmed without stability');
assert(confirmation.observe(sample(target), 200).status === 'confirmed',
    'late configure never stabilized');
assert(confirmation.attempts === 2, 'retry count is incorrect');

confirmation = machine();
assert(confirmation.observe(sample(target, {maximizedHorizontally: true}), 50).action ===
    ConfirmationAction.WAIT, 'partial maximization was accepted');
assert(confirmation.observe(sample(target, {tiled: true}), 1_000).status ===
    'constraint-rejected', 'tiled state was accepted at timeout');

confirmation = machine();
assert(confirmation.observe(sample(target, {monitor: 0}), 1_000).status ===
    'constraint-rejected', 'wrong monitor was accepted');

confirmation = machine();
assert(confirmation.observe({windowGone: true}, 50).status === 'window-gone',
    'closed window was not classified');

confirmation = machine();
// Pruebas de convergencia con cuadrícula discreta (Terminal / Editor)
const gridSample = {x: target.x, y: target.y, width: target.width - 8, height: target.height - 12};
confirmation = machine();
assert(confirmation.observe(sample(gridSample), 50).action === ConfirmationAction.WAIT,
    'first grid sample confirmed too early');
const gridResult = confirmation.observe(sample(gridSample), 100);
assert(gridResult.status === 'confirmed', 'grid sample must confirm after stability');
assert(gridResult.constraint === 'size-increments', 'grid sample must be classified as size-increments');

// Pruebas de convergencia con tamaño mínimo (Spotify / Electron)
const minSizeSample = {x: target.x, y: target.y, width: target.width + 160, height: target.height};
confirmation = machine();
assert(confirmation.observe(sample(minSizeSample), 50).action === ConfirmationAction.WAIT,
    'first min-size sample confirmed too early');
const minSizeResult = confirmation.observe(sample(minSizeSample), 100);
assert(minSizeResult.status === 'confirmed', 'min-size sample must confirm after stability');
assert(minSizeResult.constraint === 'minimum-size', 'min-size sample must be classified as minimum-size');

print('GNOME move-resize confirmation tests passed');
