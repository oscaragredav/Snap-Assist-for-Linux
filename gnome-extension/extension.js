import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Meta from 'gi://Meta';
import Shell from 'gi://Shell';

import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';

import {
    endpointForChannel,
    protocolInfo,
    toGnomeAccelerator,
} from './lib/protocol.js';
import {OperationStore} from './lib/operation-store.js';
import {
    ConfirmationAction,
    MoveResizeConfirmation,
} from './lib/move-resize-confirmation.js';
import {NativePresentation} from './lib/native-presentation.js';
import {isTiled, sizeLimitsFor, SnapshotProvider} from './lib/snapshot.js';

function monitorForRect(x, y, width, height) {
    const centerX = x + width / 2;
    const centerY = y + height / 2;
    return Main.layoutManager.monitors.findIndex(monitor =>
        centerX >= monitor.x && centerX < monitor.x + monitor.width &&
        centerY >= monitor.y && centerY < monitor.y + monitor.height,
    );
}

const MOVE_RESIZE_SAMPLE_INTERVAL_MS = 50;

function rectToObject(rect) {
    return {x: rect.x, y: rect.y, width: rect.width, height: rect.height};
}

function moveResizeConstraint(window) {
    if (window.is_fullscreen?.() ?? window.fullscreen)
        return 'fullscreen';
    return null;
}

class SpikeService {
    constructor(sessionId, presentation, settings, emitOperationCompleted) {
        this._sessionId = sessionId;
        this._snapshots = new SnapshotProvider(sessionId);
        this._operations = new OperationStore();
        this._presentation = presentation;
        this._settings = settings;
        this._emitOperationCompleted = emitOperationCompleted;
        this._pendingMoveResizes = new Map();
    }

    GetProtocolInfo() {
        return JSON.stringify(protocolInfo(this._sessionId));
    }

    GetSnapshot() {
        return JSON.stringify(this._snapshots.capture());
    }

    Activate(operationId, handle) {
        return this._execute(operationId, ['Activate', handle], () => {
            const window = this._requireWindow(handle);
            if (window.minimized)
                window.unminimize();
            Main.activateWindow(window, global.get_current_time());
        });
    }

    MoveResizeAsync(params, invocation) {
        const [operationId, handle, x, y, width, height] = params;
        const fingerprint = JSON.stringify(['MoveResize', handle, x, y, width, height]);
        let cached;
        try {
            cached = this._operations.lookup(operationId, fingerprint);
        } catch (error) {
            this._returnMoveResize(invocation, this._moveResizeError(
                String(operationId ?? ''), error.code ?? 'operation-failed', error.message,
            ));
            return;
        }
        if (cached) {
            this._returnMoveResize(invocation, cached);
            return;
        }

        const pending = this._pendingMoveResizes.get(operationId);
        if (pending) {
            if (pending.fingerprint !== fingerprint) {
                this._returnMoveResize(invocation, this._moveResizeError(
                    operationId,
                    'operation-id-conflict',
                    'operation_id was reused with different arguments',
                ));
            } else {
                pending.invocations.push({invocation, duplicate: true});
            }
            return;
        }

        const reservation = this._operations.reserve(operationId, fingerprint);
        if (reservation) {
            this._returnMoveResize(invocation, reservation);
            return;
        }

        try {
            if (width <= 0 || height <= 0)
                throw this._operationError('invalid-geometry', 'width and height must be positive');
            const window = this._requireWindow(handle);
            const constraint = moveResizeConstraint(window);
            if (constraint) {
                const result = this._moveResizeConstraint(
                    operationId,
                    {x, y, width, height},
                    constraint,
                );
                this._operations.remember(operationId, fingerprint, result);
                this._emitOperationCompleted(JSON.stringify({...result, sessionId: this._sessionId}));
                this._returnMoveResize(invocation, result);
                return;
            }
            const targetMonitor = monitorForRect(x, y, width, height);
            const request = {
                operationId,
                fingerprint,
                handle,
                window,
                target: {x, y, width, height},
                targetMonitor,
                originalRect: rectToObject(window.get_frame_rect()),
                originalMonitor: window.get_monitor(),
                originalMaximizedHorizontally: window.maximized_horizontally,
                originalMaximizedVertically: window.maximized_vertically,
                originalMinimized: window.minimized,
                invocations: [{invocation, duplicate: false}],
                startedAtUs: GLib.get_monotonic_time(),
                confirmation: new MoveResizeConfirmation({
                    target: {x, y, width, height},
                    originalRect: rectToObject(window.get_frame_rect()),
                    targetMonitor,
                }),
                phase: 'preparing',
                observations: [],
                sourceId: 0,
            };
            this._pendingMoveResizes.set(operationId, request);
            this._prepareMoveResize(request);
            request.sourceId = GLib.timeout_add(
                GLib.PRIORITY_DEFAULT,
                MOVE_RESIZE_SAMPLE_INTERVAL_MS,
                () => this._confirmMoveResize(request),
            );
        } catch (error) {
            const request = this._pendingMoveResizes.get(operationId);
            if (request) {
                this._pendingMoveResizes.delete(operationId);
                this._restoreMoveResizeWindow(request);
            }
            const result = this._moveResizeError(
                String(operationId ?? ''),
                error.code ?? 'operation-failed',
                error.message ?? String(error),
            );
            this._operations.remember(operationId, fingerprint, result);
            this._emitOperationCompleted(JSON.stringify({...result, sessionId: this._sessionId}));
            this._returnMoveResize(invocation, result);
        }
    }

