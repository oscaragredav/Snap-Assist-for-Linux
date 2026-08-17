# U5 — Personalización de layouts y atajos

Esta puerta se ejecuta después de U2–U4 en el canal `test`. No modifica la
configuración estable. Registra fecha, commit, GNOME Shell, tipo de sesión,
aplicaciones, monitores y resultado.

## Preparación

```bash
bash install.sh --channel test
gnome-extensions enable snapassist-test@oscaragredav
snapassist-channel test
```

Abre `Super+Z` y pulsa **Configurar layouts y atajos**. El comando
`gnome-extensions prefs` queda únicamente como alternativa de diagnóstico.

La configuración se guarda únicamente en
`~/.config/snapassist-test/settings.json`. El daemon la aplica automáticamente
en aproximadamente un segundo; no se debe reiniciar el servicio.

## Recorrido manual

1. Crear un layout de tres columnas con el botón **Crear** y confirmar en la
   vista previa que las tres zonas cubren el área completa.
2. Duplicar `1/2 : 1/2`, confirmar que aparece su forma original, elegir otra
   forma y guardar. Seleccionar zonas haciendo clic en la vista previa,
   usar ambas direcciones de división y comprobar **Deshacer**;
   comprobar que la vista previa cambia antes de guardar.
3. Mover ambos layouts al principio; desactivar `1/4 : 1/4 : 1/4 : 1/4`.
4. Abrir `Super+Z` y comprobar orden, layouts desactivados y navegación con
   flechas, números, `Enter` y `Esc`, sin mouse.
5. Borrar una copia y confirmar que desaparece del selector sin reiniciar el
   servicio.
6. Cambiar “Mostrar layouts” a `super+l`; confirmar que el atajo anterior deja
   de actuar y el nuevo abre el selector.
7. Intentar asignar el mismo atajo a dos acciones; el editor debe rechazar el
   guardado y conservar la configuración válida anterior.
8. Restaurar atajos predeterminados y confirmar `Super+Z`, `Super+Alt+Tab` y
   `Super+/`.
9. Repetir los pasos funcionales en GNOME X11 y Wayland, incluyendo escala
   100 % y una escala distinta si está disponible.

## Evidencia automática previa

```bash
venv/bin/python tests/test_settings.py
venv/bin/python tests/test_gnome_extension.py
venv/bin/python tests/run_all.py
```

## Resultado

- Fecha y commit:
- X11: pendiente / aprobado / rechazado
- Wayland: pendiente / aprobado / rechazado
- Persistencia tras logout/login:
- Conflicto de atajos rechazado:
- Configuración stable intacta:
- Logs y observaciones:
