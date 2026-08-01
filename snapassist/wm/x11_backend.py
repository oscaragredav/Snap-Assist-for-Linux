"""
wm/x11_backend.py — Implementación concreta de WindowManager para X11.

Usa python-xlib para conectarse al servidor X11 y leer propiedades de ventanas
mediante los átomos EWMH estándar.
"""

import logging
from typing import List, Optional

from Xlib import X, Xutil, display, Xatom
from Xlib.protocol import event as xevent
from Xlib.error import BadWindow, BadDrawable

from snapassist.config import (
    Rect,
    WindowInfo,
    WindowGeometry,
    WindowState,
    WindowType,
)
from snapassist.wm.backend import WindowManager

logger = logging.getLogger(__name__)


class X11Backend(WindowManager):
    """
    Backend X11 que implementa la interfaz WindowManager.

    Se conecta al servidor X al instanciarse y expone operaciones de lectura
    de ventanas usando los átomos EWMH estándar.
    """

    def __init__(self) -> None:
        logger.info("Inicializando backend X11...")
        self._display = display.Display()
        self._root = self._display.screen().root

        # Cache de átomos EWMH usados frecuentemente
        self._atoms = {
            "_NET_CLIENT_LIST": self._display.intern_atom("_NET_CLIENT_LIST"),
            "_NET_ACTIVE_WINDOW": self._display.intern_atom("_NET_ACTIVE_WINDOW"),
            "_NET_SUPPORTED": self._display.intern_atom("_NET_SUPPORTED"),
            "_NET_WORKAREA": self._display.intern_atom("_NET_WORKAREA"),
            "_NET_WM_NAME": self._display.intern_atom("_NET_WM_NAME"),
            "_NET_WM_WINDOW_TYPE": self._display.intern_atom("_NET_WM_WINDOW_TYPE"),
            "_NET_WM_WINDOW_TYPE_NORMAL": self._display.intern_atom(
                "_NET_WM_WINDOW_TYPE_NORMAL"
            ),
            "_NET_WM_WINDOW_TYPE_DIALOG": self._display.intern_atom(
                "_NET_WM_WINDOW_TYPE_DIALOG"
            ),
            "_NET_WM_WINDOW_TYPE_SPLASH": self._display.intern_atom(
                "_NET_WM_WINDOW_TYPE_SPLASH"
            ),
            "_NET_WM_WINDOW_TYPE_DOCK": self._display.intern_atom(
                "_NET_WM_WINDOW_TYPE_DOCK"
            ),
            "_NET_WM_STATE": self._display.intern_atom("_NET_WM_STATE"),
            "_NET_WM_STATE_HIDDEN": self._display.intern_atom(
                "_NET_WM_STATE_HIDDEN"
            ),
            "_NET_WM_STATE_MAXIMIZED_VERT": self._display.intern_atom(
                "_NET_WM_STATE_MAXIMIZED_VERT"
            ),
            "_NET_WM_STATE_MAXIMIZED_HORZ": self._display.intern_atom(
                "_NET_WM_STATE_MAXIMIZED_HORZ"
            ),
            "_NET_WM_STATE_FULLSCREEN": self._display.intern_atom(
                "_NET_WM_STATE_FULLSCREEN"
            ),
            "_NET_WM_STATE_ABOVE": self._display.intern_atom(
                "_NET_WM_STATE_ABOVE"
            ),
            "_NET_WM_STATE_SKIP_TASKBAR": self._display.intern_atom(
                "_NET_WM_STATE_SKIP_TASKBAR"
            ),
            "_NET_WM_DESKTOP": self._display.intern_atom("_NET_WM_DESKTOP"),
            "_NET_CURRENT_DESKTOP": self._display.intern_atom("_NET_CURRENT_DESKTOP"),
            "WM_TRANSIENT_FOR": self._display.intern_atom("WM_TRANSIENT_FOR"),
            "UTF8_STRING": self._display.intern_atom("UTF8_STRING"),
            "_GTK_FRAME_EXTENTS": self._display.intern_atom("_GTK_FRAME_EXTENTS"),
            "_NET_MOVERESIZE_WINDOW": self._display.intern_atom("_NET_MOVERESIZE_WINDOW"),
        }

        # Seleccionar eventos sobre el root window para recibir notificaciones
        # de cambios en la estructura de ventanas y propiedades
        self._root.change_attributes(
            event_mask=(
                X.SubstructureNotifyMask
                | X.PropertyChangeMask
            )
        )
        self._display.flush()

        # Set de window_ids cuyos resizes fueron iniciados por el daemon.
        # Se usa para distinguir resizes propios de resizes externos en
        # ConfigureNotify (ver arquitectura §5.2).
        self._pending_own_resizes: set[int] = set()
        # Historial corto de geometrías X11 solicitadas por el daemon. Algunos
        # gestores vuelven a emitirlas al mapear/enfocar una ventana.
        self._own_resize_geometries: dict[int, list[tuple[int, int, int, int]]] = {}
        # Restricciones ICCCM originales que se suspenden mientras una ventana
        # está acoplada. Terminales suelen cuantizar el tamaño por caracteres.
        self._saved_normal_hints: dict[int, Optional[dict]] = {}
        self._supports_moveresize = self._root_supports_atom(
            self._atoms["_NET_MOVERESIZE_WINDOW"]
        )

        logger.info(
            "Backend X11 inicializado. Root window: 0x%x",
            self._root.id,
        )

    # ------------------------------------------------------------------
    # Métodos de lectura de ventanas
    # ------------------------------------------------------------------

    def get_active_window(self) -> Optional[int]:
        """Retorna el window_id de la ventana activa, o None."""
        try:
            prop = self._root.get_full_property(
                self._atoms["_NET_ACTIVE_WINDOW"], X.AnyPropertyType
            )
            if prop and prop.value:
                wid = int(prop.value[0])
                # wid=0 o wid=root significan que no hay ventana activa
                if wid == 0 or wid == self._root.id:
                    return None
                return wid
        except Exception as e:
            logger.error("Error leyendo _NET_ACTIVE_WINDOW: %s", e)
        return None

    def get_all_windows(self) -> List[int]:
        """
        Retorna los window_ids elegibles de _NET_CLIENT_LIST.

        Las ventanas minimizadas se incluyen deliberadamente: aunque X11 las
        reporte como no visibles, Snap Assist puede restaurarlas al enfocarlas.
        """
        try:
            prop = self._root.get_full_property(
                self._atoms["_NET_CLIENT_LIST"], X.AnyPropertyType
            )
            if prop and prop.value is not None:
                return [int(wid) for wid in prop.value if self._is_eligible_window(int(wid))]
        except Exception as e:
            logger.error("Error leyendo _NET_CLIENT_LIST: %s", e)
        return []

    def get_eligible_windows(self) -> List[WindowInfo]:
        """Retorna las ventanas elegibles con título y estado de workspace."""
        return [
            WindowInfo(
                window_id=wid,
                title=self.get_window_title(wid),
                on_other_workspace=self._is_on_other_workspace(wid),
            )
            for wid in self.get_all_windows()
        ]

    def _is_eligible_window(self, wid: int) -> bool:
        """Aplica el filtro de Fase 6 sin excluir ventanas minimizadas."""
        try:
            window = self._display.create_resource_object("window", wid)
            attributes = window.get_attributes()
            states = self._get_wm_states(wid)
            minimized = self._atoms["_NET_WM_STATE_HIDDEN"] in states
            visible = attributes.map_state == X.IsViewable

            return (
                (visible or minimized)
                and self.get_window_type(wid) == WindowType.NORMAL
                and self._atoms["_NET_WM_STATE_SKIP_TASKBAR"] not in states
                and self._atoms["_NET_WM_STATE_FULLSCREEN"] not in states
                and self._atoms["_NET_WM_STATE_ABOVE"] not in states
            )
        except (BadWindow, BadDrawable):
            return False
        except Exception as e:
            logger.error("Error filtrando ventana 0x%x: %s", wid, e)
            return False

    def _is_on_other_workspace(self, wid: int) -> bool:
        """Indica si la ventana pertenece a un workspace distinto del actual."""
        try:
            window = self._display.create_resource_object("window", wid)
            desktop = window.get_full_property(self._atoms["_NET_WM_DESKTOP"], X.AnyPropertyType)
            current = self._root.get_full_property(
                self._atoms["_NET_CURRENT_DESKTOP"], X.AnyPropertyType
            )
            if not desktop or not desktop.value or not current or not current.value:
                return False
            # 0xFFFFFFFF significa "todos los escritorios" según EWMH.
            return int(desktop.value[0]) not in (int(current.value[0]), 0xFFFFFFFF)
        except (BadWindow, BadDrawable):
            return False
        except Exception as e:
            logger.error("Error leyendo workspace de 0x%x: %s", wid, e)
            return False

    def get_window_geometry(self, wid: int) -> WindowGeometry:
        """
        Retorna geometría en coordenadas absolutas de pantalla.

        Usa GetGeometry para obtener las dimensiones de la ventana y
        TranslateCoordinates para convertir a coordenadas absolutas
        (relativas al root window).
        """
        try:
            window = self._display.create_resource_object("window", wid)
            geom = window.get_geometry()

            # En python-xlib ``destino.translate_coords(origen, ...)``. La
            # llamada anterior estaba invertida y devolvía el origen del root
            # visto desde la ventana (signos x/y contrarios).
            translated = self._root.translate_coords(window, 0, 0)
            abs_x = translated.x
            abs_y = translated.y

            # Detectar si está maximizada
            states = self._get_wm_states(wid)
            is_maximized = (
                self._atoms["_NET_WM_STATE_MAXIMIZED_VERT"] in states
                and self._atoms["_NET_WM_STATE_MAXIMIZED_HORZ"] in states
            )

            buffer_rect = Rect(abs_x, abs_y, geom.width, geom.height)
            visible_rect = self._visible_rect_from_buffer(
                buffer_rect, self._get_frame_extents(window)
            )
            return WindowGeometry(rect=visible_rect, is_maximized=is_maximized)
        except (BadWindow, BadDrawable) as e:
            logger.warning("Ventana 0x%x desaparecida al leer geometría: %s", wid, e)
            return WindowGeometry(rect=Rect(0, 0, 0, 0))
        except Exception as e:
            logger.error("Error leyendo geometría de 0x%x: %s", wid, e)
            return WindowGeometry(rect=Rect(0, 0, 0, 0))

    def get_window_min_size(self, wid: int) -> tuple[int, int]:
        """Lee min_width/min_height de WM_NORMAL_HINTS."""
        try:
            window = self._display.create_resource_object("window", wid)
            hints = window.get_wm_normal_hints()
            if not hints:
                return (1, 1)

            def hint_value(name: str) -> int:
                try:
                    value = getattr(hints, name)
                except (AttributeError, KeyError):
                    try:
                        value = hints[name]
                    except (KeyError, TypeError):
                        value = 1
                return max(1, int(value or 1))

            return (
                hint_value("min_width"),
                hint_value("min_height"),
            )
        except (BadWindow, BadDrawable):
            return (1, 1)
        except Exception as e:
            logger.debug("Sin tamaño mínimo para 0x%x: %s", wid, e)
            return (1, 1)

    def window_exists(self, wid: int) -> bool:
        try:
            window = self._display.create_resource_object("window", wid)
            window.get_attributes()
            return True
        except (BadWindow, BadDrawable):
            return False
        except Exception:
            return False

    def get_window_title(self, wid: int) -> str:
        """
        Retorna el título de la ventana.
        Intenta _NET_WM_NAME (UTF-8) primero, con fallback a WM_NAME.
        """
        try:
            window = self._display.create_resource_object("window", wid)

            # Intentar _NET_WM_NAME (formato UTF-8)
            prop = window.get_full_property(
                self._atoms["_NET_WM_NAME"], self._atoms["UTF8_STRING"]
            )
            if prop and prop.value:
                if isinstance(prop.value, bytes):
                    return prop.value.decode("utf-8", errors="replace")
                return str(prop.value)

            # Fallback a WM_NAME
            prop = window.get_full_property(Xatom.WM_NAME, X.AnyPropertyType)
            if prop and prop.value:
                if isinstance(prop.value, bytes):
                    return prop.value.decode("latin-1", errors="replace")
                return str(prop.value)

        except (BadWindow, BadDrawable):
            logger.debug("Ventana 0x%x desaparecida al leer título", wid)
        except Exception as e:
            logger.error("Error leyendo título de 0x%x: %s", wid, e)
        return ""

    def get_window_type(self, wid: int) -> WindowType:
        """
        Retorna el tipo de ventana según _NET_WM_WINDOW_TYPE.
        """
        try:
            window = self._display.create_resource_object("window", wid)
            prop = window.get_full_property(
                self._atoms["_NET_WM_WINDOW_TYPE"], X.AnyPropertyType
            )
            if prop and prop.value:
                type_atom = int(prop.value[0])
                return self._map_window_type(type_atom)
        except (BadWindow, BadDrawable):
            logger.debug("Ventana 0x%x desaparecida al leer tipo", wid)
        except Exception as e:
            logger.error("Error leyendo tipo de 0x%x: %s", wid, e)
        return WindowType.NORMAL  # Default según EWMH

    def get_window_state(self, wid: int) -> WindowState:
        """
        Retorna el estado principal de la ventana según _NET_WM_STATE.
        En caso de múltiples estados activos, la prioridad es:
        FULLSCREEN > ALWAYS_TOP > MAXIMIZED > MINIMIZED > NORMAL.
        """
        states = self._get_wm_states(wid)

        if self._atoms["_NET_WM_STATE_FULLSCREEN"] in states:
            return WindowState.FULLSCREEN
        if self._atoms["_NET_WM_STATE_ABOVE"] in states:
            return WindowState.ALWAYS_TOP
        if (
            self._atoms["_NET_WM_STATE_MAXIMIZED_VERT"] in states
            and self._atoms["_NET_WM_STATE_MAXIMIZED_HORZ"] in states
        ):
            return WindowState.MAXIMIZED
        if self._atoms["_NET_WM_STATE_HIDDEN"] in states:
            return WindowState.MINIMIZED

        return WindowState.NORMAL

    def get_work_area(self, monitor_index: int = 0) -> Rect:
        """
        Retorna el work area del monitor especificado.
        Combina _NET_WORKAREA (que es global) con la geometría del monitor.
        """
        global_wa = None
        try:
            prop = self._root.get_full_property(
                self._atoms["_NET_WORKAREA"], X.AnyPropertyType
            )
            if prop and prop.value is not None and len(prop.value) >= 4:
                global_wa = Rect(
                    x=int(prop.value[0]),
                    y=int(prop.value[1]),
                    w=int(prop.value[2]),
                    h=int(prop.value[3])
                )
        except Exception as e:
            logger.error("Error leyendo _NET_WORKAREA: %s", e)

        monitors = self._get_monitors()
        if monitors and 0 <= monitor_index < len(monitors):
            mon_rect = monitors[monitor_index]
            if global_wa:
                # Intersectar el workarea global con el monitor
                ix = max(mon_rect.x, global_wa.x)
                iy = max(mon_rect.y, global_wa.y)
                iright = min(mon_rect.x + mon_rect.w, global_wa.x + global_wa.w)
                ibottom = min(mon_rect.y + mon_rect.h, global_wa.y + global_wa.h)
                
                if iright > ix and ibottom > iy:
                    final_wa = Rect(ix, iy, iright - ix, ibottom - iy)
                    logger.debug(
                        "Work area del monitor %d: x=%d, y=%d, w=%d, h=%d",
                        monitor_index, final_wa.x, final_wa.y, final_wa.w, final_wa.h
                    )
                    return final_wa
            return mon_rect

        # Fallback global
        if global_wa:
            return global_wa
            
        screen = self._display.screen()
        return Rect(x=0, y=0, w=screen.width_in_pixels, h=screen.height_in_pixels)

    def get_monitor_for_window(self, wid: int) -> int:
        """
        Retorna el índice del monitor donde reside la ventana.

        Calcula por intersección de geometrías: el monitor con mayor área
        de intersección con la geometría de la ventana gana.
        En esta fase retorna siempre 0 (monitor primario) si no hay
        información multi-monitor disponible via Xinerama.
        """
        try:
            win_geom = self.get_window_geometry(wid)
            monitors = self._get_monitors()

            if not monitors:
                return 0

            best_monitor = 0
            best_area = 0

            for idx, mon_rect in enumerate(monitors):
                area = win_geom.rect.intersection_area(mon_rect)
                if area > best_area:
                    best_area = area
                    best_monitor = idx

            return best_monitor
        except Exception as e:
            logger.error("Error determinando monitor para 0x%x: %s", wid, e)
            return 0

    def get_transient_for(self, wid: int) -> Optional[int]:
        """
        Retorna el window_id del padre transitorio (WM_TRANSIENT_FOR).
        Stub en Fase 1 — se completa en Fase 3.
        """
        try:
            window = self._display.create_resource_object("window", wid)
            prop = window.get_full_property(
                self._atoms["WM_TRANSIENT_FOR"], X.AnyPropertyType
            )
            if prop and prop.value:
                parent_wid = int(prop.value[0])
                if parent_wid != 0:
                    return parent_wid
        except (BadWindow, BadDrawable):
            logger.debug("Ventana 0x%x desaparecida al leer WM_TRANSIENT_FOR", wid)
        except Exception as e:
            logger.error("Error leyendo WM_TRANSIENT_FOR de 0x%x: %s", wid, e)
        return None

    # ------------------------------------------------------------------
    # Métodos de acción (stubs en Fase 1)
    # ------------------------------------------------------------------

    def prepare_window_for_snap(self, wid: int) -> None:
        """Suspende restricciones que impiden llenar una zona píxel a píxel.

        Se conserva ``PMinSize`` para no forzar una aplicación por debajo del
        tamaño que puede representar. Los incrementos de celda, el aspecto y
        el máximo se restauran al desacoplar la ventana.
        """
        try:
            window = self._display.create_resource_object("window", wid)
            if wid not in self._saved_normal_hints:
                hints = window.get_wm_normal_hints()
                original = dict(hints._data) if hints else None
                self._saved_normal_hints[wid] = original
            else:
                original = self._saved_normal_hints[wid]

            if not original:
                return

            normalized = self._normalize_snap_hints(original)
            if normalized != original:
                window.set_wm_normal_hints(normalized)
                self._display.flush()
                logger.debug(
                    "Restricciones geométricas suspendidas para 0x%x "
                    "(incremento original=%dx%d)",
                    wid,
                    int(original.get("width_inc", 1) or 1),
                    int(original.get("height_inc", 1) or 1),
                )
        except (BadWindow, BadDrawable):
            self._saved_normal_hints.pop(wid, None)
        except Exception as e:
            logger.warning(
                "No se pudieron normalizar restricciones de 0x%x: %s", wid, e
            )

    def release_window_from_snap(self, wid: int) -> None:
        """Restaura WM_NORMAL_HINTS cuando la ventana deja SnapAssist."""
        if wid not in self._saved_normal_hints:
            return
        original = self._saved_normal_hints.pop(wid)
        if not original:
            return
        try:
            window = self._display.create_resource_object("window", wid)
            window.set_wm_normal_hints(original)
            self._display.flush()
            logger.debug("Restricciones geométricas restauradas para 0x%x", wid)
        except (BadWindow, BadDrawable):
            pass
        except Exception as e:
            logger.warning(
                "No se pudieron restaurar restricciones de 0x%x: %s", wid, e
            )

    @staticmethod
    def _normalize_snap_hints(hints: dict) -> dict:
        """Devuelve hints ICCCM sin cuantización, aspecto ni máximo."""
        normalized = dict(hints)
        ignored_flags = (
            Xutil.PResizeInc
            | Xutil.PAspect
            | Xutil.PBaseSize
            | Xutil.PMaxSize
        )
        normalized["flags"] = int(normalized.get("flags", 0)) & ~ignored_flags
        normalized["width_inc"] = 1
        normalized["height_inc"] = 1
        normalized["base_width"] = 0
        normalized["base_height"] = 0
        return normalized

    def _get_frame_extents(self, window) -> tuple[int, int, int, int]:
        """
        Retorna (left, right, top, bottom) leyendo _GTK_FRAME_EXTENTS.
        Esto es crítico en GNOME (Zorin) porque las decoraciones CSD (sombras)
        son parte de la ventana X11. Si queremos que la ventana visual ocupe 
        un área, debemos compensar estos márgenes invisibles.
        """
        try:
            prop = window.get_full_property(
                self._atoms["_GTK_FRAME_EXTENTS"], X.AnyPropertyType
            )
            if prop and prop.value and len(prop.value) >= 4:
                return (prop.value[0], prop.value[1], prop.value[2], prop.value[3])
        except Exception:
            pass
        return (0, 0, 0, 0)

    def move_resize_window(self, wid: int, rect: Rect) -> None:
        """
        Mueve y redimensiona una ventana en X11.

        Las sombras CSD forman parte del búfer X11, por lo que se compensan a
        partir de ``_GTK_FRAME_EXTENTS``. La petición se envía una sola vez por
        EWMH: un ConfigureRequest adicional competiría con el gestor y podría
        recortar o sobrescribir el resultado.
        """
        try:
            window = self._display.create_resource_object('window', wid)
            self._pending_own_resizes.add(wid)

            extents = self._get_frame_extents(window)
            requested_rect = self._compensate_csd_rect(rect, extents)
            expected_geometry = (
                requested_rect.x,
                requested_rect.y,
                requested_rect.w,
                requested_rect.h,
            )
            history = self._own_resize_geometries.setdefault(wid, [])
            if expected_geometry not in history:
                history.append(expected_geometry)
                del history[:-64]
            
            flags = (
                (1 << 8)   # x
                | (1 << 9)  # y
                | (1 << 10) # width
                | (1 << 11) # height
                | (1 << 12) # source indication: aplicación
            )
            if self._supports_moveresize:
                moveresize_event = xevent.ClientMessage(
                    window=window,
                    client_type=self._atoms["_NET_MOVERESIZE_WINDOW"],
                    data=(32, [
                        flags,
                        self._to_card32(requested_rect.x),
                        self._to_card32(requested_rect.y),
                        self._to_card32(requested_rect.w),
                        self._to_card32(requested_rect.h),
                    ]),
                )
                self._root.send_event(
                    moveresize_event,
                    event_mask=X.SubstructureRedirectMask | X.SubstructureNotifyMask,
                )
            else:
                # Sólo para gestores que no anuncian _NET_MOVERESIZE_WINDOW.
                window.configure(
                    x=requested_rect.x,
                    y=requested_rect.y,
                    width=requested_rect.w,
                    height=requested_rect.h,
                )
            self._display.flush()
            logger.debug(
                "move_resize_window: 0x%x → visible=%s, X11=%s, extents=%s",
                wid, rect, requested_rect, extents,
            )
        except (BadWindow, BadDrawable):
            logger.warning("move_resize_window falló: ventana 0x%x desapareció", wid)
            self._pending_own_resizes.discard(wid)
        except Exception as e:
            logger.error(
                "Error al mover/redimensionar 0x%x: %s",
                wid,
                e,
                exc_info=True,
            )
            self._pending_own_resizes.discard(wid)

    @staticmethod
    def _to_card32(value: int) -> int:
        """Codifica enteros con signo como CARD32 para ClientMessage X11."""
        return int(value) & 0xFFFFFFFF

    @staticmethod
    def _compensate_csd_rect(
        rect: Rect, extents: tuple[int, int, int, int]
    ) -> Rect:
        """Convierte un rectángulo visible en el búfer X11 con sombras CSD."""
        left, right, top, bottom = (max(0, int(v)) for v in extents)
        return Rect(
            rect.x - left,
            rect.y - top,
            rect.w + left + right,
            rect.h + top + bottom,
        )

    @staticmethod
    def _visible_rect_from_buffer(
        rect: Rect, extents: tuple[int, int, int, int]
    ) -> Rect:
        """Elimina del búfer X11 los márgenes transparentes declarados."""
        left, right, top, bottom = (max(0, int(v)) for v in extents)
        return Rect(
            rect.x + left,
            rect.y + top,
            max(0, rect.w - left - right),
            max(0, rect.h - top - bottom),
        )

    def watch_snapped_window(self, wid: int) -> None:
        """Solicita los eventos de puntero necesarios para detectar un drag.

        La selección se limita a la ventana acoplada; así el daemon no recibe
        movimiento del ratón de todas las ventanas de la sesión.
        """
        try:
            window = self._display.create_resource_object("window", wid)
            window.change_attributes(
                event_mask=X.ButtonPressMask | X.ButtonReleaseMask | X.PointerMotionMask
            )
            self._display.flush()
        except (BadWindow, BadDrawable):
            logger.debug("No se pudo observar la ventana desaparecida 0x%x", wid)
        except Exception as e:
            logger.error("Error observando eventos de puntero de 0x%x: %s", wid, e)

    def consume_own_resize(self, wid: int, event=None) -> bool:
        """Reconoce ConfigureNotify propios, incluso si el WM los repite."""
        if event is not None:
            geometry = (
                int(getattr(event, "x", 0)),
                int(getattr(event, "y", 0)),
                int(getattr(event, "width", 0)),
                int(getattr(event, "height", 0)),
            )
            if geometry in self._own_resize_geometries.get(wid, []):
                self._pending_own_resizes.discard(wid)
                return True

        if wid in self._pending_own_resizes:
            self._pending_own_resizes.discard(wid)
            return True
        return False

    def focus_window(self, wid: int) -> None:
        """
        Pide el foco para una ventana enviando _NET_ACTIVE_WINDOW.
        """
        try:
            window = self._display.create_resource_object('window', wid)
            
            # Por seguridad, si está minimizada, hacer un map
            window.map()
            
            # Construir evento _NET_ACTIVE_WINDOW
            data = [
                1,              # 1 = aplicación normal
                X.CurrentTime,  # timestamp
                0,              # ventana activa del requestor (0 si no se conoce)
                0, 0
            ]
            
            ev = xevent.ClientMessage(
                window=window,
                client_type=self._atoms["_NET_ACTIVE_WINDOW"],
                data=(32, data)
            )
            
            self._root.send_event(
                ev,
                event_mask=X.SubstructureRedirectMask | X.SubstructureNotifyMask
            )
            self._display.flush()
            logger.debug("focus_window: enviado _NET_ACTIVE_WINDOW para 0x%x", wid)
        except (BadWindow, BadDrawable):
            logger.warning("focus_window falló: ventana 0x%x desapareció", wid)
        except Exception as e:
            logger.error("Error al enfocar ventana 0x%x: %s", wid, e)

    def set_window_maximized(self, wid: int, maximized: bool) -> None:
        """
        Añade o elimina los estados de maximizado vertical y horizontal
        enviando un evento _NET_WM_STATE al root window.
        """
        try:
            window = self._display.create_resource_object('window', wid)
            
            _NET_WM_STATE_REMOVE = 0
            _NET_WM_STATE_ADD = 1
            
            action = _NET_WM_STATE_ADD if maximized else _NET_WM_STATE_REMOVE
            atom_vert = self._atoms["_NET_WM_STATE_MAXIMIZED_VERT"]
            atom_horz = self._atoms["_NET_WM_STATE_MAXIMIZED_HORZ"]
            
            data = [
                action,
                atom_vert,
                atom_horz,
                1,  # source indication: 1 = normal app
                0
            ]
            
            ev = xevent.ClientMessage(
                window=window,
                client_type=self._atoms["_NET_WM_STATE"],
                data=(32, data)
            )
            
            self._root.send_event(
                ev,
                event_mask=X.SubstructureRedirectMask | X.SubstructureNotifyMask
            )
            self._display.flush()
            
            logger.debug(
                "set_window_maximized(0x%x, %s): evento enviado",
                wid, maximized
            )
        except (BadWindow, BadDrawable):
            pass
        except Exception as e:
            logger.error("Error modificando estado maximizado de 0x%x: %s", wid, e)

    def move_window_to_current_workspace(self, wid: int) -> None:
        """Mueve una ventana al workspace activo mediante EWMH."""
        try:
            current = self._root.get_full_property(
                self._atoms["_NET_CURRENT_DESKTOP"], X.AnyPropertyType
            )
            if not current or not current.value:
                logger.warning("No se pudo determinar el workspace actual")
                return

            window = self._display.create_resource_object("window", wid)
            event = xevent.ClientMessage(
                window=window,
                client_type=self._atoms["_NET_WM_DESKTOP"],
                data=(32, [int(current.value[0]), 1, 0, 0, 0]),
            )
            self._root.send_event(
                event,
                event_mask=X.SubstructureRedirectMask | X.SubstructureNotifyMask,
            )
            self._display.flush()
            logger.info(
                "Ventana 0x%x trasladada al workspace %d",
                wid,
                int(current.value[0]),
            )
        except (BadWindow, BadDrawable):
            logger.warning("No se pudo trasladar 0x%x: la ventana desapareció", wid)
        except Exception as e:
            logger.error("Error trasladando 0x%x al workspace actual: %s", wid, e)

    # ------------------------------------------------------------------
    # Acceso al display (para el daemon event loop)
    # ------------------------------------------------------------------

    def get_display(self) -> display.Display:
        """Retorna el objeto Display de python-xlib."""
        return self._display

    # ------------------------------------------------------------------
    # Propiedades internas del backend
    # ------------------------------------------------------------------

    @property
    def root(self):
        """Retorna el root window."""
        return self._root

    @property
    def atoms(self) -> dict:
        """Retorna el diccionario de átomos cacheados."""
        return self._atoms

    @property
    def pending_own_resizes(self) -> set:
        """
        Set de window_ids cuyos resizes fueron iniciados por el daemon.
        Ver arquitectura §5.2 para la explicación del mecanismo.
        """
        return self._pending_own_resizes

    # ------------------------------------------------------------------
    # Métodos privados auxiliares
    # ------------------------------------------------------------------

    def _get_wm_states(self, wid: int) -> list:
        """Retorna la lista de átomos de _NET_WM_STATE para la ventana."""
        try:
            window = self._display.create_resource_object("window", wid)
            prop = window.get_full_property(
                self._atoms["_NET_WM_STATE"], X.AnyPropertyType
            )
            if prop and prop.value is not None:
                return list(prop.value)
        except (BadWindow, BadDrawable):
            pass
        except Exception as e:
            logger.error("Error leyendo _NET_WM_STATE de 0x%x: %s", wid, e)
        return []

    def _root_supports_atom(self, atom: int) -> bool:
        """Consulta _NET_SUPPORTED del gestor de ventanas."""
        try:
            prop = self._root.get_full_property(
                self._atoms["_NET_SUPPORTED"], Xatom.ATOM
            )
            return bool(prop and prop.value is not None and atom in prop.value)
        except Exception as e:
            logger.debug("No se pudo leer _NET_SUPPORTED: %s", e)
            return False

    def _map_window_type(self, type_atom: int) -> WindowType:
        """Mapea un átomo de _NET_WM_WINDOW_TYPE a nuestro enum WindowType."""
        type_map = {
            self._atoms["_NET_WM_WINDOW_TYPE_NORMAL"]: WindowType.NORMAL,
            self._atoms["_NET_WM_WINDOW_TYPE_DIALOG"]: WindowType.DIALOG,
            self._atoms["_NET_WM_WINDOW_TYPE_SPLASH"]: WindowType.SPLASH,
            self._atoms["_NET_WM_WINDOW_TYPE_DOCK"]: WindowType.DOCK,
        }
        return type_map.get(type_atom, WindowType.OTHER)

    def _get_monitors(self) -> List[Rect]:
        """
        Obtiene la lista de monitores disponibles.
        Intenta usar Xinerama primero, fallback a la pantalla completa.
        """
        try:
            # Intentar Xinerama para obtener geometrías de monitores
            from Xlib.ext import xinerama

            if self._display.has_extension("XINERAMA"):
                screens = xinerama.query_screens(self._display)
                monitors = []
                for screen_info in screens._data["screens"]:
                    monitors.append(Rect(
                        x=screen_info["x"],
                        y=screen_info["y"],
                        w=screen_info["width"],
                        h=screen_info["height"],
                    ))
                if monitors:
                    logger.debug("Xinerama reportó %d monitores", len(monitors))
                    return monitors
        except Exception as e:
            logger.debug("Xinerama no disponible: %s", e)

        # Fallback: pantalla completa como un solo monitor
        screen = self._display.screen()
        return [Rect(
            x=0, y=0,
            w=screen.width_in_pixels,
            h=screen.height_in_pixels,
        )]

    def close(self) -> None:
        """Cierra la conexión al servidor X11."""
        try:
            for wid in list(self._saved_normal_hints):
                self.release_window_from_snap(wid)
            self._display.close()
            logger.info("Conexión X11 cerrada.")
        except Exception as e:
            logger.error("Error cerrando conexión X11: %s", e)
