<!-- =============================================================================
HYDRA-UMC-OS - Platform layer for a CM5 node on Raspberry Pi OS
Copyright (C) JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
GPL-3.0-or-later - see LICENSE
============================================================================= -->

<p align="center">
  <img src="images/HYDRA_UMC_BANNER.svg" alt="HYDRA-UMC-OS banner" width="100%">
</p>

# 🖥️ HYDRA-UMC-OS

<p align="center"><a href="README.md">🇺🇸 English</a> | 🇪🇸 <b>Español</b> | <a href="README_fra.md">🇫🇷 Français</a> | <a href="README_ita.md">🇮🇹 Italiano</a> | <a href="README_deu.md">🇩🇪 Deutsch</a> | <a href="README_zho.md">🇨🇳 简体中文</a> | <a href="README_jpn.md">🇯🇵 日本語</a> | <a href="README_por.md">🇵🇹 Português</a></p>

### La capa de plataforma reproducible de un nodo HYDRA-UMC sobre Raspberry Pi OS

<p align="center">
  <img src="https://img.shields.io/badge/License-GPL%203.0--or--later-blue.svg" alt="GPL 3.0 or later">
  <img src="https://img.shields.io/badge/Platform-Raspberry%20Pi%20OS%20%7C%20CM5-red.svg" alt="Platform">
  <img src="https://img.shields.io/badge/Services-systemd%20%7C%20udev-orange.svg" alt="Services">
  <img src="https://img.shields.io/badge/Stack-Debian%20%7C%20Python%20%7C%20Shell-blueviolet.svg" alt="Stack">
  <img src="https://img.shields.io/badge/Tests-20%20passing-2ea44f.svg" alt="Tests">
  <img src="https://img.shields.io/badge/Version-0.5.4-0f6cbd.svg" alt="Version">
  <img src="https://img.shields.io/badge/Maturity-functional-0F6CBD.svg" alt="Maturity">
</p>

---

