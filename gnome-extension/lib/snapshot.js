import GLib from 'gi://GLib';
import Meta from 'gi://Meta';
import Shell from 'gi://Shell';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';

import {normalizeSequence, opaqueWindowHandle} from './protocol.js';

function rectToObject(rect) {
    return {x: rect.x, y: rect.y, width: rect.width, height: rect.height};
}

function monitorHandle(index) {
    return `monitor:${index}`;
}

function workspaceHandle(index) {
    return `workspace:${index}`;
}

function clientType(window) {
    const type = window.get_client_type?.();
    if (type === Meta.WindowClientType?.WAYLAND)
        return 'wayland';
    if (type === Meta.WindowClientType?.X11)
        return (GLib.getenv('XDG_SESSION_TYPE') ?? '').toLowerCase() === 'wayland'
            ? 'xwayland'
            : 'x11';
    return 'unknown';
}

function readSizeLimit(window, methodNames) {
    for (const methodName of methodNames) {
        const method = window[methodName];
        if (typeof method !== 'function')
            continue;
        try {
            const result = method.call(window);
            if (!Array.isArray(result))
                continue;
            // Los métodos gboolean nuevos producen
            // [returnValue, outWidth, outHeight] en GJS. Algunas versiones
            // antiguas expusieron directamente [width, height].
            if (result.length >= 3 && typeof result[0] === 'boolean') {
                return {
                    known: result[0],
                    width: result[0] ? Number(result[1]) : 0,
                    height: result[0] ? Number(result[2]) : 0,
                    source: methodName,
                };
            }
            if (result.length >= 2) {
                return {
                    known: true,
                    width: Number(result[0]),
                    height: Number(result[1]),
                    source: methodName,
                };
            }
        } catch (_error) {
            // Probar la siguiente variante o declarar el límite desconocido.
        }
    }
    return {known: false, width: 0, height: 0, source: null};
}

export function sizeLimitsFor(window) {
    return {
        minimum: readSizeLimit(window, ['get_min_size', 'get_minimum_size']),
        maximum: readSizeLimit(window, ['get_max_size', 'get_maximum_size']),
    };
}

export function isTiled(window) {
    const tileType = window.get_tile_type?.() ?? window.tile_type;
    if (tileType === undefined || tileType === null)
        return false;
    const none = Meta.WindowTileType?.NONE ?? Meta.TileMode?.NONE ?? 0;
    return Number(tileType) !== Number(none);
}

function windowToObject(window) {
    const workspace = window.get_workspace();
    const app = Shell.WindowTracker.get_default().get_window_app(window);
    const frameRect = rectToObject(window.get_frame_rect());
    const limits = sizeLimitsFor(window);
    const fullscreen = window.is_fullscreen?.() ?? window.fullscreen ?? false;
    const above = window.is_above?.() ?? window.above ?? false;
    const allowsMove = window.allows_move?.() ?? true;
    const allowsResize = window.allows_resize?.() ?? window.resizeable ?? true;
    const actor = window.get_compositor_private?.();
    const mapped = actor?.mapped ?? (frameRect.width > 0 && frameRect.height > 0);
    const tiled = isTiled(window);
    const inherentlyResizable = allowsResize ||
        window.maximized_horizontally ||
        window.maximized_vertically ||
        tiled;
    return {
        handle: opaqueWindowHandle(window.get_id()),
        title: window.get_title() ?? '',
        appId: app?.get_id() ?? window.get_gtk_application_id?.() ?? '',
        appName: app?.get_name() ?? window.get_wm_class() ?? '',
        clientType: clientType(window),
        frameRect,
        bufferRect: window.get_buffer_rect
            ? rectToObject(window.get_buffer_rect())
            : null,
        monitor: monitorHandle(window.get_monitor()),
        workspace: workspace ? workspaceHandle(workspace.index()) : null,
        minimized: window.minimized,
        maximizedHorizontally: window.maximized_horizontally,
        maximizedVertically: window.maximized_vertically,
        transientFor: window.get_transient_for()
            ? opaqueWindowHandle(window.get_transient_for().get_id())
            : null,
        minimumSize: {
            width: limits.minimum.width,
            height: limits.minimum.height,
        },
        minimumSizeKnown: limits.minimum.known,
        minimumSizeSource: limits.minimum.source,
        maximumSize: {
            width: limits.maximum.width,
            height: limits.maximum.height,
        },
        maximumSizeKnown: limits.maximum.known,
        fullscreen,
        above,
        onAllWorkspaces: window.is_on_all_workspaces?.() ??
            window.on_all_workspaces ?? false,
        allowsMove,
        allowsResize,
        mapped,
        tiled,
        eligible: (window.minimized || (
            mapped && frameRect.width > 0 && frameRect.height > 0
        )) &&
            !window.skip_taskbar &&
            window.get_window_type() === Meta.WindowType.NORMAL &&
            !fullscreen && !above && allowsMove && inherentlyResizable,
    };
}

export class SnapshotProvider {
    constructor(sessionId) {
        this._sessionId = sessionId;
        this._sequence = 0;
    }

    capture() {
        this._sequence = normalizeSequence(this._sequence + 1);
        const windows = global.get_window_actors()
            .map(actor => actor.meta_window)
            .filter(window => Boolean(window))
            .map(windowToObject);
        const activeWindow = global.display.focus_window;
        const monitors = Main.layoutManager.monitors.map((monitor, index) => ({
            handle: monitorHandle(index),
            geometry: rectToObject(monitor),
            workArea: rectToObject(Main.layoutManager.getWorkAreaForMonitor(index)),
            scale: global.display.get_monitor_scale(index),
        }));
        return {
            protocolVersion: 1,
            sessionId: this._sessionId,
            sequence: this._sequence,
            capturedAtMonotonicUs: GLib.get_monotonic_time(),
            sessionType: GLib.getenv('XDG_SESSION_TYPE') ?? 'unknown',
            activeWindow: activeWindow
                ? opaqueWindowHandle(activeWindow.get_id())
                : null,
            windows,
            monitors,
            activeWorkspace: workspaceHandle(
                global.workspace_manager.get_active_workspace_index(),
            ),
        };
    }
}
