"""Espera breve y silenciosamente a que el servidor X11 esté disponible."""

from __future__ import annotations

import os
import sys
import time

from Xlib import display, error


def main() -> int:
    display_name = os.environ.get("DISPLAY")
    if not display_name:
        print("SnapAssist: DISPLAY no está definido; ejecuta de nuevo install.sh desde tu sesión X11.", file=sys.stderr)
        return 1

    timeout = float(os.environ.get("SNAPASSIST_X11_WAIT_SECONDS", "30"))
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None

    while time.monotonic() < deadline:
        try:
            connection = display.Display(display_name)
            connection.close()
            return 0
        except (error.DisplayConnectionError, OSError) as exc:
            last_error = exc
            time.sleep(0.5)

    print(
        f"SnapAssist: X11 ({display_name}) no estuvo disponible tras {timeout:g} s: {last_error}",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