> **Estado de seguridad física y de ciberseguridad:** este ecosistema no es un sistema de seguridad certificado. Todavía no existe una ruta de E-STOP por hardware, ni límites ni enclavamientos aplicados por el firmware, ni un comando de movimiento verificado; las imágenes de firmware se comprueban con CRC-32 y una firma Ed25519, y una compilación de versión rechaza las claves de desarrollo publicadas (los cabezales de herramienta y las placas de expansión detrás del relé siguen con cargadores de URTC, que usan un HMAC-SHA256 de clave compartida en lugar de una firma); TLS y TLS mutuo son opcionales y están desactivados por defecto; aún no se ha poblado ni probado ninguna placa propia. Lee la [línea base de seguridad](https://github.com/JuanenRac/HYDRA-UMC-DOCS/blob/main/docs/SECURITY_BASELINE.md) y el [modelo de amenazas](https://github.com/JuanenRac/HYDRA-UMC-DOCS/blob/main/docs/THREAT_MODEL.md) antes de fiarte de cualquier afirmación de aquí para la seguridad de una persona.

---

## 📋 De un vistazo

| | |
|---|---|
| Versión | `0.5.4` |
| Madurez | Funcional |
| Tests | 20 (`python -m unittest discover -s agent/tests`) |
| Tecnología | Raspberry Pi OS ARM64 / Debian/apt / systemd / udev / NetworkManager |
| Destino | La Raspberry Pi CM5 de una celda HYDRA-UMC |
| En hardware real | Todavía no: no consta ninguna ejecución en hardware real para esta versión |

**Ir a:** [Resumen](#-resumen) · [Arquitectura](#-arquitectura) · [Inicio rápido](#-inicio-rápido) · [Pruebas](#-pruebas) · [Estructura del repositorio](#-estructura-del-repositorio) · [Proyectos relacionados](#-proyectos-relacionados)

## 🚦 Estado del proyecto

Cada línea es una parte de este repositorio y la luz dice hasta dónde llega hoy. Se escribe con lo que el repositorio puede demostrar (pruebas, compilaciones, ejecuciones), no con lo previsto.

🟢 Hecho y verificado · 🟡 Funciona, con límites conocidos · 🟠 Hecho a medias o sin verificar · 🔴 Sin hacer o sin funcionar

| Área | Estado | Qué significa aquí |
|---|---|---|
| Software | 🟡 | Funciona para su propósito principal; la comprobación de honestidad de arriba lista lo que aún falta |
| Pruebas | 🟢 | 20 pruebas automáticas, ejecutadas en cada cambio |
| Hardware real | 🔴 | Todavía no: no consta ninguna ejecución en hardware real para esta versión |
| Documentación | 🟢 | README en ocho idiomas, comprobado contra el manifiesto en cada cambio |

## 🎯 Resumen

HYDRA-UMC-OS es la capa de plataforma instalable para un nodo HYDRA-UMC CM5.
Está construido sobre Raspberry Pi OS ARM64; no reemplaza a Linux, el
kernel de Raspberry Pi, systemd, NetworkManager, libcamera o SDK de proveedores.

Su responsabilidad es proporcionar un perfil de dispositivo HYDRA-UMC reproducible:
configuración, ciclo de vida del servicio, identidad local, diagnóstico,
marca visual y actualizaciones coordinadas para los componentes de HYDRA-UMC.

**Verificación de honestidad - qué funciona de verdad hoy:** el agente de dispositivo de solo lectura (`agent/src/hydra_umc_os/agent.py`: `DeviceDescriptor`/`HealthReport`, comprobaciones de temperatura/almacenamiento/red, carga de perfil de configuración) es real y está probado (20 tests unitarios, `agent/tests/test_agent.py`, `python -m unittest discover`). `provisioning/preflight_cm5.py` está verificado como idempotente y sin efectos secundarios mediante un test real que lo ejecuta dos veces y compara la salida (`tools/verify_preflight_idempotent.py`), más 5 comprobaciones reales de rutas negativas (`tools/verify_preflight_negative.py`); el mecanismo de backup/restauración de `provisioning/rollback.py` está verificado por 8 comprobaciones reales, incluyendo un escenario genuino de fallo parcial (`tools/verify_rollback.py`); la máquina de estados de fallback en modo AP de `provisioning/wifi_provision.py` está verificada por 46 comprobaciones reales contra un NetworkManager falso, incluyendo un round-trip HTTP real de extremo a extremo sobre un socket loopback de verdad (`tools/verify_wifi_provision.py`) - ninguna de las tres necesita root ni una CM5 física para verificarse. Lo que nada de esto ha probado: hardware real de una CM5. `image-builder/` es solo documentación (un README de notas de reproducibilidad, sin código de ensamblaje de imagen todavía); `packages/debian/` contiene los scripts del mantenedor y el fichero de copyright del paquete `hydra-umc-platform-base`, que `tools/build_deb.py` construye como un `.deb` real (Python puro, sin dpkg, los mismos bytes cada vez) y que `tools/verify_deb_package.py` vuelve a leer; no se ha instalado en una CM5 real. Ver `CHANGELOG.md` para lo que ya se ha entregado exactamente, y `docs/CM5_SOFTWARE_READINESS.md` para la línea exacta entre lo que está verificado aquí y lo que todavía necesita hardware físico.

## 🧩 Papel en HYDRA-UMC

**HYDRA-UMC-OS** es la capa de plataforma de un nodo CM5: configuración, ciclo de vida de los servicios, identidad local, diagnóstico, imagen visual y actualizaciones coordinadas sobre Raspberry Pi OS, con un agente de dispositivo de solo lectura. No sustituye a Linux, ni a systemd, ni a los SDK de los fabricantes; la imagen la construye `HYDRA-UMC-OS-REBUILDER`.

## 🏛️ Arquitectura

<p align="center">
  <img src="images/architecture.svg" alt="HYDRA-UMC-OS architecture" width="100%">
</p>

## 🚀 Inicio rápido

Las pruebas del agente solo necesitan Python 3.11 o superior; la imagen en sí la construye `HYDRA-UMC-OS-REBUILDER`.

```bash
PYTHONPATH=agent/src python3 -m unittest discover -s agent/tests
./build-test.sh  # non-mutating build check (build-test.bat on Windows)
```

## 🧪 Pruebas

20 pruebas automáticas se ejecutan con `python -m unittest discover -s agent/tests`. No necesitan hardware ni nada fuera de esta máquina.

El CI ejecuta `HYDRA_UMC_CI=1 python tools/ci_validate.py`, que comprueba el manifiesto, los documentos, los ocho README y las imágenes.

## 🏗️ Compilación y publicación

Usa la comprobación de compilación sin versionado antes de una compilación de publicación:

| Acción | Windows | Linux / macOS |
|---|---|---|
| Comprobación de compilación (sin cambiar versión ni CHANGELOG) | `build-test.bat` | `./build-test.sh` |
| Ejecución / desarrollo (cuando exista) | `run*.bat` o `dev*.bat` | `./run*.sh` o `./dev*.sh` |

`build-test.bat` y `build-test.sh` compilan o validan el stack del proyecto sin incrementar `hydra-umc.project.json` ni modificar `CHANGELOG.md`. Solo pueden crear salidas normales del compilador. Los scripts existentes `build*.bat`, `build*.sh`, `run*` y `dev*` conservan su comportamiento específico de versión o ejecución; úsalos cuando necesites ese comportamiento.

## 📂 Estructura del repositorio

<p align="center">
  <img src="images/repository-structure.svg" alt="Repository structure of HYDRA-UMC-OS" width="100%">
</p>

<details>
<summary>Versión en texto del árbol</summary>

```text
HYDRA-UMC-OS/
├── docs/                      Arquitectura, instalación, servicio y actualización de especificaciones.
├── image-builder/             Notas oficiales de reproducibilidad y límites del ensamblaje de imágenes del sistema operativo Raspberry Pi.
├── packages/                  Scripts del mantenedor y copyright del paquete Debian `hydra-umc-platform-base` (construido por `tools/build_deb.py`).
├── agent/                     Descriptor de dispositivo Python de solo lectura y agente de salud con pruebas unitarias.
├── systemd/                   Unidades de ciclo de vida reforzadas `hydra-umc-agent.service` y `hydra-umc-wifi-provision.service`.
├── config/                    Esquemas predeterminados y configuración no secreta.
├── provisioning/              Instaladores de la CM5 (uno por servicio), primer arranque, diagnóstico, recuperación, copia y restauración de los ajustes, cortafuegos, TLS para MQTT, quiosco y pantalla de arranque, reglas de polkit y las comprobaciones de una instalación.
├── tools/                     Herramientas de paquete y de versión (`build_deb.py`, `package_component.py`), las comprobaciones `verify_*.py` de los scripts de aprovisionamiento y las comprobaciones de CI compartidas.
├── .github/                   flujo de CI y plantillas de incidencias
├── images/                    banner e imágenes del README
├── CHANGELOG.md               qué cambió en cada versión
├── build-test.sh              comprobación de compilación sin cambios
├── build.sh                   compila y comprueba; nunca cambia la versión
├── bump_manifest_version.py   sincroniza la versión del manifiesto
├── bump_version.py            subida de versión explícita
├── hydra-umc.project.json     manifiesto: versión, madurez, familia
├── run.sh                     arranca el programa
└── test.sh                    ejecuta las pruebas
```

</details>

## 🗺️ Hoja de ruta y límites conocidos

**Límites conocidos hoy**

**Límites conocidos hoy**

### Estado

El agente base, su configuración no secreta validada, una unidad systemd
reforzada y pruebas del lado del host están implementados. El agente es deliberadamente
solo lectura: el ensamblaje de la imagen de producción y la validación del hardware CM5 permanecen
como puertas de liberación separadas.

La instalación preflight (`provisioning/preflight_cm5.py`) ha demostrado ser
idempotente y libre de efectos secundarios mediante una prueba real - dos
ejecuciones consecutivas producen una salida idéntica byte a byte y no tocan
ningún archivo dentro de este repositorio - y un mecanismo real de copia de
seguridad/reversión independiente del host (`provisioning/rollback.py`)
protege el único archivo del sistema que `install_local_agent.sh`
sobrescribe incondicionalmente en cada ejecución. Ambos se verifican sin
root ni una CM5 - consulte `tools/verify_preflight_idempotent.py` y
`tools/verify_rollback.py`.

**El aprovisionamiento WiFi de primer contacto también es real**
(`provisioning/wifi_provision.py` / `hydra-umc-wifi-provision.service`):
un respaldo real en modo AP de NetworkManager para una CM5 headless sin
red conocida todavía - levanta un hotspot real (`nmcli device wifi
hotspot`) al que el teléfono/portátil de un operador puede unirse para
enviar el SSID/contraseña objetivo real mediante un pequeño formulario
HTTP local, desactiva el AP y se une a la red real en caso de éxito, lo
restaura en caso de fallo para que el dispositivo nunca quede aislado.
La máquina de estados está completamente probada con pruebas unitarias
contra un NetworkManager falso, incluyendo un recorrido HTTP real de
extremo a extremo sobre un socket loopback real - consulte
`tools/verify_wifi_provision.py`. Instalado por `install_cm5_base.sh`
pero deliberadamente no habilitado automáticamente, ya que solo debe ejecutarse en un dispositivo que de verdad lo necesite: la contraseña de su punto de acceso y un código de configuración de un solo uso se generan para cada dispositivo en su primer arranque y se leen una vez del journal - consulte la sección 3 de `provisioning/CM5_DEPLOYMENT_SEQUENCE.md`.

**Los secretos se generan por dispositivo, nunca se toman de una plantilla.** `install_server.sh` e `install_voice_ui.sh` crean sus ficheros env a partir del ejemplo cuando faltan y sustituyen cada valor de ejemplo (`JWT_SECRET`, la contraseña del administrador inicial, el token del relé de voz) por uno aleatorio de este dispositivo (`provisioning/generate_secrets.py`; lo que el operador ya eligió se respeta, y la contraseña del administrador se imprime una sola vez), y después se niegan a continuar si queda un valor de ejemplo o un secreto corto; `preflight_cm5.py` rechaza un `/etc/hydra-umc/*.env` que aún lleve alguno. `install_industrial_gateway.sh` escribe los secretos del stack en `/etc/hydra-umc/gateway.env` (solo root, fuera del checkout del usuario, que compose lee con `--env-file`; un `.env` que dejó en el checkout una versión anterior se mueve allí) (`provisioning/gateway_env.py`: el secreto del gateway y una credencial MQTT y una regla de ACL por cada bridge de máquina). La red Wi-Fi de configuración ya no tiene una contraseña en el código fuente: cada dispositivo genera la suya y un código de configuración de un solo uso en su primer arranque (se lee una vez en el journal, para escribirlo en la etiqueta), el formulario pide el código (se bloquea un minuto tras cinco errores), la red de configuración solo está abierta 30 minutos tras cada arranque y el formulario rechaza peticiones demasiado grandes. Verificado con `tools/verify_generate_secrets.py`, `tools/verify_gateway_env.py` y `tools/verify_wifi_provision.py`. El nombre de host y el nombre de la red de configuración también terminan con seis caracteres tomados del dispositivo (el número de serie de la Raspberry Pi, o si no la dirección MAC), de modo que dos dispositivos grabados con la misma imagen ya no comparten nombre (`provisioning/device_identity.py`, comprobado por `tools/verify_device_identity.py`); `HYDRA_UMC_DEVICE_SUFFIX=off` mantiene los nombres fijos y un nombre que elijas tú nunca se cambia.

**Claves de firma, repartidas por el instalador.** La clave con la que la Voice UI firma el resultado de una confirmación (`HYDRA_UMC_VOICE_UI_RESULT_KEY`) la genera una sola vez para el dispositivo `install_server.sh` o `install_voice_ui.sh`, el que se ejecute primero, y la escribe en `/etc/hydra-umc/server.env` y en `/etc/hydra-umc/voice-ui.env` (a un fichero de una plantilla anterior se le añade la línea), junto con `HYDRA_UMC_VOICE_CONFIRM_REQUIRE_SIGNATURE=1` para el servidor y `HYDRA_UMC_VOICE_UI_REQUIRE_SUBJECT=1` para la Voice UI (`generate_secrets.py --ensure`; una línea que el operador ya tenga, con cualquier valor, nunca se cambia). `install_local_technician.sh` crea la clave que firma el resultado de cada herramienta en `/etc/hydra-umc-local-technician/result.key` (`provisioning/make_result_key.py`: 64 caracteres hexadecimales aleatorios, modo 0600 desde el primer byte, solo root, nunca se imprime, nunca se sustituye una vez que existe, nunca se sigue a través de un enlace simbólico) y apunta a ella el fichero de ajustes; `--no-signing` (o `HYDRA_UMC_LOCAL_TECHNICIAN_SIGNING=off`) deja la línea fuera. Ninguna clave está nunca en la imagen ni en el repositorio, y dos dispositivos nunca comparten una. Verificado por `tools/verify_result_keys.py`.

**Diarios de auditoría, activados por defecto.** `install_local_technician.sh` activa el diario de auditoría del técnico (solo se añade, encadenado por hash) e `install_node_healing.sh` el diario del vigilante (ambos rotan a 5 MiB y conservan 5 ficheros): lo que se le pidió al técnico y lo que el vigilante decidió sobre un nodo es la prueba que importa después de un fallo, así que los instaladores dejan el ajuste activo en un fichero de ajustes documentado (`/etc/hydra-umc-local-technician/local-technician.env`, `/etc/hydra-umc-node-healing/journal.env`). `--no-audit` / `--no-journal` (o `HYDRA_UMC_LOCAL_TECHNICIAN_AUDIT=off`, `HYDRA_UMC_NODE_HEALING_JOURNAL=off`) deja un diario apagado y comenta una línea activa, sin borrar nunca lo registrado; un fichero de ajustes existente no se sobrescribe. `tools/verify_optional_journals.py` comprueba de forma estática las opciones y los nombres; todavía no se ha instalado nada con ellos en una CM5 real.

**Un Go fijado para los servicios Go.** El despachador de trabajos, el vigilante de nodos y el colector de telemetría se compilan en el dispositivo, y su `go.mod` pide un Go más nuevo que el `golang-go` del archivo de Debian, que no podía compilarlos. Sus instaladores ahora cargan `provisioning/go_toolchain.sh`: una versión de go.dev, comprobada contra su SHA-256 fijado antes de descomprimirla en `/usr/local/go-<versión>` (el Go del sistema no se toca). `tools/verify_go_toolchain.py` ejecuta el ayudante con una descarga simulada (un archivo correcto, uno corrupto, uno ya instalado) y compara la versión fijada con el `go.mod` de los proyectos hermanos; todavía no se ha instalado nada con él en una CM5 real.

**Un solo registro de servicios.** El puerto, la ruta de salud y la unidad de systemd de cada servicio salen de `provisioning/ports.yaml` (copia del `contracts/ports.yaml` del SDK, generado a partir de los manifiestos de los proyectos). Cada instalador de un servicio termina diciendo dónde mirar cuando funcione, y `verify_cm5_runtime.sh --with-services` sondea la ruta de salud de cada servicio en marcha (solo lectura; lo que no está en marcha se omite). `tools/verify_service_registry.py` comprueba el ayudante, los instaladores y la comprobación en marcha con simulacros; todavía no se ha instalado nada con ello en una CM5 real.

### Primer hito

Completo, según la seccion Estado de arriba (codigo real, tests
reales, todavia no verificado contra hardware CM5 fisico):

1. ✅ Cree un perfil ARM64 del sistema operativo Raspberry Pi para CM5.
2. ✅ Instale `hydra-umc-platform-base` y `hydra-umc-agent`.
3. ✅ Detectar interfaces CM5 e informar un `DeviceDescriptor` y un `HealthReport`.
4. ✅ Inicie solo los servicios habilitados a través de systemd.
5. ✅ Muestra LISTO, DEGRADADO o FALLO localmente.

## 🌍 Idiomas

Este README y los documentos del repositorio existen en ocho idiomas: inglés, español, alemán, francés, italiano, japonés, chino y portugués (Portugal). Se escriben a la vez y el CI comprueba que los ocho ficheros tengan las mismas secciones y los mismos enlaces. Este repositorio no tiene pantalla ni catálogo de mensajes propios, así que no hay cadenas de interfaz que traducir.

## 🔗 Proyectos relacionados

Este proyecto es parte del ecosistema de robótica HYDRA-UMC del mismo autor (JuanenRac / Electro Hobby 3D). Vale la pena conocerlo, ya que una petición podría en realidad ser sobre alguno de estos en vez de sobre este repositorio.

**Proyectos Hijos**
- **[HYDRA-UMC-SDK](https://github.com/JuanenRac/HYDRA-UMC-SDK)** — el contrato JSON-Schema compartido y la barrera de software de puerta de trabajos contra la que cada bridge valida sus comandos (no es una función de seguridad certificada); contratos versionados, clientes ligeros y fixtures de conformidad utilizados por el propio agente de dispositivo de este sistema operativo.
- **[HYDRA-UMC-OS-REBUILDER](https://github.com/JuanenRac/HYDRA-UMC-OS-REBUILDER)** — herramienta de escritorio Windows/Linux que construye una imagen de este sistema operativo lista para grabar en la CM5, precargada con las versiones más actuales del ecosistema y con configuración de primer arranque al estilo de Raspberry Pi Imager.

**Directamente Relacionados**
- **[HYDRA-UMC](https://github.com/JuanenRac/HYDRA-UMC)** — el diseño de la placa madre del brazo robótico: host CM5 + coprocesador STM32H745 de doble núcleo, pensado para coordinar hasta 8 brazos herramienta por CAN-OTA/SPI-OTA (firmware en fase temprana; todavía no hay ninguna placa poblada); la plataforma de hardware y firmware CM5/MCU que esta capa de sistema operativo configura y supervisa.
- **[HYDRA-UMC-SERVER](https://github.com/JuanenRac/HYDRA-UMC-SERVER)** — el backend headless real (REST/WebSocket) con el que habla de verdad cada cliente de control; el límite de servicio autenticado para las integraciones administradas de este nodo.
- **[URTC](https://github.com/JuanenRac/URTC)** — firmware para la placa física del Universal Robot Tool Controller, más de 25 perfiles de herramienta por bus CAN; una plataforma de controlador de herramientas independiente integrada mediante adaptadores explícitos y versionados.
- **[HYDRA-UMC-UPDATER](https://github.com/JuanenRac/HYDRA-UMC-UPDATER)** — herramienta administrativa de escritorio que descubre, clona y actualiza cada repositorio de este ecosistema; su registro de artefactos, metadatos de compatibilidad y flujo de actualización coordinado.
- **[HYDRA-UMC-CONNECTOR-HUB](https://github.com/JuanenRac/HYDRA-UMC-CONNECTOR-HUB)** — registro declarativo y validador de manifiestos de adaptador para conectores de máquinas externas; extiende la propia idea de contrato del SDK a máquinas externas sin sustituir a los proyectos de pasarela industrial.
- **[HYDRA-UMC-OPS-AGENT](https://github.com/JuanenRac/HYDRA-UMC-OPS-AGENT)** — coordinador de incidencias de mantenimiento: un rol edge de bajo privilegio recopila un snapshot de inventario/salud saneado, un rol control-plane lo renderiza de solo lectura y pide a un proveedor de IA que sugiera un diagnóstico - nunca aplica un parche ni despliega nada.
- **[HYDRA-UMC-DEV-SERVER](https://github.com/JuanenRac/HYDRA-UMC-DEV-SERVER)** — host de desarrollo reproducible (Raspberry Pi 5 / CM5) que almacena el código del ecosistema y ejecuta tareas acotadas de compilación/pruebas bajo una cola duradera; un rol de desarrollo dedicado, explícitamente distinto de un CM5 operativo.

**También Forma Parte del Ecosistema**

*Backend Central y Clientes*
- **[HYDRA-UMC-STUDIO](https://github.com/JuanenRac/HYDRA-UMC-STUDIO)** — panel de control web con visualización 3D multi-robot en tiempo real.
- **[HYDRA-UMC-SUITE](https://github.com/JuanenRac/HYDRA-UMC-SUITE)** — centro de mando de enjambre de escritorio (PySide6) para varios servidores a la vez, empaquetado como ejecutable independiente.
- **[HYDRA-UMC-ANDROID-CONTROL](https://github.com/JuanenRac/HYDRA-UMC-ANDROID-CONTROL)** — app nativa de control para Android con inicio de sesión biométrico y un compañero Wear OS emparejado.
- **[HYDRA-UMC-IOS-CONTROL](https://github.com/JuanenRac/HYDRA-UMC-IOS-CONTROL)** — app de control para iOS/iPadOS (Flutter) con sincronización en tiempo real por WebSocket.
- **[HYDRA-UMC-DSI](https://github.com/JuanenRac/HYDRA-UMC-DSI)** — interfaz táctil nativa para la pantalla táctil DSI de 7" a bordo, embebida en el propio CM5.
- **[HYDRA-UMC-EDITOR-URDF](https://github.com/JuanenRac/HYDRA-UMC-EDITOR-URDF)** — creador/editor gráfico de URDF de escritorio que envía los modelos terminados al propio catálogo de STUDIO.
- **[HYDRA-UMC-EDITOR-STL](https://github.com/JuanenRac/HYDRA-UMC-EDITOR-STL)** — editor de escritorio de modelos STL, que transforma/reemplaza/quita/añade piezas reales en el mismo catálogo de modelos que también edita HYDRA-UMC-EDITOR-URDF.
- **[HYDRA-UMC-BRIDGE-AMR](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-AMR)** — barrera de coordinación para flotas AGV/AMR mediante un publicador MQTT VDA 5050 (probado solo contra una flota emulada).
- **[HYDRA-UMC-BRIDGE-CNC](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-CNC)** — coordinador de alto nivel para celdas CNC con acceso a estado/bytes de control GRBL (probado solo contra un emulador).
- **[HYDRA-UMC-BRIDGE-DROIDS](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-DROIDS)** — barrera de coordinación para droides con patas/humanoides, con un emisor de comandos para Boston Dynamics Spot (probado solo contra un emulador).
- **[HYDRA-UMC-BRIDGE-LASER](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-LASER)** — coordinador de celdas láser que lee 3 señales GPIO de llave/carcasa/enclavamiento (probado solo contra un chip simulado; no puede armar ni disparar un láser).
- **[HYDRA-UMC-BRIDGE-OPENPNP](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-OPENPNP)** — coordinador de alto nivel seguro para el flujo de placas de pick-and-place OpenPnP.
- **[HYDRA-UMC-BRIDGE-PRINTER3D](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-PRINTER3D)** — barrera de coordinación segura para impresoras 3D Moonraker/Klipper, con comandos de trabajo reales y controlados.
- **[HYDRA-UMC-BRIDGE-ROS2](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-ROS2)** — coordinador con un transporte ROS 2 rclpy importado de forma perezosa (todavía no ejecutado contra una instalación de ROS 2).
- **[HYDRA-UMC-BRIDGE-UAV](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-UAV)** — barrera de coordinación para UAV equipados con cámara, con un emisor de comandos MAVLink (probado solo contra un emulador).

*Plataforma de Herramientas URTC*
- **[URTC-FLASHER](https://github.com/JuanenRac/URTC-FLASHER)** — herramienta de escritorio con GUI para flashear placas URTC, CAN-OTA más SWD/JTAG de chip completo.
- **[URTC-TESTER](https://github.com/JuanenRac/URTC-TESTER)** — herramienta de escritorio de diagnóstico CAN-bus en vivo para placas URTC, un panel por perfil de herramienta.
- **[URTC-WEB-STUDIO](https://github.com/JuanenRac/URTC-WEB-STUDIO)** — alternativa basada en navegador a URTC-TESTER mediante la Web Serial API, sin instalación local.
- **[URTC-GATEWAY](https://github.com/JuanenRac/URTC-GATEWAY)** — pasarela delante del bus CAN de URTC: lista de identificadores permitidos, límite de tasa y clave de sesión; software probado en ordenador, aún no en un bus real.

*Nodo IA de Visión (Hailo-8)*
- **[HYDRA-UMC-VISION-NODE](https://github.com/JuanenRac/HYDRA-UMC-VISION-NODE)** — nodo de integración para el pipeline de visión Hailo-8, con una comprobación real de disponibilidad de hardware por etapa.
- **[HYDRA-UMC-DETECTION-HEF](https://github.com/JuanenRac/HYDRA-UMC-DETECTION-HEF)** — registro real de modelos compilados con verificación de carga segura por arquitectura Hailo/checksum.
- **[HYDRA-UMC-VISION-STREAMER](https://github.com/JuanenRac/HYDRA-UMC-VISION-STREAMER)** — generador real de pipeline GStreamer + config MediaMTX, con una frontera de integración HailoRT real.
- **[HYDRA-UMC-VISUAL-SERVOING-API](https://github.com/JuanenRac/HYDRA-UMC-VISUAL-SERVOING-API)** — ley de corrección Position-Based Visual Servoing con autorización condicionada al estado de zona; todavía sin estimación de pose por cámara.
- **[HYDRA-UMC-SAFETY-ZONES](https://github.com/JuanenRac/HYDRA-UMC-SAFETY-ZONES)** — lógica v0 de invasión de zona, vigencia de calibración y solicitud de E-STOP que toma las posiciones de los objetos de un fichero; ningún detector la alimenta y todavía no hay un E-STOP físico conectado.

*Nodo IA Cognitivo (Hailo-10)*
- **[HYDRA-UMC-COGNITIVE-NODE](https://github.com/JuanenRac/HYDRA-UMC-COGNITIVE-NODE)** — nodo de integración para el pipeline cognitivo Hailo-10 (orquestación de LLM/VLA/voz).
- **[HYDRA-UMC-VLA-ENGINE](https://github.com/JuanenRac/HYDRA-UMC-VLA-ENGINE)** — codificación/decodificación real de tokens de acción y generación de trayectoria para un modelo Vision-Language-Action.
- **[HYDRA-UMC-VOICE-UI](https://github.com/JuanenRac/HYDRA-UMC-VOICE-UI)** — front-end de voz real (VAD + analizador de intención) con un relé a Watch acotado y con confirmación.
- **[HYDRA-UMC-SEMANTIC-PLANNER](https://github.com/JuanenRac/HYDRA-UMC-SEMANTIC-PLANNER)** — descomposición real de tareas basada en reglas y recuperación semántica de errores sobre códigos de error del MCU.
- **[HYDRA-UMC-DOCS-QA](https://github.com/JuanenRac/HYDRA-UMC-DOCS-QA)** — búsqueda real de documentos TF-IDF (solo librería estándar) sobre los propios documentos Markdown de este ecosistema.
- **[HYDRA-UMC-LOCAL-TECHNICIAN](https://github.com/JuanenRac/HYDRA-UMC-LOCAL-TECHNICIAN)** — técnico de mantenimiento con IA local y con puertas de política para el propio ecosistema - observa, diagnostica y propone arreglos; los dos niveles de riesgo más altos están deliberadamente sin implementar todavía.

*Orquestación y Enjambre*
- **[HYDRA-UMC-ORCHESTRATOR](https://github.com/JuanenRac/HYDRA-UMC-ORCHESTRATOR)** — nodo de integración con un contrato real de informe de salud gRPC/Protobuf y una máquina de estados de misión.
- **[HYDRA-UMC-JOB-DISPATCHER](https://github.com/JuanenRac/HYDRA-UMC-JOB-DISPATCHER)** — cola de trabajos real basada en prioridad con deduplicación, sobre una API HTTP real.
- **[HYDRA-UMC-NODE-HEALING](https://github.com/JuanenRac/HYDRA-UMC-NODE-HEALING)** — watchdog de salud de flota real basado en gRPC, con reintento/backoff y detección de discrepancia de identidad.
- **[HYDRA-UMC-PATH-PLANNER-3D](https://github.com/JuanenRac/HYDRA-UMC-PATH-PLANNER-3D)** — planificador de rutas 3D real basado en RRT, con validación real de colisión de obstáculos/espacio de trabajo.
- **[HYDRA-UMC-SWARM-SYNC](https://github.com/JuanenRac/HYDRA-UMC-SWARM-SYNC)** — sincronización de estado real mediante CRDT LWW-Element-Map, con pruebas de propiedades para convergencia multi-celda.

*Gemelo Digital y Simulación*
- **[HYDRA-UMC-TWIN](https://github.com/JuanenRac/HYDRA-UMC-TWIN)** — nodo de integración para el motor de gemelo digital, con un contrato real de sincronización por compatibilidad de versión.
- **[HYDRA-UMC-HIL-BRIDGE](https://github.com/JuanenRac/HYDRA-UMC-HIL-BRIDGE)** — enrutador hardware-in-the-loop con un enclavamiento de software por colisión entre simulación y hardware real (probado sin hardware real).
- **[HYDRA-UMC-PHYSICS-REPLICA](https://github.com/JuanenRac/HYDRA-UMC-PHYSICS-REPLICA)** — cinemática directa real y validación de límites articulares sobre un subconjunto real de URDF.
- **[HYDRA-UMC-SYNTHETIC-DATA-GEN](https://github.com/JuanenRac/HYDRA-UMC-SYNTHETIC-DATA-GEN)** — generador real de escenas 2D procedurales con exportación de anotaciones YOLO/COCO.

*Datos y Analítica*
- **[HYDRA-UMC-DATALAKE](https://github.com/JuanenRac/HYDRA-UMC-DATALAKE)** — almacén de series temporales real respaldado por sqlite3, con una API HTTP real de ingesta/consulta.
- **[HYDRA-UMC-ANOMALY-DETECTOR](https://github.com/JuanenRac/HYDRA-UMC-ANOMALY-DETECTOR)** — detector de anomalías real basado en FFT + línea base estadística, con monitorización de deriva.
- **[HYDRA-UMC-PRODUCTION-REPORTS](https://github.com/JuanenRac/HYDRA-UMC-PRODUCTION-REPORTS)** — cálculo real de OEE/disponibilidad sobre el histórico de DATALAKE, con exportación CSV reproducible.
- **[HYDRA-UMC-TELEMETRY-COLLECTOR](https://github.com/JuanenRac/HYDRA-UMC-TELEMETRY-COLLECTOR)** — pipeline real de ingesta CAN/WebSocket hacia DATALAKE, con deduplicación por secuencia.

*Pasarela Industrial*
- **[HYDRA-UMC-GATEWAY-INDUSTRIAL](https://github.com/JuanenRac/HYDRA-UMC-GATEWAY-INDUSTRIAL)** — nodo de integración que retransmite a protocolos industriales, con una capa real de lista blanca de comandos/contrapresión.
- **[HYDRA-UMC-OPCUA-SERVER](https://github.com/JuanenRac/HYDRA-UMC-OPCUA-SERVER)** — espacio de direcciones OPC-UA real, verificado con una sesión de cliente real del protocolo binario.
- **[HYDRA-UMC-MQTT-BROKER](https://github.com/JuanenRac/HYDRA-UMC-MQTT-BROKER)** — broker MQTT real con autenticación por cliente opcional y ACL de tópicos.
- **[HYDRA-UMC-MTCONNECT-ADAPTER](https://github.com/JuanenRac/HYDRA-UMC-MTCONNECT-ADAPTER)** — endpoints XML reales `/probe` y `/current` de MTConnect, con salida en modo degradado.

*Herramientas Complementarias y Operaciones del Ecosistema*
- **[HYDRA-UMC-DASHBOARD-AI](https://github.com/JuanenRac/HYDRA-UMC-DASHBOARD-AI)** — paneles de Resúmenes Inteligentes y Resaltado de Anomalías sobre DATALAKE/ANOMALY-DETECTOR, con un respaldo estadístico honesto.
- **[HYDRA-UMC-TOOL-CLI](https://github.com/JuanenRac/HYDRA-UMC-TOOL-CLI)** — CLI de flota con un contrato real y estable de códigos de salida, cliente real y en vivo de la propia API de HYDRA-UMC-SERVER.
- **[HYDRA-UMC-WATCH](https://github.com/JuanenRac/HYDRA-UMC-WATCH)** — app compañera de WearOS con patrones de alerta háptica y un relé de voz al teléfono emparejado (todavía no ejecutada en un reloj físico).
- **[URTC-SMART-RACK](https://github.com/JuanenRac/URTC-SMART-RACK)** — firmware para un rack de montaje de placas con decodificación real de ID de herramienta y lógica de precalentamiento Smart Idle.
- **[URTC-VISION-TOOL](https://github.com/JuanenRac/URTC-VISION-TOOL)** — firmware más un compañero de visión real en Python para un cabezal de inspección térmica/RGB.

## 📚 Documentación

Dónde leer más:

* **[`docs/AGENT_REFERENCE.md`](docs/AGENT_REFERENCE.md)** — referencia real de comandos/salida de `hydra-umc-agent`, la CLI de diagnóstico de solo lectura.
* **[`docs/INSTALLATION.md`](docs/INSTALLATION.md)** — diseño de la instalación: plataforma objetivo y secuencia de instalación prevista.
* **[`docs/CM5_PROVISIONING.md`](docs/CM5_PROVISIONING.md)** — la guía completa para convertir Raspberry Pi OS Lite en HYDRA-UMC-OS.
* **[`docs/CM5_WINDOWS_HOST_FLASHING.md`](docs/CM5_WINDOWS_HOST_FLASHING.md)** — el procedimiento verificado para flashear una CM5 desde un host Windows.
* **[`docs/CM5_FIRST_BOOT_CHECKLIST.md`](docs/CM5_FIRST_BOOT_CHECKLIST.md)** — una checklist de plataforma BASE para el primer arranque de una CM5.
* **[`docs/CM5_PACKAGE_MANIFEST.md`](docs/CM5_PACKAGE_MANIFEST.md)** — la lista real de paquetes por fase de despliegue.
* **[`docs/CM5_ECOSYSTEM_DEPLOYMENT.md`](docs/CM5_ECOSYSTEM_DEPLOYMENT.md)** — el plan de despliegue por fases, cada una revertible por separado, del resto del ecosistema sobre una CM5.
* **[`docs/CM5_SOFTWARE_READINESS.md`](docs/CM5_SOFTWARE_READINESS.md)** — qué se ha verificado sin hardware CM5 físico, y dónde se detiene esa verificación.
* **[`docs/SERVICE_MODEL.md`](docs/SERVICE_MODEL.md)** — cómo corren los servicios HYDRA-UMC: usuarios dedicados, rutas de configuración, orden de dependencia/disponibilidad.
* **[`docs/UPDATE_MODEL.md`](docs/UPDATE_MODEL.md)** — los canales de actualización separados para el SO, los paquetes HYDRA-UMC, los runtimes Hailo y el firmware MCU/URTC.
* **[`docs/SDK_INTEGRATION_BOUNDARY.md`](docs/SDK_INTEGRATION_BOUNDARY.md)** — cómo este repo consume el contrato publicado de HYDRA-UMC-SDK sin vendorizarlo.
* **[`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md)** — reglas de desarrollo: interfaces nativas de Raspberry Pi OS primero, el orden de pruebas exigido.
* **[`docs/HEADER_CONVENTION.md`](docs/HEADER_CONVENTION.md)** — la convención de cabecera de copyright/licencia para archivos nuevos de código y documentación.
* **[`provisioning/ssh_hardening.md`](provisioning/ssh_hardening.md)** — los pasos reales de hardening de SSH para una CM5 (verificar el login por clave antes de desactivar la autenticación por contraseña).
* [Base de seguridad del ecosistema](https://github.com/JuanenRac/HYDRA-UMC-DOCS/blob/main/docs/SECURITY_BASELINE.md)
* [Modelo de amenazas del ecosistema](https://github.com/JuanenRac/HYDRA-UMC-DOCS/blob/main/docs/THREAT_MODEL.md)
* [Historial de cambios de este repositorio](CHANGELOG.md)
* [Licencia de este repositorio](LICENSE.md)

## 🤝 Contribuir y comunidad

* Antes de un pull request ejecuta `HYDRA_UMC_CI=1 py -3 tools/ci_validate.py` (o `HYDRA_UMC_CI=1 python3 tools/ci_validate.py`): debe imprimir `CI_VALIDATION=PASS`. No ejecutes `build.sh` ni `build.bat` para esta comprobación; compilar no es comprobar.
* Los ocho README se escriben desde una sola fuente en HYDRA-UMC-DOCS; no los edites a mano. Cambia la fuente y vuelve a escribirlos con `tools/make_readmes.py`.
* No afirmes en un README lo que no se ha ejecutado: di «simulado» o «sin probar en hardware» cuando esa sea la verdad.
* Mira [CONTRIBUTING.md](CONTRIBUTING.md), el [código de conducta](CODE_OF_CONDUCT.md), [SECURITY.md](SECURITY.md) y [SUPPORT.md](SUPPORT.md).

## 👤 AUTOR

**JuanenRac (Electro Hobby 3D)** · electrohobby3d@gmail.com

## 📜 LICENCIA

GPL-3.0-or-later - [LICENSE](LICENSE).
