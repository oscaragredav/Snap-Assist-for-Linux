# Roadmap de ejecución: SnapAssist 1.1.0 → 2.0.0

Este documento convierte `PLAN_EVOLUCION_1.1_A_2.0.md` en puertas de trabajo y
validación. Las etiquetas de versión marcan entregables; las puertas manuales
pueden ocurrir entre etiquetas. El commit `77a6e66` es la referencia estable y
recuperable de la máquina de prueba hasta que un release sea aprobado.

## Estado de ejecución

| Etapa | Implementación automática | Puerta del usuario |
|---|---|---|
| E0 | completada en el árbol de desarrollo | U0 pendiente |
| E1 | suite heredada, CI y packaging preparados | U1 pendiente |
| E2 | spike GNOME test, schema, paquete e IPC inicial preparados | U2 pendiente |
| E3 | contratos neutrales, adaptadores GNOME/X11 y configuración preparados | U3 pendiente |
| E4 | protocolo, idempotencia, heartbeat y recuperación preparados | U4 pendiente |
| E5 | UI/input, overlays, ayuda y preferencias gráficas preparados | U5 pendiente |
| E6 | soak, reconexión, caché y residuos automatizados | U6 pendiente |
| E7 | migración, backup, rollback y desinstalación preparados | U7 pendiente |
| E8 | bundle conjunto reproducible, identidades y checksums preparados | U8 pendiente |

Una etapa no se considera aprobada por tener su código preparado: requiere la
puerta manual indicada y, cuando corresponda, el tag reproducible.

La puerta automática consolidada no modifica servicios ni la sesión gráfica:

```bash
python3 scripts/validate-roadmap.py --full \
  --output artifacts/roadmap-validation.json
```

El informe conserva por separado `automatic` y `manualStatus`; pasar E0–E8 no
marca U0–U8 como aprobadas. Las puertas se registran mediante evidencia
estructurada siguiendo `docs/validation/README_MANUAL_GATES.md`.

## Regla operativa

- `stable` usa `snapassist.service`, `~/.local/share/snapassist` y
  `~/.config/snapassist`.
- `test` usa `snapassist-test.service`, `~/.local/share/snapassist-test` y
  `~/.config/snapassist-test`.
- Los servicios son mutuamente excluyentes. `snapassist-channel stable|test`
  cambia coordinadamente servicio y extensión, valida el runtime y
  `snapassist-channel status` muestra versión, backend y extensión.
- Instalar `test` nunca lo activa automáticamente. Solo tags aprobados se
  promueven a `stable`.
- Cada puerta manual registra commit, sesión, aplicaciones, resultado y logs.

## E0 — Baseline y aislamiento

Implementar canales, manifests, logs separados, cambio seguro y rollback.

**Automático:** instalación idempotente de ambos canales en rutas temporales;
unidades y manifests separados; exclusión mutua; cambio y rollback simulados;
suite heredada y compilación.

**Usuario U0:** validar `77a6e66`; instalar `test`; alternar a test; ejecutar un
flujo; revisar su log; volver a stable; cerrar sesión y confirmar que solo
arranca el canal seleccionado.

## E1 — v1.1.0 estable X11

Cerrar packaging, licencia, changelog, XDG, nombres `.desktop`, `flow_id`,
afinidad de hilo, clasificación de errores, CI y artefactos reproducibles.

**Automático:** fases 1–10 y QA; pytest, Ruff y compileall en Python 3.11–3.13;
wheel; instalación, actualización y desinstalación aisladas; contratos de
versión, licencia, servicio y paquete.

**Usuario U1:** desde `test`, validar atajos, layouts, Snap Assist, grupos,
cancelación y restauración con Firefox, Terminal, GTK y Electron; ventanas
minimizadas, workspaces y dos monitores; alternar dos veces con stable.
La lista reproducible está en `docs/validation/U1_X11_BASELINE.md`.

## E2 — v2.0.0-alpha.1, spike GNOME/Mutter

Crear la extensión GNOME 46 experimental y una matriz X11/Wayland/XWayland.

**Automático:** metadata, ESM, schemas, lint GJS, módulos puros, handshake,
enable/disable y GNOME 46 Wayland headless con monitor virtual, snapshot y
comprobación de residuos.

