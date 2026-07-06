# Arquitectura Técnica: SnapAssist para Linux
**Versión 1.0 — Documento interno de diseño**

---

## 0. Alcance de este Documento

Este documento describe la arquitectura interna del sistema SnapAssist: cómo están organizados sus módulos, qué responsabilidades tiene cada uno, cómo se comunican entre sí, qué librerías utilizan, qué eventos intercambian, cómo está modelado el estado en memoria, cómo se manejan los errores, y cómo se estructura el soporte actual para X11 con vistas a una futura capa de Wayland.

No es un documento de requerimientos funcionales (ese es un documento separado) ni una guía de instalación. Es la referencia de diseño que debe consultarse antes de modificar o extender cualquier módulo.

---

## 1. Visión General del Sistema

SnapAssist es un **daemon de usuario** (proceso en segundo plano que corre en la sesión del usuario, no como root) que:

1. Se subscribe a eventos del servidor X11 para conocer en tiempo real el estado de todas las ventanas del sistema.
2. Captura atajos de teclado globales mediante `XGrabKey` para recibir invocaciones del usuario independientemente de qué aplicación tenga el foco.
3. Mantiene en memoria el estado completo del sistema: historial MRU, geometrías previas, grupos activos, y layouts en curso.
4. Delega la presentación visual al proceso externo `rofi` y a overlays propios dibujados con `tkinter`.
5. Ejecuta operaciones de movimiento y redimensionamiento de ventanas mediante llamadas directas al protocolo X11.

El daemon es el único proceso persistente del sistema. Todo lo demás (Rofi, overlays) se instancia bajo demanda y termina al completar su función.

---

## 2. Estructura del Proyecto

```
snapassist/
│
├── main.py                  # Punto de entrada: inicializa el daemon y el event loop
│
├── core/
│   ├── daemon.py            # Event loop principal, despacho de eventos X11
│   ├── state.py             # Estado global en memoria (MRU, grupos, geometrías)
│   └── hotkeys.py           # Registro y captura de atajos globales (XGrabKey)
│
├── wm/
│   ├── backend.py           # Interfaz abstracta WindowManager (protocolo)
│   ├── x11_backend.py       # Implementación X11 de la interfaz WindowManager
│   └── wayland_backend.py   # Stub vacío para futura implementación Wayland
│
├── layout/
│   ├── engine.py            # Cálculo de zonas: geometría, work area, distribución
│   └── templates.py         # Definición de los layouts preconfigurados
│
├── snap/
│   ├── snap_flow.py         # Orquestador del flujo completo: Super+Z → Snap Assist
│   └── group_manager.py     # Gestión de Snap Groups: creación, disolución, validación
│
├── ui/
│   ├── layout_menu.py       # Menú visual de selección de layouts (Rofi o tkinter)
│   ├── snap_assist_menu.py  # Menú de sugerencias de ventanas en zonas vacías (Rofi)
│   ├── overlay.py           # Overlay semitransparente de zona sobre la pantalla real
│   └── notifier.py          # Notificaciones no intrusivas (notify-send)
│
├── config.py                # Constantes configurables: atajos, umbrales, duraciones
└── themes/
    └── snap_assist.rasi     # Tema Rofi para el menú de Snap Assist
```

### Principio de organización

Los módulos en `core/` y `wm/` no conocen nada de UI. Los módulos en `ui/` no conocen nada del protocolo X11. El módulo `snap/snap_flow.py` es el único que orquesta comunicación entre ambas capas. Esta separación permite sustituir la capa `wm/` por una implementación Wayland sin tocar nada de `ui/` ni de `snap/`.

---

## 3. Responsabilidades de Cada Módulo

### 3.1 `main.py`

Punto de entrada del proceso. Responsabilidades:

- Instanciar el backend de WM correcto según `XDG_SESSION_TYPE` (actualmente siempre X11Backend).
- Instanciar y conectar `State`, `HotkeyManager`, y `Daemon`.
- Iniciar el event loop del daemon.
- Registrar el handler de señales SIGTERM/SIGINT para un apagado limpio.

