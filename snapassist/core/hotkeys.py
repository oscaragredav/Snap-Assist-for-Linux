"""
core/hotkeys.py — Registro y captura de atajos globales mediante pynput.

GNOME (y otros compositores modernos) a menudo bloquean `XGrabKey` para la tecla Super.
Para solucionar esto, utilizamos `pynput`, que internamente usa la extensión XRecord 
para escuchar el flujo de eventos globalmente sin requerir exclusividad.
"""

import logging
from typing import Callable, Dict, List

from pynput import keyboard

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
        # En la Fase 2 solo necesitamos super+z. Si necesitamos otras, las mapearemos.
        if key == "tab":
            key = "<tab>"
        elif key in ("esc", "escape"):
            key = "<esc>"
        # etc... (se pueden añadir más según sea necesario)
        
    pynput_parts.append(key)
    return "+".join(pynput_parts)


class HotkeyManager:
    """
    Gestiona el registro y captura de atajos de teclado globales usando pynput.
    """

    def __init__(self, display_obj=None, root_window=None) -> None:
        # display_obj y root_window se mantienen por compatibilidad con main.py
        self._bindings: Dict[str, Callable] = {}
        self._original_names: Dict[str, str] = {}
        self._listener = None

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
            self._listener = keyboard.GlobalHotKeys(self._bindings)
            self._listener.start()
            logger.info("Listener de teclado iniciado en segundo plano.")

    def unregister_all(self) -> None:
        """
        Detiene el listener y limpia los atajos.
        """
        if self._listener:
            self._listener.stop()
            self._listener = None
            
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
