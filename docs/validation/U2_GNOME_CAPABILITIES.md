# U2 — Matriz de capacidades GNOME/Mutter

Ejecutar después de aprobar U0. Instalar únicamente en el canal de prueba:

```bash
bash install.sh --channel test
gnome-extensions enable snapassist-test@oscaragredav
```

En GNOME, el instalador selecciona el runtime nativo para el canal `test`. Si
se fuerza `SNAPASSIST_RUNTIME=x11`, no debe activarse a la vez la extensión
experimental porque ambos registrarían `Super+Z`.

El smoke del protocolo es de solo lectura:

```bash
python3 scripts/check-gnome-protocol.py --json
```

La integración básica puede repetirse sin tocar la sesión real:

```bash
bash scripts/run-gnome-nested-smoke.sh
```

Usa HOME, GSettings, runtime, bus y monitor virtual temporales; valida carga,
handshake, snapshot, disable y ausencia de residuos.

Para probar el flujo nativo directamente desde el árbol, sin instalar ni
modificar el servicio:

```bash
bash scripts/run-gnome-test.sh
```

El flujo experimental cubre layout, zona, sugerencias, grupos y restauración
con handles opacos. La paridad final depende de completar esta matriz manual.

## Evidencia común

- Fecha:
- Commit y manifest test:
- GNOME Shell:
- Sesión:
- Aplicaciones usadas:
- Monitores y escalas:
- Resultado:
- Logs (`journalctl --user -b /usr/bin/gnome-shell`):

## Matriz

Registrar aprobado, rechazado o no disponible para cada sesión.

| Capacidad | X11 | Wayland nativo | XWayland | Evidencia |
|---|---|---|---|---|
| Ventana activa y listado | pendiente | pendiente | pendiente | |
| Título e identidad de aplicación | pendiente | pendiente | pendiente | |
| Geometría lógica y work area | pendiente | pendiente | pendiente | |
| Monitor, escala y workspace | pendiente | pendiente | pendiente | |
| Foco, move/resize y maximización | pendiente | pendiente | pendiente | |
| Tamaños mínimos y transients | pendiente | pendiente | pendiente | |
| Eventos de ventana y foco | pendiente | pendiente | pendiente | |
| Hotplug de monitor | pendiente | pendiente | pendiente | |
| Atajo Super+Z y conflictos | pendiente | pendiente | pendiente | |
| UI nativa de layouts y sugerencias | pendiente | pendiente | pendiente | |
| GetProtocolInfo/GetSnapshot D-Bus | pendiente | pendiente | pendiente | |
| Limpieza enable/disable | pendiente | pendiente | pendiente | |

## Limpieza obligatoria

Tras cinco ciclos de enable/disable no deben quedar el bus test, el atajo ni
actores visibles. Al finalizar:

```bash
gnome-extensions disable snapassist-test@oscaragredav
snapassist-channel stable
```
