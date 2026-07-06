# Plan de Implementación: SnapAssist para Linux
**Versión 1.0 — Documento de planificación**

---

## Principios del Plan

Cada fase produce un sistema funcionalmente verificable, no un conjunto de archivos incompletos. Una fase no comienza hasta que la anterior pasa todos sus criterios de aceptación. Las pruebas funcionales de cada fase se ejecutan manualmente sobre el entorno real (Zorin OS, sesión X11) antes de avanzar.

Las fases están ordenadas por dependencia técnica estricta: las capas inferiores (conexión X11, lectura de ventanas) deben estar sólidas antes de construir las capas superiores (flujo de Snap, grupos). Invertir ese orden genera deuda técnica difícil de deshacer.

---

## Resumen de Fases

| Fase | Nombre | Entregable principal |
|---|---|---|
| 1 | Infraestructura base y conexión X11 | Daemon arranca, lee ventanas, escribe log |
| 2 | Captura de atajos y lectura de estado | Super+Z loguea ventana activa y monitor |
| 3 | Cálculo de zonas y movimiento de ventanas | Ventana se mueve a zona calculada correctamente |
| 4 | Menú de layouts (Super+Z visual) | Usuario selecciona layout con teclado y ventana se acopla |
| 5 | Toggle de memoria y desacoplamiento | Ventana recupera geometría original al desanclarse |
| 6 | Filtro de ventanas y MRU | Lista elegible correcta y ordenada por recencia |
| 7 | Snap Assist (sugerencias automáticas) | Flujo completo de llenado de zonas vacías |
| 8 | Gestión de Snap Groups | Super+Alt+Tab trae grupo al frente |
| 9 | Casos borde y robustez | Sistema estable ante cierres, resizes, monitores |
| 10 | Configurabilidad y empaquetado | Daemon instalable como servicio de usuario |

---

## Fase 1 — Infraestructura Base y Conexión X11

### Objetivo
Establecer la estructura del proyecto, conectar al servidor X11, verificar que el daemon puede leer el estado básico de las ventanas del sistema y que el sistema de logging funciona correctamente. Esta fase no mueve ninguna ventana ni presenta ninguna UI.

### Archivos creados en esta fase
- `main.py`
- `core/daemon.py` (solo inicialización y event loop vacío)
- `wm/backend.py` (interfaz abstracta)
- `wm/x11_backend.py` (solo conexión y lectura de propiedades básicas)
- `wm/wayland_backend.py` (stub con NotImplementedError)
- `core/state.py` (estructura de datos, sin lógica aún)
- `config.py` (constantes base)

### Tareas
- Crear la estructura de directorios del proyecto completa.
- Implementar la interfaz abstracta `WindowManager` con todos sus métodos.
- Implementar `X11Backend.__init__`: conexión a `Display()`, selección de eventos sobre el root window (`SubstructureNotifyMask`, `PropertyChangeMask`).
- Implementar `X11Backend.get_all_windows()` usando `_NET_CLIENT_LIST`.
- Implementar `X11Backend.get_window_geometry()` usando `GetGeometry` y traducción a coordenadas absolutas.
- Implementar `X11Backend.get_window_title()` usando `_NET_WM_NAME` con fallback a `WM_NAME`.
- Implementar `X11Backend.get_window_type()` usando `_NET_WM_WINDOW_TYPE`.
- Implementar `X11Backend.get_work_area()` usando `_NET_WORKAREA`.
- Implementar `X11Backend.get_monitor_for_window()` usando `_NET_WM_FULLSCREEN_MONITORS` o cálculo por intersección de geometrías.
- Configurar el sistema de logging con rotación diaria en `~/.local/share/snapassist/daemon.log`.
- Implementar detección de `XDG_SESSION_TYPE` en `main.py` y selección del backend correspondiente.
- Implementar handler de SIGTERM/SIGINT para apagado limpio.
- Escribir tests unitarios para: parseo de `_NET_CLIENT_LIST`, conversión de geometría relativa a absoluta, selección de backend por variable de entorno.

### Criterios técnicos de aceptación
- El proyecto importa sin errores con `python3 main.py`.
- `X11Backend.get_all_windows()` devuelve una lista no vacía en una sesión X11 con ventanas abiertas.
- `X11Backend.get_window_geometry()` devuelve coordenadas absolutas correctas verificables con `xwininfo`.
- `X11Backend.get_work_area()` devuelve un `Rect` que excluye el panel de Zorin.
- Todos los tests unitarios pasan.
- El daemon escribe al log sin errores al arrancar y al terminar con SIGTERM.
- Al correr con `XDG_SESSION_TYPE=wayland`, el daemon termina con un mensaje claro en lugar de un crash por importación.

