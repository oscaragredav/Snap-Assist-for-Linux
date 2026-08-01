# Informe exhaustivo de QA — SnapAssist Linux

**Fecha:** 2026-07-31  
**Revisión evaluada:** `fcdef2a` (`main`)  
**Alcance:** fases 1–9  
**Regla de esta revisión:** documentar defectos y planes de acción; no modificar el código del producto.

> Nota de seguimiento (2026-07-31): el informe anterior conserva la evidencia
> original. La implementación posterior aplicó y automatizó las correcciones
> siguientes; los estados de abajo sustituyen el veredicto histórico.

## Seguimiento de remediación

| ID | Estado posterior | Validación automatizada |
|---|---|---|
| QA-002 | Corregido | `/tmp/snapassist_qa_ssd.py`: 5 ciclos X11 reales sin deriva. |
| QA-001 | Mitigado y acotado | `/tmp/snapassist_qa_terminal.py`: zonas CSD y restauración; diferencia máxima del cliente medida: 4 px, sin bucles. |
| QA-003 | Corregido | `test_qa_regressions.py`: conserva más de 10 candidatos; UI con `Listbox`, scrollbar y contador. |
| QA-004 | Corregido | Inyección de fallo UI: cancelación/rollback atómico. |
| QA-009 | Corregido | Cancelación parcial conserva `ZoneRef(group_id=None)`, sin UUID huérfano. |
| QA-006/007 | Corregido | Rechazo de activa no elegible y work area 0×0. |
| QA-008 | Corregido | Sólo se desacopla un drag cuando la geometría confirma desplazamiento. |
| QA-005 | Corregido como política segura | Tamaño mínimo se limita al work area para conservar accesibilidad. |
| QA-010 | Corregido | Cálculo por `_NET_WM_STRUT_PARTIAL` y prueba de reserva sólo en su monitor. |
| QA-011 | Corregido | La ayuda declara explícitamente `Daemon: activo`. |
| QA-012 | Corregido | README, arquitectura y plan actualizados a Tkinter/pynput y logs actuales. |
| QA-013 | Corregido | `tests/run_all.py`, `test_phase4.py` y regresiones QA se ejecutan como gate. |

La tolerancia de QA-001 no se presenta como una geometría exacta: una GNOME
Terminal CSD puede rechazar cuatro píxeles verticales aun sin `PResizeInc`.
SnapAssist evita las derivas grandes, conserva el resultado verificable y no
entra en un ciclo de corrección. Cualquier diferencia superior a esa tolerancia
queda como advertencia diagnóstica.

## 1. Veredicto ejecutivo

La base funcional es estable en las rutas transaccionales y de grupos, pero la
versión evaluada **no está lista para considerarse cerrada en QA**. El bloqueo
principal es la geometría real: una Terminal todavía puede dejar huecos de 4 a
7 px según la zona, y las aplicaciones con decoraciones administradas por el
gestor de ventanas (SSD) acumulan un desplazamiento real al restaurarse.

Se registraron:

- **4 hallazgos de severidad alta**.
- **7 hallazgos de severidad media**.
- **2 hallazgos de severidad baja**.
- **0 crashes o errores nuevos** en `errors.log` durante esta ejecución.

Los puntos más sólidos fueron la atomicidad, la serialización de cancelaciones,
las invariantes de Snap Groups, la matemática de layouts, la detección de dos
monitores y el apagado limpio.

## 2. Entorno y metodología

### 2.1 Entorno

| Elemento | Valor |
|---|---|
| SO/kernel | Linux 7.0.0-28-generic x86_64 |
| Escritorio | Zorin / GNOME |
| Sesión | X11 (`DISPLAY=:1`) |
| Python | 3.12.3 |
| python-xlib | 0.33 |
| pynput | 1.8.2 |
| Pantallas | 2 × 1920×1080, escritorio virtual 3840×1080 |
| Xinerama | Monitor 0: 1920,0; monitor 1: 0,0 |
| `_NET_WORKAREA` | 0,0,3840,1036 |

### 2.2 Capas de prueba

1. Revisión de `Requerimientos.md`, `plan_implementacion.md`,
   `arquitectura_tecnica.md` y `README.md`.
2. Ejecución de las pruebas oficiales de las fases 1–9.
3. Pruebas de contrato adicionales con mocks y estados adversos.
4. Estrés determinista de grupos y cancelaciones.
5. Pruebas reales X11 con ventanas desechables `SnapQA-*`.
6. Prueba real con una instancia desechable de GNOME Terminal.
7. Inspección no destructiva de Firefox, VS Code, Terminal, Archivos,
   WhatsApp, Helium, Editor de texto y Flatseal.