    SetMaximized(operationId, handle, maximized) {
        return this._execute(operationId, ['SetMaximized', handle, maximized], () => {
            const window = this._requireWindow(handle);
            if (maximized)
                window.maximize(Meta.MaximizeFlags.BOTH);
            else
                window.unmaximize(Meta.MaximizeFlags.BOTH);
        });
    }

    MoveToWorkspace(operationId, handle, workspaceHandle) {
        return this._execute(operationId, ['MoveToWorkspace', handle, workspaceHandle], () => {
            if (!workspaceHandle.startsWith('workspace:'))
                throw this._operationError('invalid-workspace', 'invalid workspace handle');
            const workspaceIndex = Number.parseInt(workspaceHandle.slice('workspace:'.length), 10);
            const workspace = global.workspace_manager.get_workspace_by_index(workspaceIndex);
            if (!workspace)
                throw this._operationError('workspace-gone', 'workspace disappeared');
            this._requireWindow(handle).change_workspace(workspace);
        });
    }

    ShowLayouts(operationId, flowId, payloadJson) {
        return this._execute(
            operationId,
            ['ShowLayouts', String(flowId), payloadJson],
            () => this._presentation.showLayouts(flowId, payloadJson),
        );
    }

    ShowSuggestions(operationId, flowId, payloadJson) {
        return this._execute(
            operationId,
            ['ShowSuggestions', String(flowId), payloadJson],
            () => this._presentation.showSuggestions(flowId, payloadJson),
        );
    }

    ShowHelp(operationId, flowId, payloadJson) {
        return this._execute(
            operationId,
            ['ShowHelp', String(flowId), payloadJson],
            () => this._presentation.showHelp(flowId, payloadJson),
        );
    }

    HidePresentation(operationId, flowId) {
        return this._execute(
            operationId,
            ['HidePresentation', String(flowId)],
            () => this._presentation.hide(flowId),
        );
    }

    Notify(operationId, message, _timeoutMs) {
        return this._execute(operationId, ['Notify', message], () => {
            Main.notify('SnapAssist', String(message));
        });
    }