No contiene lógica de negocio. Es exclusivamente inicialización y wiring.

---

### 3.2 `core/daemon.py`

Es el núcleo del sistema. Contiene el **event loop principal** que escucha eventos X11 de forma bloqueante y los despacha a los handlers correspondientes.

Responsabilidades:

- Seleccionar los eventos X11 relevantes sobre el root window: `SubstructureNotifyMask` (para MapNotify, UnmapNotify, DestroyNotify, ConfigureNotify) y `PropertyChangeMask` (para cambios en `_NET_ACTIVE_WINDOW`).
- Despachar cada evento al handler correcto dentro del mismo módulo.
- Invocar `State.update_mru()` al detectar cambio de ventana activa.
- Invocar `GroupManager.on_window_destroyed()` al detectar `DestroyNotify`.
- Invocar `GroupManager.on_window_resized()` al detectar `ConfigureNotify` sobre una ventana acoplada.
- Invocar `SnapFlow.invoke()` al detectar activación del atajo Super+Z.

El event loop **no realiza ninguna operación de movimiento de ventanas ni de UI directamente**. Solo despacha. La lógica pertenece a los módulos especializados.

---

### 3.3 `core/state.py`

Contiene el estado global en memoria del sistema. Es un singleton accesible por todos los módulos. No tiene lógica de negocio; es exclusivamente almacenamiento y consulta.

Responsabilidades:

- Mantener la lista ordenada MRU de `window_id` según recencia de enfoque.
- Mantener el buffer de geometrías previas: `Dict[int, WindowGeometry]`.
- Mantener el registro de ventanas actualmente acopladas: `Dict[int, ZoneRef]` donde `ZoneRef` contiene el `group_id` y el índice de zona.
- Exponer métodos de lectura y escritura con nombres semánticamente claros: `get_mru_list()`, `save_geometry(wid, geom)`, `restore_geometry(wid)`, `mark_snapped(wid, zone_ref)`, `unmark_snapped(wid)`.

No persiste nada a disco.

---

### 3.4 `core/hotkeys.py`

Responsable del registro y captura de atajos globales mediante `XGrabKey`.

`XGrabKey` es una llamada del protocolo X11 que instruye al servidor X a redirigir al proceso registrante los eventos de teclado correspondientes a una combinación de tecla+modificadores, independientemente de qué ventana tenga el foco en ese momento. Esto es lo que permite al daemon interceptar Super+Z aunque el usuario esté dentro de un navegador o un editor.

Responsabilidades:

- Registrar todos los atajos definidos en `config.py` al iniciar el daemon.
- Escuchar eventos `KeyPress` en el root window.
- Al detectar un `KeyPress` que coincida con un atajo registrado, invocar el callback correspondiente.
- Desregistrar todos los atajos (`XUngrabKey`) al apagar el daemon.

---

### 3.5 `wm/backend.py`

Define la **interfaz abstracta** `WindowManager` usando `abc.ABC` y `abc.abstractmethod`. Todos los módulos del sistema que necesiten interactuar con ventanas importan esta interfaz, nunca la implementación concreta.

Métodos abstractos que define:

```python
def get_active_window(self) -> Optional[int]: ...
def get_all_windows(self) -> List[int]: ...
def get_window_geometry(self, wid: int) -> WindowGeometry: ...
def get_window_title(self, wid: int) -> str: ...
def get_window_type(self, wid: int) -> WindowType: ...
def get_window_state(self, wid: int) -> WindowState: ...
def get_work_area(self, monitor_index: int) -> Rect: ...
def get_monitor_for_window(self, wid: int) -> int: ...
def move_resize_window(self, wid: int, rect: Rect) -> None: ...
def focus_window(self, wid: int) -> None: ...
def get_transient_for(self, wid: int) -> Optional[int]: ...
def subscribe_events(self, handler: Callable[[XEvent], None]) -> None: ...
```