8. Revisión de los logs históricos y del apagado controlado del daemon.

No se cerró ni modificó ninguna aplicación real del usuario. Las ventanas de
prueba fueron restauradas o cerradas al finalizar.

## 3. Resumen de resultados

### 3.1 Pruebas oficiales

| Suite | Resultado |
|---|---:|
| Fase 1 | 10/10 |
| Fase 2 | 6/6 |
| Fase 3 | 3/3 |
| Fase 5 | 6/6 |
| Fase 6 | 4/4 |
| Fase 7 | 7/7 |
| Fase 8 | 9/9 |
| Fase 9 | 9/9 |
| **Total** | **54/54** |

También pasaron:

- `pip check`: sin dependencias rotas.
- Compilación de los 33 archivos Python del proyecto.
- `git diff --check`.
- Seis layouts sobre áreas 1920×1036, 1919×1001 con coordenada negativa y
  1365×727: cobertura exacta, sin huecos matemáticos ni solapes.
- Animación: 201.19 ms y posición final exacta, dentro del rango 150–250 ms.
- 500 operaciones aleatorias de creación, reasignación y disolución de grupos:
  ninguna pertenencia duplicada ni referencia inválida durante esas operaciones.
- Rollback inyectando fallo en cada uno de los cinco movimientos posibles de un
  flujo 2×2: geometría y `State` restaurados en todos los casos.
- Fallo al mover una modal: padre y modal restaurados.
- 200 ciclos `Esc → Super+Z → callback obsoleto`: sin bloqueo ni cancelación del
  flujo nuevo.
- Una sola señal `SIGINT`: listeners, event loop, UI y conexión X11 terminaron
  limpiamente.

### 3.2 Cobertura de las pruebas oficiales

La medición con `trace` dio **1333/2674 líneas importadas ejecutadas (49.9%)**.
La cifra real global es menor porque `snap_assist_menu.py` y `overlay.py` ni
siquiera fueron importados por las suites oficiales.

| Módulo relevante | Cobertura oficial aproximada |
|---|---:|
| `snap_flow.py` | 85.3% |
| `group_manager.py` | 90.0% |
| `snapper.py` | 98.8% |
| `daemon.py` | 54.3% |
| `hotkeys.py` | 56.5% |
| `layout_menu.py` | 22.0% |
| `ui_manager.py` | 28.0% |
| `x11_backend.py` | 17.0% |
| `main.py` | 11.1% |

### 3.3 Trazabilidad de requisitos

| Sección de requisitos | Estado | Evidencia principal |
|---|---|---|
| 1. Control por teclado | Parcial | Navegación numérica y flechas pasan; atajo físico global no fue automatizable de forma fiable. |
| 2. Ventanas flotantes | Conforme | No existe tiling automático. |
| 3. Work area | Parcial | Intersección global funciona; no modela reservas distintas por monitor. |
| 4. Estado volátil | Conforme | Estado en memoria, sin persistencia. |
| 5. Menú de layouts | Parcial | Los seis layouts son visibles; falta validar elegibilidad de la activa y work area vacío. |
| 6. Snap Assist | No conforme | La lista se trunca a diez y el décimo renglón queda recortado. |
| 7–9. Snap Groups | Conforme con observación | Invariantes y disolución pasan; cancelación con un solo miembro deja una referencia huérfana. |
| 10–12. Resize/restauración | No conforme | Terminal deja huecos; SSD deriva 36 px; heurística de barra de título es demasiado amplia. |
| 13. Tamaño mínimo | Parcial | Conserva mínimo, pero Mutter impide el desborde simétrico superior. |
| 14. Modales | Parcial | Rollback pasa; la geometría SSD incorrecta afecta el centrado y restauración. |
| 15. Elegibilidad | Parcial | Minimizadas y filtros pasan; la ventana activa no se revalida. |
| 16–18. Monitores | Conforme con riesgo | Asignación, traslado mock y suspensión/reconexión pasan; work area por monitor queda pendiente. |
| 19. Traer grupo al frente | Conforme | Validación y orden de foco pasan. |
| 20. Ayuda | Parcial | Lista atajos y contadores, pero omite el estado explícito activo/inactivo. |

## 4. Hallazgos y planes de acción

### QA-001 — La Terminal todavía no llena exactamente algunas zonas

