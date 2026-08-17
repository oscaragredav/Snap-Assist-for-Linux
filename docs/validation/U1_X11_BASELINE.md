# U1 — Baseline funcional X11 1.1.0

Ejecutar en el canal `test` y comparar con el canal `stable` basado en
`77a6e66`. Registrar fecha, commit, aplicaciones, monitores y logs.

## Recorrido

1. Probar `Super+Z`, selector de layouts, Snap Assist y ayuda con teclado.
2. Completar, cancelar y restaurar grupos; arrastrar y redimensionar ventanas.
3. Repetir con Firefox, Terminal, una aplicación GTK y una Electron.
4. Cubrir ventana minimizada, modal/transient, dos workspaces, dos monitores y
   coordenadas negativas cuando la disposición lo permita.
5. Alternar `stable → test → stable → test`; comprobar exclusión mutua y
   ausencia de cambios en configuración/logs del otro canal.

## Aceptación

- No existe regresión funcional crítica frente a `77a6e66`.
- Cancelación y fallos restauran geometría y estado de maximización.
- Los atajos se liberan al detener cada canal y no existen procesos huérfanos.
- Nombres, mínimos, work areas y cambios de workspace son correctos.

Registrar el resultado con el procedimiento de `README_MANUAL_GATES.md`.
