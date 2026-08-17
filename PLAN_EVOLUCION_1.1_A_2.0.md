# Plan de implementación: SnapAssist 1.1.0 → 2.0.0

Este documento fija la ruta acordada. **1.1.0** es el punto estable y
recuperable de X11; las etapas posteriores son prereleases de 2.0.

## Decisiones de arquitectura

- Plataforma de referencia: GNOME Shell 46 sobre Zorin OS 18.1.
- La extensión GNOME será la integración principal en X11 y Wayland.
- Python conserva layouts, selección, grupos, transacciones y propiedad del estado.
- GJS controla Mutter, ventanas, eventos, hotkeys, UI y animaciones.
- Tkinter se conserva en v1.1 y para comparación, no como UI principal de v2.
- Handles de ventana, monitor y workspace son opacos para el core.
- `Rect` usa coordenadas lógicas; los monitores exponen geometría, work area y escala.
- Las capacidades del backend forman parte del contrato desde el primer refactor.
- `State` pertenece a un único event loop; no se añaden locks sin una carrera demostrada.
- Licencia: GPL-3.0-only.

## v1.1.0 — Estabilización y release X11

Limpiar código histórico, entregar licencia/changelog/metadatos/pyproject,
mantener `requirements.txt`, corregir rutas XDG de systemd, resolver nombres
mediante `.desktop`, exigir `flow_id`, verificar afinidad de hilo de `State`,
clasificar errores esperables del backend, configurar CI Python 3.11–3.13,
ampliar pruebas X11 y publicar `v1.1.0` con artefacto verificable.

**Salida:** paridad funcional X11, CI verde e instalación reproducible desde
el tag, incluyendo actualización, rollback y desinstalación.

## v2.0.0-alpha.1 — Spike GNOME/Mutter

Crear una extensión GNOME 46 con módulos ESM y validar en GNOME X11, Wayland y
XWayland: ventana activa, listado, títulos, aplicaciones, geometría lógica,
monitores, workspaces, foco, movimiento, resize, maximización, mínimos,
transients, eventos, work areas, hotplug, escalas, `Super+Z`, conflictos,
overlay, menú mínimo, handshake D-Bus y limpieza al habilitar/deshabilitar.

Entregar una matriz capacidad × sesión y un ADR. Toda capacidad esencial debe
quedar demostrada o redefinida antes del refactor.

## v2.0.0-alpha.2 — Core independiente de X11

Extraer modelos, layouts, selección, grupos y transacciones sin imports de
Xlib/Mutter/GJS/pynput/Tkinter. Definir `PlatformRuntime` con
`WindowController`, `PresentationPort`, `ShortcutProvider` y `EventSource`.
Convertir el daemon a eventos semánticos, encapsular X11 en su adaptador,
usar snapshots inmutables, operaciones visuales asíncronas y contract tests.

**Salida:** paridad con v1.1 y core sin conceptos X11.

## v2.0.0-alpha.3 — Protocolo GNOME e IPC

Servicio versionado:

```text
Bus name:   org.snapassist.Shell
Object:     /org/snapassist/Shell
Interface:  org.snapassist.Shell1
```

Implementar `GetProtocolInfo`, `GetSnapshot`, operaciones identificadas para
mover/redimensionar/activar/maximizar/workspace, operaciones de UI, señales
semánticas, `OperationCompleted`, secuencias e identificador de sesión Shell.
Cubrir reconexión, extensión deshabilitada, daemon detenido, eventos fuera de
orden y ventanas desaparecidas.

## v2.0.0-beta.1 — UI e input nativos GNOME

Trasladar selector, zonas, Snap Assist, overlays y ayuda a St/Clutter; registrar
hotkeys con GNOME Shell/GSettings; conservar navegación y reglas en Python;
mantener en GJS solo presentación, input, animación y Mutter; resolver nombres
con `Shell.WindowTracker`; garantizar teclado, contraste, escalado, texto largo
y navegación sin mouse.

**Salida:** flujo completo sin Tkinter e idéntico en GNOME X11 y Wayland.

## v2.0.0-rc.1 — Paridad y validación

Validar snap inicial, sugerencias, grupos, restauración, cancelación,
transients, mínimos, maximización, workspaces, múltiples monitores, hotplug,
coordenadas negativas, escalas 100/200/fraccional, GTK, Qt, Electron, Firefox,
Chromium, terminales, XWayland, reinicio de extensión, caída del daemon,
instalación, actualización desde v1.1, rollback y desinstalación.

La matriz obligatoria cubre Zorin OS 18.1 con GNOME 46 en X11 y Wayland,
incluyendo aplicaciones Wayland nativas y XWayland.

**Salida:** contract tests y CI verdes, matriz manual aprobada y cero
regresiones críticas frente a v1.1.

## v2.0.0 — Release GNOME X11 + Wayland

Distribuir daemon, unidad systemd, extensión y schemas como conjunto
versionado; comprobar GNOME 46; seleccionar la integración GNOME en modo
`auto`; conservar X11 directo solo como diagnóstico; publicar actualización,
rollback a v1.1 y limitaciones conocidas. No declarar versiones GNOME fuera de
la matriz probada.

## Después de 2.0

### v2.1 — Endurecimiento GNOME

Agregar versiones GNOME mediante feature detection, Ubuntu y Fedora, pruebas
D-Bus/sesiones anidadas, persistencia efímera en `$XDG_RUNTIME_DIR`,
reconexión robusta y más configuraciones multimonitor.

### v2.2 — Spike KDE

Auditar el contrato contra KWin; clasificar capacidades; probar ventana activa,
geometría, foco, eventos, hotkeys, UI e IPC sin modificar el core ni asumir
que el IPC será igual al de GNOME.

### v2.3 — KDE Plasma/KWin

Implementar adaptador, UI y empaquetado KWin propios, reutilizando core,
layouts, reglas, grupos, modelos y contract tests. Reservar v3.0 para una
ruptura real del protocolo o de las APIs públicas.

## Estrategia de pruebas

- Core: unitarias puras de layouts, selección, grupos, rollback y estados.
- Contrato: suite común contra dobles, X11 y GNOME.
- X11: dobles Xlib y Xvfb cuando sea representativo.
- Extensión: lint, módulos puros, metadata y schemas.
- D-Bus: introspección, versiones, secuencias, reconexión y errores.
- Integración: GNOME anidado para automatización básica.
- Sistema real: X11/Wayland, XWayland, varios monitores y HiDPI.

Las pruebas que requieren compositor real quedan separadas del CI unitario y
se mantienen como una lista reproducible de aceptación manual.
