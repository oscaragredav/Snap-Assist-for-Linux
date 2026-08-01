"""
core/daemon.py — Event loop principal del daemon SnapAssist.

Escucha eventos X11 de forma bloqueante y los despacha a los handlers
correspondientes. El event loop recibe PropertyNotify (cambio de ventana
activa → actualización MRU), KeyPress (atajos globales → callbacks), y
eventos estructurales (Map/Unmap/Destroy/Configure) para fases posteriores.
"""

import logging
import math
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
        pointer_event_queue = None,
        control_callback_queue = None,
        snap_flow = None,
        group_manager = None,
    ) -> None:
        self._wm = wm_backend
        self._state = state
        self._hotkeys = hotkey_manager
        self._ui_callback_queue = ui_callback_queue
        self._pointer_event_queue = pointer_event_queue
        self._control_callback_queue = control_callback_queue
        self._snap_flow = snap_flow
        self._group_manager = group_manager
        
        self._running = False
        self._display = wm_backend.get_display()

        # Átomo de _NET_ACTIVE_WINDOW para comparar en PropertyNotify
        self._atom_active_window = self._display.intern_atom("_NET_ACTIVE_WINDOW")
        self._drag_starts = {}
        self._drag_distances = {}
        self._gesture_modes = {}
        monitor_loader = getattr(self._wm, "get_monitors", None)
        self._monitors = list(monitor_loader() if monitor_loader else [])

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
                # Usamos select con un timeout corto (50 ms) para no bloquear
                # indefinidamente y permitir que el flag _running se evalúe.
                readable, _, _ = select.select([self._display.fileno()], [], [], 0.05)

                if not self._running:
                    break
                
                if readable:
                    # pending_events() retorna el número de eventos encolados
                    while self._display.pending_events():
                        event = self._display.next_event()
                        self._safe_dispatch_event(event)

                # Comprobar cola de callbacks de UI de forma no bloqueante
                if self._ui_callback_queue:
                    import queue
                    try:
                        while True:
                            msg = self._ui_callback_queue.get_nowait()
                            self._handle_ui_callback(msg)
                    except queue.Empty:
                        pass

                if self._pointer_event_queue:
                    import queue
                    try:
                        while True:
                            self._handle_pointer_event(self._pointer_event_queue.get_nowait())
                    except queue.Empty:
                        pass

                if self._control_callback_queue:
                    import queue
                    try:
                        # Un límite evita que una tecla defectuosa monopolice
                        # el event loop; el resto se procesa en la siguiente vuelta.
                        for _ in range(100):
                            callback = self._control_callback_queue.get_nowait()
                            callback()
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

        try:
            self._hotkeys.unregister_all()
        except Exception as e:
            logger.error("Error deteniendo listeners: %s", e, exc_info=True)
        logger.info("Event loop finalizado.")

    def shutdown(self) -> None:
        """
        Solicita detener el event loop. La liberación de listeners y UI se
        realiza después de salir del loop, fuera del handler de señales.
        Llamado por el handler de SIGTERM/SIGINT en main.py.
        """
        if not self._running:
            return
        logger.info("Apagando daemon...")
        self._running = False

    def _dispatch_event(self, event) -> None:
        """
        Despacha un evento X11 al handler correspondiente.
        """
        if self._is_randr_screen_change(event):
            self._handle_screen_change()
            return

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
                self._drag_starts.pop(wid, None)
                self._drag_distances.pop(wid, None)
                self._gesture_modes.pop(wid, None)
                if self._snap_flow:
                    self._snap_flow.on_window_destroyed(wid)

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
                if self._consume_own_resize(wid, event):
                    logger.debug("ConfigureNotify propio consumido: 0x%x", wid)
                elif self._state.is_snapped(wid) and self._snap_flow:
                    # Muchas aplicaciones (Terminal, Electron/WhatsApp, Spotify)
                    # y Mutter emiten ajustes propios al mapear o cambiar foco.
                    # Sólo un gesto de puntero confirmado desacopla la ventana.
                    logger.debug(
                        "ConfigureNotify no propio ignorado sin gesto de usuario: 0x%x",
                        wid,
                    )

        elif event_type == X.ButtonPress:
            self._handle_button_press(event)

        elif event_type == X.MotionNotify:
            self._handle_motion_notify(event)

        elif event_type == X.ButtonRelease:
            wid = self._extract_wid(event)
            if wid:
                self._drag_starts.pop(wid, None)
                self._drag_distances.pop(wid, None)
                self._gesture_modes.pop(wid, None)

    def _safe_dispatch_event(self, event) -> bool:
        """Aísla cada evento: uno defectuoso no detiene los siguientes."""
        try:
            self._dispatch_event(event)
            return True
        except Exception as e:
            logger.error("Error procesando evento X11: %s", e, exc_info=True)
            return False

    @staticmethod
    def _is_randr_screen_change(event) -> bool:
        return bool(
            getattr(event, "_snapassist_randr_screen_change", False)
            or event.__class__.__name__ in {
                "ScreenChangeNotify", "RRScreenChangeNotify",
                "CrtcChangeNotify", "RRCrtcChangeNotify",
                "OutputChangeNotify", "RROutputChangeNotify",
            }
        )

    def _handle_screen_change(self) -> None:
        loader = getattr(self._wm, "get_monitors", None)
        new_monitors = list(loader() if loader else [])
        if not new_monitors:
            logger.warning("XRandR notificó una topología vacía; se conserva la anterior")
            return
        old_monitors = self._monitors
        self._monitors = new_monitors
        if self._group_manager:
            self._group_manager.on_monitors_changed(old_monitors, new_monitors)
        if self._snap_flow:
            self._snap_flow.on_monitors_changed()
        logger.info(
            "Topología XRandR actualizada: %d → %d monitor(es)",
            len(old_monitors), len(new_monitors),
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

    def _handle_button_press(self, event) -> None:
        wid = self._extract_wid(event)
        if not wid or not self._state.is_snapped(wid):
            return
        self._drag_starts[wid] = (getattr(event, "root_x", 0), getattr(event, "root_y", 0))
        self._drag_distances[wid] = 0.0
        self._gesture_modes[wid] = "drag"

    def _handle_motion_notify(self, event) -> None:
        wid = self._extract_wid(event)
        if not wid or wid not in self._drag_starts or not self._state.is_snapped(wid):
            return

        previous_x, previous_y = self._drag_starts[wid]
        current_x = getattr(event, "root_x", previous_x)
        current_y = getattr(event, "root_y", previous_y)
        self._drag_distances[wid] += math.hypot(current_x - previous_x, current_y - previous_y)
        self._drag_starts[wid] = (current_x, current_y)

        from snapassist.config import DRAG_THRESHOLD_PX
        if self._drag_distances[wid] >= DRAG_THRESHOLD_PX:
            logger.info("Drag intencional detectado en 0x%x (%.1f px)", wid, self._drag_distances[wid])
            self._drag_starts.pop(wid, None)
            self._drag_distances.pop(wid, None)
            if self._snap_flow:
                mode = getattr(self, "_gesture_modes", {}).pop(wid, "drag")
                if mode == "resize":
                    self._snap_flow.on_window_resized(wid)
                else:
                    self._snap_flow.on_window_dragged(wid)

    def _consume_own_resize(self, wid: int, event=None) -> bool:
        """Consume una notificación propia si el backend puede identificarla."""
        consume = getattr(self._wm, "consume_own_resize", None)
        if not consume:
            return False
        try:
            return bool(consume(wid, event))
        except TypeError:
            # Compatibilidad con mocks y backends de fases anteriores.
            return bool(consume(wid))

    def _handle_pointer_event(self, event) -> None:
        """Procesa eventos globales de pynput en el hilo seguro de X11."""
        event_name = event.get("event")
        x, y = event.get("x", 0), event.get("y", 0)
        if event_name == "pointer_press":
            active_wid = self._wm.get_active_window()
            if active_wid and self._state.is_snapped(active_wid):
                mode = self._classify_pointer_gesture(active_wid, x, y)
                if mode:
                    self._drag_starts[active_wid] = (x, y)
                    self._drag_distances[active_wid] = 0.0
                    self._gesture_modes[active_wid] = mode
        elif event_name == "pointer_move":
            for wid in list(self._drag_starts):
                self._handle_drag_motion(wid, x, y)
        elif event_name == "pointer_release":
            self._drag_starts.clear()
            self._drag_distances.clear()
            self._gesture_modes.clear()

    def _handle_drag_motion(self, wid: int, current_x: int, current_y: int) -> None:
        """Acumula el movimiento y desacopla al superar el umbral."""
        if wid not in self._drag_starts or not self._state.is_snapped(wid):
            return
        previous_x, previous_y = self._drag_starts[wid]
        self._drag_distances[wid] += math.hypot(current_x - previous_x, current_y - previous_y)
        self._drag_starts[wid] = (current_x, current_y)

        from snapassist.config import DRAG_THRESHOLD_PX
        if self._drag_distances[wid] >= DRAG_THRESHOLD_PX:
            logger.info("Drag intencional detectado en 0x%x (%.1f px)", wid, self._drag_distances[wid])
            self._drag_starts.pop(wid, None)
            self._drag_distances.pop(wid, None)
            if self._snap_flow:
                mode = getattr(self, "_gesture_modes", {}).pop(wid, "drag")
                if mode == "resize":
                    self._snap_flow.on_window_resized(wid)
                else:
                    self._snap_flow.on_window_dragged(wid)

    def _classify_pointer_gesture(self, wid: int, x: int, y: int):
        """Distingue resize de borde, drag de título y clicks de contenido."""
        rect = self._wm.get_window_geometry(wid).rect
        edge_margin = 16
        titlebar_height = 60
        within_x = rect.x - edge_margin <= x <= rect.right + edge_margin
        within_y = rect.y - edge_margin <= y <= rect.bottom + edge_margin
        near_edge = (
            within_y
            and (
                abs(x - rect.x) <= edge_margin
                or abs(x - rect.right) <= edge_margin
            )
        ) or (
            within_x
            and (
                abs(y - rect.y) <= edge_margin
                or abs(y - rect.bottom) <= edge_margin
            )
        )
        if near_edge:
            return "resize"
        if (
            rect.x <= x <= rect.right
            and rect.y <= y <= rect.y + titlebar_height
        ):
            return "drag"
        return None

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
            self._snap_flow.confirm_selection(
                layout_index, zone_index, msg.get("flow_id")
            )
            
        elif event == "layout_cancelled":
            self._snap_flow.cancel(msg.get("flow_id"))

        elif event == "snap_assist_selected":
            self._snap_flow.confirm_assist_selection(
                msg.get("window_id"), msg.get("flow_id")
            )

        elif event == "snap_assist_cancelled":
            self._snap_flow.cancel_snap_assist(
                msg.get("reason", "escape"), msg.get("flow_id")
            )
