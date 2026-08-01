"""
ui/ui_manager.py — Gestor del hilo de UI (Tkinter).

Maneja la inicialización de Tkinter en un hilo separado (UI Thread) y procesa
los comandos recibidos desde el hilo principal de X11 a través de una cola (queue).
"""

import logging
import threading
import queue
import tkinter as tk
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class UIManager:
    """
    Administra el ciclo de vida de Tkinter en un hilo secundario y provee
    una interfaz thread-safe para que el hilo principal le envíe comandos.
    """

    def __init__(self, callback_queue: queue.Queue):
        """
        :param callback_queue: Cola thread-safe donde la UI pondrá eventos 
                               (ej. layout_selected) para el hilo principal.
        """
        self._cmd_queue = queue.Queue()
        self._callback_queue = callback_queue
        
        self._root: Optional[tk.Tk] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        
        # Referencias a componentes de UI
        self._overlay = None
        self._layout_menu = None
        self._snap_assist_menu = None
        self._layout_flow_id = None
        self._snap_assist_flow_id = None

    def start(self) -> None:
        """Inicia el hilo de la UI."""
        if self._running:
            return
            
        self._running = True
        self._thread = threading.Thread(
            target=self._run_mainloop, 
            name="UIThread", 
            daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        """Detiene la UI y cierra Tkinter."""
        if not self._running:
            return
        self.send_command({"action": "quit"})
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=2.0)
            if self._thread.is_alive():
                logger.warning("El hilo de UI no terminó dentro del timeout")

    def send_command(self, cmd: Dict[str, Any]) -> None:
        """Envia un comando a la UI. (Thread-safe)"""
        self._cmd_queue.put(cmd)

    def _run_mainloop(self) -> None:
        """Punto de entrada del hilo de UI."""
        logger.info("Iniciando hilo de UI (Tkinter)...")
        
        # Es necesario crear la ventana root en el hilo que correrá el mainloop
        self._root = tk.Tk()
        self._root.withdraw()  # Ocultar la ventana base
        
        # Inicializar componentes
        from snapassist.ui.overlay import Overlay
        from snapassist.ui.layout_menu import LayoutMenu
        from snapassist.ui.snap_assist_menu import SnapAssistMenu
        
        self._overlay = Overlay(self._root)
        self._layout_menu = LayoutMenu(
            root=self._root, 
            on_selection=self._on_menu_selection,
            on_cancel=self._on_menu_cancel,
            on_hover=self._on_menu_hover
        )
        self._snap_assist_menu = SnapAssistMenu(
            root=self._root,
            on_selection=self._on_snap_assist_selection,
            on_cancel=self._on_snap_assist_cancel,
        )
        
        self._poll_queue()
        
        try:
            self._root.mainloop()
        except Exception as e:
            logger.error("Error en Tkinter mainloop: %s", e)
            
        finally:
            self._running = False
            try:
                self._root.destroy()
            except tk.TclError:
                pass
        logger.info("Hilo de UI finalizado.")

    def _poll_queue(self) -> None:
        """Procesa comandos de la cola de forma periódica."""
        if not self._running or not self._root:
            return

        try:
            while True:
                cmd = self._cmd_queue.get_nowait()
                self._process_command(cmd)
                if not self._running:
                    break
        except queue.Empty:
            pass

        # Repetir polling a ~60 FPS
        if self._running:
            self._root.after(16, self._poll_queue)

    def _process_command(self, cmd: Dict[str, Any]) -> None:
        """Ejecuta el comando recibido en el contexto del hilo UI."""
        action = cmd.get("action")
        
        try:
            if action == "quit":
                self._running = False
                self._root.quit()
                
            elif action == "show_menu":
                self._layout_flow_id = cmd.get("flow_id")
                layouts = cmd.get("layouts")
                monitor_rect = cmd.get("monitor_rect")
                absolute_rects = cmd.get("absolute_rects")
                disabled_layouts = cmd.get("disabled_layouts")
                self._layout_menu.show(layouts, absolute_rects, monitor_rect, disabled_layouts)
                
            elif action == "hide_menu":
                if (
                    cmd.get("flow_id") is not None
                    and cmd.get("flow_id") != self._layout_flow_id
                ):
                    return
                self._layout_menu.hide()
                self._overlay.hide()
                self._layout_flow_id = None

            elif action == "show_snap_assist":
                self._snap_assist_flow_id = cmd.get("flow_id")
                self._snap_assist_menu.show(
                    cmd.get("eligible_windows", []),
                    cmd.get("zone_rect"),
                )

            elif action == "hide_snap_assist":
                if (
                    cmd.get("flow_id") is not None
                    and cmd.get("flow_id") != self._snap_assist_flow_id
                ):
                    return
                self._snap_assist_menu.hide()
                self._snap_assist_flow_id = None
                
        except Exception as e:
            logger.error("Error procesando comando UI '%s': %s", action, e)
            flow_id = cmd.get("flow_id")
            if flow_id is None:
                flow_id = (
                    self._layout_flow_id
                    if action in {"show_menu", "hide_menu"}
                    else self._snap_assist_flow_id
                )
            self._callback_queue.put({
                "event": "ui_command_failed",
                "flow_id": flow_id,
                "action": action,
                "error": str(e),
            })

    # ------------------------------------------------------------------
    # Callbacks desde la UI (ejecutados en el UI Thread)
    # ------------------------------------------------------------------

    def _on_menu_selection(self, layout_index: int, zone_index: int) -> None:
        """El usuario seleccionó una zona con Enter."""
        self._layout_menu.hide()
        self._overlay.hide()
        self._callback_queue.put({
            "event": "layout_selected",
            "flow_id": self._layout_flow_id,
            "layout_index": layout_index,
            "zone_index": zone_index
        })

    def _on_menu_cancel(self) -> None:
        """El usuario canceló con Esc."""
        self._layout_menu.hide()
        self._overlay.hide()
        self._callback_queue.put({
            "event": "layout_cancelled",
            "flow_id": self._layout_flow_id,
        })

    def _on_menu_hover(self, zone_rect) -> None:
        """El usuario movió las flechas, se debe actualizar el overlay."""
        if zone_rect:
            self._overlay.show(zone_rect)
        else:
            self._overlay.hide()

    def _on_snap_assist_selection(self, wid: int) -> None:
        self._snap_assist_menu.hide()
        self._callback_queue.put({
            "event": "snap_assist_selected",
            "flow_id": self._snap_assist_flow_id,
            "window_id": wid,
        })

    def _on_snap_assist_cancel(self, reason: str) -> None:
        self._snap_assist_menu.hide()
        self._callback_queue.put({
            "event": "snap_assist_cancelled",
            "flow_id": self._snap_assist_flow_id,
            "reason": reason,
        })