Esta interfaz es el contrato que debe cumplir cualquier backend futuro (Wayland).

---

### 3.6 `wm/x11_backend.py`

Implementación concreta de `WindowManager` para X11 usando `python-xlib` y `ewmh`.

Responsabilidades concretas:

- Conectarse al servidor X al instanciarse (`Display()`).
- Implementar cada método abstracto usando los átomos EWMH correspondientes:
  - `get_all_windows()` → `_NET_CLIENT_LIST`
  - `get_work_area()` → `_NET_WORKAREA`
  - `get_window_type()` → `_NET_WM_WINDOW_TYPE`
  - `get_window_state()` → `_NET_WM_STATE`
  - `get_transient_for()` → `WM_TRANSIENT_FOR`
  - `move_resize_window()` → `XMoveResizeWindow` + `_NET_MOVERESIZE_WINDOW`
- Filtrar ventanas no elegibles en `get_all_windows()` aplicando las condiciones de la sección 15 del documento de requerimientos.

---

### 3.7 `wm/wayland_backend.py`

Stub que implementa la interfaz `WindowManager` con métodos que lanzan `NotImplementedError`. Su propósito en v1 es documentar el punto de extensión futuro y permitir que el sistema compile y arranque bajo Wayland con un error explícito y legible en lugar de un crash por importación fallida.

En una versión futura, esta implementación usará el protocolo `wlr-foreign-toplevel-management` para compositores wlroots, o la API D-Bus de KWin para KDE Plasma en Wayland.

---

### 3.8 `layout/engine.py`

Módulo de cálculo puro. No tiene efectos secundarios sobre el estado ni sobre las ventanas. Dado un layout template y el `Rect` del work area de un monitor, produce las geometrías exactas en píxeles de cada zona.

Responsabilidades:

- Calcular `Rect` de cada zona a partir de las proporciones del template y las dimensiones del work area.
- Identificar zonas vacías dado el conjunto de zonas ya ocupadas.
- Calcular la posición de centrado para ventanas con restricciones de tamaño mínimo (comportamiento "Ignorar y Centrar").

Es un módulo de funciones puras: `calculate_zones(template, work_area) -> List[Rect]`.

---

### 3.9 `layout/templates.py`

Define los layouts preconfigurados como estructuras de datos, no como código imperativo.

Cada template es una lista de zonas expresadas en proporciones relativas (flotantes entre 0 y 1) respecto al work area. El engine convierte esas proporciones a píxeles absolutos en tiempo de ejecución.

```python
@dataclass
class ZoneTemplate:
    x: float      # fracción del ancho total
    y: float      # fracción del alto total
    w: float      # fracción del ancho total
    h: float      # fracción del alto total

@dataclass
class LayoutTemplate:
    name: str
    zones: List[ZoneTemplate]

TEMPLATES = [
    LayoutTemplate("1:1", [
        ZoneTemplate(0.0, 0.0, 0.5, 1.0),
        ZoneTemplate(0.5, 0.0, 0.5, 1.0),
    ]),
    LayoutTemplate("2/3 + 1/3", [
        ZoneTemplate(0.0, 0.0, 0.667, 1.0),
        ZoneTemplate(0.667, 0.0, 0.333, 1.0),
    ]),
    LayoutTemplate("1/2 + 1/4 + 1/4", [
        ZoneTemplate(0.0,   0.0, 0.5,  1.0),
        ZoneTemplate(0.5,   0.0, 0.25, 0.5),
        ZoneTemplate(0.5,   0.5, 0.25, 0.5),
        ZoneTemplate(0.75,  0.0, 0.25, 0.5),
        ZoneTemplate(0.75,  0.5, 0.25, 0.5),
    ]),
    # ... más templates definidos en config.py
]
```

---

### 3.10 `snap/snap_flow.py`

