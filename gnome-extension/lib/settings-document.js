export const BUILTIN_LAYOUTS = [
    ['builtin:half-half', '1/2 : 1/2'],
    ['builtin:two-thirds-left', '2/3 : 1/3'],
    ['builtin:two-thirds-right', '1/3 : 2/3'],
    ['builtin:grid-2x2', '1/4 : 1/4 : 1/4 : 1/4'],
    ['builtin:main-left', '1/2 : 1/4 : 1/4'],
    ['builtin:three-columns', '1/3 : 1/3 : 1/3'],
];

export const DEFAULT_SHORTCUTS = {
    layout_menu: 'super+z',
    snap_groups: 'super+alt+tab',
    help: 'super+slash',
};

const BUILTIN_ZONES = {
    'builtin:half-half': splitColumns([0.5, 0.5]),
    'builtin:two-thirds-left': splitColumns([2 / 3, 1 / 3]),
    'builtin:two-thirds-right': splitColumns([1 / 3, 2 / 3]),
    'builtin:grid-2x2': [
        {x: 0, y: 0, w: 0.5, h: 0.5}, {x: 0.5, y: 0, w: 0.5, h: 0.5},
        {x: 0, y: 0.5, w: 0.5, h: 0.5}, {x: 0.5, y: 0.5, w: 0.5, h: 0.5},
    ],
    'builtin:main-left': [
        {x: 0, y: 0, w: 0.5, h: 1},
        {x: 0.5, y: 0, w: 0.5, h: 0.5},
        {x: 0.5, y: 0.5, w: 0.5, h: 0.5},
    ],
    'builtin:three-columns': splitColumns([1 / 3, 1 / 3, 1 / 3]),
};

export function splitColumns(widths) {
    const total = widths.reduce((sum, width) => sum + width, 0);
    let x = 0;
    return widths.map(rawWidth => {
        const width = rawWidth / total;
        const zone = {x, y: 0, w: width, h: 1};
        x += width;
        return zone;
    });
}

export function presetZones(preset, ratio = 0.5) {
    const primary = Math.min(0.8, Math.max(0.2, Number(ratio)));
    const secondary = 1 - primary;
    const presets = {
        'columns-2': () => splitColumns([primary, secondary]),
        'columns-3': () => splitColumns([primary, secondary / 2, secondary / 2]),
        'rows-2': () => [
            {x: 0, y: 0, w: 1, h: primary},
            {x: 0, y: primary, w: 1, h: secondary},
        ],
        'grid-2x2': () => clone(BUILTIN_ZONES['builtin:grid-2x2']),
        'main-left': () => [
            {x: 0, y: 0, w: primary, h: 1},
            {x: primary, y: 0, w: secondary, h: 0.5},
            {x: primary, y: 0.5, w: secondary, h: 0.5},
        ],
        'main-top': () => [
            {x: 0, y: 0, w: 1, h: primary},
            {x: 0, y: primary, w: 0.5, h: secondary},
            {x: 0.5, y: primary, w: 0.5, h: secondary},
        ],
    };
    const create = presets[preset];
    if (!create)
        throw new Error(`Forma desconocida: ${preset}`);
    const zones = create();
    validateZones(zones, preset);
    return zones;
}

export function inferPreset(zones) {
    const close = (left, right) => Math.abs(left - right) < 1e-6;
    if (!Array.isArray(zones))
        return null;
    if (zones.length === 2 && zones.every(zone => close(zone.y, 0) && close(zone.h, 1)))
        return {preset: 'columns-2', ratio: zones[0].w};
    if (zones.length === 2 && zones.every(zone => close(zone.x, 0) && close(zone.w, 1)))
        return {preset: 'rows-2', ratio: zones[0].h};
    if (zones.length === 3 && zones.every(zone => close(zone.y, 0) && close(zone.h, 1)))
        return {preset: 'columns-3', ratio: zones[0].w};
    if (zones.length === 3 && close(zones[0].x, 0) && close(zones[0].h, 1) &&
        close(zones[1].x, zones[0].w) && close(zones[2].x, zones[0].w))
        return {preset: 'main-left', ratio: zones[0].w};
    if (zones.length === 3 && close(zones[0].y, 0) && close(zones[0].w, 1) &&
        close(zones[1].y, zones[0].h) && close(zones[2].y, zones[0].h))
        return {preset: 'main-top', ratio: zones[0].h};
    if (zones.length === 4)
        return {preset: 'grid-2x2', ratio: 0.5};
    return null;
}

export function previewRectangles(zones, width, height) {
    validateZones(zones, 'preview');
    return zones.map(zone => ({
        x: zone.x * width,
        y: zone.y * height,
        width: zone.w * width,
        height: zone.h * height,
    }));
}

export function splitZone(zones, index, axis, ratio = 0.5) {
    if (!Array.isArray(zones) || zones.length >= 10 || !zones[index])
        throw new Error('No se puede dividir la zona seleccionada.');
    if (!['horizontal', 'vertical'].includes(axis) || ratio <= 0 || ratio >= 1)
        throw new Error('División de zona inválida.');
    const result = clone(zones);
    const zone = result[index];
    let first;
    let second;
    if (axis === 'vertical') {
        first = {...zone, w: zone.w * ratio};
        second = {...zone, x: zone.x + first.w, w: zone.w - first.w};
    } else {
        first = {...zone, h: zone.h * ratio};
        second = {...zone, y: zone.y + first.h, h: zone.h - first.h};
    }
    result.splice(index, 1, first, second);
    validateZones(result, 'split');
    return result;
}