    ConfigureShortcuts(operationId, shortcutsJson) {
        return this._execute(
            operationId,
            ['ConfigureShortcuts', shortcutsJson],
            () => {
                const shortcuts = JSON.parse(shortcutsJson);
                const mapping = {
                    layout_menu: 'show-layouts',
                    snap_groups: 'show-snap-groups',
                    help: 'show-help',
                };
                if (Object.keys(shortcuts).sort().join(',') !==
                    Object.keys(mapping).sort().join(','))
                    throw this._operationError('invalid-shortcuts', 'all shortcut actions are required');
                const accelerators = new Set();
                const validated = [];
                for (const [action, key] of Object.entries(mapping)) {
                    const accelerator = toGnomeAccelerator(shortcuts[action]);
                    if (accelerators.has(accelerator))
                        throw this._operationError('shortcut-conflict', 'duplicate shortcut');
                    accelerators.add(accelerator);
                    validated.push([key, accelerator]);
                }
                for (const [key, accelerator] of validated)
                    this._settings.set_strv(key, [accelerator]);
            },
        );
    }

    destroy() {
        this.cancelPendingMoveResizes('La extensión GNOME se deshabilitó.');
        this._operations.clear();
        this._pendingMoveResizes.clear();
        this._presentation = null;
        this._settings = null;
    }

    cancelPendingMoveResizes(message) {
        for (const request of [...this._pendingMoveResizes.values()]) {
            request.confirmation.cancel();
            this._finishMoveResize(request, 'cancelled', 'cancelled', message);
        }
    }

    _execute(operationId, fingerprintParts, callback) {
        const storedResult = this._operations.execute(
            operationId,
            JSON.stringify(fingerprintParts),
            callback,
        );
        const result = {...storedResult, sessionId: this._sessionId};
        const json = JSON.stringify(result);
        if (!result.duplicate)
            this._emitOperationCompleted(json);
        return json;
    }

    _prepareMoveResize(request) {
        const {window} = request;
        if (window.minimized)
            window.unminimize();
        // Mutter aplica estas transiciones de estado de forma asíncrona. La
        // geometría se enviará solo después de observar que han terminado.
        window.unmaximize(Meta.MaximizeFlags.BOTH);
        try {
            if (window.tile && Meta.TileMode?.NONE !== undefined)
                window.tile(Meta.TileMode.NONE);
        } catch (_error) {
            // Mutter no expone destile programático en todas las versiones.
        }
    }

    _applyMoveResize(request) {
        const {window, target} = request;
        // Debe ser programática: user_op=true vuelve a activar el mosaico al
        // tocar un borde.
        window.move_resize_frame(false, target.x, target.y, target.width, target.height);
        window.move_frame(false, target.x, target.y);
    }

    _beginGeometryApplication(request) {
        const {window, targetMonitor} = request;
        if (targetMonitor >= 0 && window.get_monitor() !== targetMonitor) {
            // Cambiar de monitor provoca un configure propio de Mutter. No
            // mezclarlo con el resize final: el último se puede descartar.
            request.phase = 'moving-monitor';
            window.move_to_monitor(targetMonitor);
            return;
        }
        request.phase = 'confirming';
        this._applyMoveResize(request);
    }