Orquestador del flujo completo desde la invocación de Super+Z hasta la finalización del Snap Assist. Es el módulo con más lógica de control de flujo del sistema.

Responsabilidades:

- Al recibir invocación de Super+Z: validar que existe una ventana activa elegible, abrir el menú de layouts, esperar selección.
- Al recibir selección de layout y zona: guardar geometría previa en State, calcular rect de zona, ejecutar `move_resize_window`, registrar la ventana como acoplada.
- Iniciar el Snap Assist: congelar la lista de ventanas elegibles, calcular zonas vacías, abrir el menú de Snap Assist en cada zona vacía secuencialmente.
- Al recibir selección de ventana en Snap Assist: guardar geometría previa, ejecutar `move_resize_window`, actualizar GroupManager.
- Al recibir Esc o interrupción involuntaria: terminar el flujo respetando las ventanas ya acopladas.

Implementa el flujo como una **máquina de estados explícita** con los estados:

```
IDLE → LAYOUT_MENU_OPEN → ZONE_SELECTED →
SNAP_ASSIST_OPEN → SNAP_ASSIST_COMPLETE → IDLE
```

Cualquier interrupción (Esc, pérdida de foco, señal externa) desde cualquier estado transita directamente a IDLE aplicando la política de conservación definida en los requerimientos.

---

### 3.11 `snap/group_manager.py`

Gestiona el ciclo de vida de los Snap Groups: creación, modificación, consulta y disolución.

Responsabilidades:

- Crear un grupo nuevo al completarse un layout (asignar `group_id` UUID).
- Registrar qué ventanas pertenecen a qué grupo y en qué zona.
- Aplicar la política de pertenencia exclusiva: al acoplar una ventana ya perteneciente a un grupo, removerla del grupo anterior y aplicar la regla de disolución si el grupo queda con una sola ventana.
- Responder a eventos de cierre de ventana (`on_window_destroyed`) y resize externo (`on_window_resized`) actualizando el estado de grupos.
- Exponer `get_group_for_window(wid) -> Optional[SnapGroup]` y `get_all_windows_in_group(group_id) -> List[int]` para el módulo de Snap Groups.
- Aplicar validación de referencias al ejecutar Super+Alt+Tab: descartar silenciosamente `window_id` que ya no existen.

---

### 3.12 `ui/layout_menu.py`

Gestiona la presentación del menú de selección de layouts (invocado por Super+Z).

En v1 implementa el menú mediante Rofi con un tema custom. La interfaz del módulo es independiente de Rofi: recibe una lista de `LayoutTemplate` y devuelve el template seleccionado y la zona seleccionada, o `None` si el flujo fue cancelado.

Internamente lanza Rofi como subproceso, captura su salida por stdout, y parsea la selección.

---

### 3.13 `ui/snap_assist_menu.py`

Gestiona la presentación del menú de sugerencias de ventanas dentro de una zona vacía.

Recibe la lista congelada de ventanas elegibles (ya ordenada por MRU desde `State`), la zona (un `Rect` en coordenadas absolutas de pantalla), y las teclas de acceso rápido asignadas desde `config.py`.

Lanza Rofi posicionado dentro de la zona vacía con las teclas de acceso rápido visibles junto al nombre de cada ventana. Devuelve el `window_id` seleccionado o `None` si fue cancelado.

---

### 3.14 `ui/overlay.py`

Dibuja el overlay semitransparente sobre la zona destacada durante la navegación en el menú de layouts.

Implementado como una ventana `tkinter` sin decoraciones, sin borde, con fondo de color semitransparente, posicionada sobre las coordenadas del `Rect` de zona correspondiente. Se instancia y destruye en cada ciclo de navegación.

En X11, la transparencia se habilita mediante el átomo `_NET_WM_WINDOW_TYPE_SPLASH` y la propiedad de opacidad `_NET_WM_WINDOW_OPACITY`.

---

### 3.15 `ui/notifier.py`