### Pruebas funcionales

**Caso 1 — Lectura básica de ventanas**
Abrir Firefox, una terminal, y un editor de texto. Ejecutar el daemon. Revisar el log.

*Resultado esperado:* el log muestra los títulos, tipos y geometrías de las tres ventanas abiertas con coordenadas coherentes con su posición visual en pantalla.

**Caso 2 — Work area sin panel**
Verificar con `xprop -root _NET_WORKAREA` que el valor reportado por el daemon coincide exactamente con la salida de `xprop`.

*Resultado esperado:* los valores son idénticos. El alto del work area es menor que la resolución vertical del monitor en exactamente la altura del panel de Zorin.

**Caso 3 — Apagado limpio**
Enviar SIGTERM al proceso del daemon con `kill -TERM <pid>`.

*Resultado esperado:* el daemon escribe una línea de cierre en el log y termina sin dejar procesos huérfanos.

---

## Fase 2 — Captura de Atajos Globales y Lectura de Estado de Foco

### Objetivo
Implementar la captura de atajos de teclado globales mediante `XGrabKey` y la detección de cambios de ventana activa. Al final de esta fase, presionar Super+Z mientras cualquier aplicación tiene el foco produce una entrada en el log con el título de la ventana activa y el índice del monitor donde reside.

### Archivos creados o modificados en esta fase
- `core/hotkeys.py` (nuevo)
- `core/daemon.py` (event loop con despacho real de eventos)
- `core/state.py` (lógica de `update_mru`)

### Tareas
- Implementar `HotkeyManager.register(hotkey_str, callback)`: parsear la cadena de atajo (ej. `"super+z"`), resolver keysym y máscara de modificadores, llamar `XGrabKey` sobre el root window para todas las variantes de NumLock y CapsLock.
- Implementar `HotkeyManager.unregister_all()` con `XUngrabKey` para todos los atajos registrados.
- Implementar el event loop en `daemon.py`: llamada bloqueante a `display.next_event()`, despacho por tipo de evento a handlers específicos.
- Implementar handler de `PropertyNotify` sobre `_NET_ACTIVE_WINDOW`: extraer el nuevo `window_id` activo, llamar `State.update_mru(wid)`.
- Implementar `State.update_mru(wid)`: mover el `wid` al frente de `mru_list`, insertar si no existe, ignorar si `wid` es 0 o None.
- Implementar handler de `KeyPress`: comparar keycode+estado contra atajos registrados, invocar callback si hay coincidencia.
- Registrar Super+Z con un callback que loguee la ventana activa y su monitor.
- Escribir tests unitarios para: `update_mru` con ventana nueva, con ventana ya existente, con `wid=0`.

### Criterios técnicos de aceptación
- Presionar Super+Z con cualquier aplicación en foco produce una entrada `INFO` en el log con el título correcto de la ventana activa.
- Presionar Super+Z con el escritorio en foco produce una entrada `WARNING` indicando que no hay ventana elegible.
- El MRU se actualiza correctamente al cambiar de ventana: verificable imprimiendo `State.mru_list` desde el callback de Super+Z.
- Super+Z no es interceptado por el WM de Zorin (no activa ningún comportamiento nativo de GNOME).
- Todos los tests unitarios pasan.

### Pruebas funcionales

**Caso 1 — Interceptación global de atajo**
Abrir Firefox con el foco activo. Presionar Super+Z. Revisar el log.

*Resultado esperado:* el log muestra el título de Firefox y el índice del monitor donde se encuentra, sin que ningún menú de GNOME se abra.

**Caso 2 — Orden MRU tras cambio de foco**
Abrir Firefox, luego una terminal, luego VSCode. Presionar Super+Z. Revisar `mru_list` en el log.

*Resultado esperado:* la lista aparece en el orden `[VSCode, Terminal, Firefox]`.

**Caso 3 — Sin ventana activa**
Hacer clic en el escritorio (sin ventana enfocada). Presionar Super+Z.

*Resultado esperado:* el log registra un warning de "sin ventana elegible". No ocurre ningún otro efecto.

---

## Fase 3 — Cálculo de Zonas y Movimiento de Ventanas

### Objetivo
Implementar el motor de cálculo de zonas y la operación de movimiento y redimensionamiento de ventanas. Al final de esta fase es posible invocar desde código (sin UI todavía) la función que mueve una ventana a una zona específica de un layout y verificar que la geometría resultante es exacta.

### Archivos creados o modificados en esta fase
- `layout/templates.py` (nuevo)
- `layout/engine.py` (nuevo)
- `wm/x11_backend.py` (agregar `move_resize_window`, `get_transient_for`)

