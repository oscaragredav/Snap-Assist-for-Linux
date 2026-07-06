Especificaciones Técnicas: Clon de Windows 11 Snap Assist para Linux
Versión 2.0

Principio de Diseño Transversal — Atomicidad
Toda operación del sistema debe ser atómica. Si una acción no puede completarse íntegramente, el estado previo debe conservarse sin excepción. El sistema nunca debe terminar en un estado con layouts parcialmente aplicados, grupos con referencias inválidas, o ventanas con geometría inconsistente respecto al layout al que pertenecen. Este principio actúa como criterio de resolución para cualquier caso borde no contemplado explícitamente en este documento.

Parte I — Principios de Comportamiento Base
1. Control Estricto por Teclado
Todo el flujo de invocación, navegación, selección e interacción se realizará exclusivamente mediante teclado: atajos globales, teclas de dirección, teclas de acceso rápido por letra, Enter y Esc. Ninguna acción del flujo principal requerirá clic ni arrastre del mouse.
2. Gestión de Ventanas Flotantes (No Tiling Forzado)
El sistema opera sobre el modelo tradicional de ventanas flotantes. Las aplicaciones se abren de manera normal y no se apilan ni dividen automáticamente en mosaico. El acoplamiento a zonas de un layout ocurre únicamente de forma explícita bajo demanda del usuario mediante los atajos definidos.
3. Delimitación del Área de Trabajo
El sistema calculará las dimensiones de cada zona de forma dinámica en función del Work Area del monitor activo, restando los píxeles ocupados por paneles, docks o barras de tareas mediante el átomo EWMH _NET_WORKAREA o las geometrías nativas del compositor. Este cálculo se actualizará si el Work Area cambia en tiempo de ejecución, por ejemplo al ocultar o mostrar un panel.
4. Persistencia de Estado
Toda la memoria de grupos y layouts es volátil durante la v1. Reiniciar el daemon, la sesión o el sistema descarta todos los grupos activos. No hay serialización a disco. Las geometrías previas almacenadas por el Toggle de Memoria (sección 11) también son volátiles bajo las mismas condiciones. Este comportamiento es intencionado y declarado explícitamente.

Parte II — Flujo Principal de Snap Layout
5. Menú de Layouts Preconfigurados (Super+Z)
Invocación: atajo global Super+Z, desplegado estrictamente en el monitor donde reside la ventana activa en ese momento.
Prerequisito de ventana activa: si Super+Z es invocado sin una ventana activa elegible —foco en el escritorio, en un panel, o sin ventanas abiertas— el sistema no despliega el menú y emite una notificación breve no intrusiva indicando que no hay ventana elegible. No se produce ningún cambio de estado.
Invocación repetida: si Super+Z es presionado mientras el menú ya está abierto, la segunda pulsación se trata como Esc: el menú se cierra sin modificar ninguna ventana.
Contenido: menú visual interactivo con plantillas de división predefinidas: 1:1, 2/3+1/3, 1/2+1/4+1/4, y otras configurables en config.py. Cada plantilla se representa visualmente como un diagrama de zonas, no como texto. Los layouts cuyo número de zonas supere la cantidad de ventanas elegibles disponibles en el sistema se muestran visualmente deshabilitados, impidiendo su selección.
Navegación: teclas de dirección para moverse entre zonas de la plantilla seleccionada. Enter confirma y envía la ventana activa a la zona destacada. Esc cancela sin modificar ninguna ventana.
Feedback visual activo: al resaltar una zona en el menú, se proyecta simultáneamente un overlay semitransparente sobre la región correspondiente de la pantalla real, indicando el espacio físico exacto que ocupará la ventana. El overlay desaparece al confirmar o cancelar.
Estado de zonas en layouts previos: si el usuario ya tiene ventanas acopladas y abre nuevamente Super+Z, las zonas ya ocupadas se muestran visualmente diferenciadas de las zonas disponibles.
Confirmación visual post-acoplamiento: al completarse el acoplamiento de una ventana, se ejecuta una transición de posición y tamaño de 150 a 250ms que confirma visualmente que la operación finalizó. La duración es configurable y puede desactivarse desde config.py.
6. Snap Assist Automático (Sugerencias Post-Primera Ventana)
Inmediatamente después de colocar la primera ventana en una zona del layout, el sistema identifica matemáticamente los espacios vacíos restantes y despliega en cada uno de ellos un menú interactivo con la lista de ventanas elegibles abiertas en el sistema completo, incluyendo las de otros monitores.
Captura de lista: la lista de ventanas elegibles se captura en el momento exacto en que se inicia el Snap Assist y permanece congelada durante todo el flujo. Las ventanas que aparezcan, desaparezcan o cambien de estado durante el flujo no modifican la lista activa.
Ordenamiento MRU: las ventanas se listan en orden descendente de recencia de uso según el historial MRU mantenido por el daemon. La ventana enfocada más recientemente aparece en primer lugar.
Doble modalidad de selección:

Navegación con teclas de dirección + Enter.
Teclas de acceso rápido por letra: cada ventana listada tiene asignada una tecla visible junto a su nombre, siguiendo el orden físico de la fila superior del teclado activo (en QWERTY: Q, W, E, R, T, Y, …; en AZERTY: A, Z, E, R, T, Y, …). La asignación sigue el orden MRU: la ventana más reciente recibe la primera tecla física. Presionar la tecla asignada selecciona y acopla esa ventana de forma inmediata. La secuencia de teclas utilizada es configurable en config.py.

Traslado entre monitores: al seleccionar una ventana de otro monitor, esta es trasladada al cuadrante del monitor activo. El monitor origen no recibe ninguna acción compensatoria. Sus ventanas restantes mantienen posición y estado.
Interrupción involuntaria: si durante el Snap Assist el foco es robado por una notificación del sistema, una ventana modal emergente, o un clic del usuario en otra ventana, el sistema trata ese evento como un Esc implícito. El menú se cierra, las ventanas ya posicionadas conservan su lugar, y los espacios restantes quedan vacíos.
Cancelación explícita: Esc en cualquier punto del flujo conserva las ventanas ya acopladas y deja los espacios restantes vacíos sin acción adicional.

Parte III — Gestión de Grupos y Pertenencia
7. Pertenencia Exclusiva a un Grupo
Una ventana solo puede pertenecer a un Snap Group a la vez. Al ser acoplada a un nuevo layout, abandona automáticamente el grupo anterior sin requerir confirmación del usuario. Si el grupo anterior queda con una sola ventana tras esa salida, el grupo se disuelve: la ventana restante vuelve a estado flotante independiente sin cambio de geometría.
8. Re-Snap sobre una Ventana ya Acoplada
Si el usuario aplica Super+Z sobre una ventana que ya pertenece a un layout activo, la operación reubica únicamente esa ventana en la nueva zona seleccionada. Las demás ventanas del layout anterior conservan su posición y siguen perteneciendo al grupo. La ventana reubicada pasa a pertenecer al nuevo grupo si se forma uno, o queda en estado flotante si el flujo es cancelado.
9. Cierre de una Ventana Dentro de un Grupo
El daemon escucha eventos DestroyNotify (X11) en tiempo real. Al detectar el cierre de una ventana que pertenece a un grupo activo, la elimina del grupo inmediatamente. Si el grupo resultante queda con una sola ventana, el grupo se disuelve. El espacio físico que deja la ventana cerrada permanece vacío sin acción automática sobre las ventanas restantes.
10. Ventana que Cambia de Tamaño por Sí Misma
Si el daemon detecta un evento ConfigureNotify de resize sobre una ventana acoplada que no fue iniciado por el propio daemon, registra ese evento como un desacoplamiento implícito: la ventana es liberada del grupo con la misma semántica que un arrastre con mouse. El daemon no reimpondrá las dimensiones del layout. El grupo resultante sigue las mismas reglas de disolución de la sección 9.

