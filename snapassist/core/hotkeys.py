"""
core/hotkeys.py — Registro y captura de atajos globales mediante pynput.

GNOME (y otros compositores modernos) a menudo bloquean `XGrabKey` para la tecla Super.
Para solucionar esto, utilizamos `pynput`, que internamente usa la extensión XRecord 
para escuchar el flujo de eventos globalmente sin requerir exclusividad.
"""

import logging
import queue
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


def parse_hotkey(hotkey_str: str) -> str:
    """
    Convierte una cadena de atajo de SnapAssist (ej. "super+z") 
    al formato esperado por pynput (ej. "<cmd>+z").
    """
    parts = [p.strip().lower() for p in hotkey_str.split("+")]
    pynput_parts = []
    
    for part in parts[:-1]:
        if part in ("super", "win", "cmd"):
            pynput_parts.append("<cmd>")
        elif part in ("ctrl", "control"):
            pynput_parts.append("<ctrl>")
        elif part == "alt":
            pynput_parts.append("<alt>")
        elif part == "shift":
            pynput_parts.append("<shift>")
        else:
            raise ValueError(f"Modificador desconocido: {part}")
            
    # La tecla final
    key = parts[-1]
    if len(key) > 1:
        # Para teclas especiales como "tab", "esc", pynput no usa <tab> en GlobalHotKeys
        # sino un formato específico, pero por ahora solo soportamos letras o teclas simples.
        # Las combinaciones adicionales se normalizan en este mismo mapa.
        if key == "tab":
            key = "<tab>"
        elif key in ("esc", "escape"):
            key = "<esc>"
        elif key == "slash":
            key = "/"
        # etc... (se pueden añadir más según sea necesario)
        
    pynput_parts.append(key)
    return "+".join(pynput_parts)


class HotkeyManager:
    """
    Gestiona el registro y captura de atajos de teclado globales usando pynput.
    """

    def __init__(
        self,
        display_obj=None,
        root_window=None,
        pointer_event_queue=None,
        callback_queue: Optional[queue.Queue] = None,
    ) -> None:
        # display_obj y root_window se mantienen por compatibilidad con main.py
        self._bindings: Dict[str, Callable] = {}
        self._original_names: Dict[str, str] = {}
        self._listener: Optional[object] = None
        self._pointer_listener: Optional[object] = None
        self._pointer_event_queue = pointer_event_queue
        self._callback_queue = callback_queue
        self._pointer_pressed = False

        logger.info("HotkeyManager inicializado (usando pynput/XRecord).")

    def register(self, hotkey_str: str, callback: Callable) -> bool:
        """
        Registra un atajo global.
        """
        try:
            pynput_hotkey = parse_hotkey(hotkey_str)
        except ValueError as e:
            logger.error("Error parseando atajo '%s': %s", hotkey_str, e)
            return False

        # Envolver el callback para capturar excepciones
        def safe_callback():
            try:
                if self._callback_queue is not None:
                    self._callback_queue.put(callback)
                else:
                    callback()
            except Exception as e:
                logger.error("Error en callback de hotkey '%s': %s", hotkey_str, e, exc_info=True)

        self._bindings[pynput_hotkey] = safe_callback
        self._original_names[pynput_hotkey] = hotkey_str
        
        logger.info("Atajo registrado: '%s' (pynput: '%s')", hotkey_str, pynput_hotkey)
        return True

    def start(self) -> None:
        """
        Inicia el hilo en segundo plano que escucha el teclado.
        """
        if not self._bindings:
            logger.warning("No hay atajos registrados para escuchar.")
            return

        if self._listener is None:
            # pynput intenta conectarse a X11 durante la importación. Hacerlo
            # aquí permite importar y probar la lógica pura sin display, y
            # conserva la conexión sólo para el daemon que realmente arranca.
            from pynput import keyboard
            self._listener = keyboard.GlobalHotKeys(self._bindings)
            self._listener.start()
            logger.info("Listener de teclado iniciado en segundo plano.")

        # El puntero se activa bajo demanda cuando State contiene ventanas
        # acopladas. Mantener XRecord escuchando todos los movimientos durante
        # el idle consume CPU sin que exista nada que desacoplar.

    def set_pointer_tracking(self, enabled: bool) -> None:
        """Activa el listener global sólo mientras hay ventanas acopladas."""
        if enabled and self._pointer_event_queue is not None and self._pointer_listener is None:
            from pynput import mouse
            self._pointer_listener = mouse.Listener(
                on_click=self._on_pointer_click,
                on_move=self._on_pointer_move,
            )
            self._pointer_listener.start()
            logger.info("Listener global de puntero iniciado en segundo plano.")
        elif not enabled and self._pointer_listener is not None:
            try:
                self._pointer_listener.stop()
            except Exception as e:
                logger.warning("No se pudo detener el listener de puntero: %s", e)
            self._pointer_listener = None
            self._pointer_pressed = False
            logger.info("Listener global de puntero detenido (sin ventanas acopladas).")

    def unregister_all(self) -> None:
        """
        Detiene el listener y limpia los atajos.
        """
        if not self._listener and not self._pointer_listener and not self._bindings:
            return

        if self._listener:
            try:
                self._listener.stop()
            except Exception as e:
                logger.warning("No se pudo detener el listener de teclado: %s", e)
            self._listener = None

        if self._pointer_listener:
            try:
                self._pointer_listener.stop()
            except Exception as e:
                logger.warning("No se pudo detener el listener de puntero: %s", e)
            self._pointer_listener = None
        self._pointer_pressed = False
            
        count = len(self._bindings)
        self._bindings.clear()
        self._original_names.clear()

        logger.info("Todos los atajos desregistrados (%d bindings).", count)

    def handle_key_press(self, event) -> bool:
        """
        Mantenido por compatibilidad con daemon.py, pero pynput 
        maneja los eventos en su propio hilo.
        """
        return False

    @property
    def registered_count(self) -> int:
        return len(self._bindings)

    def get_registered_hotkeys(self) -> List[str]:
        return list(self._original_names.values())

    def _on_pointer_click(self, x, y, _button, pressed) -> None:
        """Reenvía el ciclo de click al event loop sin tocar X11 desde este hilo."""
        if self._pointer_event_queue is None:
            return
        self._pointer_pressed = pressed
        self._pointer_event_queue.put({
            "event": "pointer_press" if pressed else "pointer_release",
            "x": x,
            "y": y,
        })

    def _on_pointer_move(self, x, y) -> None:
        """Sólo reenvía movimiento mientras existe un botón presionado."""
        if self._pointer_event_queue is not None and self._pointer_pressed:
            self._pointer_event_queue.put({"event": "pointer_move", "x": x, "y": y})
