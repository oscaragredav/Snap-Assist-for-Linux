"""
snap/animation.py — Motor de animaciones para acoplamiento de ventanas.
"""

import time
import threading
import logging
from typing import Callable, Optional
from snapassist.layout.engine import Rect

logger = logging.getLogger(__name__)

class AnimationEngine:
    """
    Realiza la interpolación geométrica (lerp) entre un Rect inicial y uno final.
    """
    
    def __init__(self, fps: int = 60, duration_ms: int = 200):
        self.fps = fps
        self.duration_ms = duration_ms

    def animate(self, start_rect: Rect, end_rect: Rect, update_callback: Callable[[Rect], None]) -> None:
        """
        Ejecuta la animación de forma bloqueante.
        """
        steps = int((self.duration_ms / 1000.0) * self.fps)
        if steps <= 0:
            update_callback(end_rect)
            return

        sleep_time = 1.0 / self.fps

        for i in range(1, steps + 1):
            t = i / float(steps)
            # Ease-out quad para un efecto más suavizado al final
            ease_t = t * (2 - t)
            
            curr_x = int(start_rect.x + (end_rect.x - start_rect.x) * ease_t)
            curr_y = int(start_rect.y + (end_rect.y - start_rect.y) * ease_t)
            curr_w = int(start_rect.w + (end_rect.w - start_rect.w) * ease_t)
            curr_h = int(start_rect.h + (end_rect.h - start_rect.h) * ease_t)
            
            update_callback(Rect(curr_x, curr_y, curr_w, curr_h))
            time.sleep(sleep_time)
            
        # Asegurar posición final exacta
        update_callback(end_rect)

    def animate_async(
        self, 
        start_rect: Rect, 
        end_rect: Rect, 
        update_callback: Callable[[Rect], None],
        on_complete: Optional[Callable[[], None]] = None
    ) -> None:
        """
        Ejecuta la animación en un hilo separado para no bloquear el event loop de X11.
        """
        def _run():
            try:
                self.animate(start_rect, end_rect, update_callback)
            except Exception as e:
                logger.error("Error durante animación: %s", e)
            finally:
                if on_complete:
                    on_complete()
                    
        t = threading.Thread(target=_run, daemon=True, name="AnimationThread")
        t.start()