### Tareas
- Definir los tipos `ZoneTemplate`, `LayoutTemplate` y `Rect` como dataclasses.
- Definir los templates de layouts predefinidos en `templates.py`: 1:1, 2/3+1/3, 1/2+1/4+1/4, cuadrícula 2x2, columna izquierda completa + dos celdas derechas.
- Implementar `LayoutEngine.calculate_zones(template, work_area) -> List[Rect]`: convertir proporciones flotantes a píxeles absolutos truncando (no redondeando) para evitar solapamientos de un píxel.
- Implementar `LayoutEngine.get_empty_zones(template, occupied_zone_indices) -> List[int]`.
- Implementar `LayoutEngine.center_in_zone(min_size, zone_rect) -> Rect` para el comportamiento "Ignorar y Centrar".
- Implementar `X11Backend.move_resize_window(wid, rect)`: usar `_NET_MOVERESIZE_WINDOW` vía `SendEvent` al root window para respetar las decoraciones del WM, con fallback a `XMoveResizeWindow` directo si el WM no responde.
- Implementar `X11Backend.get_transient_for(wid) -> Optional[int]` leyendo `WM_TRANSIENT_FOR`.
- Implementar `_pending_own_resizes` en el backend: agregar `wid` al set antes de `move_resize_window`, removerlo al recibir el `ConfigureNotify` correspondiente.
- Escribir tests unitarios para `calculate_zones`: verificar que las zonas no se solapan, que cubren exactamente el work area, y que los bordes son contiguos (el borde derecho de una zona es el borde izquierdo de la siguiente).

### Criterios técnicos de aceptación
- `calculate_zones` con el template 1:1 y un work area de 1920x1040 produce dos rectángulos de 960x1040 sin píxeles solapados ni espacios entre ellos.
- `move_resize_window` aplicado a Firefox produce una geometría verificable con `xwininfo` que coincide exactamente con el `Rect` calculado (tolerancia: 0px para posición, ±2px para tamaño por decoraciones del WM).
- `_pending_own_resizes` previene que el daemon registre como resize externo el movimiento que él mismo ejecuta: verificable en el log (no debe aparecer `on_window_resized` tras un `move_resize_window` propio).
- Todos los tests unitarios pasan.

### Pruebas funcionales

**Caso 1 — Movimiento a zona izquierda**
Desde el callback de Super+Z (sin UI), invocar `move_resize_window` con la zona izquierda del template 1:1 sobre Firefox.

*Resultado esperado:* Firefox ocupa exactamente la mitad izquierda del work area sin dejar espacios visibles ni sobrepasar el panel.

**Caso 2 — Ventana con tamaño mínimo**
Repetir el caso 1 con una aplicación que tenga restricción de tamaño mínimo mayor que la zona (por ejemplo, GIMP con paneles abiertos).

*Resultado esperado:* la ventana queda centrada dentro de la zona con desborde simétrico. El log registra un `WARNING` de "Ignorar y Centrar" con las dimensiones de la ventana y la zona.

**Caso 3 — Movimiento desde otro monitor**
En un setup de dos monitores, abrir Firefox en el monitor secundario. Desde código, moverlo al cuadrante izquierdo del monitor primario.

*Resultado esperado:* Firefox aparece correctamente posicionado en el monitor primario con la geometría calculada para ese monitor.

---
z
## Fase 4 — Menú Visual de Layouts (Super+Z Completo)

### Objetivo
Implementar el menú visual de selección de layouts invocado por Super+Z, incluyendo el overlay de zona sobre la pantalla real durante la navegación y la animación de confirmación post-acoplamiento.

### Archivos creados o modificados en esta fase
- `ui/layout_menu.py` (nuevo)
- `ui/overlay.py` (nuevo)
- `ui/notifier.py` (nuevo)
- `snap/snap_flow.py` (parcial: solo la mitad del flujo hasta acoplar la primera ventana)
- `themes/snap_assist.rasi` (nuevo)

