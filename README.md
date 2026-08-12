# SnapAssist para Linux

Daemon de usuario para X11 que replica el flujo de Snap Assist de Windows:
selección de layouts con `Super+Z`, acoplamiento de ventanas y restauración de
su geometría al desacoplarlas. Está orientado inicialmente a Zorin OS en una
sesión X11; Wayland aún no está soportado.

## Estado del proyecto

Las fases 1 a 10 del plan están implementadas. SnapAssist puede ejecutarse en
desarrollo o instalarse como servicio systemd del usuario. Las pruebas que
interactúan con ventanas requieren una sesión X11 real.

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

- Zorin OS, Ubuntu o distribución equivalente con systemd de usuario.
- Python 3.11 o superior, con los módulos `venv` y `tkinter`.
- Sesión gráfica X11.
- Dependencias de Python en `requirements.txt`.
- `notify-send` recomendado para ayuda y avisos (`libnotify-bin` en Ubuntu).

En Zorin/Ubuntu se pueden instalar los requisitos del sistema con:

```bash
sudo apt install python3 python3-venv python3-tk libnotify-bin
```

## Instalación como servicio de usuario

SnapAssist sólo funciona actualmente en X11. En la pantalla de inicio de sesión
elige una sesión con **Xorg/X11** si tu distribución inicia Wayland de forma
predeterminada. Después, abre una terminal y ejecuta:

```bash
sudo apt update
sudo apt install git python3 python3-venv python3-tk libnotify-bin
git clone https://github.com/oscaragredav/Snap-Assist-for-Linux.git
cd Snap-Assist-for-Linux
bash install.sh
```

El instalador copia la aplicación a `~/.local/share/snapassist`, crea allí un
entorno virtual aislado, instala las versiones fijadas en `requirements.txt`,
instala `~/.config/systemd/user/snapassist.service` y habilita/reinicia el
servicio. Es seguro volver a ejecutar `bash install.sh` para actualizar una
instalación existente. Además, detecta el `DISPLAY` real de la sesión en vez de
suponer que siempre es `:0`, espera hasta 30 segundos a que X11 esté listo y
termina con un error visible si el servicio no logra arrancar.

Una instalación correcta termina con `Estado: activo`. Pulsa `Super+Z` para
abrir el selector de layouts. No hace falta ejecutar el programa manualmente ni
mantener la terminal abierta; se iniciará con las siguientes sesiones gráficas.

Comandos operativos útiles:

```bash
systemctl --user status snapassist
systemctl --user restart snapassist
systemctl --user stop snapassist
journalctl --user -u snapassist -f
tail -f ~/.local/share/snapassist/daemon.log
tail -f ~/.local/share/snapassist/errors.log
```

El entorno gráfico detectado se guarda con permisos privados en
`~/.config/snapassist/environment`. Si cambia el display o el archivo de
autorización X11, basta con ejecutar de nuevo `bash install.sh` desde una
terminal de la sesión gráfica.

### Desinstalación

```bash
systemctl --user disable --now snapassist.service
rm ~/.config/systemd/user/snapassist.service
rm -r ~/.local/share/snapassist ~/.config/snapassist
systemctl --user daemon-reload
```

## Atajos y configuración

Todos los valores se encuentran al principio de
`snapassist/config.py`. Tras modificarlos, reinstala con `bash install.sh`.

| Acción | Valor predeterminado | Constante |
|---|---|---|
| Abrir layouts | `Super+Z` | `HOTKEY_LAYOUT_MENU` |
| Traer Snap Group al frente | `Super+Alt+Tab` | `HOTKEY_SNAP_GROUPS` |
| Mostrar ayuda y estado | `Super+/` | `HOTKEY_HELP` |
| Quickkeys de sugerencias | `QWERTYUIOP` | `QUICKKEY_SEQUENCE` |
| Umbral para desacoplar | 8 px | `DRAG_THRESHOLD_PX` |
| Duración de animación | 200 ms | `SNAP_ANIMATION_MS` |
| Opacidad del overlay | 0.35 | `OVERLAY_OPACITY` |

Para agregar un layout, incorpora otro `LayoutTemplate` a
`LAYOUT_TEMPLATES`. Cada `ZoneTemplate(x, y, w, h)` usa proporciones entre 0 y
1 respecto del área útil. Las zonas deben cubrir el layout sin solaparse; por
ejemplo, dos filas iguales son:

```python
LayoutTemplate("1 arriba + 1 abajo", [
    ZoneTemplate(0.0, 0.0, 1.0, 0.5),
    ZoneTemplate(0.0, 0.5, 1.0, 0.5),
])
```

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

La puerta anterior ejecuta las fases 1–10, la cobertura del menú de Fase 4 y
las regresiones de `QA_REPORT.md`. Las comprobaciones X11 reales de SSD y
Terminal se realizan con ventanas temporales cerradas automáticamente.

Para validar los límites de recursos de un daemon ya iniciado:

```bash
venv/bin/python tests/measure_idle.py "$(systemctl --user show -p MainPID --value snapassist)" --seconds 60
```

En la validación de Fase 10 del 2026-08-11 se midieron `0.000%` de CPU y
`30.28 MB` de RSS durante 60 segundos sin interacción. El listener global del
puntero se activa únicamente mientras existen ventanas acopladas.

Los criterios funcionales y el orden completo de implementación se encuentran
en [plan_implementacion.md](plan_implementacion.md). Los requisitos de
comportamiento están en [Requerimientos.md](Requerimientos.md) y el diseño de
módulos en [arquitectura_tecnica.md](arquitectura_tecnica.md).