    _confirmMoveResize(request) {
        if (!this._pendingMoveResizes.has(request.operationId))
            return GLib.SOURCE_REMOVE;
        const window = this._resolveWindow(request.handle);
        const elapsedMs = (GLib.get_monotonic_time() - request.startedAtUs) / 1_000;
        if (!window) {
            request.observations.push({elapsedMs: Math.round(elapsedMs), windowGone: true});
            // El callback actual se retira con SOURCE_REMOVE; no intentes
            // eliminar de nuevo su source id desde _finishMoveResize.
            request.sourceId = 0;
            request.confirmation.observe({windowGone: true}, elapsedMs);
            this._finishMoveResize(request, 'window-gone', 'window-gone', 'La ventana desapareció mientras se acomodaba.');
            return GLib.SOURCE_REMOVE;
        }

        const observed = rectToObject(window.get_frame_rect());
        request.observations.push({
            phase: request.phase,
            elapsedMs: Math.round(elapsedMs),
            geometry: observed,
            monitor: window.get_monitor(),
            scale: window.get_monitor() >= 0
                ? global.display.get_monitor_scale(window.get_monitor())
                : null,
            maximizedHorizontally: window.maximized_horizontally,
            maximizedVertically: window.maximized_vertically,
            tiled: isTiled(window),
        });
        if (request.phase === 'preparing') {
            const actor = window.get_compositor_private?.();
            const mapped = actor?.mapped ??
                (observed.width > 0 && observed.height > 0);
            const ready = !window.minimized &&
                !window.maximized_horizontally &&
                !window.maximized_vertically && !isTiled(window) &&
                mapped && observed.width > 0 && observed.height > 0;
            if (ready) {
                const constraint = moveResizeConstraint(window);
                if (constraint) {
                    const restored = this._restoreMoveResizeWindow(request);
                    request.sourceId = 0;
                    this._finishMoveResize(
                        request,
                        'constraint-rejected',
                        'constraint-rejected',
                        'La ventana no admite el redimensionamiento solicitado.',
                        observed,
                        constraint,
                        restored,
                    );
                    return GLib.SOURCE_REMOVE;
                }
                this._beginGeometryApplication(request);
            } else if (elapsedMs >= request.confirmation.timeoutMs) {
                const restored = this._restoreMoveResizeWindow(request);
                request.sourceId = 0;
                this._finishMoveResize(
                    request,
                    'constraint-rejected',
                    'state-transition-timeout',
                    'Mutter no liberó la maximización o el mosaico antes de mover la ventana.',
                    observed,
                    'window-state',
                    restored,
                );
                return GLib.SOURCE_REMOVE;
            }
            return GLib.SOURCE_CONTINUE;
        }
        if (request.phase === 'moving-monitor') {
            if (request.targetMonitor < 0 || window.get_monitor() === request.targetMonitor) {
                // Esperar una vuelta adicional: el monitor ya cambió, pero su
                // configure de tamaño puede llegar después de este callback.
                request.phase = 'monitor-settling';
            } else if (elapsedMs >= request.confirmation.timeoutMs) {
                const restored = this._restoreMoveResizeWindow(request);
                request.sourceId = 0;
                this._finishMoveResize(
                    request,
                    'constraint-rejected',
                    'state-transition-timeout',
                    'Mutter no trasladó la ventana al monitor de destino antes de redimensionarla.',
                    observed,
                    'monitor-transition',
                    restored,
                );
                return GLib.SOURCE_REMOVE;
            }
            return GLib.SOURCE_CONTINUE;
        }
        if (request.phase === 'monitor-settling') {
            if (request.targetMonitor >= 0 && window.get_monitor() !== request.targetMonitor) {
                request.phase = 'moving-monitor';
                window.move_to_monitor(request.targetMonitor);
            } else {
                request.phase = 'confirming';
                this._applyMoveResize(request);
            }
            return GLib.SOURCE_CONTINUE;
        }
        const decision = request.confirmation.observe({
            geometry: observed,
            monitor: window.get_monitor(),
            maximizedHorizontally: window.maximized_horizontally,
            maximizedVertically: window.maximized_vertically,
            tiled: isTiled(window),
            windowGone: false,
        }, elapsedMs);
        if (decision.action === ConfirmationAction.RETRY) {
            // Solo se reintenta al volver al frame previo; la máquina limita
            // el número de reafirmaciones y no oculta restricciones reales.
            this._applyMoveResize(request);
        } else if (decision.status === 'confirmed') {
            request.sourceId = 0;
            this._finishMoveResize(
                request,
                'confirmed',
                null,
                '',
                observed,
                decision.constraint ?? null,
            );
            return GLib.SOURCE_REMOVE;
        } else if (decision.status === 'constraint-rejected') {
            const minimum = sizeLimitsFor(window).minimum;
            const constraint = minimum.known && (
                minimum.width > request.target.width ||
                minimum.height > request.target.height)
                ? 'minimum-size'
                : 'client-geometry';
            const restored = this._restoreMoveResizeWindow(request);
            request.sourceId = 0;
            this._finishMoveResize(
                request,
                'constraint-rejected',
                'constraint-rejected',
                'La aplicación no puede mantener la zona solicitada.',
                observed,
                constraint,
                restored,
            );
            return GLib.SOURCE_REMOVE;
        }
        return GLib.SOURCE_CONTINUE;
    }

