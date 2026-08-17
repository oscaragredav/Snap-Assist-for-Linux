# U3 — Paridad del core y configuración

Esta puerta comprueba en X11 que el refactor neutral conserva el comportamiento
de 1.1.0 y que los canales no comparten configuración.

## Recorrido

1. Guardar copias de las configuraciones `stable` y `test`.
2. Verificar layouts y atajos predeterminados sin archivo de configuración.
3. Crear un layout y cambiar un atajo únicamente en `test`; reiniciar el canal.
4. Introducir en test una copia corrupta y confirmar fallback seguro sin
   reescribir silenciosamente el archivo original.
5. Restaurar la configuración válida y comprobar orden, IDs y geometrías.
6. Cambiar a stable y confirmar que defaults, configuración y grupos no fueron
   afectados; volver a test y completar snap, cancelación y rollback.

## Aceptación

- La geometría observada coincide con X11 1.1.0 en los mismos work areas.
- No se filtran IDs nativos a archivos o mensajes del core neutral.
- Duplicados, solapamientos y atajos inválidos se rechazan de forma segura.
- Configuración, logs, estado y backups permanecen aislados por canal.

Registrar el resultado con el procedimiento de `README_MANUAL_GATES.md`.
