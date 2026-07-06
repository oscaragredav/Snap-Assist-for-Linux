"""
core/daemon.py — Event loop principal del daemon SnapAssist.

Escucha eventos X11 de forma bloqueante y los despacha a los handlers
correspondientes. El event loop recibe PropertyNotify (cambio de ventana
activa → actualización MRU), KeyPress (atajos globales → callbacks), y
eventos estructurales (Map/Unmap/Destroy/Configure) para fases posteriores.
"""

import logging
from typing import Optional

from Xlib import X

from snapassist.core.hotkeys import HotkeyManager
from snapassist.core.state import State
from snapassist.wm.backend import WindowManager

logger = logging.getLogger(__name__)


class Daemon:
    """
    Daemon principal de SnapAssist.

    Contiene el event loop que escucha eventos X11 sobre el root window
    y los despacha a los handlers registrados.
    """

    def __init__(
        self,
        wm_backend: WindowManager,
        state: State,
        hotkey_manager: HotkeyManager,
        ui_callback_queue = None,
        snap_flow = None
    ) -> None:
        self._wm = wm_backend
        self._state = state
        self._hotkeys = hotkey_manager
        self._ui_callback_queue = ui_callback_queue
        self._snap_flow = snap_flow
        
        self._running = False
        self._display = wm_backend.get_display()

        # Átomo de _NET_ACTIVE_WINDOW para comparar en PropertyNotify
        self._atom_active_window = self._display.intern_atom("_NET_ACTIVE_WINDOW")

        logger.info("Daemon inicializado.")

    def run(self) -> None:
        """
        Inicia el event loop bloqueante.

        Escucha eventos X11 y los despacha a handlers específicos:
        - PropertyNotify sobre _NET_ACTIVE_WINDOW → actualización MRU
        - Map/Unmap/Destroy/ConfigureNotify → logging (fases futuras)
        """
        import select
        self._running = True
        self._hotkeys.start()
        logger.info("Event loop iniciado. Escuchando eventos X11...")

        while self._running:
            try:
                # Usamos select con un timeout corto (0.5s) para no bloquear
                # indefinidamente y permitir que el flag _running se evalúe.
                readable, _, _ = select.select([self._display.fileno()], [], [], 0.5)
                
                if readable:
                    # pending_events() retorna el número de eventos encolados
                    while self._display.pending_events():
                        event = self._display.next_event()
                        self._dispatch_event(event)

                # Comprobar cola de callbacks de UI de forma no bloqueante
                if self._ui_callback_queue:
                    import queue
                    try:
                        while True:
                            msg = self._ui_callback_queue.get_nowait()
                            self._handle_ui_callback(msg)
                    except queue.Empty:
                        pass

            except KeyboardInterrupt:
                logger.info("Event loop interrumpido por KeyboardInterrupt.")
                break
            except Exception as e:
                # El event loop nunca debe crashear por un error individual.
                # Loguear y continuar (ver arquitectura §6.1).
                logger.error(
                    "Error no capturado en event loop: %s", e, exc_info=True
                )

        logger.info("Event loop finalizado.")

    def shutdown(self) -> None:
        """
        Detiene el event loop y libera recursos.

        Desregistra todos los atajos globales (XUngrabKey) y señaliza
        al event loop que debe terminar.
        Llamado por el handler de SIGTERM/SIGINT en main.py.
        """
        logger.info("Apagando daemon...")
        self._hotkeys.unregister_all()
        self._running = False

    def _dispatch_event(self, event) -> None:
        """
        Despacha un evento X11 al handler correspondiente.
        """
        event_type = event.type

        if event_type == X.PropertyNotify:
            self._handle_property_notify(event)

        elif event_type == X.MapNotify:
            wid = self._extract_wid(event)
            if wid:
                logger.debug("MapNotify: ventana 0x%x", wid)

        elif event_type == X.UnmapNotify:
            wid = self._extract_wid(event)
            if wid:
                logger.debug("UnmapNotify: ventana 0x%x", wid)

        elif event_type == X.DestroyNotify:
            wid = self._extract_wid(event)
            if wid:
                logger.debug("DestroyNotify: ventana 0x%x", wid)
                # Limpiar la ventana de la lista MRU
                self._state.remove_from_mru(wid)

        elif event_type == X.ConfigureNotify:
            wid = self._extract_wid(event)
            if wid:
                logger.debug(
                    "ConfigureNotify: ventana 0x%x (x=%d, y=%d, w=%d, h=%d)",
                    wid,
                    getattr(event, 'x', 0),
                    getattr(event, 'y', 0),
                    getattr(event, 'width', 0),
                    getattr(event, 'height', 0),
                )

    # ------------------------------------------------------------------
    # Handlers específicos
    # ------------------------------------------------------------------

    def _handle_property_notify(self, event) -> None:
        """
        Handler de PropertyNotify.

        Detecta cambios en _NET_ACTIVE_WINDOW sobre el root window y
        actualiza la lista MRU del estado global.
        """
        # Solo nos interesa _NET_ACTIVE_WINDOW
        if event.atom != self._atom_active_window:
            return

        # Obtener la nueva ventana activa
        active_wid = self._wm.get_active_window()

        if active_wid:
            title = self._wm.get_window_title(active_wid)
            logger.debug(
                "Cambio de ventana activa: 0x%x \"%s\"",
                active_wid, title[:60],
            )
            self._state.update_mru(active_wid)
        else:
            logger.debug("Ventana activa: ninguna (foco en escritorio).")

    # ------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_wid(event) -> Optional[int]:
        """Extrae el window_id de un evento X11, retorna None si no existe."""
        wid = getattr(event, 'window', None)
        if wid is None:
            return None
        return wid.id if hasattr(wid, 'id') else int(wid)

    @property
    def is_running(self) -> bool:
        """Retorna True si el event loop está activo."""
        return self._running

    def _handle_ui_callback(self, msg) -> None:
        """Procesa callbacks enviados desde el hilo de la UI."""
        if not self._snap_flow:
            return
            
        event = msg.get("event")
        if event == "layout_selected":
            layout_index = msg.get("layout_index")
            zone_index = msg.get("zone_index")
            self._snap_flow.confirm_selection(layout_index, zone_index)
            
        elif event == "layout_cancelled":
            self._snap_flow.cancel()
