# SnapAssist para Linux

Daemon de usuario para X11 que replica el flujo de Snap Assist de Windows:
selección de layouts con `Super+Z`, acoplamiento de ventanas y restauración de
su geometría al desacoplarlas. Está orientado inicialmente a Zorin OS en una
sesión X11; Wayland aún no está soportado.

## Estado del proyecto

Las fases 1 a 9 del plan están implementadas. Las fases recientes cuentan con
pruebas unitarias; su validación funcional requiere una sesión X11 real.

La siguiente fase del plan será la 10: configurabilidad y empaquetado.

## Funcionalidad disponible

- Conexión X11, lectura de ventanas, work area y monitores.
- Atajo global `Super+Z` y menú visual de layouts.
- Cálculo de zonas y movimiento/redimensionamiento de ventanas.
- Animación de acoplamiento.
- Restauración de la geometría original al arrastrar una ventana acoplada más
  de 8 px; un resize manual la desacopla sin restaurar el tamaño anterior.
- Filtro de ventanas elegibles, orden MRU y quickkeys; las ventanas minimizadas
  también son elegibles para el flujo de sugerencias.
- Sugerencias automáticas para completar zonas libres, con lista congelada,
  quickkeys para las primeras diez, lista desplazable para el resto, soporte
  entre monitores y traslado desde otros workspaces.
- Snap Groups con pertenencia exclusiva, disolución automática y recuperación
  mediante `Super+Alt+Tab`; `Super+/` muestra ayuda y estado.
- Aplicaciones con tamaño mínimo grande, como Spotify, permanecen en el grupo:
  se centran y se mantienen accesibles dentro del work area; si no pueden
  representar una zona exacta, el daemon registra la restricción del cliente.
- Operaciones multi-ventana atómicas: un fallo restaura la geometría y el
  estado previos de todas las ventanas ya movidas.
- Seguimiento XRandR de desconexiones, suspensión de grupos del monitor
  retirado y descarte seguro al reconectar.
- Ventanas modales centradas sobre su padre al acoplarlo y aislamiento de
  errores X11 para que un evento no crítico no detenga el daemon.
- Cancelaciones y atajos serializados por el daemon: callbacks atrasados de
  `Esc`/`FocusOut` se descartan por identificador de flujo y no pueden cerrar
  una invocación posterior de `Super+Z`. El apagado espera el cierre de Tkinter.

El menú de layouts se controla en dos pasos: primero se escoge el grupo con
`←`/`→` y Enter, o directamente con `1`–`6`; después se escoge la posición con
las flechas y Enter, o con el número mostrado dentro de cada zona. Por ejemplo,
`6`, `3` selecciona el layout `1:1:1` y su columna derecha.

## Requisitos

- Python 3.12 o superior.
- Sesión gráfica X11.
- Dependencias de Python en `requirements.txt`.
- `tkinter` disponible en el sistema para el menú y los overlays.

## Uso durante el desarrollo

```bash
python3 -m venv venv
venv/bin/pip install -r requirements.txt
venv/bin/python -m snapassist.main
```

Los registros detallados se escriben en
`~/.local/share/snapassist/daemon.log`. Los errores también se separan en
`~/.local/share/snapassist/errors.log`, incluyendo el traceback. La terminal
muestra los eventos operativos de nivel `INFO`, las advertencias y los errores,
suprimiendo repeticiones durante las animaciones. El detalle `DEBUG` queda sólo
en los archivos para evitar saturar la consola.

En X11, SnapAssist usa un rectángulo visible canónico: compensa sombras CSD y
decoraciones SSD (`_NET_FRAME_EXTENTS`) tanto al leer como al mover/restaurar.
Mientras una ventana está acoplada también suspende sus incrementos de tamaño
(por ejemplo, la cuadrícula de caracteres de una Terminal) y restaura las
restricciones originales al desacoplarla o al cerrar el daemon. Algunos clientes
pueden redondear su contenido unos pocos píxeles; el resultado se verifica y se
registra en vez de repetir redimensionamientos indefinidamente.

## Pruebas

```bash
venv/bin/python tests/run_all.py
```

La puerta anterior ejecuta las fases 1–9, la cobertura del menú de Fase 4 y
las regresiones de `QA_REPORT.md`. Las comprobaciones X11 reales de SSD y
Terminal se realizan con ventanas temporales cerradas automáticamente.

Los criterios funcionales y el orden completo de implementación se encuentran
en [plan_implementacion.md](plan_implementacion.md). Los requisitos de
comportamiento están en [Requerimientos.md](Requerimientos.md) y el diseño de
módulos en [arquitectura_tecnica.md](arquitectura_tecnica.md).
