import Atk from 'gi://Atk';
import Clutter from 'gi://Clutter';
import St from 'gi://St';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';

function parsePayload(payloadJson) {
    let value;
    try {
        value = JSON.parse(payloadJson);
    } catch (error) {
        throw new Error(`invalid presentation JSON: ${error.message}`);
    }
    if (!value || typeof value !== 'object')
        throw new Error('presentation payload must be an object');
    return value;
}

function ensureVisibleInScrollView(scrollView, actor) {
    let box = actor.get_allocation_box();
    let top = box.y1;
    let bottom = box.y2;
    let parent = actor.get_parent();
    while (parent && parent !== scrollView) {
        box = parent.get_allocation_box();
        top += box.y1;
        bottom += box.y1;
        parent = parent.get_parent();
    }
    if (parent !== scrollView)
        return;
    const adjustment = scrollView.vadjustment;
    let [value, _lower, upper, _step, _page, pageSize] = adjustment.get_values();
    if (top < value)
        value = top;
    else if (bottom > value + pageSize)
        value = bottom - pageSize;
    else
        return;
    adjustment.ease(Math.max(0, Math.min(value, upper - pageSize)), {
        duration: 120,
        mode: Clutter.AnimationMode.EASE_OUT_QUAD,
    });
}

export class NativePresentation {
    constructor(emitAction) {
        this._emitAction = emitAction;
        this._actor = null;
        this._modalGrab = null;
        this._flowId = null;
        this._items = [];
        this._activeIndex = 0;
        this._mode = null;
        this._animatedActors = new Set();
    }

    showLayouts(flowId, payloadJson) {
        const payload = parsePayload(payloadJson);
        if (!Array.isArray(payload.layouts) || payload.layouts.length === 0)
            throw new Error('layouts must be a non-empty array');
        const items = payload.layouts.map((layout, index) => ({
            label: String(layout.name ?? `Layout ${index + 1}`),
            value: index,
            disabled: Boolean(layout.disabled),
            zones: Array.isArray(layout.zones) ? layout.zones : [],
        }));
        this._show(
            flowId,
            'layouts',
            payload.title ?? 'Elegir layout',
            payload.subtitle ?? '',
            items,
        );
    }

    showSuggestions(flowId, payloadJson) {
        const payload = parsePayload(payloadJson);
        if (!Array.isArray(payload.candidates))
            throw new Error('candidates must be an array');
        const items = payload.candidates.map(candidate => ({
            label: String(candidate.label ?? candidate.handle ?? 'Ventana'),
            value: String(candidate.handle ?? ''),
            disabled: !candidate.handle,
        }));
        this._show(
            flowId,
            'suggestions',
            payload.title ?? 'Completar zona',
            payload.subtitle ?? '',
            items,
        );
        this._showZoneOverlay(payload.zone);
    }

    showHelp(flowId, payloadJson) {
        const payload = parsePayload(payloadJson);
        const lines = Array.isArray(payload.lines) ? payload.lines : [];
        this._show(
            flowId,
            'help',
            payload.title ?? 'Ayuda de SnapAssist',
            payload.subtitle ?? 'Pulsa Esc para cerrar',
            lines.map(line => ({label: String(line), value: null, disabled: true})),
        );
    }

    hide(flowId) {
        if (this._flowId !== null && Number(flowId) !== Number(this._flowId))
            return false;
        this._destroyActor();
        return true;
    }

    destroy() {
        this._destroyActor();
        for (const actor of this._animatedActors) {
            actor.remove_all_transitions();
            actor.set_translation(0, 0, 0);
            actor.set_scale(1, 1);
        }
        this._animatedActors.clear();
        this._emitAction = null;
    }

    animateWindow(window, previousRect, targetRect) {
        if (!St.Settings.get().enable_animations)
            return;
        const actor = window.get_compositor_private?.();
        if (!actor)
            return;
        actor.remove_all_transitions();
        const scaleX = targetRect.width > 0 ? previousRect.width / targetRect.width : 1;
        const scaleY = targetRect.height > 0 ? previousRect.height / targetRect.height : 1;
        actor.set_translation(previousRect.x - targetRect.x, previousRect.y - targetRect.y, 0);
        actor.set_scale(scaleX, scaleY);
        actor.set_pivot_point(0, 0);
        this._animatedActors.add(actor);
        actor.ease({
            translation_x: 0,
            translation_y: 0,
            scale_x: 1,
            scale_y: 1,
            duration: 180,
            mode: Clutter.AnimationMode.EASE_OUT_QUAD,
            onComplete: () => {
                actor.set_translation(0, 0, 0);
                actor.set_scale(1, 1);
                this._animatedActors.delete(actor);
            },
        });
    }

    _show(flowId, mode, title, subtitle, items) {
        this._destroyActor();
        this._flowId = Number(flowId);
        this._mode = mode;
        this._items = items;
        this._activeIndex = Math.max(0, items.findIndex(item => !item.disabled));

        this._actor = new St.BoxLayout({
            style_class: 'snapassist-native-dialog',
            vertical: true,
            reactive: true,
            can_focus: true,
            accessible_role: Atk.Role.DIALOG,
            opacity: 0,
            scale_x: 0.97,
            scale_y: 0.97,
        });
        this._backdrop = new St.Widget({
            reactive: true,
            can_focus: true,
            x: 0,
            y: 0,
            width: global.stage.width,
            height: global.stage.height,
            layout_manager: new Clutter.FixedLayout(),
        });
        this._stageCaptureId = global.stage.connect('captured-event', (_stage, event) => {
            if (event.type() === Clutter.EventType.BUTTON_PRESS && this._actor) {
                const [pointerX, pointerY] = event.get_coords();
                const [actorX, actorY] = this._actor.get_transformed_position();
                const [actorWidth, actorHeight] = this._actor.get_transformed_size();
                const outside = pointerX < actorX || pointerX > actorX + actorWidth ||
                    pointerY < actorY || pointerY > actorY + actorHeight;
                if (!outside)
                    return Clutter.EVENT_PROPAGATE;
                this._send('cancel', null);
                return Clutter.EVENT_STOP;
            }
            return Clutter.EVENT_PROPAGATE;
        });
        this._backdrop.add_child(this._actor);
        const titleLabel = new St.Label({
            style_class: 'snapassist-native-title',
            text: String(title),
        });
        titleLabel.clutter_text.line_wrap = true;
        this._actor.add_child(titleLabel);
        if (subtitle) {
            const subtitleLabel = new St.Label({
                style_class: 'snapassist-native-subtitle',
                text: String(subtitle),
            });
            subtitleLabel.clutter_text.line_wrap = true;
            this._actor.add_child(subtitleLabel);
        }
        this._list = new St.BoxLayout({vertical: true});
        this._scroll = new St.ScrollView({
            style_class: 'snapassist-native-scroll',
            overlay_scrollbars: true,
            x_expand: true,
        });
        this._scroll.set_policy(St.PolicyType.NEVER, St.PolicyType.AUTOMATIC);
        this._scroll.set_child(this._list);
        this._actor.add_child(this._scroll);
        this._buttons = items.map((item, index) => {
            const button = new St.Button({
                style_class: 'snapassist-native-item',
                reactive: !item.disabled,
                can_focus: !item.disabled,
                accessible_role: Atk.Role.PUSH_BUTTON,
            });
            const content = new St.BoxLayout({vertical: false, x_expand: true});
            const label = new St.Label({
                text: `${index + 1}. ${item.label}`,
                x_expand: true,
                y_align: Clutter.ActorAlign.CENTER,
            });
            label.clutter_text.line_wrap = true;
            content.add_child(label);
            if (item.zones?.length)
                content.add_child(this._layoutPreview(item.zones));
            button.set_child(content);
            if (item.disabled)
                button.add_style_pseudo_class('disabled');
            button.connect('clicked', () => this._activate(index));
            this._list.add_child(button);
            return button;
        });
        if (mode === 'layouts') {
            const configure = new St.Button({
                label: 'Configurar layouts y atajos',
                style_class: 'snapassist-configure-button',
                reactive: true,
                can_focus: true,
            });
            configure.connect('clicked', () => this._send('open-preferences', null));
            this._actor.add_child(configure);
        }
        this._actor.connect('key-press-event', (_actor, event) => this._onKey(event));
        Main.layoutManager.addTopChrome(this._backdrop);
        const monitor = Main.layoutManager.primaryMonitor;
        const width = Math.min(640, Math.max(320, monitor.width - 48));
        this._actor.set_width(width);
        this._actor.set_position(
            monitor.x + Math.round((monitor.width - width) / 2),
            monitor.y + Math.round(monitor.height / 6),
        );
        this._modalGrab = Main.pushModal(this._backdrop);
        this._actor.grab_key_focus();
        this._refreshSelection();
        this._actor.ease({
            opacity: 255,
            scale_x: 1,
            scale_y: 1,
            duration: 140,
            mode: Clutter.AnimationMode.EASE_OUT_QUAD,
        });
    }

