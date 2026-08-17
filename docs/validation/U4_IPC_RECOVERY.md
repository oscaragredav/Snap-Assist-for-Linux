# U4 — Recuperación del protocolo GNOME

Prerequisitos: U2 aprobada y extensión test habilitada. Adjuntar la salida de:

```bash
python3 scripts/check-gnome-protocol.py --json
```

El selector ejecuta automáticamente `GetProtocolInfo` y `GetSnapshot` antes
de confirmar un canal GNOME. También puede comprobarse sin mutar ventanas:

```bash
SNAPASSIST_CHANNEL=test /usr/bin/python3 -m snapassist.health --json
```

Si la extensión se recarga después del arranque, el heartbeat del daemon
recrea las suscripciones. Una transacción interrumpida restaura sus ventanas
cuando reaparece la sesión Shell.

## Evidencia

- Fecha, commit y manifest test:
- Sesión X11/Wayland:
- `sessionId` inicial/final:
- Resultado:
- Logs de extensión y daemon:

## Casos

1. Ejecutar cinco handshakes y snapshots consecutivos.
2. Cerrar una ventana entre snapshot y operación; esperar `window-gone`.
3. Repetir una operación con el mismo ID y argumentos; comprobar que solo se
   aplica una vez y el segundo resultado indica duplicado.
4. Reutilizar ese ID con argumentos distintos; esperar
   `operation-id-conflict`.
5. Deshabilitar y habilitar la extensión; comprobar un nuevo `sessionId` y
   reconexión limpia.
6. Detener y reiniciar el daemon durante un flujo.
7. Cerrar sesión y entrar nuevamente; comprobar que no quedan overlays, atajos,
   nombres D-Bus ni procesos huérfanos.

La puerta falla ante una operación duplicada aplicada dos veces, aceptación de
eventos de otra sesión o residuos después de deshabilitar la extensión.