### Tareas
- Implementar `Notifier.send(message, timeout_ms)` como wrapper de `notify-send`.
- Implementar `Overlay.show(rect, monitor)` y `Overlay.hide()`: ventana tkinter sin decoraciones, fondo semitransparente, posicionada con coordenadas absolutas, en hilo separado para no bloquear el event loop.
- Implementar `LayoutMenu.show(templates, disabled_indices) -> Optional[Tuple[LayoutTemplate, int]]`: invocar Rofi con el tema custom, parsear la selección devuelta por stdout, manejar código de salida 1 (Esc) como `None`.
- Diseñar el tema Rofi `snap_assist.rasi` que represente cada layout como un diagrama de zonas usando caracteres Unicode de bloque.
- Implementar la lógica de navegación en `LayoutMenu`: al cambiar selección en Rofi, mostrar el overlay de la zona correspondiente en la pantalla real. Esto requiere comunicación entre el proceso Rofi y el daemon; implementar mediante un socket Unix o un archivo temporal de estado que Rofi actualiza vía `-kb-custom-*` y el daemon lee.
- Implementar en `snap_flow.py` el flujo hasta el primer acoplamiento: validar ventana activa → obtener monitor y work area → calcular zonas → deshabilitar layouts insuficientes → abrir menú → guardar geometría en State → ejecutar `move_resize_window` → ejecutar animación de confirmación.
- Implementar la animación de confirmación: serie de `move_resize_window` interpolados linealmente entre la geometría actual y la geometría destino en `SNAP_ANIMATION_MS` milisegundos, ejecutados en hilo separado.
- Registrar el doble-press de Super+Z como cancelación (máquina de estados en `SnapFlow`).

### Criterios técnicos de aceptación
- Super+Z despliega el menú de layouts en el monitor correcto (el de la ventana activa).
- Navegar entre layouts con las flechas actualiza el overlay en pantalla en tiempo real.
- Seleccionar un layout y una zona con Enter acopla la ventana activa a esa zona con animación visible.
- Super+Z con escritorio enfocado muestra notificación y no abre el menú.
- Segundo Super+Z mientras el menú está abierto cierra el menú sin modificar ninguna ventana.
- Esc en cualquier punto del menú cancela sin modificar ninguna ventana.

### Pruebas funcionales

**Caso 1 — Flujo completo de selección**
Abrir Firefox. Presionar Super+Z. Navegar con flechas entre los layouts. Seleccionar el template 1:1 y la zona izquierda con Enter.

*Resultado esperado:* Firefox se anima hacia la mitad izquierda del monitor. El overlay semitransparente fue visible durante la navegación. La animación dura aproximadamente 200ms.

**Caso 2 — Layouts deshabilitados**
Abrir una sola ventana en el sistema. Presionar Super+Z.

*Resultado esperado:* los layouts de 3 o más zonas aparecen visualmente deshabilitados y no son seleccionables.

**Caso 3 — Cancelación con Esc**
Abrir Firefox en una posición conocida. Presionar Super+Z, navegar a una zona, y cancelar con Esc.

*Resultado esperado:* Firefox permanece exactamente en su posición original. El overlay desaparece.

**Caso 4 — Monitor correcto en setup dual**
Con dos monitores, enfocar una ventana en el monitor secundario. Presionar Super+Z.

*Resultado esperado:* el menú de layouts aparece en el monitor secundario, no en el primario.

---Z

## Fase 5 — Toggle de Memoria y Desacoplamiento

### Objetivo
Implementar la restauración de geometría previa al desanclar una ventana, la detección del umbral de arrastre con mouse, y el desacoplamiento implícito por resize externo. Al final de esta fase el ciclo completo acoplar→desacoplar→restaurar funciona correctamente.

### Archivos creados o modificados en esta fase
- `core/state.py` (lógica completa de `save_geometry`, `restore_geometry`)
- `core/daemon.py` (handlers de `ConfigureNotify` y detección de drag)
- `wm/x11_backend.py` (suscripción a `ButtonPress`/`MotionNotify` para detección de drag)

### Tareas
- Implementar `State.save_geometry(wid, geom)` y `State.restore_geometry(wid) -> Optional[WindowGeometry]`.
- Implementar detección de drag con umbral: suscribirse a `ButtonPress` y `MotionNotify` sobre ventanas acopladas; calcular distancia euclidiana acumulada desde el primer `ButtonPress`; si supera `DRAG_THRESHOLD_PX`, marcar como drag intencional y disparar `on_window_dragged(wid)`.
- Implementar `SnapFlow.on_window_dragged(wid)`: remover de `State.snapped_windows`, llamar a `GroupManager.on_window_detached(wid)`, restaurar geometría.
- Implementar handler de `ConfigureNotify` externo en `daemon.py`: si el `wid` está en `snapped_windows` y no está en `_pending_own_resizes`, llamar `GroupManager.on_window_resized(wid)`.
- Implementar `GroupManager.on_window_resized(wid)`: desacoplar la ventana del grupo, aplicar reglas de disolución de grupo si corresponde.
- Escribir tests unitarios para: `save_geometry` seguido de `restore_geometry` devuelve la geometría original; `restore_geometry` sobre un `wid` sin geometría guardada devuelve `None`.

