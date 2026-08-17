# U7/U8 — RC, promoción y release

## Evidencia automática requerida

```bash
venv/bin/python tests/run_all.py
python3 scripts/run-soak.py --cycles 10000 --json
bash scripts/build-release.sh dist/release
sha256sum -c dist/release/snapassist-2.0.0.dev0-bundle.tar.gz.sha256
```

Además, reconstruye dos veces con el mismo `SOURCE_DATE_EPOCH` y comprueba que
los bundles son idénticos. CI conserva el bundle de cada versión de Python.

## U7 — Matriz RC

En Zorin OS 18.1/GNOME 46, repetir en X11 y Wayland con GTK, Qt, Electron,
Firefox, Chromium, Terminal y una aplicación XWayland: snap, sugerencias,
grupos, restauración, cancelación, modales, mínimos, maximización, workspaces,
dos monitores, hotplug y escalas 100 %, 200 % y fraccional disponible.

Validar instalación limpia, actualización, `snapassist-manage migrate`,
`rollback` y `uninstall`; ninguna regresión crítica frente a 1.1.0 permite
aprobar U7.

## U8 — Promoción

1. Instalar el candidato únicamente en `test` y completar smoke X11/Wayland.
2. Comprobar una vez más `snapassist-channel stable` y el baseline `77a6e66`.
3. Solo después de aprobar la matriz, actualizar versión a `2.0.0`, crear el
   tag firmado `v2.0.0` y construir desde ese árbol limpio.
4. Verificar checksums, instalar el bundle promovido, habilitar la extensión
   `snapassist@oscaragredav` y realizar logout/login.

Resultado U7: pendiente. Resultado U8: pendiente.
