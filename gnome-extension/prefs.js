import Adw from 'gi://Adw';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Gtk from 'gi://Gtk';

import {ExtensionPreferences} from 'resource:///org/gnome/Shell/Extensions/js/extensions/prefs.js';
import {
    BUILTIN_LAYOUTS,
    DEFAULT_SHORTCUTS,
    defaultDocument,
    layoutZones,
    mutateDocument,
    nextCustomId,
    normalizeDocument,
    presetZones,
    previewRectangles,
    splitZone,
    validateDocument,
} from './lib/settings-document.js';

const ACTION_LABELS = {
    layout_menu: 'Mostrar layouts',
    snap_groups: 'Enfocar Snap Group',
    help: 'Mostrar ayuda',
};

export default class SnapAssistPreferences extends ExtensionPreferences {
    fillPreferencesWindow(window) {
        this._window = window;
        const channel = this.metadata['snapassist-channel'] ?? 'stable';
        const appName = channel === 'test' ? 'snapassist-test' : 'snapassist';
        this._path = GLib.build_filenamev([GLib.get_user_config_dir(), appName, 'settings.json']);
        this._document = this._load();
        window.set_default_size(760, 680);
        this._render();
    }

    _render() {
        for (const page of this._pages ?? [])
            this._window.remove(page);
        this._pages = [this._layoutsPage(), this._shortcutsPage()];
        for (const page of this._pages)
            this._window.add(page);
    }

    _layoutsPage() {
        const page = new Adw.PreferencesPage({title: 'Layouts', icon_name: 'view-grid-symbolic'});
        const group = new Adw.PreferencesGroup({title: 'Layouts disponibles'});
        page.add(group);
        for (const id of this._document.layout_order) {
            const custom = this._document.custom_layouts.find(item => item.id === id);
            const builtin = BUILTIN_LAYOUTS.find(item => item[0] === id);
            const row = new Adw.ActionRow({title: custom?.name ?? builtin?.[1] ?? id});
            const enabled = new Gtk.Switch({active: !this._document.disabled_layouts.includes(id), valign: Gtk.Align.CENTER});
            enabled.connect('notify::active', () => this._toggle(id, enabled.active));
            row.add_suffix(enabled);
            const up = new Gtk.Button({icon_name: 'go-up-symbolic', valign: Gtk.Align.CENTER});
            up.connect('clicked', () => this._move(id, -1));
            row.add_suffix(up);
            const down = new Gtk.Button({icon_name: 'go-down-symbolic', valign: Gtk.Align.CENTER});
            down.connect('clicked', () => this._move(id, 1));
            row.add_suffix(down);
            const edit = new Gtk.Button({icon_name: custom ? 'document-edit-symbolic' : 'edit-copy-symbolic', valign: Gtk.Align.CENTER});
            edit.connect('clicked', () => custom ? this._edit(custom) : this._duplicate(id));
            row.add_suffix(edit);
            if (custom) {
                const remove = new Gtk.Button({icon_name: 'user-trash-symbolic', valign: Gtk.Align.CENTER});
                remove.connect('clicked', () => this._delete(id));
                row.add_suffix(remove);
            }
            group.add(row);
        }
        const create = new Adw.ActionRow({title: 'Nuevo layout'});
        const createButton = new Gtk.Button({label: 'Crear', valign: Gtk.Align.CENTER});
        createButton.connect('clicked', () => this._create());
        create.add_suffix(createButton);
        group.add(create);
        return page;
    }

    _shortcutsPage() {
        const page = new Adw.PreferencesPage({title: 'Atajos', icon_name: 'preferences-desktop-keyboard-shortcuts-symbolic'});
        const group = new Adw.PreferencesGroup({title: 'Atajos de teclado'});
        page.add(group);
        for (const action of Object.keys(ACTION_LABELS)) {
            const row = new Adw.EntryRow({
                title: ACTION_LABELS[action],
                text: this._document.shortcuts[action],
                show_apply_button: false,
            });
            const applyShortcut = () => {
                const previous = this._document.shortcuts[action];
                try {
                    mutateDocument(this._document, candidate => {
                        candidate.shortcuts[action] = row.text;
                    });
                } catch (error) {
                    row.text = previous;
                    this._error(error.message);
                    return;
                }
                if (!this._save()) row.text = previous;
            };
            const save = new Gtk.Button({label: 'Guardar', valign: Gtk.Align.CENTER});
            save.connect('clicked', applyShortcut);
            row.add_suffix(save);
            group.add(row);
        }
        const reset = new Adw.ActionRow({title: 'Restaurar atajos predeterminados'});
        reset.set_activatable(true);
        reset.connect('activated', () => {
            mutateDocument(this._document, candidate => {
                candidate.shortcuts = {...DEFAULT_SHORTCUTS};
            });
            if (this._save())
                this._render();
        });
        group.add(reset);
        return page;
    }