**Severidad:** Alta  
**Tipo:** Funcional / UX  
**Estado:** Reproducido en X11 real

Con una GNOME Terminal desechable y las restricciones ICCCM suspendidas:

| Layout/zona | Esperado | Obtenido | Diferencia |
|---|---:|---:|---:|
| 1:1 izquierda | 960×1036 | 960×1036 | 0×0 |
| 2/3+1/3 derecha | 639×1036 | 632×1036 | **−7×0** |
| 2×2 superior derecha | 960×518 | 960×514 | **0×−4** |
| 1/2+1/4+1/4 inferior | 960×518 | 960×518 | 0×0 |
| 1:1:1 centro | 642×1036 | 640×1036 | −2×0 |

`prepare_window_for_snap()` elimina `PResizeInc`, pero la ventana o Mutter aún
normalizan ciertos tamaños. Una petición X11 aceptada no garantiza que la
geometría final sea la solicitada.

**Plan de acción:**

1. Añadir una fase de verificación después de que el WM confirme el
   `ConfigureNotify` final.
2. Comparar destino y geometría visible real; si el delta supera ±1 px, aplicar
   una corrección limitada y volver a verificar.
3. Esperar la confirmación de cambio de `WM_NORMAL_HINTS` antes del primer resize.
4. Guardar por ventana la relación entre tamaño solicitado y aceptado para no
   repetir oscilaciones durante una animación.
5. Si una aplicación rechaza la corrección tras un número acotado de intentos,
   aplicar explícitamente la política de tamaño mínimo/compatibilidad y loguear
   el motivo, sin declarar el snap como exacto.

**Pruebas de regresión/aceptación:** las 16 zonas deben quedar en ±1 px en
Terminal, Firefox, Electron, GTK, Qt y Tk; no debe existir un ciclo infinito de
correcciones.

### QA-002 — Las decoraciones SSD provocan deriva de 36 px al restaurar

**Severidad:** Alta  
**Tipo:** Funcional / compatibilidad  
**Estado:** Reproducido en X11 real

Una ventana Tk administrada por Mutter declaró
`_NET_FRAME_EXTENTS=[0,0,36,0]`. SnapAssist sólo consulta
`_GTK_FRAME_EXTENTS`. Resultado del ciclo real:

- Lectura original: `[2100,216,700,500]`.
- Lectura tras snap: `[1920,36,960,1000]` para destino `[1920,0,960,1036]`.
- Lectura tras restaurar: `[2100,252,700,500]`.
- **Deriva acumulada: +36 px en Y**.

Esto explica por qué no es posible garantizar restauración, centrado modal ni
comparación de zonas para cualquier toolkit con el modelo geométrico actual.

**Plan de acción:**

1. Incorporar `_NET_FRAME_EXTENTS` y definir una única geometría canónica
   (marco exterior visible) para lectura, guardado, comparación y movimiento.
2. Usar `_GTK_FRAME_EXTENTS` sólo para sombras CSD y `_NET_FRAME_EXTENTS` para
   marcos SSD, evitando sumar ambos sin identificar su semántica.
3. Separar en nombres/tipos distintos `buffer_rect`, `client_rect` y
   `outer_frame_rect` para impedir conversiones dobles.
4. Restaurar siempre en el mismo espacio geométrico en el que se guardó.

**Pruebas de regresión/aceptación:** 100 ciclos snap/restaurar en una ventana
SSD no deben acumular ningún desplazamiento; tolerancia final ±1 px. Repetir con
modal SSD y con monitores que tengan coordenadas negativas.

### QA-003 — Snap Assist pierde candidatos y recorta el décimo renglón

**Severidad:** Alta  
**Tipo:** Funcional / UX / accesibilidad  
**Estado:** Reproducido

Con 12 ventanas elegibles, `State.get_sorted_eligible()` devolvió sólo 10. El
`break` está ligado a la longitud de `QUICKKEY_SEQUENCE`, por lo que las
ventanas 11 y 12 desaparecen incluso para navegación con flechas.

Además, con diez entradas y una zona de 960×518, las primeras nueve filas
midieron 37 px de alto, mientras la décima quedó sin layout útil (1 px). La
quickkey `P` todavía la selecciona, pero el usuario no puede verla.

**Plan de acción:**

1. Conservar la lista completa; asignar quickkeys sólo a las primeras N.
2. Permitir seleccionar el resto mediante flechas y Enter.
3. Reemplazar el `pack` directo por una lista desplazable (`Canvas`/frame o
   widget equivalente) con auto-scroll de la selección.
