# SnapAssist para Linux

SnapAssist ayuda a ordenar las ventanas abiertas en tu pantalla. Al pulsar
`Super+Z`, muestra varios diseños y permite colocar una ventana en una mitad,
un tercio u otra zona de la pantalla. Después propone otras aplicaciones para
rellenar los espacios libres, de forma parecida a Snap Assist de Windows.

No necesitas saber programar para instalarlo ni para usarlo.

> **Importante:** actualmente funciona en sesiones **X11 (Xorg)** de Zorin OS,
> Ubuntu y distribuciones similares. Wayland todavía no es compatible.

La versión estable actual es **1.1.0**. Se distribuye bajo GPL-3.0-only.

## Qué puedes hacer

- Elegir visualmente cómo dividir la pantalla.
- Colocar varias ventanas con el teclado, sin arrastrarlas una por una.
- Ver qué aplicación estás organizando antes de elegir su posición.
- Completar los espacios con sugerencias fáciles de identificar, como
  `Mozilla Firefox - Wikipedia` o `Archivos - Descargas`.
- Usar ventanas de otros escritorios o que estén minimizadas.
- Recuperar el tamaño anterior de una ventana al separarla de su zona.
- Volver a mostrar juntas las ventanas de un mismo grupo.
- Trabajar con más de un monitor.

## Requisitos

- Una distribución Linux basada en Ubuntu, como Zorin OS o Ubuntu.
- Una sesión gráfica X11/Xorg.
- Python 3.11 o posterior.
- Una cuenta con permiso para instalar paquetes mediante `sudo`.
- Conexión a Internet durante la instalación.

Si no sabes si usas X11, abre una terminal y ejecuta:

```bash
echo $XDG_SESSION_TYPE
```

El resultado debe ser `x11`. Si aparece `wayland`, cierra la sesión y, en la
pantalla de acceso, selecciona una opción que incluya **Xorg** o **X11** antes
de volver a entrar.

## Instalación

Abre una terminal, copia estas instrucciones y ejecútalas una línea a la vez:

```bash
sudo apt update
sudo apt install git python3 python3-venv python3-tk libnotify-bin
git clone https://github.com/oscaragredav/Snap-Assist-for-Linux.git
cd Snap-Assist-for-Linux
bash install.sh
```

Cuando aparezca `Estado: activo`, la instalación habrá terminado. Puedes cerrar
la terminal: SnapAssist queda funcionando en segundo plano y se inicia
automáticamente al entrar en tu sesión.

Si ya lo tenías instalado y descargaste una versión nueva, ejecuta otra vez
`bash install.sh` desde la carpeta del proyecto para actualizarlo.

## Cómo se usa

1. Haz clic en la ventana que quieres organizar.
2. Pulsa `Super+Z`. La tecla `Super` suele tener el logotipo de Windows.
3. Comprueba la línea **Organizando**, que indica la aplicación y la ventana
   seleccionadas.
4. Elige un diseño con `←` y `→`, y pulsa `Enter`. También puedes pulsar el
   número mostrado junto al diseño.
5. Elige la posición con las flechas y `Enter`, o con el número de la zona.
6. Para cada espacio restante, selecciona una aplicación de la lista. Usa
   `↑`/`↓` y `Enter`, o pulsa la letra que aparece a su izquierda.

Pulsa `Esc` cuando quieras cerrar el selector sin añadir más ventanas. Las que
ya hayas colocado conservarán su posición.

### Atajos

| Atajo | Acción |
|---|---|
| `Super+Z` | Abrir o cerrar el selector de diseños |
| `Super+Alt+Tab` | Traer al frente el último grupo de ventanas |
| `Super+/` | Mostrar ayuda y comprobar si SnapAssist está activo |
| `Esc` | Volver atrás o cerrar el selector |

## Desacoplar una ventana

Arrastra una ventana acoplada varios píxeles para recuperar el tamaño y la
posición que tenía antes. Si la redimensionas manualmente, dejará de pertenecer
al grupo y conservará el nuevo tamaño.

## Solución de problemas

### `Super+Z` no muestra nada

Comprueba que el servicio esté activo:

```bash
systemctl --user status snapassist
```

Si aparece detenido, reinícialo:

```bash
systemctl --user restart snapassist
```

También puedes pulsar `Super+/` para ver un aviso con el estado. Si tu sesión
es Wayland, cambia a X11/Xorg como se explica en la sección de requisitos.

### El instalador muestra un error

Lee el último mensaje de la terminal: normalmente indicará si falta un paquete,
si la sesión no es X11 o si el servicio no pudo arrancar. Para consultar sus
mensajes recientes usa:

```bash
journalctl --user -u snapassist -n 30 --no-pager
```

Después de corregir el problema puedes repetir `bash install.sh` sin desinstalar
nada primero.

### Una aplicación no encaja exactamente

Algunas aplicaciones imponen un tamaño mínimo. SnapAssist intentará mantenerlas
visibles y centradas, aunque no puedan ocupar exactamente una zona pequeña.

## Desinstalación

Abre una terminal y ejecuta:

```bash
systemctl --user disable --now snapassist.service
rm ~/.config/systemd/user/snapassist.service
rm -r ~/.local/share/snapassist ~/.config/snapassist
systemctl --user daemon-reload
```

Esto detiene SnapAssist, elimina su inicio automático y borra sus archivos y
configuración. La carpeta que descargaste con `git clone` no se elimina; puedes
borrarla desde el administrador de archivos si ya no la necesitas.

## Privacidad

SnapAssist funciona localmente en tu equipo. Lee los nombres y la posición de
las ventanas para mostrarlas y organizarlas; no necesita una cuenta ni envía
esa información a un servicio en línea.

## Limitaciones conocidas

- Wayland no está soportado actualmente.
- Algunas aplicaciones pueden ajustar ligeramente el tamaño solicitado.
- Los atajos pueden entrar en conflicto con combinaciones ya reservadas por el
  escritorio u otra aplicación.

## Ayuda y colaboración

Si encuentras un problema o quieres proponer una mejora, abre un *issue* en el
[repositorio de SnapAssist](https://github.com/oscaragredav/Snap-Assist-for-Linux/issues)
e incluye tu distribución de Linux, si usas X11 y qué ocurrió.

Los diagnósticos de `scratch/` son herramientas para mantenedores y no forman
parte del paquete instalado. Consulta [CONTRIBUTING.md](CONTRIBUTING.md) para
ejecutar las comprobaciones de desarrollo.
