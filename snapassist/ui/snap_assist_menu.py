"""Menú de sugerencias de ventanas para las zonas vacías."""

import tkinter as tk
from typing import Callable, List

from snapassist.config import Rect, WindowInfo


class SnapAssistMenu:
    """Lista controlable por teclado, posicionada dentro de una zona."""

    def __init__(
        self,
        root: tk.Tk,
        on_selection: Callable[[int], None],
        on_cancel: Callable[[str], None],
    ) -> None:
        self._window = tk.Toplevel(root)
        self._window.withdraw()
        self._window.attributes("-type", "splash")
        self._window.attributes("-topmost", True)
        self._window.configure(bg="#1f2933")

        self._on_selection = on_selection
        self._on_cancel = on_cancel
        self._windows: List[WindowInfo] = []
        self._active_index = 0
        self._listbox = None
        self._position_label = None
        self._visible = False
        self._generation = 0

        self._window.bind("<Up>", lambda _event: self._handle_move(-1))
        self._window.bind("<Down>", lambda _event: self._handle_move(1))
        self._window.bind("<Return>", self._handle_confirm)
        self._window.bind("<Escape>", self._handle_escape)
        self._window.bind("<Key>", self._handle_quickkey)
        self._window.bind("<FocusOut>", self._focus_lost)

    def show(self, eligible_windows: List[WindowInfo], zone_rect: Rect) -> None:
        self._generation += 1
        self._windows = list(eligible_windows)
        self._active_index = 0
        self._draw()

        width = max(280, min(520, zone_rect.w - 32))
        # Ocho filas visibles conservan una lectura cómoda; el resto se alcanza
        # por scrollbar, flechas y auto-scroll de la selección.
        height = max(160, min(420, 70 + min(8, len(self._windows)) * 42))
        width = min(width, zone_rect.w)
        height = min(height, zone_rect.h)
        x = zone_rect.x + max(0, (zone_rect.w - width) // 2)
        y = zone_rect.y + max(0, (zone_rect.h - height) // 2)

        self._window.geometry(f"{width}x{height}+{x}+{y}")
        self._visible = True
        self._window.deiconify()
        self._window.lift()
        self._window.focus_force()
        self._window.grab_set()
        self._paint_selection()

    def hide(self) -> None:
        if not self._visible:
            return
        self._visible = False
        self._generation += 1
        try:
            self._window.grab_release()
        except tk.TclError:
            pass
        self._window.withdraw()

    def _draw(self) -> None:
        for widget in self._window.winfo_children():
            widget.destroy()
        title = tk.Label(
            self._window,
            text="Completar esta zona",
            fg="white",
            bg="#1f2933",
            font=("Inter", 13, "bold"),
            pady=12,
        )
        title.pack(fill="x")
        self._position_label = tk.Label(
            self._window,
            fg="#9ca3af",
            bg="#1f2933",
            font=("Inter", 9),
        )
        self._position_label.pack(fill="x", pady=(0, 5))

        list_frame = tk.Frame(self._window, bg="#1f2933")
        list_frame.pack(expand=True, fill="both", padx=12, pady=(0, 10))
        scrollbar = tk.Scrollbar(list_frame, orient="vertical")
        self._listbox = tk.Listbox(
            list_frame,
            activestyle="none",
            exportselection=False,
            selectbackground="#2563eb",
            selectforeground="#ffffff",
            bg="#374151",
            fg="#e5e7eb",
            highlightthickness=0,
            relief="flat",
            font=("Inter", 11),
            yscrollcommand=scrollbar.set,
        )
        scrollbar.configure(command=self._listbox.yview)
        self._listbox.pack(side="left", expand=True, fill="both")
        scrollbar.pack(side="right", fill="y")

        for info in self._windows:
            key = (info.quickkey or "→").upper()
            text = f"[{key}]  {info.title or f'Ventana 0x{info.window_id:x}'}"
            self._listbox.insert("end", text)

        for widget in (self._window, self._listbox):
            widget.bind("<Up>", lambda _event: self._handle_move(-1))
            widget.bind("<Down>", lambda _event: self._handle_move(1))
            widget.bind("<Return>", self._handle_confirm)
            widget.bind("<Escape>", self._handle_escape)
            widget.bind("<Key>", self._handle_quickkey)

    def _handle_move(self, delta: int) -> str:
        self._move(delta)
        return "break"

    def _handle_confirm(self, _event) -> str:
        self._confirm()
        return "break"

    def _handle_escape(self, _event) -> str:
        self._cancel("escape")
        return "break"

    def _handle_quickkey(self, event) -> str:
        self._quickkey(event)
        return "break"

    def _move(self, delta: int) -> None:
        if not self._windows:
            return
        self._active_index = (self._active_index + delta) % len(self._windows)
        self._paint_selection()

    def _paint_selection(self) -> None:
        if not self._listbox:
            return
        self._listbox.selection_clear(0, "end")
        self._listbox.selection_set(self._active_index)
        self._listbox.activate(self._active_index)
        self._listbox.see(self._active_index)
        if self._position_label:
            self._position_label.configure(
                text=f"{self._active_index + 1}/{len(self._windows)}"
            )

    def _confirm(self) -> None:
        if self._windows:
            self._on_selection(self._windows[self._active_index].window_id)

    def _quickkey(self, event) -> None:
        key = (getattr(event, "char", "") or "").lower()
        for info in self._windows:
            if info.quickkey == key:
                self._on_selection(info.window_id)
                return

    def _cancel(self, reason: str) -> None:
        if self._visible:
            self._on_cancel(reason)

    def _focus_lost(self, _event) -> None:
        # after_idle evita interpretar como interrupción un cambio de foco
        # interno durante la creación/ocultación de la ventana.
        generation = self._generation
        self._window.after_idle(
            lambda: self._cancel_if_still_unfocused(generation)
        )

    def _cancel_if_still_unfocused(self, generation=None) -> None:
        if (
            (generation is None or generation == self._generation)
            and self._visible
            and self._window.focus_displayof() is None
        ):
            self._cancel("focus_out")