**Usuario U2:** ventana activa, geometría, monitor, workspace, foco, resize,
Super+Z, overlay, menú, hotplug y escalas en X11 y Wayland. El ADR y todas las
capacidades esenciales deben quedar aprobados antes del refactor.

## E3 — v2.0.0-alpha.2, core y configuración

Extraer el core mediante contratos de plataforma y eventos semánticos. Definir
configuración versionada para layouts personalizados y acciones con atajos.

**Automático:** prohibición de imports de plataforma en el core neutral 2.x;
contract tests;
paridad X11; geometría válida de layouts; IDs y atajos duplicados; migración,
archivo corrupto y defaults; rollback transaccional.

El backend X11 dispone de un adaptador a snapshots/handles neutrales para
compararlo con GNOME sin filtrar IDs nativos al coordinador 2.x.

**Usuario U3:** regresión X11, defaults sin cambios, recuperación de config
inválida y aislamiento de configuración entre canales.
La lista reproducible está en `docs/validation/U3_CORE_CONFIGURATION.md`.

## E4 — v2.0.0-alpha.3, protocolo GNOME

Implementar D-Bus versionado, operaciones identificadas, snapshots,
secuencias, sesión Shell y reconexión, con identidad IPC distinta para test.

**Automático:** introspección, versiones, duplicados, eventos fuera de orden,
ventanas desaparecidas, timeouts y reinicios.

El daemon mantiene un heartbeat read-only; una recarga de extensión renueva
signal matches y difiere restauraciones hasta recuperar el runtime.

**Usuario U4:** detener daemon, recargar extensión, cerrar ventanas durante una
operación y volver a iniciar sesión sin overlays, grabs ni procesos huérfanos.

## E5 — v2.0.0-beta.1, UI y personalización

Trasladar UI, input y animación a GNOME. Añadir editor gráfico para crear,
duplicar, dividir, redimensionar, ordenar, activar y eliminar layouts. Los
predeterminados se personalizan duplicándolos. Añadir edición de los atajos de
layouts, grupos y ayuda, con detección de duplicados/conflictos y restauración.

**Automático:** round-trip y migración; operaciones del editor; vista previa;
conflictos de atajos; navegación por teclado; escalado, contraste y textos
largos; paridad GJS/Python.

La UI incluye miniaturas de zonas, overlay de la zona sugerida, animación de
entrada y ayuda nativa cerrable con `Esc`.

**Usuario U5:** crear un layout de tres zonas; modificar una copia; reordenar,
desactivar y borrar; comprobar persistencia; cambiar Super+Z; provocar un
conflicto; restaurar defaults; completar el flujo sin mouse en X11 y Wayland.
La lista reproducible está en `docs/validation/U5_CUSTOMIZATION.md`.

## E6 — Puerta de uso prolongado U6

No genera una versión. Automatizar soak tests, fallos, ciclos de reconexión,
residuos y consumo. El usuario completa dos sesiones de trabajo en X11 y dos en
Wayland, logout/login, reinicios, hotplug, layouts y atajos personalizados,
confirmando diariamente el rollback a stable.
El registro reproducible está en `docs/validation/U6_SOAK.md`.

## E7 — v2.0.0-rc.1

Completar paridad, matriz de aplicaciones, migración y empaquetado conjunto.

**Automático:** todas las suites; instalación limpia; actualización desde v1.1;
migración, rollback y desinstalación; versiones y artefactos reproducibles.

**Usuario U7:** matriz Zorin 18.1/GNOME 46 en X11 y Wayland con GTK, Qt,
Electron, Firefox, Chromium, terminal y XWayland; monitores, escalas, fallos,
instalación, actualización, personalización y rollback. Se exige cero regresión
crítica frente a v1.1.
Las operaciones y evidencia están en `docs/validation/U7_U8_RELEASE.md`.

## E8 — v2.0.0

Distribuir daemon, unidad, extensión y schemas como conjunto versionado.

**Automático:** reconstrucción desde tag, artefacto publicado, checksums,
metadatos, smoke de actualización/rollback y documentación empaquetada.

**Usuario U8:** instalar primero en test; smoke final X11 y Wayland; promover a
stable; comprobar una última recuperación de `77a6e66` y logout/login.
La construcción y recuperación se documentan en `docs/release.md`.