    _layoutPreview(zones) {
        const width = 120;
        const height = 64;
        const preview = new St.Widget({
            style_class: 'snapassist-layout-preview',
            width,
            height,
            layout_manager: new Clutter.FixedLayout(),
        });
        for (const zone of zones) {
            const actor = new St.Widget({style_class: 'snapassist-layout-zone'});
            actor.set_position(Math.round(Number(zone.x) * width), Math.round(Number(zone.y) * height));
            actor.set_size(
                Math.max(2, Math.round(Number(zone.w) * width) - 2),
                Math.max(2, Math.round(Number(zone.h) * height) - 2),
            );
            preview.add_child(actor);
        }
        return preview;
    }

    _showZoneOverlay(zone) {
        if (!zone || !Number.isFinite(zone.width) || !Number.isFinite(zone.height))
            return;
        this._zoneActor = new St.Widget({style_class: 'snapassist-zone-overlay'});
        this._zoneActor.set_position(zone.x, zone.y);
        this._zoneActor.set_size(zone.width, zone.height);
        Main.layoutManager.addChrome(this._zoneActor);
    }

    _onKey(event) {
        const symbol = event.get_key_symbol();
        if (symbol === Clutter.KEY_Escape) {
            this._send('cancel', null);
            return Clutter.EVENT_STOP;
        }
        if (symbol === Clutter.KEY_Return || symbol === Clutter.KEY_KP_Enter) {
            this._activate(this._activeIndex);
            return Clutter.EVENT_STOP;
        }
        if (symbol === Clutter.KEY_Up || symbol === Clutter.KEY_Left) {
            this._move(-1);
            return Clutter.EVENT_STOP;
        }
        if (symbol === Clutter.KEY_Down || symbol === Clutter.KEY_Right) {
            this._move(1);
            return Clutter.EVENT_STOP;
        }
        if (symbol >= Clutter.KEY_1 && symbol <= Clutter.KEY_9) {
            this._activate(symbol - Clutter.KEY_1);
            return Clutter.EVENT_STOP;
        }
        return Clutter.EVENT_PROPAGATE;
    }

    _move(delta) {
        if (this._items.length === 0)
            return;
        for (let offset = 1; offset <= this._items.length; offset++) {
            const index = (
                this._activeIndex + delta * offset + this._items.length
            ) % this._items.length;
            if (!this._items[index].disabled) {
                this._activeIndex = index;
                this._refreshSelection();
                return;
            }
        }
    }

    _activate(index) {
        const item = this._items[index];
        if (!item || item.disabled)
            return;
        this._send(
            this._mode === 'layouts' ? 'layout-selected' : 'suggestion-selected',
            item.value,
        );
    }

    _send(action, value) {
        this._emitAction({flowId: this._flowId, action, value});
    }

    _refreshSelection() {
        for (const [index, button] of this._buttons.entries()) {
            if (index === this._activeIndex)
                button.add_style_pseudo_class('selected');
            else
                button.remove_style_pseudo_class('selected');
        }
        const selected = this._buttons[this._activeIndex];
        if (selected && this._scroll)
            ensureVisibleInScrollView(this._scroll, selected);
    }

    _destroyActor() {
        if (this._stageCaptureId) {
            global.stage.disconnect(this._stageCaptureId);
            this._stageCaptureId = 0;
        }
        if (this._modalGrab) {
            Main.popModal(this._modalGrab);
            this._modalGrab = null;
        }
        if (this._backdrop) {
            Main.layoutManager.removeChrome(this._backdrop);
            this._backdrop.destroy();
            this._backdrop = null;
            this._actor = null;
        }
        if (this._zoneActor) {
            Main.layoutManager.removeChrome(this._zoneActor);
            this._zoneActor.destroy();
            this._zoneActor = null;
        }
        this._flowId = null;
        this._items = [];
        this._buttons = [];
        this._scroll = null;
        this._mode = null;
    }
}
