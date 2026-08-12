"""
ui/layout_menu.py — Menú visual en pantalla.
"""

import tkinter as tk
from typing import Callable, List
import logging

logger = logging.getLogger(__name__)


class LayoutMenu:
    """
    Dibuja un menú flotante en el centro de la pantalla permitiendo
    seleccionar un layout y una zona usando las teclas direccionales.
    """

    def __init__(
        self,
        root: tk.Tk,
        on_selection: Callable[[int, int], None],
        on_cancel: Callable[[], None],
        on_hover: Callable[[any], None]
    ):
        self._window = tk.Toplevel(root)
        self._window.withdraw()
        
        # Usar -type splash en lugar de overrideredirect permite que el gestor 
        # de ventanas (Mutter) asigne el foco del teclado correctamente.
        self._window.attributes("-type", "splash")
        self._window.attributes("-topmost", True)
        self._window.configure(bg="#2c3e50")
        
        self.on_selection = on_selection
        self.on_cancel = on_cancel
        self.on_hover = on_hover
        
        self._templates = []
        self._absolute_rects = []
        self._monitor_rect = None
        
        self._active_layout_idx = 0
        self._active_zone_idx = 0
        self._zone_widgets = []  # Tuplas (layout_idx, zone_idx, tk_widget)
        self._layout_widgets = []
        self._stage = "layout"
        self._visible = False
        self._generation = 0
        
        # Bindings de teclado
        self._window.bind("<Left>", lambda _event: self._move(-1))
        self._window.bind("<Right>", lambda _event: self._move(1))
        self._window.bind("<Up>", lambda _event: self._move(-1))
        self._window.bind("<Down>", lambda _event: self._move(1))
        self._window.bind("<Return>", lambda _event: self._confirm())
        self._window.bind("<Escape>", lambda _event: self._back_or_cancel())
        self._window.bind("<Key>", self._handle_key)
        
        # Si la ventana pierde el foco (ej. clic en otro lado o Alt-Tab), se cancela
        self._window.bind("<FocusOut>", self._focus_lost)

    def show(self, templates: List, absolute_rects: List[List], monitor_rect, disabled_layouts: List[bool] = None, active_window_name: str = "") -> None:
        """
        templates: lista de LayoutTemplate
        absolute_rects: rectángulos absolutos calculados para las zonas de cada layout
        monitor_rect: Rect del monitor para centrar el menú
        """
        self._generation += 1
        self._templates = templates
        self._absolute_rects = absolute_rects
        self._monitor_rect = monitor_rect
        self._disabled_layouts = disabled_layouts or [False] * len(templates)
        self._active_window_name = active_window_name
        
        # Encontrar el primer layout no deshabilitado
        self._active_layout_idx = 0
        for i, disabled in enumerate(self._disabled_layouts):
            if not disabled:
                self._active_layout_idx = i
                break
        self._active_zone_idx = 0
        self._stage = "layout"

        # Ajustar columnas y filas al monitor. Esto evita que el sexto layout
        # (1:1:1) quede recortado aunque todos los layouts sean elegibles.
        available_width = max(150, monitor_rect.w - 80)
        self._grid_columns = max(
            1,
            min(len(templates), available_width // 150),
        )
        
        self._draw_ui()
        
        rows = (len(templates) + self._grid_columns - 1) // self._grid_columns
        window_width = min(monitor_rect.w - 40, self._grid_columns * 150 + 60)
        window_height = min(monitor_rect.h - 40, rows * 120 + 185)
        
        # Centrar el menú dentro del monitor actual
        x = monitor_rect.x + (monitor_rect.w - window_width) // 2
        y = monitor_rect.y + (monitor_rect.h - window_height) // 2
        
        self._window.geometry(f"{window_width}x{window_height}+{x}+{y}")
        self._visible = True
        self._window.deiconify()
        self._window.focus_force()
        self._window.grab_set()  # Capturar TODO el input del teclado/mouse
        self._update_hover()

    def hide(self) -> None:
        """Oculta el menú visual."""
        # Marcarlo como oculto antes de liberar el foco evita que el FocusOut
        # generado por la propia confirmación se convierta en una cancelación.
        self._visible = False
        self._generation += 1
        try:
            self._window.grab_release()
        except tk.TclError:
            pass
        self._window.withdraw()
        
    def _draw_ui(self):
        """Dibuja los mini-mapas de layouts."""
        for widget in self._window.winfo_children():
            widget.destroy()
            
        self._zone_widgets.clear()
        self._layout_widgets.clear()
        
        main_frame = tk.Frame(self._window, bg="#2c3e50", padx=20, pady=20)
        main_frame.pack(expand=True, fill="both")
        
        self._title_label = tk.Label(
            main_frame, 
            text="Paso 1: elige un layout con ←/→, Enter o las teclas 1–6",
            fg="white", 
            bg="#2c3e50", 
            font=("Inter", 14, "bold")
        )
        self._title_label.pack(pady=(0, 12))

        if self._active_window_name:
            active_label = tk.Label(
                main_frame,
                text=f"Organizando: {self._active_window_name}",
                fg="#93c5fd",
                bg="#2c3e50",
                font=("Inter", 11, "bold"),
                wraplength=760,
            )
            active_label.pack(pady=(0, 12))
        
        grid_frame = tk.Frame(main_frame, bg="#2c3e50")
        grid_frame.pack()
        
        for l_idx, template in enumerate(self._templates):
            is_disabled = self._disabled_layouts[l_idx]
            frame_bg = "#1a252f" if is_disabled else "#34495e"
            zone_bg = "#2c3e50" if is_disabled else "#7f8c8d"
            
            item_frame = tk.Frame(
                grid_frame,
                bg="#2c3e50",
                highlightthickness=2,
                highlightbackground="#2c3e50",
            )
            row = l_idx // self._grid_columns
            column = l_idx % self._grid_columns
            item_frame.grid(row=row, column=column, padx=8, pady=6)

            name_label = tk.Label(
                item_frame,
                text=f"[{l_idx + 1}] {template.name}",
                fg="#6b7280" if is_disabled else "white",
                bg="#2c3e50",
                font=("Inter", 9, "bold"),
            )
            name_label.pack(pady=(0, 4))

            frame_w = 120
            frame_h = 64
            layout_frame = tk.Frame(
                item_frame,
                bg=frame_bg,
                bd=0,
                width=frame_w,
                height=frame_h,
            )
            layout_frame.pack()
            layout_frame.pack_propagate(False)
            self._layout_widgets.append((l_idx, item_frame))
            
            # Dibujar rectángulos proporcionales para cada zona
            for z_idx, zone in enumerate(template.zones):
                zx = int(zone.x * frame_w)
                zy = int(zone.y * frame_h)
                zw = int(zone.w * frame_w)
                zh = int(zone.h * frame_h)
                
                # Ajuste para dejar bordes negros entre zonas
                pad = 1
                z_lbl = tk.Label(
                    layout_frame,
                    bg=zone_bg,
                    fg="white",
                    text=str(z_idx + 1),
                    font=("Inter", 9, "bold"),
                )
                z_lbl.place(x=zx+pad, y=zy+pad, width=zw-(pad*2), height=zh-(pad*2))
                self._zone_widgets.append((l_idx, z_idx, z_lbl))

        self._hint_label = tk.Label(
            main_frame,
            text="",
            fg="#d1d5db",
            bg="#2c3e50",
            font=("Inter", 10),
        )
        self._hint_label.pack(pady=(10, 0))

    def _move(self, delta: int):
        """Navega layouts en el paso 1 y posiciones en el paso 2."""
        if not self._templates:
            return

        if self._stage == "layout":
            for _ in range(len(self._templates)):
                self._active_layout_idx = (
                    self._active_layout_idx + delta
                ) % len(self._templates)
                if not self._disabled_layouts[self._active_layout_idx]:
                    break
            self._active_zone_idx = 0
        else:
            zones = self._templates[self._active_layout_idx].zones
            self._active_zone_idx = (
                self._active_zone_idx + delta
            ) % len(zones)
        self._update_hover()
        
    def _update_hover(self):
        """Actualiza el color de resaltado y avisa a la UI manager del cambio."""
        for layout_idx, widget in self._layout_widgets:
            selected = (
                self._stage == "layout"
                and layout_idx == self._active_layout_idx
            )
            widget.configure(
                highlightbackground="#3498db" if selected else "#2c3e50"
            )

        for l_idx, z_idx, widget in self._zone_widgets:
            if self._disabled_layouts[l_idx]:
                widget.configure(bg="#2c3e50")
            elif (
                self._stage == "zone"
                and l_idx == self._active_layout_idx
                and z_idx == self._active_zone_idx
            ):
                widget.configure(bg="#3498db")
            else:
                widget.configure(bg="#7f8c8d")

        if self._stage == "layout":
            self._title_label.configure(
                text="Paso 1: elige un layout con ←/→, Enter o las teclas 1–6"
            )
            self._hint_label.configure(
                text=f"Seleccionado: {self._templates[self._active_layout_idx].name}"
            )
            self.on_hover(None)
        else:
            template = self._templates[self._active_layout_idx]
            descriptions = "   ".join(
                f"[{index + 1}] {self._zone_name(zone)}"
                for index, zone in enumerate(template.zones)
            )
            self._title_label.configure(
                text=f"Paso 2: elige posición en {template.name}"
            )
            self._hint_label.configure(
                text=f"{descriptions}   ·   Flechas + Enter"
            )
            try:
                target_rect = self._absolute_rects[
                    self._active_layout_idx
                ][self._active_zone_idx]
                self.on_hover(target_rect)
            except IndexError:
                self.on_hover(None)
            
        # Garantizar que el menú se mantiene sobre el overlay en el Z-index
        self._window.lift()
        
    def _confirm(self):
        if not self._visible:
            return
        if self._stage == "layout":
            self._stage = "zone"
            self._active_zone_idx = 0
            self._update_hover()
            return
        # El callback oculta la ventana. Desactivar primero el manejo de
        # FocusOut hace atómica la transición selección → animación.
        self._visible = False
        self.on_selection(self._active_layout_idx, self._active_zone_idx)

    def _handle_key(self, event):
        """Selección directa: número de layout y después número de posición."""
        char = (getattr(event, "char", "") or "")
        if not char.isdigit() or char == "0":
            return
        index = int(char) - 1
        if self._stage == "layout":
            if index >= len(self._templates) or self._disabled_layouts[index]:
                return
            self._active_layout_idx = index
            self._active_zone_idx = 0
            self._stage = "zone"
            self._update_hover()
            return

        zones = self._templates[self._active_layout_idx].zones
        if index < len(zones):
            self._active_zone_idx = index
            self._confirm()

    def _back_or_cancel(self):
        self._cancel()
        
    def _cancel(self):
        if not self._visible:
            return
        self._visible = False
        self.on_cancel()

    def _focus_lost(self, _event):
        """Cancela únicamente si la pérdida de foco fue externa."""
        generation = self._generation
        self._window.after_idle(
            lambda: self._cancel_if_still_unfocused(generation)
        )

    def _cancel_if_still_unfocused(self, generation=None):
        if (
            (generation is None or generation == self._generation)
            and self._visible
            and self._window.focus_displayof() is None
        ):
            self._cancel()

    @staticmethod
    def _zone_name(zone):
        """Genera una descripción espacial breve para una zona proporcional."""
        center_x = zone.x + zone.w / 2
        center_y = zone.y + zone.h / 2

        horizontal = (
            "izquierda" if center_x < 0.4
            else "derecha" if center_x > 0.6
            else "centro"
        )
        vertical = (
            "arriba" if center_y < 0.4
            else "abajo" if center_y > 0.6
            else "medio"
        )

        if zone.h >= 0.8:
            return horizontal.capitalize()
        if zone.w >= 0.8:
            return vertical.capitalize()
        if horizontal == "centro":
            return vertical.capitalize()
        if vertical == "medio":
            return horizontal.capitalize()
        return f"{vertical.capitalize()} {horizontal}"
