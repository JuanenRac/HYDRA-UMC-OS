<!--
=============================================================================
HYDRA-UMC-OS - Aperçu du projet public et guide de mise en œuvre
Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
CC BY-SA 4.0 - voir LICENSE.md
=============================================================================
-->

<p align="center">
  <img src="images/HYDRA_UMC_BANNER.svg" alt="Bannière HYDRA-UMC-OS" width="100%">
</p>

<p align="center">
  <a href="README.md">???? English</a> |
  <a href="README_spa.md">🇪🇸 Español</a> |
  <a href="README_fra.md">🇫🇷 Français</a> |
  <a href="README_ita.md">🇮🇹 Italien</a> |
  <a href="README_deu.md">🇩🇪 Allemand</a> |
  <a href="README_zho.md">🇨🇳 简体中文</a> |
  <a href="README_jpn.md">🇯🇵 日本語</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/License-GPL%203.0-blue.svg" alt="Licence : GPL 3.0">
  <img src="https://img.shields.io/badge/Platform-Raspberry%20Pi%20OS%20%7C%20CM5-red.svg" alt="Plateforme : OS Raspberry Pi | CM5">
  <img src="https://img.shields.io/badge/Services-systemd%20%7C%20udev-orange.svg" alt="Services : systemd | udev">
  <img src="https://img.shields.io/badge/Stack-Debian%20%7C%20Python%20%7C%20Shell-blueviolet.svg" alt="Pile : Debian | Python | Shell">
</p>

# HYDRA-UMC-OS

## 🖥️ Couche de plateforme HYDRA-UMC pour Raspberry Pi OS

HYDRA-UMC-OS est la couche de plate-forme installable pour un nœud HYDRA-UMC CM5.
Il est construit sur Raspberry Pi OS ARM64 ; il ne remplace pas Linux, le
Noyau Raspberry Pi, systemd, NetworkManager, libcamera ou SDK du fournisseur.

Sa responsabilité est de fournir un profil reproductible du dispositif HYDRA-UMC :
configuration, cycle de vie du service, identité locale, diagnostics, visuel
la marque et les mises à jour coordonnées des composants HYDRA-UMC.

## 🚧 Statut

L'agent de base, sa configuration non secrète validée, un systemd renforcé
les tests unitaires et côté hôte sont implémentés. L'agent est délibérément
lecture seule : l'assemblage de l'image de production et la validation matérielle CM5 restent
portes de dégagement séparées.

Le preflight d'installation (`provisioning/preflight_cm5.py`) s'avère
idempotent et sans effet de bord grâce à un test réel - deux exécutions
consécutives produisent une sortie identique octet pour octet et ne
touchent aucun fichier dans ce dépôt - et un mécanisme réel de
sauvegarde/restauration (rollback), indépendant de l'hôte
(`provisioning/rollback.py`), protège l'unique fichier système que
`install_local_agent.sh` écrase inconditionnellement à chaque exécution.
Les deux sont vérifiés sans root ni CM5 - voir
`tools/verify_preflight_idempotent.py` et `tools/verify_rollback.py`.

## 🎯 Première étape prévue

1. Créez un profil Raspberry Pi OS ARM64 pour CM5.
2. Installez « hydra-umc-platform-base » et « hydra-umc-agent ».
3. Détectez les interfaces CM5 et signalez un « DeviceDescriptor » et un « HealthReport ».
4. Démarrez uniquement les services activés via systemd.
5. Affichez localement PRÊT, DÉGRADÉ, INHIBITÉ ou DÉFAUT.

## 📂 Disposition du référentiel

<p align="center">
  <img src="images/REPOSITORY_LAYOUT.svg" alt="Carte visuelle de la disposition du référentiel HYDRA-UMC-OS" width="100%">
</p>

| Chemin | Objectif |
| --- | --- |
| `docs/` | Spécifications d’architecture, d’installation, de service et de mise à jour. |
| `image-builder/` | Notes officielles sur les limites d’assemblage d’images et la reproductibilité du système d’exploitation Raspberry Pi. |
| `paquets/` | Métadonnées du paquet Debian pour « hydra-umc-platform-base ». |
| `agent/` | Descripteur de périphérique Python en lecture seule et agent d'intégrité avec tests unitaires. |
| `systemd/` | Unité de cycle de vie « hydra-umc-agent.service » renforcée. |
| `config/` | Schémas par défaut et configuration non secrète. |

Lisez [l'architecture](docs/ARCHITECTURE.md) avant d'implémenter le code.

## 🛠️ BUILD & RUN

Utilisez la vérification de compilation sans versionnement avant une compilation de publication :

| Action | Windows | Linux / macOS |
|---|---|---|
| Vérification de compilation (sans modifier la version ni le CHANGELOG) | `build-test.bat` | `./build-test.sh` |
| Exécution / développement (si disponible) | `run*.bat` ou `dev*.bat` | `./run*.sh` ou `./dev*.sh` |

`build-test.bat` et `build-test.sh` compilent ou valident la pile du projet sans incrémenter `hydra-umc.project.json` ni modifier `CHANGELOG.md`. Ils peuvent uniquement créer les sorties normales du compilateur. Les scripts existants `build*.bat`, `build*.sh`, `run*` et `dev*` conservent leur comportement spécifique de versionnement ou d'exécution ; utilisez-les lorsque ce comportement est requis.

## 🔗 Projets connexes

> Carte canonique des relations entre les écosystèmes publics.

| Projet | Relation avec HYDRA-UMC-OS |
| --- | --- |
| [HYDRA-UMC-SDK](https://github.com/JuanenRac/HYDRA-UMC-SDK) | Contrats versionnés, clients légers et dispositifs de conformité utilisés par l'agent de périphérique. |
| [HYDRA-UMC-SERVER](https://github.com/JuanenRac/HYDRA-UMC-SERVER) | Limite de service authentifiée pour les intégrations gérées du nœud. |
| [HYDRA-UMC-UPDATER](https://github.com/JuanenRac/HYDRA-UMC-UPDATER) | Registre des artefacts, métadonnées de compatibilité et flux de travail de mise à jour coordonné. |
| [HYDRA-UMC](https://github.com/JuanenRac/HYDRA-UMC) | Plate-forme matérielle et micrologicielle CM5/MCU que la couche OS configure et supervise. |
| [URTC](https://github.com/JuanenRac/URTC) | Plateforme de contrôleur d'outils indépendante intégrée via des adaptateurs explicites et versionnés. |

**Reste de l'écosystème :** explorez les sept couches publiques dans le [tableau de bord de l'écosystème JuanenRac](https://juanenrac.github.io/JuanenRac/).

## 📜 Licence

Le code est GPL-3.0 ou version ultérieure et la documentation est CC BY-SA 4.0. Voir [LICENCE](LICENSE).
