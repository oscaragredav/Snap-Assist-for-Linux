"""
ui/notifier.py — Wrapper para mostrar notificaciones de escritorio.
"""

import logging
import subprocess

logger = logging.getLogger(__name__)


class Notifier:
    """Wrapper para notify-send."""

    @staticmethod
    def send(message: str, timeout_ms: int = 3000) -> None:
        """
        Muestra una notificación en el escritorio usando notify-send.
        No bloquea el hilo actual.
        """
        try:
            # -t especifica el timeout en ms
            # -a especifica el nombre de la app
            subprocess.Popen(
                ["notify-send", "-a", "SnapAssist", "-t", str(timeout_ms), message]
            )
            logger.debug("Notificación enviada: %s", message)
        except Exception as e:
            logger.error("Error al enviar notificación: %s", e)