    _create() {
        this._layoutDialog(null, 'Nuevo layout', 'Mi layout', 3);
    }

    _duplicate(sourceId) {
        const label = BUILTIN_LAYOUTS.find(item => item[0] === sourceId)?.[1] ?? 'Layout';
        this._layoutDialog(sourceId, 'Duplicar layout', `Copia de ${label}`, 2);
    }

    _edit(layout) {
        this._layoutDialog(layout, 'Editar layout', layout.name, layout.zones.length);
    }

    _layoutDialog(source, title, initialName, _columns) {
        const dialog = new Adw.AlertDialog({heading: title});
        const box = new Gtk.Box({orientation: Gtk.Orientation.VERTICAL, spacing: 12});
        const name = new Gtk.Entry({text: initialName, placeholder_text: 'Nombre'});
        let currentZones = source
            ? layoutZones(this._document, typeof source === 'string' ? source : source.id)
            : presetZones('columns-3');
        let selectedIndex = 0;
        const history = [];

        const selectedLabel = new Gtk.Label({label: 'Zona 1 seleccionada', xalign: 0});
        const preview = new Gtk.DrawingArea({content_height: 240, hexpand: true});
        const refresh = () => {
            selectedIndex = Math.min(selectedIndex, currentZones.length - 1);
            selectedLabel.label = `Zona ${selectedIndex + 1} seleccionada`;
            preview.queue_draw();
        };
        const replaceZones = zones => {
            history.push(currentZones);
            currentZones = zones;
            selectedIndex = 0;
            refresh();
        };
        preview.set_draw_func((_area, cr, width, height) => {
            cr.setSourceRGBA(0.10, 0.11, 0.14, 1); cr.paint();
            for (const [index, rectangle] of previewRectangles(currentZones, width, height).entries()) {
                if (index === selectedIndex)
                    cr.setSourceRGBA(0.18, 0.62, 1, 0.95);
                else
                    cr.setSourceRGBA(0.28, 0.40, 0.58, 0.82);
                cr.rectangle(rectangle.x + 4, rectangle.y + 4,
                    Math.max(0, rectangle.width - 8), Math.max(0, rectangle.height - 8));
                cr.fill();
                cr.setSourceRGBA(1, 1, 1, 0.95);
                cr.selectFontFace('Sans', 0, 1); cr.setFontSize(18);
                cr.moveTo(rectangle.x + rectangle.width / 2 - 5,
                    rectangle.y + rectangle.height / 2 + 6);
                cr.showText(String(index + 1));
            }
        });
        const click = new Gtk.GestureClick();
        click.connect('released', (_gesture, _presses, x, y) => {
            const width = preview.get_width();
            const height = preview.get_height();
            const index = currentZones.findIndex(zone =>
                x >= zone.x * width && x <= (zone.x + zone.w) * width &&
                y >= zone.y * height && y <= (zone.y + zone.h) * height);
            if (index >= 0) {
                selectedIndex = index;
                refresh();
            }
        });
        preview.add_controller(click);

        const forms = new Gtk.FlowBox({
            selection_mode: Gtk.SelectionMode.NONE,
            max_children_per_line: 3,
            min_children_per_line: 2,
            column_spacing: 6,
            row_spacing: 6,
        });
        const presets = [
            ['1/2 : 1/2 ↔', 'columns-2'], ['1/3 : 1/3 : 1/3 ↔', 'columns-3'],
            ['1/2 : 1/2 ↕', 'rows-2'], ['1/4 : 1/4 : 1/4 : 1/4', 'grid-2x2'],
            ['1/2 : 1/4 : 1/4 ↔', 'main-left'], ['1/2 : 1/4 : 1/4 ↕', 'main-top'],
        ];
        for (const [label, preset] of presets) {
            const button = new Gtk.Button({label});
            button.connect('clicked', () => {
                replaceZones(presetZones(preset));
            });
            forms.insert(button, -1);
        }

        const actions = new Gtk.Box({spacing: 6, homogeneous: true});
        for (const [axis, label] of [['vertical', 'Dividir lado a lado'], ['horizontal', 'Dividir arriba y abajo']]) {
            const button = new Gtk.Button({label});
            button.connect('clicked', () => {
                try {
                    replaceZones(splitZone(currentZones, selectedIndex, axis));
                } catch (error) { this._error(error.message); }
            });
            actions.append(button);
        }
        const undo = new Gtk.Button({label: 'Deshacer'});
        undo.connect('clicked', () => {
            const previous = history.pop();
            if (previous) {
                currentZones = previous;
                selectedIndex = 0;
                refresh();
            }
        });

        box.append(name);
        box.append(forms);
        box.append(preview);
        box.append(selectedLabel);
        box.append(actions);
        box.append(undo);
        refresh();
        dialog.set_extra_child(box);
        dialog.add_response('cancel', 'Cancelar');
        dialog.add_response('save', 'Guardar');
        dialog.set_response_appearance('save', Adw.ResponseAppearance.SUGGESTED);
        dialog.connect('response', (_dialog, response) => {
            if (response !== 'save') return;
            try {
                const parsedZones = currentZones;
                if (source !== null && typeof source === 'object') {
                    mutateDocument(this._document, candidate => {
                        const target = candidate.custom_layouts.find(item => item.id === source.id);
                        if (!target) throw new Error(`Layout desconocido: ${source.id}`);
                        target.name = name.text;
                        target.zones = parsedZones;
                    });
                } else if (typeof source === 'string') {
                    const newId = nextCustomId(this._document, name.text);
                    mutateDocument(this._document, candidate => {
                        candidate.custom_layouts.push({id: newId, name: name.text, zones: parsedZones});
                        candidate.layout_order.push(newId);
                    });
                } else {
                    const newId = nextCustomId(this._document, name.text);
                    mutateDocument(this._document, candidate => {
                        candidate.custom_layouts.push({id: newId, name: name.text, zones: parsedZones});
                        candidate.layout_order.push(newId);
                    });
                }
                if (this._save()) this._render();
            } catch (error) { this._error(error.message); }
        });
        dialog.present(this._window);
    }