    _restoreMoveResizeWindow(request) {
        const {window, originalRect, originalMonitor} = request;
        try {
            window.unmaximize(Meta.MaximizeFlags.BOTH);
            if (originalMonitor >= 0 && window.get_monitor() !== originalMonitor)
                window.move_to_monitor(originalMonitor);
            window.move_resize_frame(
                false,
                originalRect.x,
                originalRect.y,
                originalRect.width,
                originalRect.height,
            );
            let flags = 0;
            if (request.originalMaximizedHorizontally)
                flags |= Meta.MaximizeFlags.HORIZONTAL;
            if (request.originalMaximizedVertically)
                flags |= Meta.MaximizeFlags.VERTICAL;
            if (flags)
                window.maximize(flags);
            if (request.originalMinimized)
                window.minimize();
            return true;
        } catch (_error) {
            // La aplicación ya recibió la restauración; no convertir el
            // resultado clasificado en una excepción sin contrato.
            return false;
        }
    }

    _finishMoveResize(
        request,
        status,
        errorCode,
        message,
        observed = null,
        constraint = null,
        restored = false,
    ) {
        if (!this._pendingMoveResizes.delete(request.operationId))
            return;
        if (request.sourceId) {
            GLib.Source.remove(request.sourceId);
            request.sourceId = 0;
        }
        const result = {
            operationId: request.operationId,
            accepted: status === 'confirmed',
            errorCode,
            message,
            value: null,
            duplicate: false,
            status,
            requestedGeometry: request.target,
            observedGeometry: observed,
            constraint,
            attempts: request.confirmation.attempts,
            confirmationMs: Math.round(
                (GLib.get_monotonic_time() - request.startedAtUs) / 1_000,
            ),
            restored,
            observations: request.observations,
        };
        this._operations.remember(request.operationId, request.fingerprint, result);
        if (status === 'confirmed')
            this._presentation?.animateWindow(request.window, request.originalRect, request.target);
        const resultJson = JSON.stringify({...result, sessionId: this._sessionId});
        this._emitOperationCompleted(resultJson);
        for (const pending of request.invocations)
            this._returnMoveResize(pending.invocation, result, pending.duplicate);
    }

    _moveResizeError(operationId, errorCode, message) {
        return {
            operationId,
            accepted: false,
            errorCode,
            message,
            value: null,
            duplicate: false,
            status: errorCode === 'window-gone' ? 'window-gone' : 'cancelled',
            requestedGeometry: null,
            observedGeometry: null,
            constraint: null,
            attempts: 0,
            confirmationMs: 0,
            restored: false,
            observations: [],
        };
    }

    _moveResizeConstraint(operationId, requestedGeometry, constraint) {
        const labels = {
            fullscreen: 'La ventana está en pantalla completa.',
            'not-movable': 'La ventana no permite movimiento.',
            'not-resizable': 'La ventana no permite redimensionamiento.',
        };
        return {
            operationId,
            accepted: false,
            errorCode: 'constraint-rejected',
            message: labels[constraint] ?? 'La ventana no admite la operación solicitada.',
            value: null,
            duplicate: false,
            status: 'constraint-rejected',
            requestedGeometry,
            observedGeometry: null,
            constraint,
            attempts: 0,
            confirmationMs: 0,
            restored: false,
            observations: [],
        };
    }