Wrapper sobre `notify-send` para emitir notificaciones no intrusivas al usuario (por ejemplo, cuando Super+Z es invocado sin ventana activa elegible). Lanza `notify-send` como subproceso con un timeout corto.

---

### 3.16 `config.py`

Archivo de configuración central. Contiene todas las constantes modificables por el usuario sin tocar código de lógica:

```python
HOTKEY_LAYOUT_MENU     = "super+z"
HOTKEY_SNAP_GROUPS     = "super+alt+tab"
HOTKEY_HELP            = "super+slash"
SNAP_ANIMATION_MS      = 200       # duración de transición post-acoplamiento
DRAG_THRESHOLD_PX      = 8         # umbral de desacoplamiento por mouse
QUICKKEY_SEQUENCE      = "qwertyu" # teclas de acceso rápido en Snap Assist
OVERLAY_OPACITY        = 0.35      # opacidad del overlay de zona (0.0 - 1.0)
LAYOUT_TEMPLATES       = [...]     # lista de LayoutTemplate activos
```

---

## 4. Modelo de Datos

### 4.1 Tipos base

```python
@dataclass
class Rect:
    x: int
    y: int
    w: int
    h: int

@dataclass
class WindowGeometry:
    rect: Rect
    is_maximized: bool

@dataclass
class ZoneRef:
    group_id: str       # UUID del grupo
    zone_index: int     # índice de zona dentro del layout del grupo

@dataclass
class SnapGroup:
    group_id: str
    template: LayoutTemplate
    monitor_index: int
    zones: Dict[int, int]   # zone_index → window_id
                            # (solo zonas ocupadas; zonas vacías no aparecen)

class WindowType(Enum):
    NORMAL = "normal"
    DIALOG = "dialog"
    SPLASH = "splash"
    DOCK   = "dock"
    OTHER  = "other"

class WindowState(Enum):
    NORMAL      = "normal"
    MINIMIZED   = "minimized"
    MAXIMIZED   = "maximized"
    FULLSCREEN  = "fullscreen"
    ALWAYS_TOP  = "always_top"
```

### 4.2 Estado global en `State`

```python
class State:
    # Lista de window_id ordenada por recencia de foco (índice 0 = más reciente)
    mru_list: List[int]

    # Geometrías previas al acoplamiento, indexadas por window_id
    saved_geometries: Dict[int, WindowGeometry]

    # Referencia de zona para cada ventana actualmente acoplada
    snapped_windows: Dict[int, ZoneRef]

    # Todos los grupos activos, indexados por group_id
    active_groups: Dict[str, SnapGroup]

    # Grupos suspendidos por desconexión de monitor, indexados por monitor_index
    suspended_groups: Dict[int, List[SnapGroup]]
```

Ningún campo de `State` se serializa a disco. Todo se inicializa vacío al arrancar el daemon.

---

## 5. Eventos que Intercambian los Módulos

El sistema no usa un bus de mensajes interno formal. La comunicación entre módulos es por **llamadas directas** (el daemon llama a métodos del GroupManager, el SnapFlow llama al LayoutEngine, etc.). Lo que sí existe es un flujo de eventos X11 que el daemon recibe y despacha.

### 5.1 Eventos X11 consumidos por el daemon

| Evento X11 | Condición de interés | Acción despachada |
|---|---|---|
| `PropertyNotify` sobre `_NET_ACTIVE_WINDOW` | Siempre | `State.update_mru(new_active_wid)` |
| `DestroyNotify` | La ventana destruida está en `State.snapped_windows` | `GroupManager.on_window_destroyed(wid)` |
| `ConfigureNotify` | La ventana reconfigurada está en `State.snapped_windows` Y el resize no fue iniciado por el daemon | `GroupManager.on_window_resized(wid)` |
| `MapNotify` | Siempre | Actualizar caché interno de ventanas visibles |
| `UnmapNotify` | Siempre | Actualizar caché interno de ventanas visibles |
| `KeyPress` | El keycode coincide con un atajo registrado | Callback del `HotkeyManager` correspondiente |

