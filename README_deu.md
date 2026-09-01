<!--
=========================================================================
HYDRA-UMC-OS – Öffentliche Projektübersicht und Implementierungsleitfaden
Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
CC BY-SA 4.0 – siehe LICENSE.md
=========================================================================
-->

<p align="center">
  <img src="images/HYDRA_UMC_BANNER.svg" alt="HYDRA-UMC-OS-Banner" width="100%">
</p>

<p align="center">
  <a href="README.md">???? English</a> |
  <a href="README_spa.md">🇪🇸 Spanisch</a> |
  <a href="README_fra.md">🇫🇷 Französisch</a> |
  <a href="README_ita.md">🇮🇹 Italienisch</a> |
  <a href="README_deu.md">🇩🇪 Deutsch</a> |
  <a href="README_zho.md">🇨🇳 简体中文</a> |
  <a href="README_jpn.md">🇯🇵 日本語</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/License-GPL%203.0-blue.svg" alt="Lizenz: GPL 3.0">
  <img src="https://img.shields.io/badge/Platform-Raspberry%20Pi%20OS%20%7C%20CM5-red.svg" alt="Plattform: Raspberry Pi OS | CM5">
  <img src="https://img.shields.io/badge/Services-systemd%20%7C%20udev-orange.svg" alt="Dienste: systemd | udev">
  <img src="https://img.shields.io/badge/Stack-Debian%20%7C%20Python%20%7C%20Shell-blueviolet.svg" alt="Stack: Debian | Python | Shell">
</p>

# HYDRA-UMC-OS

## 🖥️ HYDRA-UMC-Plattformschicht für Raspberry Pi OS

HYDRA-UMC-OS ist die installierbare Plattformschicht für einen HYDRA-UMC CM5-Knoten.
Es basiert auf Raspberry Pi OS ARM64; Es ersetzt nicht Linux, das
Raspberry Pi-Kernel, systemd, NetworkManager, libcamera oder Hersteller-SDKs.

Seine Aufgabe besteht darin, ein reproduzierbares HYDRA-UMC-Geräteprofil bereitzustellen:
Konfiguration, Servicelebenszyklus, lokale Identität, Diagnose, visuell
Branding und koordinierte Updates für HYDRA-UMC-Komponenten.

## 🚧 Status

Der Basisagent, seine validierte, nicht geheime Konfiguration, ein gehärtetes Systemd
Unit- und Host-seitige Tests sind implementiert. Der Agent ist bewusst
schreibgeschützt: Produktions-Image-Assemblierung und CM5-Hardwarevalidierung bleiben bestehen
separate Freigabetore.

Die Installations-Preflight-Prüfung (`provisioning/preflight_cm5.py`)
erweist sich durch einen echten Test als idempotent und frei von
Nebenwirkungen - zwei aufeinanderfolgende Durchläufe erzeugen eine
byteidentische Ausgabe und greifen auf keine Datei innerhalb dieses
Repositorys zu - und ein echter, hostunabhängiger
Backup-/Rollback-Mechanismus (`provisioning/rollback.py`) schützt die eine
Systemdatei, die `install_local_agent.sh` bei jedem Lauf bedingungslos
überschreibt. Beide werden ohne Root-Rechte oder eine CM5 verifiziert -
siehe `tools/verify_preflight_idempotent.py` und
`tools/verify_rollback.py`.

## 🎯 Geplanter erster Meilenstein

1. Erstellen Sie ein Raspberry Pi OS ARM64-Profil für CM5.
2. Installieren Sie „hydra-umc-platform-base“ und „hydra-umc-agent“.
3. CM5-Schnittstellen erkennen und einen „DeviceDescriptor“ und einen „HealthReport“ melden.
4. Starten Sie nur aktivierte Dienste über systemd.
5. Zeigen Sie lokal BEREIT, DEGRADED, GESPERRT oder FEHLER an.

## 📂 Repository-Layout

<p align="center">
  <img src="images/REPOSITORY_LAYOUT.svg" alt="Visuelle Karte des HYDRA-UMC-OS-Repository-Layouts" width="100%">
</p>

| Pfad | Zweck |
| --- | --- |
| `docs/` | Architektur-, Installations-, Service- und Update-Spezifikationen. |
| `image-builder/` | Offizielle Hinweise zur Bildassemblierung und Reproduzierbarkeit des Raspberry Pi OS. |
| `Pakete/` | Metadaten des Debian-Pakets für „hydra-umc-platform-base“. |
| `agent/` | Schreibgeschützter Python-Gerätedeskriptor und Integritätsagent mit Komponententests. |
| `systemd/` | Gehärtete Lebenszykluseinheit „hydra-umc-agent.service“. |
| `config/` | Standardschemata und nicht geheime Konfiguration. |

Lesen Sie [die Architektur](docs/ARCHITECTURE.md), bevor Sie Code implementieren.

## 🛠️ BUILD UND AUSFÜHRUNG

Verwenden Sie den Build-Check ohne Versionierung vor einem Release-Build:

| Aktion | Windows | Linux / macOS |
|---|---|---|
| Build-Check (ohne Änderung von Version oder CHANGELOG) | `build-test.bat` | `./build-test.sh` |
| Ausführung / Entwicklung (falls vorhanden) | `run*.bat` oder `dev*.bat` | `./run*.sh` oder `./dev*.sh` |

`build-test.bat` und `build-test.sh` kompilieren oder validieren den Projekt-Stack, ohne `hydra-umc.project.json` zu erhöhen oder `CHANGELOG.md` zu verändern. Sie dürfen nur normale Compiler-Ausgaben erzeugen. Die vorhandenen Skripte `build*.bat`, `build*.sh`, `run*` und `dev*` behalten ihr projektbezogenes Versions- oder Laufzeitverhalten bei; verwenden Sie sie, wenn dieses Verhalten benötigt wird.

## 🔗 Verwandte Projekte

> Kanonische Karte der öffentlichen Ökosystembeziehungen.

| Projekt | Beziehung zu HYDRA-UMC-OS |
| --- | --- |
| [HYDRA-UMC-SDK](https://github.com/JuanenRac/HYDRA-UMC-SDK) | Versionierte Verträge, Thin Clients und Konformitätsvorkehrungen, die vom Geräteagenten verwendet werden. |
| [HYDRA-UMC-SERVER](https://github.com/JuanenRac/HYDRA-UMC-SERVER) | Authentifizierte Dienstgrenze für die verwalteten Integrationen des Knotens. |
| [HYDRA-UMC-UPDATER](https://github.com/JuanenRac/HYDRA-UMC-UPDATER) | Artefaktregistrierung, Kompatibilitätsmetadaten und koordinierter Update-Workflow. |
| [HYDRA-UMC](https://github.com/JuanenRac/HYDRA-UMC) | CM5/MCU-Hardware- und Firmware-Plattform, die die Betriebssystemschicht konfiguriert und überwacht. |
| [URTC](https://github.com/JuanenRac/URTC) | Unabhängige Tool-Controller-Plattform, integriert durch explizite, versionierte Adapter. |

**Rest des Ökosystems:** Erkunden Sie die sieben öffentlichen Ebenen im [JuanenRac-Ökosystem-Dashboard](https://juanenrac.github.io/JuanenRac/).

## 📜 Lizenz

Der Code ist GPL-3.0-or-later und die Dokumentation ist CC BY-SA 4.0. Siehe [LICENSE](LICENSE).
