<!--
================================================================================
HYDRA-UMC-OS: descripción general del proyecto público y guía de implementación
Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
CC BY-SA 4.0 - ver LICENCIA.md
================================================================================
-->

<p align="center">
  <img src="images/HYDRA_UMC_BANNER.svg" alt="Banner de HYDRA-UMC-OS" width="100%">
</p>

<p align="center">
  <a href="README.md">🇺🇸 English</a> |
  <a href="README_spa.md">🇪🇸 Español</a> |
  <a href="README_fra.md">🇫🇷 Francés</a> |
  <a href="README_ita.md">🇮🇹 Italiano</a> |
  <a href="README_deu.md">🇩🇪 Alemán</a> |
  <a href="README_zho.md">🇨🇳 简体中文</a> |
  <a href="README_jpn.md">🇯🇵 日本語</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/License-GPL%203.0-blue.svg" alt="Licencia: GPL 3.0">
  <img src="https://img.shields.io/badge/Platform-Raspberry%20Pi%20OS%20%7C%20CM5-red.svg" alt="Plataforma: SO Raspberry Pi | CM5">
  <img src="https://img.shields.io/badge/Services-systemd%20%7C%20udev-orange.svg" alt="Servicios: systemd | udev">
  <img src="https://img.shields.io/badge/Stack-Debian%20%7C%20Python%20%7C%20Shell-blueviolet.svg" alt="Pila: Debian | Python | Shell">
</p>

# HYDRA-UMC-OS

## 🖥️ Capa de plataforma HYDRA-UMC para el sistema operativo Raspberry Pi

HYDRA-UMC-OS es la capa de plataforma instalable para un nodo HYDRA-UMC CM5.
Está construido sobre Raspberry Pi OS ARM64; no reemplaza a Linux, el
Kernel de Raspberry Pi, systemd, NetworkManager, libcamera o SDK de proveedores.

Su responsabilidad es proporcionar un perfil de dispositivo HYDRA-UMC reproducible:
configuración, ciclo de vida del servicio, identidad local, diagnóstico, visual
marca y actualizaciones coordinadas para los componentes de HYDRA-UMC.

## 🚧 Estado

El agente base, su configuración no secreta validada, un sistema reforzado
Se implementan pruebas de unidad y del lado del host. El agente es deliberadamente
solo lectura: el ensamblaje de la imagen de producción y la validación del hardware CM5 permanecen
puertas de liberación separadas.

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
pero deliberadamente no habilitado automáticamente, ya que no debe
arrancar con su propia contraseña de AP de marcador de posición en un
dispositivo real accesible de forma inalámbrica - consulte la sección 3
de `provisioning/CM5_DEPLOYMENT_SEQUENCE.md` para el paso de la
contraseña real requerido primero.

## 🎯 Primer hito planificado

1. Cree un perfil ARM64 del sistema operativo Raspberry Pi para CM5.
2. Instale `hydra-umc-platform-base` y `hydra-umc-agent`.
3. Detectar interfaces CM5 e informar un `DeviceDescriptor` y un `HealthReport`.
4. Inicie solo los servicios habilitados a través de systemd.
5. Muestra LISTO, DEGRADADO, INHIBIDO o FALLO localmente.

## 📂 Diseño del repositorio

<p align="center">
  <img src="images/REPOSITORY_LAYOUT.svg" alt="Mapa visual del diseño del repositorio de HYDRA-UMC-OS" width="100%">
</p>

| Camino | Propósito |
| --- | --- |
| `docs/` | Arquitectura, instalación, servicio y actualización de especificaciones. |
| `image-builder/` | Notas oficiales de reproducibilidad y límites del ensamblaje de imágenes del sistema operativo Raspberry Pi. |
| `packages/` | Metadatos del paquete Debian para `hydra-umc-platform-base`. |
| `agent/` | Descriptor de dispositivo Python de solo lectura y agente de salud con pruebas unitarias. |
| `systemd/` | Unidad de ciclo de vida reforzada `hydra-umc-agent.service`. |
| `config/` | Esquemas predeterminados y configuración no secreta. |

Lea [la arquitectura](docs/ARCHITECTURE.md) antes de implementar el código.

## 🛠️ BUILD Y EJECUCIÓN

Usa la comprobación de compilación sin versionado antes de una compilación de publicación:

| Acción | Windows | Linux / macOS |
|---|---|---|
| Comprobación de compilación (sin cambiar versión ni CHANGELOG) | `build-test.bat` | `./build-test.sh` |
| Ejecución / desarrollo (cuando exista) | `run*.bat` o `dev*.bat` | `./run*.sh` o `./dev*.sh` |

`build-test.bat` y `build-test.sh` compilan o validan el stack del proyecto sin incrementar `hydra-umc.project.json` ni modificar `CHANGELOG.md`. Solo pueden crear salidas normales del compilador. Los scripts existentes `build*.bat`, `build*.sh`, `run*` y `dev*` conservan su comportamiento específico de versión o ejecución; úsalos cuando necesites ese comportamiento.

## 🔗 Proyectos relacionados

> Mapa canónico de relaciones entre ecosistemas públicos.

| Proyecto | Relación con HYDRA-UMC-OS |
| --- | --- |
| [HYDRA-UMC-SDK](https://github.com/JuanenRac/HYDRA-UMC-SDK) | Contratos versionados, clientes ligeros y dispositivos de conformidad utilizados por el agente del dispositivo. |
| [HYDRA-UMC-SERVER](https://github.com/JuanenRac/HYDRA-UMC-SERVER) | Límite de servicio autenticado para las integraciones administradas del nodo. |
| [HYDRA-UMC-UPDATER](https://github.com/JuanenRac/HYDRA-UMC-UPDATER) | Registro de artefactos, metadatos de compatibilidad y flujo de trabajo de actualización coordinado. |
| [HYDRA-UMC](https://github.com/JuanenRac/HYDRA-UMC) | Plataforma de hardware y firmware CM5/MCU que la capa del sistema operativo configura y supervisa. |
| [URTC](https://github.com/JuanenRac/URTC) | Plataforma de controlador de herramientas independiente integrada a través de adaptadores versionados explícitos. |

**Resto del ecosistema:** explore las siete capas públicas en el [panel del ecosistema JuanenRac](https://juanenrac.github.io/JuanenRac/).

## 👤 AUTOR
**JuanenRac** (Electro Hobby 3D)
📧 electrohobby3d@gmail.com
📺 [youtube.com/@electrohobby3d](https://youtube.com/@electrohobby3d)

## 📜 LICENCIA

El código es GPL-3.0 o posterior y la documentación es CC BY-SA 4.0. Consulte [LICENCIA](LICENSE).