### Criterios técnicos de aceptación
- Tras acoplar una ventana y desacoplarla arrastrando con el mouse más de 8px, la ventana recupera exactamente su geometría previa (posición y tamaño, tolerancia ±1px).
- Arrastrar menos de 8px (clic normal en la barra de título sin mover) no produce desacoplamiento.
- Un resize externo (redimensionar manualmente una ventana acoplada por el borde) la desacopla del grupo sin restaurar geometría (el resize del usuario es intencional).
- El daemon no loguea `on_window_resized` para los movimientos ejecutados por él mismo.

### Pruebas funcionales

**Caso 1 — Restauración de geometría**
Mover Firefox a una posición y tamaño conocidos (verificar con `xwininfo`). Acoplarlo a una zona. Desacoplarlo arrastrando con el mouse. Verificar con `xwininfo`.

*Resultado esperado:* Firefox recupera exactamente la posición y tamaño previos al acoplamiento.

**Caso 2 — Umbral de tolerancia**
Acoplar Firefox. Hacer clic en su barra de título y mover el mouse 3px sin soltar, luego soltar.

*Resultado esperado:* Firefox permanece acoplado. No se produce desacoplamiento.

**Caso 3 — Desacoplamiento por resize externo**
Acoplar Firefox. Arrastrar su borde derecho para redimensionarlo manualmente.

*Resultado esperado:* Firefox queda con el tamaño elegido por el usuario. El log registra un desacoplamiento implícito. No se restaura la geometría previa.

---

## Fase 6 — Filtro de Ventanas Elegibles y Ordenamiento MRU

### Objetivo
Implementar el filtro completo de ventanas elegibles para el Snap Assist y verificar que el ordenamiento MRU produce la lista correcta en todos los escenarios relevantes.

### Archivos creados o modificados en esta fase
- `wm/x11_backend.py` (filtro completo en `get_all_windows`)
- `core/state.py` (verificación de `mru_list` como fuente de verdad del orden)

### Tareas
- Extender `X11Backend.get_all_windows()` para aplicar los cuatro criterios de elegibilidad: `IsViewable`, ausencia de `_NET_WM_STATE_SKIP_TASKBAR`, tipo `_NET_WM_WINDOW_TYPE_NORMAL`, ausencia de `_NET_WM_STATE_FULLSCREEN` y `_NET_WM_STATE_ABOVE`.
- Implementar la lógica de inclusión de ventanas de otros workspaces: leer `_NET_WM_DESKTOP` de cada ventana y comparar contra `_NET_CURRENT_DESKTOP`; incluir las de otros workspaces marcándolas con un flag `on_other_workspace=True` en el objeto de ventana.
- Implementar `State.get_sorted_eligible(all_windows, exclude_wid) -> List[WindowInfo]`: ordenar por posición en `mru_list`, excluir `exclude_wid` (la ventana ya acoplada en la primera zona), excluir ventanas minimizadas, excluir `Always on Top` y fullscreen.
- Asignar teclas de acceso rápido a la lista ordenada usando `QUICKKEY_SEQUENCE` de `config.py`.
- Escribir tests unitarios para: filtro con ventanas de sistema presentes (deben ser excluidas), orden MRU con 5 ventanas en secuencia conocida de enfoque, asignación de quickkeys a lista de 10 ventanas.

### Criterios técnicos de aceptación
- `get_all_windows()` no incluye el panel de Zorin, el dock, ni ninguna notificación del sistema.
- `get_all_windows()` no incluye ventanas minimizadas.
- `get_all_windows()` incluye ventanas de otros workspaces.
- `get_sorted_eligible()` devuelve las ventanas en el orden correcto según el historial de enfoque real de la sesión, verificable manualmente enfocando ventanas en secuencia conocida.
- La asignación de quickkeys es biyectiva: dos ventanas distintas no reciben la misma tecla.
- Todos los tests unitarios pasan.

### Pruebas funcionales

**Caso 1 — Exclusión de ventanas de sistema**
Abrir Firefox, una terminal, y asegurarse de que el panel de Zorin y el dock están visibles. Invocar `get_all_windows()` desde el daemon e imprimir el resultado en el log.

*Resultado esperado:* la lista contiene Firefox y la terminal, pero no el panel ni el dock.

**Caso 2 — Orden MRU verificable**
Enfocar las ventanas en este orden: Firefox → Terminal → VSCode → Firefox. Invocar `get_sorted_eligible()`.

*Resultado esperado:* la lista comienza con Firefox (el más recientemente enfocado), seguido de VSCode, luego Terminal.

**Caso 3 — Ventana minimizada**
Minimizar Firefox. Invocar `get_sorted_eligible()`.

