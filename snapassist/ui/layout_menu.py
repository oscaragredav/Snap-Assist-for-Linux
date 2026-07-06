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
        
        # Bindings de teclado
        self._window.bind("<Left>", lambda e: self._move(-1))
        self._window.bind("<Right>", lambda e: self._move(1))
        self._window.bind("<Return>", lambda e: self._confirm())
        self._window.bind("<Escape>", lambda e: self._cancel())
        
        # Si la ventana pierde el foco (ej. clic en otro lado o Alt-Tab), se cancela
        self._window.bind("<FocusOut>", lambda e: self._cancel())

    def show(self, templates: List, absolute_rects: List[List], monitor_rect, disabled_layouts: List[bool] = None) -> None:
        """
        templates: lista de LayoutTemplate
        absolute_rects: rectángulos absolutos calculados para las zonas de cada layout
        monitor_rect: Rect del monitor para centrar el menú
        """
        self._templates = templates
        self._absolute_rects = absolute_rects
        self._monitor_rect = monitor_rect
        self._disabled_layouts = disabled_layouts or [False] * len(templates)
        
        # Encontrar el primer layout no deshabilitado
        self._active_layout_idx = 0
        for i, disabled in enumerate(self._disabled_layouts):
            if not disabled:
                self._active_layout_idx = i
                break
        self._active_zone_idx = 0
        
        self._draw_ui()
        
        # Tamaño base del menú
        window_width = 800
        window_height = 200
        
        # Centrar el menú dentro del monitor actual
        x = monitor_rect.x + (monitor_rect.w - window_width) // 2
        y = monitor_rect.y + (monitor_rect.h - window_height) // 2
        
        self._window.geometry(f"{window_width}x{window_height}+{x}+{y}")
        self._window.deiconify()
        self._window.focus_force()
        self._window.grab_set()  # Capturar TODO el input del teclado/mouse
        self._update_hover()

    def hide(self) -> None:
        """Oculta el menú visual."""
        self._window.grab_release()
        self._window.withdraw()
        
    def _draw_ui(self):
        """Dibuja los mini-mapas de layouts."""
        for widget in self._window.winfo_children():
            widget.destroy()
            
        self._zone_widgets.clear()
        
        main_frame = tk.Frame(self._window, bg="#2c3e50", padx=20, pady=20)
        main_frame.pack(expand=True, fill="both")
        
        title = tk.Label(
            main_frame, 
            text="Selecciona una Zona (Usa ← / → y Enter)", 
            fg="white", 
            bg="#2c3e50", 
            font=("Inter", 14, "bold")
        )
        title.pack(pady=(0, 20))
        
        grid_frame = tk.Frame(main_frame, bg="#2c3e50")
        grid_frame.pack()
        
        for l_idx, template in enumerate(self._templates):
            is_disabled = self._disabled_layouts[l_idx]
            frame_bg = "#1a252f" if is_disabled else "#34495e"
            zone_bg = "#2c3e50" if is_disabled else "#7f8c8d"
            
            # Frame contenedor para un layout (mini-mapa)
            frame_w = 120
            frame_h = 80
            layout_frame = tk.Frame(
                grid_frame, bg=frame_bg, bd=0, 
                width=frame_w, height=frame_h
            )
            layout_frame.grid(row=0, column=l_idx, padx=15)
            layout_frame.pack_propagate(False)
            
            # Dibujar rectángulos proporcionales para cada zona
            for z_idx, zone in enumerate(template.zones):
                zx = int(zone.x * frame_w)
                zy = int(zone.y * frame_h)
                zw = int(zone.w * frame_w)
                zh = int(zone.h * frame_h)
                
                # Ajuste para dejar bordes negros entre zonas
                pad = 1
                z_lbl = tk.Label(layout_frame, bg=zone_bg)
                z_lbl.place(x=zx+pad, y=zy+pad, width=zw-(pad*2), height=zh-(pad*2))
                self._zone_widgets.append((l_idx, z_idx, z_lbl))

    def _move(self, dx: int):
        """Mueve la selección hacia izquierda o derecha a través de las zonas."""
        if not self._templates:
            return
            
        template = self._templates[self._active_layout_idx]
        
        if dx == 1:
            self._active_zone_idx += 1
            if self._active_zone_idx >= len(template.zones):
                for _ in range(len(self._templates)):
                    self._active_layout_idx = (self._active_layout_idx + 1) % len(self._templates)
                    if not self._disabled_layouts[self._active_layout_idx]:
                        break
                self._active_zone_idx = 0
        elif dx == -1:
            self._active_zone_idx -= 1
            if self._active_zone_idx < 0:
                for _ in range(len(self._templates)):
                    self._active_layout_idx = (self._active_layout_idx - 1) % len(self._templates)
                    if not self._disabled_layouts[self._active_layout_idx]:
                        break
                prev_template = self._templates[self._active_layout_idx]
                self._active_zone_idx = len(prev_template.zones) - 1
                
        self._update_hover()
        
    def _update_hover(self):
        """Actualiza el color de resaltado y avisa a la UI manager del cambio."""
        for l_idx, z_idx, widget in self._zone_widgets:
            if l_idx == self._active_layout_idx and z_idx == self._active_zone_idx:
                widget.configure(bg="#3498db") # Resaltado
            else:
                widget.configure(bg="#7f8c8d") # Normal
                
        # Emitir callback con el rectángulo absoluto correspondiente
        try:
            target_rect = self._absolute_rects[self._active_layout_idx][self._active_zone_idx]
            self.on_hover(target_rect)
        except IndexError:
            self.on_hover(None)
            
        # Garantizar que el menú se mantiene sobre el overlay en el Z-index
        self._window.lift()
        
    def _confirm(self):
        self.on_selection(self._active_layout_idx, self._active_zone_idx)
        
    def _cancel(self):
        self.on_cancel()
