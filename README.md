# SnapAssist para Linux

Daemon de usuario para X11 que replica el flujo de Snap Assist de Windows:
selección de layouts con `Super+Z`, acoplamiento de ventanas y restauración de
su geometría al desacoplarlas. Está orientado inicialmente a Zorin OS en una
sesión X11; Wayland aún no está soportado.

## Estado del proyecto

Las fases 1 a 8 del plan están implementadas. Las fases recientes cuentan con
pruebas unitarias; su validación funcional requiere una sesión X11 real.

La siguiente fase del plan será la 9: casos borde y robustez.

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
  quickkeys, soporte entre monitores y traslado desde otros workspaces.
- Snap Groups con pertenencia exclusiva, disolución automática y recuperación
  mediante `Super+Alt+Tab`; `Super+/` muestra ayuda y estado.
- Aplicaciones con tamaño mínimo grande, como Spotify, permanecen en el grupo:
  se centran en su zona y desbordan simétricamente cuando es necesario.

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
sólo muestra advertencias y errores, suprimiendo repeticiones durante las
animaciones.

## Pruebas

```bash
venv/bin/python tests/test_phase1.py
venv/bin/python tests/test_phase2.py
venv/bin/python tests/test_phase3.py
venv/bin/python tests/test_phase5.py
venv/bin/python tests/test_phase6.py
venv/bin/python tests/test_phase7.py
venv/bin/python tests/test_phase8.py
```

Los criterios funcionales y el orden completo de implementación se encuentran
en [plan_implementacion.md](plan_implementacion.md). Los requisitos de
comportamiento están en [Requerimientos.md](Requerimientos.md) y el diseño de
módulos en [arquitectura_tecnica.md](arquitectura_tecnica.md).