### 5.2 Distinción entre resize propio y resize externo

Para que `ConfigureNotify` no dispare un desacoplamiento cuando es el propio daemon el que mueve una ventana, el daemon mantiene un `Set[int]` llamado `_pending_own_resizes` con los `window_id` sobre los que acaba de ejecutar `move_resize_window`. Al recibir `ConfigureNotify`, si el `wid` está en ese set, el evento se ignora y se remueve del set. Si no está, se trata como resize externo.

### 5.3 Flujo de invocación Super+Z (secuencia de llamadas)

```
HotkeyManager.on_keypress(Super+Z)
  → SnapFlow.invoke()
    → WMBackend.get_active_window()          # ¿hay ventana activa?
    → WMBackend.get_monitor_for_window(wid)  # ¿en qué monitor?
    → WMBackend.get_work_area(monitor)       # dimensiones del work area
    → LayoutEngine.calculate_zones(template, work_area)
    → UI.LayoutMenu.show(templates)          # bloqueante: espera selección
    → [si selección válida]:
        State.save_geometry(wid, current_geom)
        WMBackend.move_resize_window(wid, zone_rect)
        State.mark_snapped(wid, zone_ref)
        SnapFlow._start_snap_assist(empty_zones)

SnapFlow._start_snap_assist(empty_zones):
  → eligible = WMBackend.get_all_windows()   # lista congelada aquí
  → eligible = filter_and_sort_mru(eligible) # aplica State.mru_list
  → for each empty_zone:
      → UI.SnapAssistMenu.show(eligible, zone_rect)  # bloqueante
      → [si selección válida]:
          State.save_geometry(selected_wid, geom)
          WMBackend.move_resize_window(selected_wid, zone_rect)
          State.mark_snapped(selected_wid, zone_ref)
  → GroupManager.create_or_update_group(all_snapped_wids, template, monitor)
```

---

## 6. Manejo de Errores

### 6.1 Principio base

Todo error en una operación de acoplamiento debe preservar el estado previo completo. Ningún error debe dejar ventanas en geometría inconsistente ni grupos con referencias inválidas. Esto es la aplicación directa del principio de atomicidad del documento de requerimientos.

### 6.2 Clasificación de errores y respuesta

| Tipo de error | Ejemplo concreto | Respuesta |
|---|---|---|
| Ventana desaparecida entre consulta y operación | `move_resize_window` lanza `BadWindow` | Capturar excepción X11, abortar la operación de esa ventana, limpiar referencias en State y GroupManager, continuar el flujo si hay más zonas pendientes |
| Rofi terminado por el usuario (Esc) | Código de salida 1 de Rofi | Tratar como cancelación limpia, aplicar política de preservación de ventanas ya acopladas |
| Rofi no encontrado en el sistema | `FileNotFoundError` al hacer `subprocess.run` | Loguear error crítico, emitir notificación al usuario via `notifier.py`, abortar flujo completo sin modificar ninguna ventana |
| Backend WM no disponible | `Display()` lanza `error.DisplayConnectionError` | Terminar el daemon con mensaje de error claro en stderr. Sin servidor X no hay nada que hacer |
| ConfigureNotify en ventana ya destruida | Race condition entre DestroyNotify y ConfigureNotify | Verificar existencia del wid en `State.snapped_windows` antes de procesar; si no existe, ignorar silenciosamente |
| Error en cálculo de zona (división por cero en work area vacío) | Monitor con work area de 0px de alto | Loguear warning, abortar flujo, no modificar ninguna ventana |

### 6.3 Logging

El daemon escribe a un archivo de log en `~/.local/share/snapassist/daemon.log` con rotación diaria. Niveles usados:

