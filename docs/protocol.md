# Protocolo GNOME `org.snapassist.Shell1`

La definición canónica está en `protocol/org.snapassist.Shell1.xml`. El canal
de prueba usa el bus `org.snapassist.Shell.Test` y el objeto
`/org/snapassist/Shell/Test`. La integración promovida usa
`org.snapassist.Shell` y `/org/snapassist/Shell`; el cliente selecciona el
endpoint mediante `SNAPASSIST_CHANNEL`.

## Reglas

- `GetProtocolInfo` precede a cualquier otra llamada y valida versión, interfaz
  e identificador de sesión Shell.
- Snapshots, eventos, ventanas, monitores y workspaces usan handles opacos.
- Cada evento incluye `sessionId` y una secuencia estrictamente creciente. El
  cliente ignora duplicados, eventos atrasados y sesiones ajenas.
- Las operaciones y sus señales incluyen el `sessionId` vigente y llevan un
  `operationId` globalmente único. Repetir exactamente
  la misma operación devuelve el resultado almacenado sin ejecutarla de nuevo.
- Reutilizar el ID con argumentos distintos produce `operation-id-conflict`.
- El servicio conserva como máximo 256 resultados para acotar memoria.
- Si se pierde el bus, el cliente reconecta, repite el handshake y reintenta una
  vez con el mismo ID. Esto mantiene la operación idempotente.
- Ventanas o workspaces desaparecidos producen resultados clasificados, no
  excepciones sin contrato.
- `MoveResize` se completa de forma asíncrona en GNOME Shell. La extensión
  libera maximización/mosaico, mueve al monitor de destino y espera dos
  muestras consecutivas del frame exterior con una tolerancia máxima de un
  píxel lógico. El daemon no realiza pausas ni sondeo adicional.
- El resultado de `MoveResize` incluye `status` (`confirmed`,
  `constraint-rejected`, `window-gone` o `cancelled`), las geometrías
  solicitada y observada, la restricción detectada, el número de intentos y el
  tiempo de confirmación. Solo `confirmed` se considera aceptado.
- Una restricción restaura únicamente la ventana afectada. El core conserva
  las colocaciones confirmadas, registra la zona vacía y solo crea un grupo si
  quedan al menos dos miembros.
- Las operaciones de presentación (`ShowLayouts`, `ShowSuggestions`,
  `ShowHelp`, `HidePresentation`) conservan `flowId`; `UiAction` incluye sesión
  y secuencia.
- `ConfigureShortcuts` recibe siempre las tres acciones públicas y aplica la
  actualización solo después de validar el conjunto completo.

## Smoke read-only

Con la extensión experimental habilitada:

```bash
python3 scripts/check-gnome-protocol.py --json
```

El comando solo ejecuta handshake y snapshot. No mueve ventanas.
