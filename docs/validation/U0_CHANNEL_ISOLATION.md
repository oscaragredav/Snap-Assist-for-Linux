# U0 — Aislamiento de los canales stable y test

Completar en la PC de prueba antes de iniciar los spikes de GNOME. Esta puerta
modifica qué servicio está activo, pero no reemplaza los archivos del canal
estable cuando se instala con `--channel test`.

## Evidencia

- Fecha:
- Commit de prueba:
- Sesión (`echo $XDG_SESSION_TYPE`):
- Manifest stable (`~/.local/share/snapassist/install-manifest`, si existe):
- Manifest test (`~/.local/share/snapassist-test/install-manifest`):
- Resultado: pendiente / aprobado / rechazado
- Incidencias y logs:

## Pasos

1. Con la versión estable activa, comprobar `Super+Z`, completar un snap de dos
   ventanas, usar `Super+Alt+Tab` y restaurar una ventana por arrastre.
2. Desde el checkout de desarrollo ejecutar:

   ```bash
   bash install.sh --channel test
   snapassist-channel status
   ```

3. Confirmar que `snapassist.service` sigue activo y que la instalación test
   existe en `~/.local/share/snapassist-test`.
4. Cambiar de canal y ejecutar el mismo flujo básico:

   ```bash
   snapassist-channel test
   snapassist-channel status
   journalctl --user -u snapassist-test.service -n 30 --no-pager
   ```

5. Confirmar que únicamente `snapassist-test.service` figura activo y que sus
   logs aparecen bajo `~/.local/share/snapassist-test/logs`.
   En runtime GNOME, `snapassist-channel status` también debe mostrar la
   extensión `test` habilitada y la estable deshabilitada.
6. Restaurar estable:

   ```bash
   snapassist-channel stable
   snapassist-channel status
   ```

7. Comprobar de nuevo los atajos y el snap estable.
8. Cerrar y abrir sesión. Confirmar que solo se inicia el canal seleccionado.

## Aceptación

- Ningún archivo del árbol estable cambia al instalar `test`.
- Nunca hay dos servicios activos al mismo tiempo.
- Ambos canales tienen configuración, logs y manifest independientes.
- El selector revierte servicio y extensión si el health-check D-Bus falla.
- Si test falla al iniciar, el selector reactiva stable.
- El comportamiento estable basado en `77a6e66` continúa recuperable.