*Resultado esperado:* Firefox no aparece en la lista.

---

## Fase 7 — Snap Assist Completo

### Objetivo
Implementar el flujo completo del Snap Assist: detección de zonas vacías tras el primer acoplamiento, despliegue del menú de sugerencias con quickkeys, selección de ventanas (incluyendo las de otros monitores y workspaces), y finalización del flujo con la política de cancelación correcta.

### Archivos creados o modificados en esta fase
- `ui/snap_assist_menu.py` (nuevo)
- `snap/snap_flow.py` (completar la segunda mitad del flujo)

### Tareas
- Implementar `SnapAssistMenu.show(eligible_windows, zone_rect, quickkeys) -> Optional[int]`: invocar Rofi posicionado dentro del `zone_rect`, mostrar cada ventana con su quickkey destacada, devolver el `window_id` seleccionado o `None`.
- Implementar la congelación de la lista elegible: capturar `eligible_windows` en el momento exacto del primer acoplamiento y pasarla como argumento fijo a todos los menús de zonas vacías subsiguientes, sin releer el estado del sistema.
- Implementar el flujo de zonas vacías en `snap_flow.py`: iterar sobre `get_empty_zones()`, abrir `SnapAssistMenu` para cada una secuencialmente, acoplar la ventana seleccionada, actualizar `State` y `GroupManager`.
- Implementar la política de interrupción involuntaria: si durante el Snap Assist un evento `FocusOut` llega al daemon desde una fuente distinta al proceso Rofi activo, transitar la máquina de estados a IDLE con la política de conservación.
- Implementar la lógica de traslado entre monitores: si la ventana seleccionada está en otro monitor, leer su geometría actual, calcular la zona destino en el monitor activo, ejecutar `move_resize_window`.
- Implementar la lógica de traslado entre workspaces: si la ventana seleccionada está en otro workspace, enviar `_NET_WM_DESKTOP` para moverla al workspace activo antes de acoplarla.
- Escribir tests unitarios para: congelación de lista (agregar una ventana después de congelar no modifica la lista activa), asignación de zonas vacías tras primer acoplamiento en cada template.

### Criterios técnicos de aceptación
- Tras acoplar la primera ventana, el Snap Assist aparece automáticamente en cada zona vacía restante.
- La lista de sugerencias permanece congelada durante todo el flujo (agregar o cerrar una ventana durante el Snap Assist no modifica la lista visible).
- Presionar la quickkey de una ventana la acopla inmediatamente sin necesidad de navegar con flechas.
- Seleccionar una ventana de otro monitor la trae al monitor activo y la acopla correctamente.
- Seleccionar una ventana de otro workspace la mueve al workspace activo y la acopla.
- Esc en cualquier menú de Snap Assist detiene el flujo y conserva las ventanas ya acopladas.
- Una interrupción de foco externo produce el mismo efecto que Esc.

### Pruebas funcionales

**Caso 1 — Flujo completo de dos ventanas**
Abrir Firefox y una terminal en posiciones conocidas. Presionar Super+Z, elegir el template 1:1, acoplar Firefox a la zona izquierda. Esperar el Snap Assist. Seleccionar la terminal con la quickkey correspondiente.

*Resultado esperado:* Firefox ocupa la mitad izquierda y la terminal ocupa la mitad derecha. Ambas ventanas están alineadas sin espacios visibles.

**Caso 2 — Flujo de tres zonas**
Abrir Firefox, terminal, y VSCode. Elegir el template 1/2+1/4+1/4. Acoplar Firefox a la zona grande. Completar el Snap Assist para las dos zonas pequeñas.

*Resultado esperado:* las tres ventanas ocupan las tres zonas del layout sin solapamientos ni espacios.

**Caso 3 — Cancelación a mitad del flujo**
Elegir un template de 3 zonas. Acoplar Firefox a la primera zona. En el Snap Assist de la segunda zona, presionar Esc.

*Resultado esperado:* Firefox permanece en su zona. Las zonas 2 y 3 quedan vacías. No ocurre ninguna acción adicional.

**Caso 4 — Ventana de otro workspace**
Tener una ventana en el workspace 2 mientras el usuario está en el workspace 1. Iniciar el Snap Assist. Seleccionar esa ventana.

*Resultado esperado:* la ventana aparece en el workspace activo acoplada a la zona correcta.

**Caso 5 — Interrupción por notificación**
Durante el Snap Assist, provocar una notificación del sistema (por ejemplo, con `notify-send "test"`).

*Resultado esperado:* el Snap Assist se cierra. Las ventanas ya acopladas conservan su posición. El log registra "flujo interrumpido por pérdida de foco".

---