4. Mostrar posición y total, por ejemplo `11/14`, cuando exista scroll.
5. Añadir una alternativa configurable de quickkeys de más de un carácter si
   se desea acceso directo a todas las ventanas.

**Pruebas de regresión/aceptación:** matrices de 0, 1, 9, 10, 11, 20 y 100
candidatos; todos deben ser alcanzables, la fila activa siempre visible y las
quickkeys nunca ambiguas.

### QA-004 — Un error de Tkinter puede dejar el flujo activo sin UI

**Severidad:** Alta  
**Tipo:** Robustez / recuperación  
**Estado:** Confirmado por revisión estructural e historial de logs

`UIManager._process_command()` captura cualquier excepción, la registra y no
notifica a `SnapFlow`. Si falla `show_menu` o `show_snap_assist`, la máquina de
estados puede seguir activa aunque no exista selector visible. Los logs
históricos contienen dos fallos de `show_menu`; el mecanismo de propagación
sigue sin existir aunque aquel error concreto ya se corrigió.

**Plan de acción:**

1. Emitir `ui_command_failed` con `flow_id`, acción y error hacia el coordinador.
2. Hacer rollback si ya empezó una transacción o cancelar limpiamente si aún no
   se movió ninguna ventana.
3. Añadir un watchdog corto para `show_*`: la UI debe confirmar que quedó visible.
4. Marcar la UI como no saludable si termina su hilo y rechazar nuevos flujos
   con una notificación clara.

**Pruebas de regresión/aceptación:** inyectar errores en creación, `geometry`,
`grab_set`, dibujo y cierre; el flujo debe volver a `idle`, no dejar grabs y el
siguiente `Super+Z` debe funcionar.

### QA-005 — “Ignorar y Centrar” no puede ser simétrico en zonas superiores

**Severidad:** Media  
**Tipo:** UX / conflicto especificación–WM  
**Estado:** Reproducido

Para una ventana con mínimo 850×700 dentro de una zona 960×518, el motor calculó
Y=−91, pero Mutter mantuvo el marco superior dentro de la pantalla. La lectura
fue Y=36 para el cliente SSD. El desborde vertical no fue simétrico.

**Plan de acción:**

1. Definir explícitamente si prima el centrado matemático o la accesibilidad de
   la barra de título. En GNOME/Mutter no se puede garantizar ambos mediante
   EWMH.
2. Recomendar como política v1 “centrar hasta el límite permitido por el WM” y
   reflejarlo en requisitos y UI.
3. Verificar la geometría aceptada y centrar de nuevo en el eje que sí lo permita.
4. Mostrar un indicador discreto de incompatibilidad de tamaño en la zona.

**Pruebas de regresión/aceptación:** tamaños mínimos mayores en ancho, alto y
ambos ejes; zonas superiores/inferiores; Spotify y dos toolkits sintéticos.

### QA-006 — Una ventana activa no elegible puede abrir el menú

**Severidad:** Media  
**Tipo:** Funcional  
**Estado:** Reproducido con prueba de contrato

`SnapFlow.trigger()` sólo comprueba que exista un `window_id`. Una ventana
activa ausente de `get_all_windows()` —por ejemplo fullscreen exclusivo,
always-on-top o tipo no normal— dejó el flujo activo y envió `show_menu`.

**Plan de acción:**

1. Exponer `is_window_eligible(wid)` en el backend.
2. Resolver primero la cadena `WM_TRANSIENT_FOR` y validar después la ventana
   principal resultante.
3. Si no es elegible, notificar y no cambiar `flow_id`, `State` ni UI.

**Pruebas de regresión/aceptación:** escritorio, dock, diálogo con padre,
fullscreen, always-on-top, skip-taskbar, normal y minimizada.

### QA-007 — Un work area 0×0 abre el flujo con zonas ficticias de 1 px

**Severidad:** Media  
**Tipo:** Caso borde / robustez  
**Estado:** Reproducido con prueba de contrato

La arquitectura exige abortar si el work area es vacío. En la implementación,
`LayoutEngine` fuerza ancho/alto mínimos de 1 px y `SnapFlow` muestra el menú.

**Plan de acción:** validar `w > 0` y `h > 0` en `SnapFlow.trigger()` antes de
calcular zonas; loguear `WARNING`, notificar y volver a `idle` sin transacción.

**Pruebas de regresión/aceptación:** 0×0, 0×N, N×0, monitor retirado entre
consulta y visualización, y retorno posterior a una topología válida.

### QA-008 — La franja fija de 60 px confunde contenido con barra de título

