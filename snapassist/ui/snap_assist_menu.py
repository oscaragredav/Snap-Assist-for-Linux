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
        self._rows = []
        self._visible = False

        self._window.bind("<Up>", lambda _event: self._move(-1))
        self._window.bind("<Down>", lambda _event: self._move(1))
        self._window.bind("<Return>", lambda _event: self._confirm())
        self._window.bind("<Escape>", lambda _event: self._cancel("escape"))
        self._window.bind("<Key>", self._quickkey)
        self._window.bind("<FocusOut>", self._focus_lost)

    def show(self, eligible_windows: List[WindowInfo], zone_rect: Rect) -> None:
        self._windows = list(eligible_windows)
        self._active_index = 0
        self._draw()

        width = max(280, min(520, zone_rect.w - 32))
        height = max(160, min(420, 70 + len(self._windows) * 42))
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
        try:
            self._window.grab_release()
        except tk.TclError:
            pass
        self._window.withdraw()

    def _draw(self) -> None:
        for widget in self._window.winfo_children():
            widget.destroy()
        self._rows = []

        title = tk.Label(
            self._window,
            text="Completar esta zona",
            fg="white",
            bg="#1f2933",
            font=("Inter", 13, "bold"),
            pady=12,
        )
        title.pack(fill="x")

        for info in self._windows:
            key = (info.quickkey or "?").upper()
            text = f"[{key}]  {info.title or f'Ventana 0x{info.window_id:x}'}"
            row = tk.Label(
                self._window,
                text=text,
                anchor="w",
                padx=14,
                pady=8,
                fg="#e5e7eb",
                bg="#374151",
                font=("Inter", 11),
            )
            row.pack(fill="x", padx=12, pady=2)
            self._rows.append(row)

    def _move(self, delta: int) -> None:
        if not self._windows:
            return
        self._active_index = (self._active_index + delta) % len(self._windows)
        self._paint_selection()

    def _paint_selection(self) -> None:
        for index, row in enumerate(self._rows):
            row.configure(bg="#2563eb" if index == self._active_index else "#374151")

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
        self._window.after_idle(self._cancel_if_still_unfocused)

    def _cancel_if_still_unfocused(self) -> None:
        if self._visible and self._window.focus_displayof() is None:
            self._cancel("focus_out")