Parte IV — Comportamiento del Entorno y Casos Borde
11. Restauración de Estado (Toggle de Memoria)
Antes de aplicar cualquier redimensionamiento, el daemon almacena en memoria un par clave-valor por ventana: [window_id]: {x, y, ancho, alto, estado_maximizado}. Al desanclar una ventana del layout, ya sea por arrastre con mouse, por comando de desanclaje, o por desacoplamiento implícito, el sistema restaura exactamente esas dimensiones flotantes originales.
12. Umbral de Tolerancia al Desacoplar con Mouse
Para evitar desacoplamientos accidentales por microdesplazamientos involuntarios durante un clic en la barra de título, el sistema aplica un umbral mínimo de desplazamiento antes de considerar un gesto como arrastre intencional. El valor por defecto es 8px y es configurable en config.py.
13. Restricciones de Tamaño Mínimo de Ventanas
Si una aplicación tiene restricciones de tamaño mínimo que impidan su acoplamiento exacto a una zona, el sistema aplica el comportamiento "Ignorar y Centrar": posiciona la ventana flotante centrada dentro de su zona asignada, con desborde simétrico si es necesario, sin interrumpir el flujo del Snap Assist.
14. Jerarquía de Ventanas Hijas y Modales
El sistema identifica la jerarquía de la ventana seleccionada mediante WM_TRANSIENT_FOR (X11). Si la ventana principal tiene un diálogo modal activo, el redimensionamiento se aplica al padre y la ventana modal se desplaza en bloque manteniéndose centrada sobre él para evitar que quede huérfana u oculta.
15. Filtro de Ventanas Elegibles
El Snap Assist solo presenta como elegibles las ventanas que cumplan simultáneamente todas las condiciones siguientes:

Estar en estado visible (IsViewable / mapeadas gráficamente). Las ventanas minimizadas quedan excluidas.
No tener activada la bandera _NET_WM_STATE_SKIP_TASKBAR.
Pertenecer al tipo _NET_WM_WINDOW_TYPE_NORMAL o equivalente. Las ventanas con tipo Always on Top o en estado de pantalla completa exclusiva quedan excluidas.
No ser la ventana activa que ya ocupa la primera zona del layout en curso.

Las ventanas ubicadas en otro espacio de trabajo (workspace) distinto al activo son elegibles e incluidas en la lista. Al ser seleccionadas, son trasladadas al workspace activo junto con su acoplamiento.

Parte V — Múltiples Monitores
16. Política de Monitor Activo
Todos los flujos (Super+Z, Snap Assist, Snap Groups) operan sobre el monitor donde reside la ventana activa en el momento de la invocación. Los menús y overlays se despliegan siempre en ese monitor.
17. Traslado de Ventanas entre Monitores
Al acoplar una ventana proveniente de otro monitor, esta es trasladada al cuadrante del monitor activo. El monitor origen no recibe ninguna acción compensatoria. Este comportamiento es consistente con Windows 11.
18. Desconexión y Reconexión de Monitores
Al desconectarse un monitor, los grupos asociados a ese monitor se marcan como suspendidos en memoria. Las ventanas que estaban en ese monitor son gestionadas por el WM de forma nativa. Al reconectarse el monitor, los grupos suspendidos se descartan: no se restauran porque la geometría del nuevo estado puede diferir de la original. Este comportamiento es intencionado para la v1.

Parte VI — Productividad Extendida
19. Snap Groups (Super+Alt+Tab)
El daemon mantiene en memoria un mapa {grupo_id: [window_id_1, window_id_2, ...]}. El atajo Super+Alt+Tab trae al frente en bloque todas las ventanas del grupo al que pertenece la ventana actualmente enfocada. Antes de ejecutar el enfoque, el daemon valida que todas las referencias del grupo apunten a ventanas existentes, descartando silenciosamente las inválidas.
Un atajo secundario de consulta (a definir en config.py) despliega un overlay no intrusivo con la lista de ventanas que forman el grupo activo, permitiendo al usuario conocer la composición del grupo antes de invocar Super+Alt+Tab.
20. Discoverability — Ayuda de Atajos
El atajo Super+/ despliega un overlay con la lista completa de atajos activos del sistema, sus descripciones, y el estado actual del daemon: activo/inactivo, número de grupos activos, número de ventanas monitoreadas.

Parte VII — Extensibilidad Futura (Fuera de Alcance v1)
21. Bordes Compartidos Redimensionables
En una versión posterior, las ventanas adyacentes en un layout compartirán bordes interactivos: al arrastrar el borde divisor, ambas ventanas se redimensionarán proporcionalmente de forma simultánea. Esta funcionalidad requiere monitoreo continuo de eventos ConfigureNotify y está fuera del alcance de v1 por su complejidad aislada respecto al flujo principal.
