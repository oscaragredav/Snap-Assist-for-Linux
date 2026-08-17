import {
    defaultDocument,
    duplicateLayout,
    inferPreset,
    layoutZones,
    mutateDocument,
    nextCustomId,
    normalizeDocument,
    presetZones,
    previewRectangles,
    resizeZone,
    splitZone,
    splitColumns,
    validateDocument,
} from '../lib/settings-document.js';

const document = defaultDocument();
duplicateLayout(document, 'builtin:half-half', 'custom:copy', 'Copia');
if (document.custom_layouts[0].zones.length !== 2)
    throw new Error('duplicate failed');
if (layoutZones(document, 'builtin:main-left').length !== 3)
    throw new Error('builtin geometry does not match runtime layout');
if (nextCustomId(document, 'Cópia Fácil') !== 'custom:copia-facil')
    throw new Error('automatic custom id failed');
document.custom_layouts.push({id: 'custom:copia-facil', name: 'Una', zones: splitColumns([1])});
document.layout_order.push('custom:copia-facil');
if (nextCustomId(document, 'Copia facil') !== 'custom:copia-facil-2')
    throw new Error('automatic custom id collision failed');
const weighted = presetZones('columns-2', 0.7);
if (weighted[0].w !== 0.7 || Math.abs(weighted[1].w - 0.3) > 1e-9)
    throw new Error('visual preset ratio failed');
if (presetZones('main-top', 0.6).length !== 3)
    throw new Error('visual main preset failed');
const inferredPreset = inferPreset(presetZones('main-left', 0.65));
if (inferredPreset?.preset !== 'main-left' || inferredPreset.ratio !== 0.65)
    throw new Error('visual preset inference failed');
document.custom_layouts.push({id: 'custom:three', name: 'Tres', zones: splitColumns([1, 1, 1])});
document.layout_order.push('custom:three');
validateDocument(document);
normalizeDocument(JSON.parse(JSON.stringify(document)));
const preview = previewRectangles(splitColumns([1, 2]), 900, 600);
if (preview[0].width !== 300 || preview[1].x !== 300 || preview[1].width !== 600)
    throw new Error('preview geometry does not match normalized zones');
const divided = splitZone([{x: 0, y: 0, w: 1, h: 1}], 0, 'vertical');
if (divided.length !== 2 || divided[1].x !== 0.5)
    throw new Error('graphical split geometry failed');
const resized = resizeZone(divided, 0, {x: 0, y: 0, w: 0.4, h: 1});
if (resized[0].w !== 0.4)
    throw new Error('graphical resize geometry failed');

const duplicateShortcuts = defaultDocument();
duplicateShortcuts.shortcuts.help = duplicateShortcuts.shortcuts.layout_menu;
try {
    validateDocument(duplicateShortcuts);
    throw new Error('duplicate shortcut accepted');
} catch (error) {
    if (!error.message.includes('duplicados')) throw error;
}

const transactional = defaultDocument();
const beforeInvalidMutation = JSON.stringify(transactional);
try {
    mutateDocument(transactional, candidate => {
        candidate.shortcuts.help = candidate.shortcuts.layout_menu;
    });
    throw new Error('invalid transactional mutation accepted');
} catch (error) {
    if (!error.message.includes('duplicados')) throw error;
}
if (JSON.stringify(transactional) !== beforeInvalidMutation)
    throw new Error('invalid mutation changed the original document');

const beforeInvalidDuplicate = JSON.stringify(transactional);
try {
    duplicateLayout(transactional, 'builtin:half-half', 'INVALID', 'Copia inválida');
    throw new Error('invalid duplicate accepted');
} catch (error) {
    if (!error.message.includes('inválido')) throw error;
}
if (JSON.stringify(transactional) !== beforeInvalidDuplicate)
    throw new Error('invalid duplicate changed the original document');

print('GNOME settings document tests passed');