    _returnMoveResize(invocation, result, duplicate = false) {
        const json = JSON.stringify({
            ...result,
            duplicate: result.duplicate || duplicate,
            sessionId: this._sessionId,
        });
        invocation.return_value(new GLib.Variant('(s)', [json]));
    }

    _requireWindow(handle) {
        const window = this._resolveWindow(handle);
        if (!window)
            throw this._operationError('window-gone', 'window disappeared');
        return window;
    }

    _operationError(code, message) {
        const error = new Error(message);
        error.code = code;
        return error;
    }

    _resolveWindow(handle) {
        if (!handle.startsWith('mutter:'))
            return null;
        const id = Number.parseInt(handle.slice('mutter:'.length), 10);
        return global.get_window_actors()
            .map(actor => actor.meta_window)
            .find(window => window?.get_id() === id) ?? null;
    }
}

export default class SnapAssistTestExtension extends Extension {
    enable() {
        this._signals = [];
        this._windowSignals = new Map();
        this._settings = this.getSettings();
        const endpoint = endpointForChannel(this.metadata['snapassist-channel'] ?? 'stable');
        this._sessionId = GLib.uuid_string_random();

        const [xmlOk, xmlBytes] = GLib.file_get_contents(
            `${this.path}/protocol/org.snapassist.Shell1.xml`,
        );
        if (!xmlOk)
            throw new Error('No se pudo cargar la introspección D-Bus');
        const dbusXml = new TextDecoder().decode(xmlBytes);
        this._eventSequence = 0;
        this._uiSequence = 0;
        this._presentation = new NativePresentation(
            action => this._emitUiAction(action),
        );
        this._dbusService = new SpikeService(
            this._sessionId,
            this._presentation,
            this._settings,
            resultJson => this._emitOperationCompleted(resultJson),
        );
        this._dbusObject = Gio.DBusExportedObject.wrapJSObject(
            dbusXml,
            this._dbusService,
        );
        this._dbusObject.export(Gio.DBus.session, endpoint.objectPath);
        this._busOwnerId = Gio.bus_own_name_on_connection(
            Gio.DBus.session,
            endpoint.busName,
            Gio.BusNameOwnerFlags.NONE,
            null,
            null,
        );

        Main.wm.addKeybinding(
            'show-layouts',
            this._settings,
            Meta.KeyBindingFlags.NONE,
            Shell.ActionMode.NORMAL | Shell.ActionMode.OVERVIEW,
            () => {
                this._emitUiAction({
                    flowId: 0,
                    action: 'shortcut-invoked',
                    value: 'layout_menu',
                });
            },
        );
        Main.wm.addKeybinding(
            'show-snap-groups',
            this._settings,
            Meta.KeyBindingFlags.NONE,
            Shell.ActionMode.NORMAL | Shell.ActionMode.OVERVIEW,
            () => this._emitUiAction({
                flowId: 0,
                action: 'shortcut-invoked',
                value: 'snap_groups',
            }),
        );
        Main.wm.addKeybinding(
            'show-help',
            this._settings,
            Meta.KeyBindingFlags.NONE,
            Shell.ActionMode.NORMAL | Shell.ActionMode.OVERVIEW,
            () => this._emitUiAction({
                flowId: 0,
                action: 'shortcut-invoked',
                value: 'help',
            }),
        );

        this._signals.push([
            global.display,
            global.display.connect(
                'notify::focus-window',
                () => this._emitPlatformEvent('active-window-changed'),
            ),
        ]);
        this._signals.push([
            Main.layoutManager,
            Main.layoutManager.connect(
                'monitors-changed',
                () => {
                    this._dbusService?.cancelPendingMoveResizes(
                        'La configuración de monitores cambió durante la operación.',
                    );
                    this._emitPlatformEvent('monitors-changed');
                },
            ),
        ]);
        this._signals.push([
            global.display,
            global.display.connect(
                'window-created',
                (_display, window) => {
                    this._trackWindow(window);
                    this._emitPlatformEvent(
                        'window-opened',
                        window ? `mutter:${window.get_id()}` : null,
                    );
                },
            ),
        ]);
        this._signals.push([
            global.workspace_manager,
            global.workspace_manager.connect(
                'active-workspace-changed',
                () => this._emitPlatformEvent('workspace-changed'),
            ),
        ]);
        this._signals.push([
            global.display,
            global.display.connect(
                'grab-op-end',
                (_display, window, operation) => {
                    const moving = operation === Meta.GrabOp.MOVING ||
                        operation === Meta.GrabOp.KEYBOARD_MOVING;
                    this._emitPlatformEvent(
                        moving ? 'window-dragged' : 'window-resized',
                        window ? `mutter:${window.get_id()}` : null,
                        {grabOperation: Number(operation)},
                    );
                },
            ),
        ]);
        for (const actor of global.get_window_actors())
            this._trackWindow(actor.meta_window);
    }

