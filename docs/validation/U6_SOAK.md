# U6 — Uso prolongado y residuos

Antes de cada jornada ejecuta el soak automatizado:

```bash
python3 scripts/run-soak.py --cycles 10000 --reconnect-every 17 --json
```

Debe informar cero suscripciones residuales. La caché GJS se comprueba acotada
a 256 operaciones en la suite. Registra consumo inicial/final del servicio con
`systemctl --user status` y `ps`, pero no fija un umbral universal porque GNOME
y las aplicaciones alteran el consumo de la sesión.

Completa dos jornadas reales en GNOME X11 y dos en Wayland. En cada una prueba
logout/login, reinicio del daemon, recarga de extensión, hotplug, layouts y
atajos personalizados. Al final de cada día ejecuta `snapassist-channel stable`
y confirma que solo el baseline queda activo.

| Jornada | Sesión | Inicio/fin memoria | Reconexiones | Residuos | Rollback stable |
|---|---|---|---|---|---|
| 1 | X11 | pendiente | pendiente | pendiente | pendiente |
| 2 | X11 | pendiente | pendiente | pendiente | pendiente |
| 3 | Wayland | pendiente | pendiente | pendiente | pendiente |
| 4 | Wayland | pendiente | pendiente | pendiente | pendiente |
