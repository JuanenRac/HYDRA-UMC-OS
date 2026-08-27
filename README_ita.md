<!--
==============================================================================
HYDRA-UMC-OS - Panoramica del progetto pubblico e guida all'implementazione
Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
CC BY-SA 4.0 - vedere LICENZA.md
==============================================================================
-->

<p align="center">
  <img src="images/HYDRA_UMC_BANNER.svg" alt="HYDRA-UMC-OS banner" width="100%">
</p>

<p align="center">
  <a href="README.md">???? English</a> |
  <a href="README_spa.md">🇪🇸 Español</a> |
  <a href="README_fra.md">🇫🇷 Français</a> |
  <a href="README_ita.md">🇮🇹 Italiano</a> |
  <a href="README_deu.md">🇩🇪 Tedesco</a> |
  <a href="README_zho.md">🇨🇳 简体中文</a> |
  <a href="README_jpn.md">🇯🇵 日本語</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/License-GPL%203.0-blue.svg" alt="Licenza: GPL 3.0">
  <img src="https://img.shields.io/badge/Platform-Raspberry%20Pi%20OS%20%7C%20CM5-red.svg" alt="Piattaforma: sistema operativo Raspberry Pi | CM5">
  <img src="https://img.shields.io/badge/Services-systemd%20%7C%20udev-orange.svg" alt="Servizi: systemd | udev">
  <img src="https://img.shields.io/badge/Stack-Debian%20%7C%20Python%20%7C%20Shell-blueviolet.svg" alt="Stack: Debian | Python | Shell">
</p>

# HYDRA-UMC-OS

## 🖥️ Livello della piattaforma HYDRA-UMC per il sistema operativo Raspberry Pi

HYDRA-UMC-OS è il livello della piattaforma installabile per un nodo HYDRA-UMC CM5.
È basato sul sistema operativo Raspberry Pi ARM64; non sostituisce Linux, il
Kernel Raspberry Pi, systemd, NetworkManager, libcamera o SDK del fornitore.

La sua responsabilità è fornire un profilo riproducibile del dispositivo HYDRA-UMC:
configurazione, ciclo di vita del servizio, identità locale, diagnostica, visualizzazione
branding e aggiornamenti coordinati per i componenti HYDRA-UMC.

## 🚧Stato

L'agente di base, la sua configurazione non segreta convalidata, un systemd rafforzato
unità e vengono implementati i test lato host. L'agente lo è deliberatamente
di sola lettura: rimangono l'assemblaggio dell'immagine di produzione e la convalida dell'hardware CM5
cancelli di rilascio separati.

## 🎯 Primo traguardo previsto

1. Crea un profilo ARM64 del sistema operativo Raspberry Pi per CM5.
2. Installa "hydra-umc-platform-base" e "hydra-umc-agent".
3. Rileva le interfacce CM5 e segnala un `DeviceDescriptor` e un `HealthReport`.
4. Avvia solo i servizi abilitati tramite systemd.
5. Visualizzare localmente PRONTO, DEGRADATO, INIBITO o GUASTO.

## 📂 Layout del repository

<p align="center">
  <img src="images/REPOSITORY_LAYOUT.svg" alt="Mappa visiva del layout del repository HYDRA-UMC-OS" width="100%">
</p>

| Percorso | Scopo |
| --- | --- |
| `documenti/` | Specifiche di architettura, installazione, servizio e aggiornamento. |
| `costruttore di immagini/` | Note ufficiali sui limiti di assemblaggio delle immagini e sulla riproducibilità del sistema operativo Raspberry Pi. |
| `pacchetti/` | Metadati del pacchetto Debian per `hydra-umc-platform-base`. |
| "agente/" | Descrittore del dispositivo Python di sola lettura e agente di integrità con test unitari. |
| `systemd/` | Unità del ciclo di vita "hydra-umc-agent.service" rafforzata. |
| `config/` | Schemi predefiniti e configurazione non segreta. |

Leggi [l'architettura](docs/ARCHITECTURE.md) prima di implementare il codice.

## 🔗Progetti correlati

> Mappa delle relazioni canoniche dell'ecosistema pubblico.

| Progetto | Rapporto con HYDRA-UMC-OS |
| --- | --- |
| [HYDRA-UMC-SDK](https://github.com/JuanenRac/HYDRA-UMC-SDK) | Contratti con versione, thin client e dispositivi di conformità utilizzati dall'agente del dispositivo. |
| [SERVER-HYDRA-UMC](https://github.com/JuanenRac/HYDRA-UMC-SERVER) | Limite del servizio autenticato per le integrazioni gestite del nodo. |
| [HYDRA-UMC-UPDATER](https://github.com/JuanenRac/HYDRA-UMC-UPDATER) | Registro degli artefatti, metadati di compatibilità e flusso di lavoro di aggiornamento coordinato. |
| [HYDRA-UMC](https://github.com/JuanenRac/HYDRA-UMC) | Piattaforma hardware e firmware CM5/MCU configurata e supervisionata dal livello del sistema operativo. |
| [URTC](https://github.com/JuanenRac/URTC) | Piattaforma tool-controller indipendente integrata tramite adattatori espliciti con versione. |

**Resto dell'ecosistema:** esplora i sette livelli pubblici nella [dashboard dell'ecosistema JuanenRac](https://juanenrac.github.io/JuanenRac/).

## 📜 Licenza

Il codice è GPL-3.0 o successivo e la documentazione è CC BY-SA 4.0. Vedere [LICENZA](LICENSE).
