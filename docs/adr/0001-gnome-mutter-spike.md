# ADR 0001 — Integración GNOME/Mutter para SnapAssist 2.0

- Estado: propuesto, pendiente de U2
- Fecha: 2026-08-12
- Plataforma de referencia: Zorin OS 18.1, GNOME Shell 46

## Decisión

La integración principal de SnapAssist 2.0 será una extensión GNOME Shell ESM.
GJS poseerá objetos Mutter, eventos, input, overlay y presentación. Python
conservará layouts, selección, grupos y transacciones. La comunicación usará un
protocolo D-Bus versionado y handles opacos.

El spike usa exclusivamente:

- UUID `snapassist-test@oscaragredav`.
- Bus `org.snapassist.Shell.Test`.
- Objeto `/org/snapassist/Shell/Test`.
- Interfaz inicial `org.snapassist.Shell1`.

La identidad pública estable no se utilizará hasta la promoción de un release.

## Condiciones para aceptar

La puerta U2 debe demostrar en GNOME X11, Wayland y XWayland todas las
capacidades esenciales de la matriz. Una capacidad ausente debe provocar una
redefinición explícita del contrato antes de comenzar alpha.2.

## Consecuencias

- El core no podrá almacenar ni interpretar IDs nativos de X11 o Mutter.
- La extensión debe retirar señales, atajos, actores y nombres D-Bus al
  deshabilitarse.
- Tkinter y el backend X11 directo se mantienen durante la migración y como
  referencia de paridad, pero no serán la UI principal de 2.0.