**Severidad:** Media  
**Tipo:** UX / desacoplamiento accidental  
**Estado:** Reproducido con prueba de contrato

Un punto a 50 px del borde superior se clasificó como `drag`. En aplicaciones
con barra más baja, esa coordenada pertenece a toolbar o contenido. Arrastrar
allí más de 8 px puede desacoplar y restaurar la ventana inesperadamente.

**Plan de acción:**

1. No inferir la barra de título sólo por una altura fija.
2. Confirmar el gesto mediante el cambio real de geometría: variación de X/Y
   implica movimiento; variación de W/H implica resize; sin variación, ignorar.
3. Usar extents reales donde existan y una ruta específica para CSD.
4. Medir desplazamiento neto desde el punto inicial, además de distancia
   acumulada, para evitar que jitter circular alcance el umbral.

**Pruebas de regresión/aceptación:** drag en título, selección de texto,
scrollbar, toolbar, borde y esquina en GTK, Electron, Terminal, Qt y SSD.

### QA-009 — Cancelar tras la primera ventana deja un `ZoneRef` huérfano

**Severidad:** Media  
**Tipo:** Integridad de estado  
**Estado:** Reproducido

Después de cancelar Snap Assist con una sola zona ocupada, la ventana queda en
`snapped_windows`, pero su `group_id=phase7-*` no existe en `active_groups`.
Visualmente es razonable que una sola ventana no forme un Snap Group, pero el
modelo de datos queda referencialmente inconsistente.

**Plan de acción:**

1. Separar el concepto “ventana acoplada” del de “miembro de grupo”.
2. Hacer `group_id` opcional o introducir una entidad de sesión/layout que pueda
   tener un solo miembro sin fingir un grupo activo.
3. Centralizar un validador de invariantes y ejecutarlo al confirmar, cancelar,
   hacer rollback, destruir y desconectar monitores.

**Pruebas de regresión/aceptación:** cancelar tras 1, 2 y 3 ventanas; toda
referencia no nula debe apuntar a una entidad existente y `Super+Alt+Tab` debe
dar el resultado esperado.

### QA-010 — `_NET_WORKAREA` global no representa reservas por monitor

**Severidad:** Media  
**Tipo:** Compatibilidad multi-monitor  
**Estado:** Riesgo confirmado por diseño; no reproducido con paneles distintos

El backend intersecta un único `_NET_WORKAREA` global con cada monitor. Esto no
puede representar un panel presente sólo en una pantalla, paneles de alturas
distintas o docks laterales por monitor. Puede generar bordes vacíos o cubrir un
panel.

**Plan de acción:**

1. Enumerar ventanas dock y aplicar `_NET_WM_STRUT_PARTIAL` por intersección con
   cada monitor.
2. Usar `_NET_WORKAREA` como fallback, no como única fuente multi-monitor.
3. Invalidar la caché ante cambios de struts, paneles y XRandR.

**Pruebas de regresión/aceptación:** panel sólo en primario, panel sólo en
secundario, docks izquierdo/derecho, auto-ocultación y monitores apilados.

### QA-011 — La ayuda omite el estado explícito del daemon

**Severidad:** Baja  
**Tipo:** UX / requisito incompleto  
**Estado:** Confirmado por revisión

`Super+/` muestra atajos, grupos y ventanas monitoreadas, pero no la línea
“Daemon: activo/inactivo” requerida.

**Plan de acción:** añadir el estado y, si la UI está degradada, distinguir
“daemon activo / UI no disponible”. Añadir una prueba sobre el texto completo.

### QA-012 — Documentación técnica desalineada con la implementación

**Severidad:** Baja  
**Tipo:** Mantenibilidad / QA  
**Estado:** Confirmado por revisión

`arquitectura_tecnica.md` y partes de `plan_implementacion.md` aún describen
Rofi, sockets/archivos temporales, `XGrabKey`, UI bloqueante y rotación diaria.
El producto usa Tkinter asíncrono, pynput/XRecord y rotación por tamaño.

**Plan de acción:** actualizar diagramas, secuencias, estrategia de errores,
logging y archivos por fase. Añadir una revisión documental obligatoria al
cierre de cada fase.

### QA-013 — La suite oficial no protege las superficies de mayor riesgo

**Severidad:** Media  
**Tipo:** Deuda de testing  
**Estado:** Confirmado

No existe `tests/test_phase4.py`; `snap_assist_menu.py` y `overlay.py` no tienen
cobertura oficial directa. `x11_backend.py`, `layout_menu.py`, `ui_manager.py` y
`main.py` están entre 11% y 28%.