export function resizeZone(zones, index, geometry) {
    if (!Array.isArray(zones) || !zones[index])
        throw new Error('Zona seleccionada inválida.');
    const result = clone(zones);
    result[index] = {
        x: Number(geometry.x), y: Number(geometry.y),
        w: Number(geometry.w), h: Number(geometry.h),
    };
    const zone = result[index];
    if (!Object.values(zone).every(Number.isFinite) || zone.x < 0 || zone.y < 0 ||
        zone.w <= 0 || zone.h <= 0 || zone.x + zone.w > 1.000001 ||
        zone.y + zone.h > 1.000001)
        throw new Error('Geometría de zona fuera de límites.');
    return result;
}

export function defaultDocument() {
    return {
        version: 1,
        shortcuts: {...DEFAULT_SHORTCUTS},
        custom_layouts: [],
        layout_order: BUILTIN_LAYOUTS.map(([id]) => id),
        disabled_layouts: [],
    };
}

export function layoutZones(document, layoutId) {
    const custom = document.custom_layouts.find(layout => layout.id === layoutId);
    const zones = custom?.zones ?? BUILTIN_ZONES[layoutId];
    if (!zones)
        throw new Error(`Layout desconocido: ${layoutId}`);
    return clone(zones);
}

export function nextCustomId(document, name) {
    const base = String(name ?? '')
        .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
        .toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')
        .slice(0, 48) || 'layout';
    const used = new Set(document.layout_order);
    let suffix = 1;
    let candidate = `custom:${base}`;
    while (used.has(candidate)) {
        suffix += 1;
        candidate = `custom:${base}-${suffix}`;
    }
    return candidate;
}

export function normalizeDocument(raw) {
    if (!raw || raw.version !== 1)
        throw new Error('La versión de configuración debe ser 1.');
    const document = clone(raw);
    document.custom_layouts ??= [];
    document.disabled_layouts ??= [];
    document.layout_order ??= BUILTIN_LAYOUTS.map(([id]) => id);
    document.shortcuts = {...DEFAULT_SHORTCUTS, ...(document.shortcuts ?? {})};
    validateDocument(document);
    return document;
}

export function validateDocument(document) {
    const ids = new Set(BUILTIN_LAYOUTS.map(([id]) => id));
    for (const layout of document.custom_layouts) {
        if (!/^custom:[a-z0-9][a-z0-9._-]{0,63}$/.test(layout.id) || ids.has(layout.id))
            throw new Error(`ID de layout inválido o duplicado: ${layout.id}`);
        ids.add(layout.id);
        if (!String(layout.name ?? '').trim())
            throw new Error(`El layout ${layout.id} necesita nombre.`);
        validateZones(layout.zones, layout.id);
    }
    if (new Set(document.layout_order).size !== ids.size ||
        document.layout_order.some(id => !ids.has(id)))
        throw new Error('El orden debe contener cada layout una vez.');
    if (document.disabled_layouts.some(id => !ids.has(id)) ||
        document.disabled_layouts.length >= ids.size)
        throw new Error('Debe quedar al menos un layout habilitado.');
    const shortcuts = Object.values(document.shortcuts).map(value => value.trim().toLowerCase());
    if (shortcuts.some(value => !/^(?=.*(?:super|ctrl|control|alt)\+).+/.test(`${value}+`)))
        throw new Error('Cada atajo requiere Super, Ctrl o Alt.');
    if (new Set(shortcuts).size !== shortcuts.length)
        throw new Error('Los atajos no pueden estar duplicados.');
    return true;
}

export function mutateDocument(document, mutation) {
    const candidate = clone(document);
    mutation(candidate);
    validateDocument(candidate);
    for (const key of Object.keys(document))
        delete document[key];
    Object.assign(document, candidate);
    return document;
}

export function validateZones(zones, layoutId = 'layout') {
    if (!Array.isArray(zones) || zones.length < 1 || zones.length > 10)
        throw new Error(`${layoutId} debe tener entre 1 y 10 zonas.`);
    let area = 0;
    for (const zone of zones) {
        for (const key of ['x', 'y', 'w', 'h']) {
            if (!Number.isFinite(zone[key]))
                throw new Error(`Zona inválida en ${layoutId}.`);
        }
        if (zone.x < 0 || zone.y < 0 || zone.w <= 0 || zone.h <= 0 ||
            zone.x + zone.w > 1.000001 || zone.y + zone.h > 1.000001)
            throw new Error(`Zona fuera de límites en ${layoutId}.`);
        area += zone.w * zone.h;
    }
    for (let i = 0; i < zones.length; i++) {
        for (let j = i + 1; j < zones.length; j++) {
            const a = zones[i];
            const b = zones[j];
            if (Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x) > 1e-9 &&
                Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y) > 1e-9)
                throw new Error(`Zonas superpuestas en ${layoutId}.`);
        }
    }
    if (Math.abs(area - 1) > 1e-6)
        throw new Error(`Las zonas de ${layoutId} deben cubrir toda el área.`);
}

export function duplicateLayout(document, sourceId, newId, newName) {
    mutateDocument(document, candidate => {
        const zones = layoutZones(candidate, sourceId);
        candidate.custom_layouts.push({id: newId, name: newName, zones: clone(zones)});
        candidate.layout_order.push(newId);
    });
}

function clone(value) {
    return JSON.parse(JSON.stringify(value));
}