## Fase 8 — Gestión de Snap Groups

### Objetivo
Implementar la creación, modificación, disolución y consulta de Snap Groups, y el atajo Super+Alt+Tab que trae al frente en bloque todas las ventanas de un grupo.

### Archivos creados o modificados en esta fase
- `snap/group_manager.py` (completo)
- `core/hotkeys.py` (registrar Super+Alt+Tab y Super+/)
- `ui/notifier.py` (extender para overlay de consulta de grupo)

### Tareas
- Implementar `GroupManager.create_group(snapped_map, template, monitor) -> SnapGroup`: generar UUID, construir `SnapGroup`, registrar en `State.active_groups`, aplicar política de pertenencia exclusiva (remover cada ventana de su grupo anterior, aplicar disolución si corresponde).
- Implementar `GroupManager.on_window_destroyed(wid)`: remover de grupo, disolver si queda una sola ventana.
- Implementar `GroupManager.on_window_detached(wid)`: remover de grupo, disolver si corresponde.
- Implementar `GroupManager.get_group_for_window(wid) -> Optional[SnapGroup]`.
- Implementar `GroupManager.validate_group(group_id)`: recorrer `zones`, eliminar referencias a ventanas que ya no existen (verificando contra `get_all_windows()`), disolver si el grupo queda con una sola ventana.
- Implementar el callback de Super+Alt+Tab: obtener la ventana activa, buscar su grupo con `get_group_for_window`, llamar `validate_group`, invocar `WMBackend.focus_window` sobre cada ventana del grupo en orden de `zone_index`.
- Implementar el overlay de consulta de grupo (Super+/): invocar `Notifier` con la lista de títulos de las ventanas del grupo activo.
- Escribir tests unitarios para: `create_group` con ventana ya en otro grupo (pertenencia exclusiva), `on_window_destroyed` con grupo que queda en una sola ventana (disolución), `validate_group` con una referencia inválida.

### Criterios técnicos de aceptación
- Super+Alt+Tab enfocado sobre una ventana de un grupo trae al frente todas las ventanas del grupo.
- Una ventana no puede pertenecer a dos grupos simultáneamente: verificable creando dos layouts con ventanas compartidas.
- Cerrar una ventana de un grupo de dos ventanas disuelve el grupo: la ventana restante vuelve a estado flotante independiente.
- `validate_group` elimina referencias inválidas sin crash: verificable cerrando una ventana externamente durante el ciclo de vida del grupo.
- Todos los tests unitarios pasan.

### Pruebas funcionales

**Caso 1 — Super+Alt+Tab trae el grupo al frente**
Crear un layout con Firefox y Terminal. Enfocar otra ventana fuera del grupo. Presionar Super+Alt+Tab.

*Resultado esperado:* Firefox y Terminal son traídos al frente simultáneamente y el foco queda sobre la ventana principal del grupo.

**Caso 2 — Pertenencia exclusiva**
Crear un layout A con Firefox + Terminal. Luego crear un layout B con Firefox + VSCode.

*Resultado esperado:* Firefox pertenece al grupo B. El grupo A queda con Terminal solamente y se disuelve. Terminal vuelve a estado flotante.

**Caso 3 — Cierre de ventana en grupo**
Crear un layout con Firefox y Terminal. Cerrar Firefox.

*Resultado esperado:* el grupo se disuelve. Terminal permanece en su posición acoplada pero sin pertenecer a ningún grupo. Super+Alt+Tab no tiene efecto sobre ella.

---

## Fase 9 — Casos Borde y Robustez

### Objetivo
Verificar y endurecer el sistema ante los casos borde definidos en el documento de requerimientos: desconexión de monitores, ventanas modales, segunda invocación de Super+Z, cambio de tamaño autónomo de aplicaciones, y el principio de atomicidad bajo condiciones de fallo.

### Archivos modificados en esta fase
- `core/daemon.py`
- `wm/x11_backend.py`
- `snap/snap_flow.py`
- `snap/group_manager.py`

### Tareas
- Implementar detección de desconexión de monitor: suscribirse a eventos `RRScreenChangeNotify` (XRandR); al detectar pérdida de monitor, suspender los grupos asociados en `State.suspended_groups` y descartarlos al reconectar.
- Implementar manejo de ventanas modales en `snap_flow.py`: antes de `move_resize_window`, verificar `get_transient_for(wid)`; si existe una ventana modal activa, mover el padre y centrar la modal sobre él.
- Implementar manejo de error `BadWindow` en `X11Backend.move_resize_window`: capturar la excepción X11, loguear el error, limpiar referencias en `State` y `GroupManager`, retornar `False` al caller.
- Implementar el test de atomicidad: si `move_resize_window` falla en mitad de un flujo multi-ventana, revertir todas las ventanas ya movidas a sus geometrías previas guardadas en `State`.
- Revisar todos los handlers de eventos para verificar que ninguno puede dejar `State` en estado inconsistente si lanza una excepción no capturada. Agregar bloques try/except en el event loop con logging de `ERROR` y continuación del loop.
- Escribir tests unitarios para: revert atómico tras fallo en tercera ventana de un layout de tres, manejo de `BadWindow` sin crash del daemon, handler de `RRScreenChangeNotify`.