**Plan de acción:**

1. Migrar a un runner estándar (`pytest` o `unittest`) con códigos de salida
   uniformes y cobertura de ramas.
2. Añadir Xvfb para UI/X11 sintético y una capa de pruebas reales marcada
   `x11_integration` para Zorin/Mutter.
3. Convertir los escenarios adicionales de este informe en regresiones:
   >10 candidatos, SSD, Terminal, work area vacío, activa no elegible, fallo UI,
   cada punto de rollback y 200 reinvocaciones.
4. Añadir CI para pruebas puras y una ejecución manual/release gate en X11 real.
5. Definir umbrales iniciales por módulo, priorizando UI, backend y `main`.

**Criterio de aceptación:** ninguna fase se declara cerrada sin pruebas de sus
criterios manuales y automatizados; cobertura de rutas críticas ≥90%, además de
la matriz real de toolkits.

## 5. Validaciones que sí quedaron conformes

- Las ventanas minimizadas siguen siendo elegibles.
- Los filtros de fullscreen, always-on-top, skip-taskbar y tipos de sistema
  funcionan en la lista de sugerencias.
- Los seis layouts, incluida la opción visual 1:1:1, se dibujan y son accesibles
  por selección numérica en dos pasos.
- El menú de layouts cabe en 1920×1036 y 1366×728.
- La asignación de ventanas a ambos monitores fue correcta.
- El traslado entre workspace/monitor está cubierto por pruebas unitarias.
- La lista elegible permanece congelada durante el flujo.
- La pertenencia exclusiva, disolución y orden de foco de Snap Groups pasan.
- La desconexión real registrada a las 21:14 suspendió el grupo del monitor
  retirado; la reconexión descartó el suspendido. Esto coincide con el requisito
  v1: el grupo **no debe** recuperarse después de reconectar.
- `BadWindow` no derriba el daemon y los rollbacks restauran estado y geometría
  en los escenarios simulados.
- No reaparecieron los errores antiguos de CARD32 negativo durante esta sesión.
- La terminal conserva actividad operativa en nivel INFO y el detalle DEBUG se
  mantiene en `daemon.log`.

## 6. Limitaciones y riesgos residuales de esta ejecución

- El envío sintético de `Super+Z` mediante pynput abrió Actividades de GNOME y
  no fue capturado de forma fiable. Esto se clasificó como limitación de la
  automatización, no como fallo del producto, porque el atajo físico ya había
  sido validado por el usuario. Debe repetirse como prueba humana de release.
- `Alt+F4` mientras el menú de sugerencias posee el grab actúa sobre el menú, no
  sobre una candidata sin foco. Para reproducir un `BadWindow` real se debe
  cerrar la ventana desde otro proceso/control o usar una ventana desechable;
  no es una forma válida de cerrar la tercera candidata desde el propio menú.
- No se desconectó físicamente el cable durante esta ejecución. Se usaron la
  prueba automatizada y el registro real previo de desconexión/reconexión.
- No se probó Wayland porque está explícitamente fuera del alcance de v1.
- No se evaluaron instalación, systemd, consumo de 10 minutos ni reinicio de
  sesión; pertenecen a la fase 10, todavía no implementada.
- Ningún sistema X11 puede prometer geometría exacta “bajo toda circunstancia”
  frente a aplicaciones que ignoran EWMH o imponen políticas internas. El
  objetivo verificable debe ser: compatibilidad exacta para la matriz soportada,
  detección de divergencias y fallback seguro y visible para el resto.

## 7. Orden recomendado de corrección

1. **QA-002** — unificar geometría CSD/SSD y eliminar deriva de restauración.
2. **QA-001** — verificación/corrección real para Terminal y tamaños aceptados.
3. **QA-003** — lista completa y scroll accesible.
4. **QA-004** — recuperación ante fallo de UI.
5. **QA-009** — normalizar el modelo de ventana acoplada sin grupo.
6. **QA-006 y QA-007** — precondiciones del flujo.
7. **QA-008** — detección robusta de drag/resize.
8. **QA-005 y QA-010** — políticas de mínimo y work area multi-monitor.
9. **QA-011 y QA-012** — ayuda y documentación.
10. **QA-013** — convertir todos los casos en gates permanentes de regresión.

Después de corregir los puntos 1–4 debe ejecutarse nuevamente la matriz completa
antes de considerar válidas las fases 8 y 9 en conjunto.
