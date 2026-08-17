"""
main.py — Punto de entrada del daemon SnapAssist.

Responsabilidades:
- Detectar el tipo de sesión (XDG_SESSION_TYPE) y seleccionar el backend.
- Configurar el sistema de logging con rotación.
- Instanciar State, HotkeyManager, el backend WM, y el Daemon.
- Registrar atajos globales (Super+Z).
- Loguear el estado inicial del sistema (ventanas abiertas).
- Registrar handlers de SIGTERM/SIGINT para apagado limpio.
- Iniciar el event loop del daemon.

No contiene lógica de negocio. Es exclusivamente inicialización y wiring.
"""

import logging
import logging.handlers
import os
import signal
import sys
import time
from pathlib import Path

from snapassist.config import (
    ERROR_LOG_FILE, LOG_DIR, LOG_FILE, LOG_MAX_BYTES, LOG_BACKUP_COUNT,
)
from snapassist.core.daemon import Daemon, WakeableQueue
from snapassist.core.hotkeys import HotkeyManager
from snapassist.core.state import State
from snapassist.layout.engine import LayoutEngine
from snapassist.snap.snapper import SnapEngine
from snapassist.snap.group_manager import GroupManager
from snapassist.ui.notifier import Notifier
from snapassist.settings import DEFAULT_SHORTCUTS, RuntimeSettings