- `DEBUG`: cada evento X11 recibido, cada llamada a `move_resize_window`.
- `INFO`: invocaciones de atajos, creación y disolución de grupos, acoplamientos completados.
- `WARNING`: casos borde no fatales (ventana con tamaño mínimo, ConfigureNotify ignorado).
- `ERROR`: operaciones fallidas por errores X11, Rofi no encontrado, referencias inválidas.
- `CRITICAL`: condiciones que impiden el funcionamiento del daemon (sin servidor X, sin work area).

---

## 7. Soporte X11 y Ruta a Wayland

### 7.1 Estado actual: X11

Toda la implementación concreta de acceso a ventanas reside en `wm/x11_backend.py`. El resto del sistema interactúa únicamente con la interfaz abstracta `WindowManager`. Esta separación es deliberada y es el mecanismo que hace posible agregar soporte Wayland sin refactorizar la lógica de negocio.

Las operaciones X11 utilizadas y sus equivalentes conceptuales:

| Operación | X11 (v1) | Wayland futuro |
|---|---|---|
| Listar ventanas | `_NET_CLIENT_LIST` | `wlr-foreign-toplevel-management` / KWin D-Bus |
| Ventana activa | `_NET_ACTIVE_WINDOW` | `wlr-foreign-toplevel-management` / `ext-foreign-toplevel-list-v1` |
| Mover y redimensionar | `XMoveResizeWindow` + `_NET_MOVERESIZE_WINDOW` | Protocolo específico del compositor (no estandarizado aún) |
| Tipo de ventana | `_NET_WM_WINDOW_TYPE` | Roles de superficie xdg-shell |
| Jerarquía modal | `WM_TRANSIENT_FOR` | `xdg_popup` parent / `xdg_toplevel set_parent` |
| Captura global de teclado | `XGrabKey` sobre root window | Sin estándar; requiere extensión del compositor o `wlr-input-inhibit` |
| Work area | `_NET_WORKAREA` | `xdg-output-unstable-v1` + geometría de paneles por compositor |
| Eventos de ventana | `SubstructureNotifyMask` sobre root | Listeners del protocolo foreign-toplevel |

### 7.2 El problema central de Wayland

Wayland no tiene un equivalente de `XGrabKey` que funcione de forma universal. La captura global de atajos de teclado en Wayland requiere uno de los siguientes mecanismos, ninguno estandarizado entre compositores:

- **wlr-input-inhibit-unstable-v1**: solo wlroots (Hyprland, Sway).
- **KDE Global Shortcuts (D-Bus)**: solo KWin/Plasma.
- **GNOME Extension API**: solo GNOME Shell.
- **`org.freedesktop.portal.GlobalShortcuts`** (XDG Portal): el más prometedor como estándar futuro, disponible desde GNOME 43 y KDE Plasma 5.27.

La ruta más pragmática para Wayland es implementar `wm/wayland_backend.py` usando XDG Portals para atajos globales y `wlr-foreign-toplevel-management` para gestión de ventanas, lo que cubriría Hyprland, Sway, y parcialmente KDE sin soporte de GNOME. GNOME en Wayland requeriría una extensión Shell separada.

### 7.3 Detección del entorno en `main.py`

```python
session_type = os.environ.get("XDG_SESSION_TYPE", "x11").lower()

if session_type == "x11":
    from wm.x11_backend import X11Backend
    wm_backend = X11Backend()
elif session_type == "wayland":
    from wm.wayland_backend import WaylandBackend
    wm_backend = WaylandBackend()   # lanza NotImplementedError con mensaje claro
else:
    sys.exit("SnapAssist: entorno de display no reconocido.")
```

---

## 8. Diagrama de Componentes

