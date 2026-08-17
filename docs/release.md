# Construcción, actualización y recuperación

El árbol evolutivo se identifica como `2.0.0.dev0`; por seguridad no puede
sobrescribir el canal estable sin `--promote`. Esa opción se reserva para una
puerta U7/U8 aprobada. Una versión final `2.0.0` solo puede construirse desde
el tag exacto `v2.0.0` y con los archivos versionados limpios.

## Artefacto conjunto

```bash
bash scripts/build-release.sh dist/release
sha256sum -c dist/release/snapassist-2.0.0.dev0-bundle.tar.gz.sha256
```

El bundle contiene wheel, fuente, extensiones GNOME estable y test, manifest
de release y `SHA256SUMS`. `SOURCE_DATE_EPOCH` permite reconstruirlo de forma
binariamente idéntica. El manifest registra versión, commit, baseline
`77a6e66`, protocolo y GNOME Shell soportado.

La validación integral y su evidencia JSON se generan con:

```bash
python3 scripts/validate-roadmap.py --full \
  --output artifacts/roadmap-validation.json
```

## Actualización y rollback

Cada reinstalación guarda una copia anterior del código, metadatos y unidad,
sin copiar logs, entorno virtual ni configuración. Para volver al candidato
anterior del mismo canal:

```bash
snapassist-manage rollback test
```

La migración de configuración es explícita y nunca sobrescribe el destino:

```bash
snapassist-manage migrate stable test
```

La desinstalación conserva configuración salvo petición explícita:

```bash
snapassist-manage uninstall test
snapassist-manage uninstall stable --purge-config
```