    _toggle(id, active) {
        try {
            mutateDocument(this._document, candidate => {
                const disabled = new Set(candidate.disabled_layouts);
                active ? disabled.delete(id) : disabled.add(id);
                candidate.disabled_layouts = candidate.layout_order.filter(item => disabled.has(item));
            });
        } catch (error) {
            this._error(error.message);
            this._render();
            return;
        }
        if (!this._save()) this._render();
    }

    _move(id, offset) {
        const index = this._document.layout_order.indexOf(id);
        const target = index + offset;
        if (target < 0 || target >= this._document.layout_order.length) return;
        mutateDocument(this._document, candidate => {
            [candidate.layout_order[index], candidate.layout_order[target]] =
                [candidate.layout_order[target], candidate.layout_order[index]];
        });
        if (this._save()) this._render();
    }

    _delete(id) {
        mutateDocument(this._document, candidate => {
            candidate.custom_layouts = candidate.custom_layouts.filter(item => item.id !== id);
            candidate.layout_order = candidate.layout_order.filter(item => item !== id);
            candidate.disabled_layouts = candidate.disabled_layouts.filter(item => item !== id);
        });
        if (this._save()) this._render();
    }

    _load() {
        try {
            const [ok, bytes] = GLib.file_get_contents(this._path);
            return ok ? normalizeDocument(JSON.parse(new TextDecoder().decode(bytes))) : defaultDocument();
        } catch (error) {
            console.error(`SnapAssist: ${error.message}`);
            return defaultDocument();
        }
    }

    _save() {
        try {
            validateDocument(this._document);
            const directory = GLib.path_get_dirname(this._path);
            GLib.mkdir_with_parents(directory, 0o700);
            const file = Gio.File.new_for_path(this._path);
            file.replace_contents(JSON.stringify(this._document, null, 2) + '\n', null, false, Gio.FileCreateFlags.REPLACE_DESTINATION, null);
            this._window.add_toast(new Adw.Toast({title: 'Cambios guardados y enviados a SnapAssist'}));
            return true;
        } catch (error) {
            this._error(error.message);
            return false;
        }
    }

    _error(message) {
        const dialog = new Adw.AlertDialog({heading: 'Configuración inválida', body: message});
        dialog.add_response('ok', 'Aceptar');
        dialog.present(this._window);
    }
}