```
┌─────────────────────────────────────────────────────────────────────┐
│                        PROCESO DAEMON                               │
│                                                                     │
│  ┌──────────────┐     eventos X11      ┌────────────────────────┐  │
│  │  core/       │ ◄─────────────────── │  Servidor X11          │  │
│  │  daemon.py   │                      │  (proceso externo)      │  │
│  │              │ ──────────────────►  │                        │  │
│  │  (event loop)│   XMoveResizeWindow  └────────────────────────┘  │
│  └──────┬───────┘                                                   │
│         │ despacha                                                   │
│         ▼                                                            │
│  ┌──────────────┐    ┌──────────────┐    ┌────────────────────┐    │
│  │  core/       │    │  core/       │    │  core/             │    │
│  │  hotkeys.py  │    │  state.py    │    │  hotkeys.py        │    │
│  └──────────────┘    └──────┬───────┘    └────────────────────┘    │
│                             │                                        │
│                             │ lee/escribe                            │
│                             ▼                                        │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                    snap/snap_flow.py                         │   │
│  │                  (máquina de estados)                        │   │
│  └───┬───────────────┬──────────────────┬───────────────────────┘   │
│      │               │                  │                            │
│      ▼               ▼                  ▼                            │
│  ┌────────┐  ┌──────────────┐  ┌──────────────────┐                │
│  │layout/ │  │snap/         │  │wm/               │                │
│  │engine  │  │group_manager │  │backend.py        │                │
│  │.py     │  │.py           │  │(interfaz abstracta)│              │
│  └────────┘  └──────────────┘  └────────┬─────────┘                │
│                                          │                           │
│                               ┌──────────┴──────────┐               │
│                               ▼                     ▼               │
│                        ┌────────────┐      ┌──────────────┐         │
│                        │x11_backend │      │wayland_backend│        │
│                        │.py (activo)│      │.py (stub v1) │         │
│                        └────────────┘      └──────────────┘         │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                        ui/                                   │   │
│  │  layout_menu.py │ snap_assist_menu.py │ overlay.py │         │   │
│  │  notifier.py                                                 │   │
│  └──────────────┬───────────────────────────────────────────────┘   │
│                 │                                                    │
└─────────────────┼────────────────────────────────────────────────── ┘
                  │ subprocesos
                  ▼
        ┌──────────────────┐
        │  Rofi (externo)  │
        │  tkinter overlay │
        │  notify-send     │
        └──────────────────┘
```

---

## 9. Dependencias del Sistema

### Librerías Python (instalables vía pip)

| Librería | Versión mínima | Uso |
|---|---|---|
| `python-xlib` | 0.33 | Protocolo X11: eventos, átomos, XGrabKey, XMoveResizeWindow |
| `ewmh` | 0.1.6 | Wrapper de átomos EWMH sobre python-xlib |
| `python-xlib` incluye `Xlib.display` | — | Conexión al servidor X |

### Herramientas del sistema (deben estar instaladas)

| Herramienta | Uso |
|---|---|
| `rofi` | Menú de layouts y Snap Assist |
| `notify-send` (libnotify) | Notificaciones no intrusivas |
| `python3` ≥ 3.11 | Runtime del daemon |

### Librería estándar Python usada

`subprocess`, `os`, `sys`, `abc`, `dataclasses`, `enum`, `typing`, `uuid`, `logging`, `logging.handlers`, `signal`, `threading` (para el overlay tkinter en hilo separado).

---

## 10. Ejecución y Ciclo de Vida

El daemon se inicia como servicio de usuario mediante systemd:

```ini
# ~/.config/systemd/user/snapassist.service
[Unit]
Description=SnapAssist Window Manager Daemon
After=graphical-session.target

[Service]
ExecStart=/usr/bin/python3 /opt/snapassist/main.py
Restart=on-failure
RestartSec=3
Environment=DISPLAY=:0

[Install]
WantedBy=graphical-session.target
```

Al arrancar, el daemon: conecta al servidor X → registra eventos sobre el root window → registra atajos globales → entra en el event loop bloqueante.

Al recibir SIGTERM o SIGINT: desregistra todos los atajos (`XUngrabKey`) → cierra la conexión X → termina limpiamente sin dejar ninguna ventana en estado inconsistente.
```