def setup_logging() -> None:
    """
    Configura el sistema de logging con dos handlers:
    1. RotatingFileHandler para el archivo de log con rotación por tamaño.
    2. StreamHandler para stderr (útil durante desarrollo).

    Los niveles:
    - Archivo: DEBUG (captura todo)
    - Consola: INFO (solo mensajes relevantes)
    """
    log_dir = Path(LOG_DIR).expanduser()
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / LOG_FILE
    error_log_path = log_dir / ERROR_LOG_FILE

    # Formato de log
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)-8s] %(name)-30s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Handler de archivo con rotación
    file_handler = logging.handlers.RotatingFileHandler(
        filename=str(log_path),
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    error_file_handler = logging.handlers.RotatingFileHandler(
        filename=str(error_log_path),
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    error_file_handler.setLevel(logging.ERROR)
    error_file_handler.setFormatter(formatter)

    class DuplicateConsoleFilter(logging.Filter):
        """Evita inundar la terminal con el mismo mensaje en una animación."""

        def __init__(self, interval_seconds: float = 5.0) -> None:
            super().__init__()
            self.interval_seconds = interval_seconds
            self._last_seen = {}

        def filter(self, record) -> bool:
            key = (record.name, record.levelno, record.getMessage())
            now = time.monotonic()
            previous = self._last_seen.get(key, 0.0)
            self._last_seen[key] = now
            return now - previous >= self.interval_seconds

    # La terminal muestra la actividad operativa sin repetir mensajes idénticos.
    # El detalle DEBUG continúa en daemon.log y los errores en errors.log.
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(DuplicateConsoleFilter())

    # Configurar root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(error_file_handler)
    root_logger.addHandler(console_handler)

    logging.getLogger(__name__).info(
        "Logs: actividad=%s | errores=%s",
        log_path,
        error_log_path,
    )


def detect_and_create_backend():
    """
    Detecta XDG_SESSION_TYPE y crea el backend de WindowManager apropiado.

    En X11: instancia X11Backend.
    En Wayland: intenta instanciar WaylandBackend (que lanza NotImplementedError).
    En otro caso: termina con error.
    """
    session_type = os.environ.get("XDG_SESSION_TYPE", "x11").lower()
    logger = logging.getLogger(__name__)

    logger.info("Tipo de sesión detectado: %s", session_type)

    if session_type == "x11":
        from snapassist.wm.x11_backend import X11Backend
        return X11Backend()

    elif session_type == "wayland":
        try:
            from snapassist.wm.wayland_backend import WaylandBackend
            return WaylandBackend()
        except NotImplementedError as e:
            logger.critical(str(e))
            sys.exit(
                "SnapAssist: el backend Wayland no está implementado en v1. "
                "Por favor, utilice una sesión X11."
            )

    else:
        logger.critical("Entorno de display no reconocido: %s", session_type)
        sys.exit(
            f"SnapAssist: entorno de display no reconocido: '{session_type}'. "
            "Se esperaba 'x11' o 'wayland'."
        )


def log_system_state(wm_backend, state: State) -> None:
    """
    Loguea el estado inicial del sistema: ventanas abiertas con sus
    títulos, tipos, estados y geometrías.

    Esto verifica que la conexión X11 funciona y que se pueden leer
    las propiedades de las ventanas.
    """
    logger = logging.getLogger(__name__)

    # Work area
    work_area = wm_backend.get_work_area()
    logger.info(
        "Work area: x=%d, y=%d, w=%d, h=%d",
        work_area.x, work_area.y, work_area.w, work_area.h,
    )

    # Ventana activa
    active_wid = wm_backend.get_active_window()
    if active_wid:
        active_title = wm_backend.get_window_title(active_wid)
        logger.info("Ventana activa: 0x%x \"%s\"", active_wid, active_title)
    else:
        logger.info("Sin ventana activa (foco en el escritorio).")

    # Listar todas las ventanas
    windows = wm_backend.get_all_windows()
    logger.info("Ventanas abiertas: %d", len(windows))

    for wid in windows:
        title = wm_backend.get_window_title(wid)
        wtype = wm_backend.get_window_type(wid)
        wstate = wm_backend.get_window_state(wid)
        geom = wm_backend.get_window_geometry(wid)
        monitor = wm_backend.get_monitor_for_window(wid)

        logger.info(
            "  0x%08x | %-12s | %-12s | Mon:%d | "
            "Rect(%d, %d, %d, %d) | \"%s\"",
            wid,
            wtype.value,
            wstate.value,
            monitor,
            geom.rect.x, geom.rect.y, geom.rect.w, geom.rect.h,
            title[:60],
        )

    # Actualizar MRU con la ventana activa
    if active_wid:
        state.update_mru(active_wid)

    logger.info(state.summary())


def build_help_message(
    wm_backend,
    state: State,
    group_manager,
    active_wid,
    shortcuts=None,
) -> str:
    """Construye el contenido de `Super+/`, también reutilizable en pruebas."""
    shortcuts = shortcuts or DEFAULT_SHORTCUTS
    group = group_manager.get_group_for_window(active_wid) if active_wid else None
    def display_hotkey(value: str) -> str:
        names = {
            "super": "Super",
            "ctrl": "Ctrl",
            "alt": "Alt",
            "shift": "Shift",
            "slash": "/",
        }
        return "+".join(names.get(part, part.upper()) for part in value.split("+"))

    lines = [
        f"{display_hotkey(shortcuts['layout_menu'])} — layouts",
        f"{display_hotkey(shortcuts['snap_groups'])} — traer grupo al frente",
        f"{display_hotkey(shortcuts['help'])} — ayuda y estado",
        "",
        "Daemon: activo",
        f"Grupos activos: {len(state.active_groups)}",
        f"Ventanas monitoreadas: {len(wm_backend.get_all_windows())}",
    ]
    if group:
        titles = [
            wm_backend.get_window_title(wid)
            for wid in group_manager.get_all_windows_in_group(group.group_id)
        ]
        lines.extend(["", "Grupo activo:", *[f"• {title}" for title in titles]])
    return "\n".join(lines)


from snapassist.ui.ui_manager import UIManager
from snapassist.snap.snap_flow import SnapFlow
def main() -> None:
    """Punto de entrada principal del daemon SnapAssist."""
    setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("=" * 70)
    logger.info("SnapAssist daemon iniciando...")
    logger.info("=" * 70)
    settings = RuntimeSettings.load()
    if settings.error:
        Notifier.send(
            "La configuración no es válida; se usaron layouts y atajos predeterminados."
        )
    logger.info(
        "Configuración: %s | layouts=%d | archivo=%s",
        "personalizada" if settings.loaded_from_file else "predeterminada",
        len(settings.layouts),
        settings.source_path,
    )

    try:
        wm_backend = detect_and_create_backend()
    except Exception as e:
        logger.critical("Error fatal al crear el backend WM: %s", e, exc_info=True)
        sys.exit(f"SnapAssist: error fatal al inicializar: {e}")

    state = State()
    layout_engine = LayoutEngine(gap_px=0)
    snap_engine = SnapEngine(wm_backend, state, layout_engine)
    group_manager = GroupManager(state, wm_backend)

    pointer_event_queue = WakeableQueue()
    control_callback_queue = WakeableQueue()
    hotkey_manager = HotkeyManager(
        display_obj=wm_backend.get_display(),
        root_window=wm_backend.root,
        pointer_event_queue=pointer_event_queue,
        callback_queue=control_callback_queue,
    )
    
    # Inicializar UI en hilo separado.
    ui_callback_queue = WakeableQueue()
    ui_manager = UIManager(ui_callback_queue)
    ui_manager.start()
    
    # Máquina de estados interactiva.
    snap_flow = SnapFlow(
        wm_backend,
        state,
        snap_engine,
        ui_manager,
        group_manager=group_manager,
        layouts=settings.layout_templates,
    )

    def on_super_z():
        # HotkeyManager lo encola; el daemon lo ejecuta en el hilo de X11.
        snap_flow.trigger()

    layout_hotkey = settings.shortcuts["layout_menu"]
    if not hotkey_manager.register(layout_hotkey, on_super_z):
        logger.error(
            "No se pudo registrar el atajo '%s'. "
            "Posiblemente otro programa ya lo capturó.",
            layout_hotkey,
        )

    def on_snap_group():
        active_wid = wm_backend.get_active_window()
        group = (
            group_manager.focus_group_for_window(active_wid)
            if active_wid else None
        )
        if not group:
            Notifier.send("La ventana activa no pertenece a un Snap Group.")

    def on_help():
        active_wid = wm_backend.get_active_window()
        Notifier.send(
            build_help_message(
                wm_backend,
                state,
                group_manager,
                active_wid,
                settings.shortcuts,
            ),
            timeout_ms=6000,
        )

    groups_hotkey = settings.shortcuts["snap_groups"]
    help_hotkey = settings.shortcuts["help"]
    if not hotkey_manager.register(groups_hotkey, on_snap_group):
        logger.error("No se pudo registrar el atajo '%s'.", groups_hotkey)
    if not hotkey_manager.register(help_hotkey, on_help):
        logger.error("No se pudo registrar el atajo '%s'.", help_hotkey)

    logger.info(
        "Atajos registrados: %s",
        ", ".join(hotkey_manager.get_registered_hotkeys()),
    )

    # 7. Crear daemon (pasando ui_callback_queue y snap_flow)
    daemon = Daemon(
        wm_backend=wm_backend,
        state=state,
        hotkey_manager=hotkey_manager,
        ui_callback_queue=ui_callback_queue,
        pointer_event_queue=pointer_event_queue,
        control_callback_queue=control_callback_queue,
        snap_flow=snap_flow,
        group_manager=group_manager,
    )
    state.bind_to_current_thread()

    # 8. Registrar handlers de señales para apagado limpio
    def signal_handler(signum, frame):
        sig_name = signal.Signals(signum).name
        logger.info("Señal %s recibida. Iniciando apagado limpio...", sig_name)
        daemon.shutdown()

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    # 9. Loguear estado inicial del sistema
    try:
        log_system_state(wm_backend, state)
    except Exception as e:
        logger.error("Error logueando estado inicial: %s", e, exc_info=True)

    # 9. Iniciar event loop
    logger.info("Iniciando event loop del daemon...")
    try:
        daemon.run()
    except Exception as e:
        logger.critical("Error fatal en el event loop: %s", e, exc_info=True)
    finally:
        # 10. Limpieza ordenada fuera del handler de señales.
        ui_manager.stop()
        hotkey_manager.unregister_all()
        logger.info("Cerrando conexión X11...")
        wm_backend.close()
        logger.info("SnapAssist daemon finalizado.")


if __name__ == "__main__":
    main()
