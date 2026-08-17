# Configuración versionada de SnapAssist

La configuración de `stable` vive en `~/.config/snapassist/settings.json` y la
de `test` en `~/.config/snapassist-test/settings.json`. Un archivo ausente usa
los defaults de v1.1. Un archivo inválido se conserva para diagnóstico y el
daemon arranca con defaults.

En GNOME, el canal `test` incluye un editor gráfico accesible desde la
aplicación Extensiones (`SnapAssist Test` → Preferencias). Permite crear,
duplicar, editar, ordenar, activar y eliminar layouts, además de cambiar o
restaurar atajos. El editor muestra una vista previa, permite seleccionar cada
zona, cambiar `x/y/ancho/alto` y dividirla horizontal o verticalmente. Los
cambios se validan antes de guardarse y se aplican al
reiniciar `snapassist-test.service`. El JSON continúa disponible para edición
manual y como formato de intercambio.

```json
{
  "version": 1,
  "shortcuts": {
    "layout_menu": "super+l",
    "snap_groups": "super+alt+g",
    "help": "super+h"
  },
  "custom_layouts": [
    {
      "id": "custom:focus-center",
      "name": "Centro amplio",
      "zones": [
        {"x": 0.0, "y": 0.0, "w": 0.25, "h": 1.0},
        {"x": 0.25, "y": 0.0, "w": 0.5, "h": 1.0},
        {"x": 0.75, "y": 0.0, "w": 0.25, "h": 1.0}
      ]
    }
  ],
  "layout_order": [
    "custom:focus-center",
    "builtin:half-half",
    "builtin:two-thirds-left",
    "builtin:two-thirds-right",
    "builtin:grid-2x2",
    "builtin:main-left",
    "builtin:three-columns"
  ],
  "disabled_layouts": ["builtin:grid-2x2"]
}
```

## Reglas

- IDs personalizados: prefijo `custom:` seguido por letras minúsculas,
  números, punto, guion o guion bajo.
- Entre una y diez zonas; coordenadas normalizadas de 0 a 1.
- Las zonas no pueden solaparse y juntas deben cubrir toda el área.
- Los layouts predeterminados se desactivan o duplican; no se redefinen.
- Cada atajo debe incluir Super, Ctrl o Alt y no puede duplicar otra acción.
- Guardar el archivo y reiniciar el canal aplica los cambios en la UI X11.
