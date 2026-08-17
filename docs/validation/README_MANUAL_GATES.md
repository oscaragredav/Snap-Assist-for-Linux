# Registro de puertas manuales U0–U8

Las guías de este directorio describen qué debe comprobar el usuario. La
evidencia se guarda fuera del código, por defecto en
`artifacts/manual-validation/Ux.json`.

Crear una plantilla:

```bash
python3 scripts/manual-gate.py U0 --init
```

Editarla con resultados reales. Para aprobar una puerta, todos los elementos
de `checks` deben tener `passed: true`, `result` debe ser `approved` y
`evidence` debe referenciar al menos un log, captura o informe. Validar:

```bash
python3 scripts/manual-gate.py U0 --check
python3 scripts/validate-roadmap.py --full \
  --output artifacts/roadmap-validation.json
```

El validador informa `automaticPassed` y `manualPassed` por separado. Nunca
ejecuta una prueba manual ni convierte una plantilla en aprobación.

Correspondencia:

| Puerta | Guía |
|---|---|
| U0 | `U0_CHANNEL_ISOLATION.md` |
| U1 | `U1_X11_BASELINE.md` |
| U2 | `U2_GNOME_CAPABILITIES.md` |
| U3 | `U3_CORE_CONFIGURATION.md` |
| U4 | `U4_IPC_RECOVERY.md` |
| U5 | `U5_CUSTOMIZATION.md` |
| U6 | `U6_SOAK.md` |
| U7–U8 | `U7_U8_RELEASE.md` |