### Criterios técnicos de aceptación
- Desconectar un monitor externo durante una sesión activa no crashea el daemon. El log registra la suspensión de grupos.
- Una ventana modal sobre una ventana acoplada se mueve centrada sobre su padre al aplicar el layout.
- Un fallo de `BadWindow` en mitad de un Snap Assist de 3 ventanas revierte las dos ventanas ya movidas a sus geometrías previas.
- El daemon continúa funcionando después de cualquier error no crítico.
- Todos los tests unitarios pasan.

### Pruebas funcionales

**Caso 1 — Ventana modal**
Abrir Firefox con un diálogo de descarga activo. Acoplar Firefox a una zona.

*Resultado esperado:* Firefox se acopla a la zona. El diálogo de descarga se mueve centrado sobre Firefox y no queda huérfano ni oculto.

**Caso 2 — Desconexión de monitor**
Crear un layout en el monitor secundario. Desconectar el monitor físicamente (o desactivarlo con `xrandr --off`).

*Resultado esperado:* el daemon no crashea. El log registra la suspensión del grupo. El monitor primario no se ve afectado.

**Caso 3 — Atomicidad tras fallo**
Simular un fallo de `BadWindow` en la tercera ventana de un layout de tres (cerrando la ventana justo antes de que el daemon la mueva). Verificar el estado de las dos primeras.

*Resultado esperado:* las dos primeras ventanas regresan exactamente a sus posiciones previas. El log registra el fallo y el revert.

---

## Fase 10 — Configurabilidad y Empaquetado

### Objetivo
Hacer el sistema instalable como servicio de usuario, documentar la configuración, y asegurar que el daemon arranca automáticamente con la sesión X11.

### Archivos creados en esta fase
- `install.sh`
- `snapassist.service` (unidad systemd de usuario)
- `README.md`
- `requirements.txt`

### Tareas
- Escribir `requirements.txt` con las versiones exactas de `python-xlib` y `ewmh` verificadas durante el desarrollo.
- Escribir `install.sh`: instalar dependencias con pip, copiar archivos a `~/.local/share/snapassist/`, instalar la unidad systemd en `~/.config/systemd/user/`, habilitar e iniciar el servicio.
- Escribir la unidad systemd con `After=graphical-session.target`, `Restart=on-failure`, `RestartSec=3`, y la variable `DISPLAY=:0`.
- Documentar en `README.md`: requisitos del sistema, instrucciones de instalación, todos los atajos configurables, cómo agregar layouts custom en `config.py`, cómo consultar el log.
- Verificar que el daemon sobrevive el reinicio de sesión: cerrar sesión gráfica y volver a entrar.
- Verificar que el daemon no consume CPU measurable en estado idle: leer `/proc/<pid>/stat` durante 60 segundos sin interacción.

### Criterios técnicos de aceptación
- `bash install.sh` en un Zorin OS limpio instala y activa el servicio sin intervención manual adicional.
- `systemctl --user status snapassist` muestra `active (running)` tras el login.
- El daemon consume menos de 0.1% de CPU en idle (medido con `top` durante 60 segundos).
- El daemon consume menos de 50MB de RAM en estado normal.
- `systemctl --user restart snapassist` reinicia el daemon sin dejar atajos fantasma registrados.

### Pruebas funcionales

**Caso 1 — Arranque automático**
Reiniciar la sesión gráfica de Zorin (cerrar sesión y volver a entrar).

*Resultado esperado:* Super+Z funciona sin ninguna acción manual. `systemctl --user status snapassist` confirma que el proceso está activo.

**Caso 2 — Reinstalación limpia**
Ejecutar `install.sh` sobre una instalación existente del daemon.

*Resultado esperado:* la instalación actualiza los archivos, reinicia el servicio, y el sistema funciona correctamente sin configuración manual adicional.

**Caso 3 — Consumo en idle**
Dejar el daemon corriendo durante 10 minutos sin interacción. Medir CPU y RAM.

*Resultado esperado:* CPU por debajo de 0.1% sostenido. RAM por debajo de 50MB.
```