    disable() {
        Main.wm.removeKeybinding('show-layouts');
        Main.wm.removeKeybinding('show-snap-groups');
        Main.wm.removeKeybinding('show-help');
        for (const [object, signalId] of this._signals ?? [])
            object.disconnect(signalId);
        this._signals = [];
        for (const window of [...(this._windowSignals?.keys() ?? [])])
            this._untrackWindow(window);
        // Responde las invocaciones D-Bus pendientes antes de retirar el
        // objeto exportado; de lo contrario el daemon solo vería un timeout.
        this._dbusService?.destroy();
        this._dbusService = null;
        this._windowSignals = null;
        this._presentation?.destroy();
        this._presentation = null;

        if (this._busOwnerId) {
            Gio.bus_unown_name(this._busOwnerId);
            this._busOwnerId = 0;
        }
        this._dbusObject?.unexport();
        this._dbusObject = null;
        this._settings = null;
        this._sessionId = null;
    }

    _emitPlatformEvent(kind, window = null, payload = null) {
        if (!this._dbusObject)
            return;
        this._eventSequence += 1;
        const event = JSON.stringify({
            sessionId: this._sessionId,
            sequence: this._eventSequence,
            kind,
            window,
            operationId: null,
            payload,
        });
        this._dbusObject.emit_signal(
            'PlatformEvent',
            new GLib.Variant('(s)', [event]),
        );
    }

    _emitOperationCompleted(resultJson) {
        if (!this._dbusObject)
            return;
        this._dbusObject.emit_signal(
            'OperationCompleted',
            new GLib.Variant('(s)', [resultJson]),
        );
    }

    _emitUiAction(action) {
        if (!this._dbusObject)
            return;
        if (action.action === 'open-preferences') {
            this._presentation?.hide(action.flowId);
            this.openPreferences();
            return;
        }
        this._uiSequence += 1;
        const value = JSON.stringify({
            sessionId: this._sessionId,
            sequence: this._uiSequence,
            flowId: action.flowId,
            action: action.action,
            value: action.value,
        });
        this._dbusObject.emit_signal(
            'UiAction',
            new GLib.Variant('(s)', [value]),
        );
    }

    _trackWindow(window) {
        if (!window || this._windowSignals.has(window))
            return;
        const handle = `mutter:${window.get_id()}`;
        const changed = () => this._emitPlatformEvent('window-changed', handle);
        const signals = [
            window.connect('position-changed', changed),
            window.connect('size-changed', changed),
            window.connect('notify::minimized', changed),
            window.connect('workspace-changed', changed),
            window.connect('unmanaged', () => {
                this._untrackWindow(window);
                this._emitPlatformEvent('window-closed', handle);
            }),
        ];
        this._windowSignals.set(window, signals);
    }

    _untrackWindow(window) {
        const signals = this._windowSignals?.get(window);
        if (!signals)
            return;
        for (const signalId of signals) {
            try {
                window.disconnect(signalId);
            } catch (_error) {
                // `unmanaged` may invalidate some handlers during teardown.
            }
        }
        this._windowSignals.delete(window);
    }

}
