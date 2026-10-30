<!-- =============================================================================
HYDRA-UMC-OS - Platform layer for a CM5 node on Raspberry Pi OS
Copyright (C) JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
GPL-3.0-or-later - see LICENSE
============================================================================= -->

<p align="center">
  <img src="images/HYDRA_UMC_BANNER.svg" alt="HYDRA-UMC-OS banner" width="100%">
</p>

# 🖥️ HYDRA-UMC-OS

<p align="center"><a href="README.md">🇺🇸 English</a> | <a href="README_spa.md">🇪🇸 Español</a> | <a href="README_fra.md">🇫🇷 Français</a> | 🇮🇹 <b>Italiano</b> | <a href="README_deu.md">🇩🇪 Deutsch</a> | <a href="README_zho.md">🇨🇳 简体中文</a> | <a href="README_jpn.md">🇯🇵 日本語</a> | <a href="README_por.md">🇵🇹 Português</a></p>

### Lo strato di piattaforma riproducibile di un nodo HYDRA-UMC su Raspberry Pi OS

<p align="center">
  <img src="https://img.shields.io/badge/License-GPL%203.0--or--later-blue.svg" alt="GPL 3.0 or later">
  <img src="https://img.shields.io/badge/Platform-Raspberry%20Pi%20OS%20%7C%20CM5-red.svg" alt="Platform">
  <img src="https://img.shields.io/badge/Services-systemd%20%7C%20udev-orange.svg" alt="Services">
  <img src="https://img.shields.io/badge/Stack-Debian%20%7C%20Python%20%7C%20Shell-blueviolet.svg" alt="Stack">
  <img src="https://img.shields.io/badge/Tests-20%20passing-2ea44f.svg" alt="Tests">
  <img src="https://img.shields.io/badge/Version-0.5.5-0f6cbd.svg" alt="Version">
  <img src="https://img.shields.io/badge/Maturity-functional-0F6CBD.svg" alt="Maturity">
</p>

---

> **Stato di sicurezza (safety e security):** questo ecosistema non è un sistema di sicurezza certificato. Non esiste ancora un percorso E-STOP hardware, né limiti o interblocchi imposti dal firmware, né un comando di movimento verificato; le immagini firmware sono controllate con CRC-32 e una firma Ed25519, e una compilazione di rilascio rifiuta le chiavi di sviluppo pubblicate (le teste utensile e le schede di espansione dietro il relè usano ancora i bootloader di URTC, che accettano un HMAC-SHA256 a chiave condivisa invece di una firma); TLS e TLS reciproco sono opzionali e disattivati per impostazione predefinita; nessuna scheda propria è stata ancora assemblata o provata. Leggi la [base di sicurezza](https://github.com/JuanenRac/HYDRA-UMC-DOCS/blob/main/docs/SECURITY_BASELINE.md) e il [modello delle minacce](https://github.com/JuanenRac/HYDRA-UMC-DOCS/blob/main/docs/THREAT_MODEL.md) prima di fidarti di qualsiasi affermazione qui per la sicurezza di una persona.

---

## 📋 In breve

| | |
|---|---|
| Versione | `0.5.5` |
| Maturità | Funzionale |
| Test | 20 (`python -m unittest discover -s agent/tests`) |
| Tecnologia | Raspberry Pi OS ARM64 / Debian/apt / systemd / udev / NetworkManager |
| Destinazione | Il Raspberry Pi CM5 di una cella HYDRA-UMC |
| Su hardware reale | Eseguito su un banco di prova: la verifica di onestà qui sopra indica quali parti hanno girato su hardware reale |

**Vai a:** [Panoramica](#-panoramica) · [Architettura](#-architettura) · [Avvio rapido](#-avvio-rapido) · [Test](#-test) · [Struttura del repository](#-struttura-del-repository) · [Progetti correlati](#-progetti-correlati)

## 🚦 Stato del progetto

Ogni riga è una parte di questo repository e il semaforo dice a che punto è oggi. È scritta in base a ciò che il repository può mostrare (test, compilazioni, esecuzioni), non a ciò che è previsto.

🟢 Fatto e verificato · 🟡 Funziona, con limiti noti · 🟠 Fatto a metà o non ancora verificato · 🔴 Non fatto o non funzionante

| Area | Stato | Cosa significa qui |
|---|---|---|
| Software | 🟡 | Funziona per il suo scopo principale; la verifica di onestà qui sopra elenca ciò che manca ancora |
| Test | 🟢 | 20 test automatici, eseguiti a ogni modifica |
| Hardware reale | 🟡 | Eseguito su un banco di prova: la verifica di onestà qui sopra indica quali parti hanno girato su hardware reale |
| Documentazione | 🟢 | README in otto lingue, verificato rispetto al manifesto a ogni modifica |

## 🎯 Panoramica

HYDRA-UMC-OS è il livello della piattaforma installabile per un nodo HYDRA-UMC CM5.
È basato sul sistema operativo Raspberry Pi ARM64; non sostituisce Linux, il
Kernel Raspberry Pi, systemd, NetworkManager, libcamera o SDK del fornitore.

La sua responsabilità è fornire un profilo riproducibile del dispositivo HYDRA-UMC:
configurazione, ciclo di vita del servizio, identità locale, diagnostica,
branding visivo e aggiornamenti coordinati per i componenti HYDRA-UMC.

**Verifica di onestà - cosa funziona davvero oggi:** l'agente del dispositivo in sola lettura (`agent/src/hydra_umc_os/agent.py`: `DeviceDescriptor`/`HealthReport`, controlli di temperatura/spazio di archiviazione/rete, caricamento del profilo di configurazione) è reale e testato (20 test unitari, `agent/tests/test_agent.py`, `python -m unittest discover`). `provisioning/preflight_cm5.py` è verificato come idempotente e privo di effetti collaterali da un test reale che lo esegue due volte e confronta l'output (`tools/verify_preflight_idempotent.py`), più 5 controlli reali sui percorsi negativi (`tools/verify_preflight_negative.py`); il meccanismo di backup/ripristino di `provisioning/rollback.py` è verificato da 8 controlli reali, incluso uno scenario di fallimento parziale genuino (`tools/verify_rollback.py`); la macchina a stati del fallback in modalità AP di `provisioning/wifi_provision.py` è verificata da 46 controlli reali contro un NetworkManager fittizio, incluso un vero round-trip HTTP end-to-end su un socket loopback reale (`tools/verify_wifi_provision.py`) - nessuno dei tre richiede permessi root o una CM5 fisica per essere verificato. Ciò che non è mai stato testato: hardware CM5 reale. `image-builder/` è solo documentazione (un README di note sulla riproducibilità, senza ancora codice di assemblaggio immagine); `packages/debian/` contiene gli script del manutentore e il file di copyright del pacchetto `hydra-umc-platform-base`, che `tools/build_deb.py` costruisce in un vero `.deb` (Python puro, senza dpkg, gli stessi byte ogni volta) e che `tools/verify_deb_package.py` rilegge; non è stato installato su una vera CM5. Vedi `CHANGELOG.md` per ciò che è stato consegnato finora esattamente, e `docs/CM5_SOFTWARE_READINESS.md` per la linea esatta tra ciò che è verificato qui e ciò che richiede ancora hardware fisico.

## 🧩 Ruolo in HYDRA-UMC

**HYDRA-UMC-OS** è lo strato di piattaforma di un nodo CM5: configurazione, ciclo di vita dei servizi, identità locale, diagnostica, aspetto visivo e aggiornamenti coordinati su Raspberry Pi OS, con un agente di dispositivo in sola lettura. Non sostituisce Linux, systemd né gli SDK dei produttori; l'immagine è costruita da `HYDRA-UMC-OS-REBUILDER`.

## 🏛️ Architettura

<p align="center">
  <img src="images/architecture.svg" alt="HYDRA-UMC-OS architecture" width="100%">
</p>

## 🚀 Avvio rapido

I test dell'agente richiedono solo Python 3.11 o successivo; l'immagine in sé è costruita da `HYDRA-UMC-OS-REBUILDER`.

```bash
PYTHONPATH=agent/src python3 -m unittest discover -s agent/tests
./build-test.sh  # non-mutating build check (build-test.bat on Windows)
```

## 🧪 Test

20 test automatici si eseguono con `python -m unittest discover -s agent/tests`. Non richiedono hardware né nulla al di fuori di questa macchina.

La CI esegue `HYDRA_UMC_CI=1 python tools/ci_validate.py`, che controlla il manifesto, i documenti, gli otto README e le immagini.

## 🏗️ Compilazione e rilascio

Usa il controllo di compilazione senza versionamento prima di una compilazione di rilascio:

| Azione | Windows | Linux / macOS |
|---|---|---|
| Controllo di compilazione (senza modificare versione o CHANGELOG) | `build-test.bat` | `./build-test.sh` |
| Esecuzione / sviluppo (se disponibile) | `run*.bat` o `dev*.bat` | `./run*.sh` o `./dev*.sh` |

`build-test.bat` e `build-test.sh` compilano o convalidano lo stack del progetto senza incrementare `hydra-umc.project.json` né modificare `CHANGELOG.md`. Possono creare solo i normali output del compilatore. Gli script esistenti `build*.bat`, `build*.sh`, `run*` e `dev*` mantengono il comportamento specifico di versione o esecuzione; usali quando tale comportamento è necessario.

## 📂 Struttura del repository

<p align="center">
  <img src="images/repository-structure.svg" alt="Repository structure of HYDRA-UMC-OS" width="100%">
</p>

<details>
<summary>Versione testuale dell'albero</summary>

```text
HYDRA-UMC-OS/
├── docs/                      Specifiche di architettura, installazione, servizio e aggiornamento.
├── image-builder/             Note ufficiali sui limiti di assemblaggio delle immagini e sulla riproducibilità del sistema operativo Raspberry Pi.
├── packages/                  Script del manutentore e copyright del pacchetto Debian `hydra-umc-platform-base` (costruito da `tools/build_deb.py`).
├── agent/                     Descrittore del dispositivo Python di sola lettura e agente di integrità con test unitari.
├── systemd/                   Unità del ciclo di vita rafforzate `hydra-umc-agent.service` e `hydra-umc-wifi-provision.service`.
├── config/                    Schemi predefiniti e configurazione non segreta.
├── provisioning/              Installer della CM5 (uno per servizio), primo avvio, diagnostica, ripristino, backup e ripristino delle impostazioni, firewall, TLS per MQTT, kiosk e schermata di avvio, regole polkit e i controlli di un'installazione.
├── tools/                     Strumenti di pacchetto e di rilascio (`build_deb.py`, `package_component.py`), i controlli `verify_*.py` degli script di provisioning e i controlli CI condivisi.
├── .github/                   workflow di CI e modelli di segnalazione
├── images/                    banner e immagini del README
├── CHANGELOG.md               cosa è cambiato in ogni versione
├── build-test.sh              controllo di build senza modifiche
├── build.sh                   compila e controlla; non cambia mai la versione
├── bump_manifest_version.py   sincronizza la versione del manifesto
├── bump_version.py            aumento di versione esplicito
├── hydra-umc.project.json     manifesto: versione, maturità, famiglia
├── run.sh                     avvia il programma
└── test.sh                    esegue i test
```

</details>

## 🗺️ Roadmap e limiti noti

**Limiti noti oggi**

**Limiti noti oggi**

### Stato

L'agente di base, la sua configurazione non segreta convalidata, un'unità systemd
rafforzata e i test lato host sono implementati. L'agente è deliberatamente
di sola lettura: rimangono l'assemblaggio dell'immagine di produzione e la convalida dell'hardware CM5
come cancelli di rilascio separati.

Il preflight di installazione (`provisioning/preflight_cm5.py`) si dimostra
idempotente e privo di effetti collaterali grazie a un test reale - due
esecuzioni consecutive producono un output identico byte per byte e non
toccano alcun file all'interno di questo repository - e un meccanismo
reale di backup/rollback indipendente dall'host
(`provisioning/rollback.py`) protegge l'unico file di sistema che
`install_local_agent.sh` sovrascrive incondizionatamente a ogni
esecuzione. Entrambi sono verificati senza root o una CM5 - vedere
`tools/verify_preflight_idempotent.py` e `tools/verify_rollback.py`.

**Anche il provisioning WiFi al primo contatto è reale**
(`provisioning/wifi_provision.py` / `hydra-umc-wifi-provision.service`):
un vero fallback in modalità AP di NetworkManager per una CM5 headless
senza ancora una rete nota - attiva un vero hotspot (`nmcli device wifi
hotspot`) a cui il telefono/laptop di un operatore può connettersi per
inviare il vero SSID/password di destinazione tramite un piccolo modulo
HTTP locale, disattiva l'AP e si unisce alla rete reale in caso di
successo, lo ripristina in caso di errore così il dispositivo non resta
mai isolato. La macchina a stati è completamente testata con unit test
contro un NetworkManager fittizio, incluso un vero round-trip HTTP
end-to-end su un vero socket di loopback - vedere
`tools/verify_wifi_provision.py`. Installato da `install_cm5_base.sh`
ma deliberatamente non abilitato automaticamente, poiché deve girare solo su un dispositivo che ne ha davvero bisogno: la password del suo access point e un codice di configurazione monouso vengono generati per ogni dispositivo al primo avvio e letti una sola volta dal journal - vedere la sezione 3 di `provisioning/CM5_DEPLOYMENT_SEQUENCE.md`.

**I segreti si generano per dispositivo, mai presi da un modello.** `install_server.sh` e `install_voice_ui.sh` creano i loro file env dall'esempio quando mancano e sostituiscono ogni valore di esempio (`JWT_SECRET`, la password dell'amministratore iniziale, il token del relay vocale) con uno casuale di questo dispositivo (`provisioning/generate_secrets.py`; ciò che l'operatore ha già scelto resta, e la password dell'amministratore viene stampata una sola volta), poi si rifiutano di proseguire se resta un valore di esempio o un segreto troppo corto; `preflight_cm5.py` rifiuta un `/etc/hydra-umc/*.env` che ne contenga ancora. `install_industrial_gateway.sh` scrive i segreti dello stack in `/etc/hydra-umc/gateway.env` (solo root, fuori dal checkout dell'utente, letto da compose con `--env-file`; un `.env` lasciato nel checkout da una versione precedente viene spostato lì) (`provisioning/gateway_env.py`: il segreto del gateway e una credenziale MQTT e una regola ACL per ogni bridge di macchina). La rete Wi-Fi di configurazione non ha più una password nel codice sorgente: ogni dispositivo genera la propria e un codice di configurazione monouso al primo avvio (da leggere una volta nel journal, da scrivere sull'etichetta), il modulo chiede il codice (bloccato un minuto dopo cinque errori), la rete di configurazione resta aperta solo 30 minuti dopo ogni avvio e il modulo rifiuta richieste troppo grandi. Verificato da `tools/verify_generate_secrets.py`, `tools/verify_gateway_env.py` e `tools/verify_wifi_provision.py`. Anche il nome host e il nome della rete di configurazione terminano con sei caratteri presi dal dispositivo (il numero di serie del Raspberry Pi, altrimenti l'indirizzo MAC), così due dispositivi scritti con la stessa immagine non condividono più lo stesso nome (`provisioning/device_identity.py`, verificato da `tools/verify_device_identity.py`); `HYDRA_UMC_DEVICE_SUFFIX=off` mantiene i nomi fissi e un nome scelto da voi non viene mai cambiato.

**Chiavi di firma, distribuite dall'installatore.** La chiave con cui la Voice UI firma il risultato di una conferma (`HYDRA_UMC_VOICE_UI_RESULT_KEY`) viene generata una sola volta per il dispositivo da `install_server.sh` o `install_voice_ui.sh`, quello che gira per primo, e scritta in `/etc/hydra-umc/server.env` e `/etc/hydra-umc/voice-ui.env` (a un file di un modello precedente viene aggiunta la riga), insieme a `HYDRA_UMC_VOICE_CONFIRM_REQUIRE_SIGNATURE=1` per il server e `HYDRA_UMC_VOICE_UI_REQUIRE_SUBJECT=1` per la Voice UI (`generate_secrets.py --ensure`; una riga che l'operatore ha già, con qualsiasi valore, non viene mai cambiata). `install_local_technician.sh` crea la chiave che firma il risultato di ogni strumento in `/etc/hydra-umc-local-technician/result.key` (`provisioning/make_result_key.py`: 64 caratteri esadecimali casuali, modo 0600 fin dal primo byte, solo root, mai stampata, mai sostituita una volta creata, mai seguita attraverso un collegamento simbolico) e vi fa puntare il file delle impostazioni; `--no-signing` (o `HYDRA_UMC_LOCAL_TECHNICIAN_SIGNING=off`) lascia fuori la riga. Nessuna chiave è mai nell'immagine né nel repository, e due dispositivi non ne condividono mai una. Verificato da `tools/verify_result_keys.py`.

**Registri di audit, attivi per impostazione predefinita.** `install_local_technician.sh` attiva il registro di audit del tecnico (solo aggiunte, concatenato per hash) e `install_node_healing.sh` quello del sorvegliante (entrambi ruotano a 5 MiB e conservano 5 file): ciò che è stato chiesto al tecnico e ciò che il sorvegliante ha deciso su un nodo sono le prove che contano dopo un guasto, quindi gli installatori scrivono l'impostazione attiva in un file di impostazioni documentato (`/etc/hydra-umc-local-technician/local-technician.env`, `/etc/hydra-umc-node-healing/journal.env`). `--no-audit` / `--no-journal` (o `HYDRA_UMC_LOCAL_TECHNICIAN_AUDIT=off`, `HYDRA_UMC_NODE_HEALING_JOURNAL=off`) lascia un registro spento e commenta una riga attiva, senza mai cancellare ciò che è stato registrato; un file di impostazioni esistente non viene mai sovrascritto. `tools/verify_optional_journals.py` verifica staticamente le opzioni e i nomi; finora nulla è stato installato con essi su una vera CM5.

**Un Go fissato per i servizi Go.** Il dispatcher dei lavori, il sorvegliante dei nodi e il collettore di telemetria vengono compilati sul dispositivo, e il loro `go.mod` richiede un Go più recente del `golang-go` dell'archivio Debian, che non poteva compilarli. I loro installatori ora caricano `provisioning/go_toolchain.sh`: una versione di go.dev, verificata rispetto al suo SHA-256 fissato prima di essere decompressa in `/usr/local/go-<versione>` (il Go di sistema non viene toccato). `tools/verify_go_toolchain.py` esegue l'helper con un download simulato (un archivio corretto, uno corrotto, uno già installato) e confronta la versione fissata con il `go.mod` dei progetti fratelli; finora nulla è stato installato con esso su una vera CM5.

**Un solo registro dei servizi.** La porta, il percorso di salute e l'unità systemd di ogni servizio vengono da `provisioning/ports.yaml` (copia del `contracts/ports.yaml` dell'SDK, generato dai manifesti dei progetti). Ogni installatore di un servizio finisce dicendo dove guardare quando gira, e `verify_cm5_runtime.sh --with-services` sonda il percorso di salute di ogni servizio in esecuzione (sola lettura; ciò che non gira viene saltato). `tools/verify_service_registry.py` controlla l'aiuto, gli installatori e la verifica a runtime con simulacri; finora nulla è stato installato con esso su un vero CM5.

### Primo traguardo

Completo, secondo la sezione Stato sopra (codice reale, test reali,
non ancora verificato contro hardware CM5 fisico):

1. ✅ Crea un profilo ARM64 del sistema operativo Raspberry Pi per CM5.
2. ✅ Installa `hydra-umc-platform-base` e `hydra-umc-agent`.
3. ✅ Rileva le interfacce CM5 e segnala un `DeviceDescriptor` e un `HealthReport`.
4. ✅ Avvia solo i servizi abilitati tramite systemd.
5. ✅ Visualizzare localmente PRONTO, DEGRADATO o GUASTO.

## 🌍 Lingue

Questo README e i documenti del repository esistono in otto lingue: inglese, spagnolo, tedesco, francese, italiano, giapponese, cinese e portoghese (Portogallo). Sono scritti insieme e la CI verifica che gli otto file abbiano le stesse sezioni e gli stessi link. Questo repository non ha uno schermo né un catalogo di messaggi propri, quindi non ci sono stringhe di interfaccia da tradurre.

## 🔗 Progetti correlati

Questo progetto fa parte dell'ecosistema robotico HYDRA-UMC dello stesso autore (JuanenRac / Electro Hobby 3D). Vale la pena conoscerlo, poiché una richiesta potrebbe in realtà riguardare uno di questi invece di questo repository.

**Progetti Figli**
- **[HYDRA-UMC-SDK](https://github.com/JuanenRac/HYDRA-UMC-SDK)** — il contratto JSON-Schema condiviso e la barriera software di controllo dei job contro cui ogni bridge valida i propri comandi (non è una funzione di sicurezza certificata); contratti versionati, client leggeri e fixture di conformità usati dall'agente dispositivo di questo sistema operativo.
- **[HYDRA-UMC-OS-REBUILDER](https://github.com/JuanenRac/HYDRA-UMC-OS-REBUILDER)** — strumento desktop Windows/Linux che costruisce un'immagine di questo sistema operativo pronta da scrivere per la CM5, precaricata con le versioni più aggiornate dell'ecosistema e configurazione di primo avvio in stile Raspberry Pi Imager.

**Direttamente Correlati**
- **[HYDRA-UMC](https://github.com/JuanenRac/HYDRA-UMC)** — il progetto della scheda madre del braccio robotico: host CM5 + coprocessore STM32H745 dual-core, pensato per coordinare fino a 8 bracci utensile via CAN-OTA/SPI-OTA (firmware in fase iniziale; nessuna scheda assemblata per ora); la piattaforma hardware e firmware CM5/MCU che questo strato di sistema operativo configura e supervisiona.
- **[HYDRA-UMC-SERVER](https://github.com/JuanenRac/HYDRA-UMC-SERVER)** — il vero backend headless (REST/WebSocket) con cui parla davvero ogni client di controllo; il confine di servizio autenticato per le integrazioni gestite di questo nodo.
- **[URTC](https://github.com/JuanenRac/URTC)** — firmware per la scheda fisica dell'Universal Robot Tool Controller, oltre 25 profili utensile su bus CAN; una piattaforma di controller utensili indipendente integrata tramite adattatori espliciti e versionati.
- **[HYDRA-UMC-UPDATER](https://github.com/JuanenRac/HYDRA-UMC-UPDATER)** — strumento amministrativo desktop che scopre, clona e aggiorna ogni repository di questo ecosistema; il suo registro di artefatti, metadati di compatibilità e flusso di aggiornamento coordinato.
- **[HYDRA-UMC-CONNECTOR-HUB](https://github.com/JuanenRac/HYDRA-UMC-CONNECTOR-HUB)** — registro dichiarativo e validatore di manifesti adattatore per connettori di macchine esterne; estende la propria idea di contratto dell'SDK alle macchine esterne senza sostituire i progetti di gateway industriale.
- **[HYDRA-UMC-OPS-AGENT](https://github.com/JuanenRac/HYDRA-UMC-OPS-AGENT)** — coordinatore di incidenti di manutenzione: un ruolo edge a basso privilegio raccoglie uno snapshot di inventario/salute sanificato, un ruolo control-plane lo rende in sola lettura e chiede a un provider di IA di suggerire una diagnosi - non applica mai una patch né distribuisce nulla.
- **[HYDRA-UMC-DEV-SERVER](https://github.com/JuanenRac/HYDRA-UMC-DEV-SERVER)** — host di sviluppo riproducibile (Raspberry Pi 5 / CM5) che conserva il codice sorgente dell'ecosistema ed esegue attività delimitate di build/test tramite una coda durevole; un ruolo di sviluppo dedicato, esplicitamente distinto da un CM5 operativo.

**Fa Anche Parte dell'Ecosistema**

*Backend Centrale e Client*
- **[HYDRA-UMC-STUDIO](https://github.com/JuanenRac/HYDRA-UMC-STUDIO)** — dashboard di controllo web con visualizzazione 3D multi-robot in tempo reale.
- **[HYDRA-UMC-SUITE](https://github.com/JuanenRac/HYDRA-UMC-SUITE)** — centro di comando sciame desktop (PySide6) per più server contemporaneamente, pacchettizzato come eseguibile standalone.
- **[HYDRA-UMC-ANDROID-CONTROL](https://github.com/JuanenRac/HYDRA-UMC-ANDROID-CONTROL)** — app di controllo nativa per Android con login biometrico e un companion Wear OS abbinato.
- **[HYDRA-UMC-IOS-CONTROL](https://github.com/JuanenRac/HYDRA-UMC-IOS-CONTROL)** — app di controllo per iOS/iPadOS (Flutter) con sincronizzazione WebSocket in tempo reale.
- **[HYDRA-UMC-DSI](https://github.com/JuanenRac/HYDRA-UMC-DSI)** — interfaccia touch nativa per il touchscreen DSI da 7" a bordo, incorporata direttamente nel CM5.
- **[HYDRA-UMC-EDITOR-URDF](https://github.com/JuanenRac/HYDRA-UMC-EDITOR-URDF)** — creatore/editor grafico desktop di URDF che invia i modelli finiti al catalogo di STUDIO.
- **[HYDRA-UMC-EDITOR-STL](https://github.com/JuanenRac/HYDRA-UMC-EDITOR-STL)** — editor desktop di modelli STL, che trasforma/sostituisce/rimuove/aggiunge veri pezzi nello stesso catalogo di modelli modificato anche da HYDRA-UMC-EDITOR-URDF.
- **[HYDRA-UMC-BRIDGE-AMR](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-AMR)** — barriera di coordinamento per flotte AGV/AMR tramite un publisher MQTT VDA 5050 (testato solo contro una flotta emulata).
- **[HYDRA-UMC-BRIDGE-CNC](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-CNC)** — coordinatore ad alto livello per celle CNC con accesso a stato/byte di controllo GRBL (testato solo contro un emulatore).
- **[HYDRA-UMC-BRIDGE-DROIDS](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-DROIDS)** — barriera di coordinamento per droidi con zampe/umanoidi, con un mittente di comandi per Boston Dynamics Spot (testato solo contro un emulatore).
- **[HYDRA-UMC-BRIDGE-LASER](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-LASER)** — coordinatore per celle laser che legge 3 segnali GPIO di chiave/involucro/interblocco (testato solo contro un chip simulato; non può armare né far partire un laser).
- **[HYDRA-UMC-BRIDGE-OPENPNP](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-OPENPNP)** — coordinatore ad alto livello sicuro per il flusso schede del pick-and-place OpenPnP.
- **[HYDRA-UMC-BRIDGE-PRINTER3D](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-PRINTER3D)** — barriera di coordinamento sicura per stampanti 3D Moonraker/Klipper, con comandi di lavoro reali e controllati.
- **[HYDRA-UMC-BRIDGE-ROS2](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-ROS2)** — coordinatore con un trasporto ROS 2 rclpy importato in modo lazy (non ancora eseguito contro un'installazione ROS 2).
- **[HYDRA-UMC-BRIDGE-UAV](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-UAV)** — barriera di coordinamento per UAV dotati di fotocamera, con un mittente di comandi MAVLink (testato solo contro un emulatore).

*Piattaforma Strumenti URTC*
- **[URTC-FLASHER](https://github.com/JuanenRac/URTC-FLASHER)** — strumento desktop con GUI per il flashing delle schede URTC, CAN-OTA più SWD/JTAG a chip intero.
- **[URTC-TESTER](https://github.com/JuanenRac/URTC-TESTER)** — strumento desktop di diagnostica CAN-bus dal vivo per schede URTC, un pannello per profilo utensile.
- **[URTC-WEB-STUDIO](https://github.com/JuanenRac/URTC-WEB-STUDIO)** — alternativa basata su browser a URTC-TESTER tramite la Web Serial API, senza installazione locale.
- **[URTC-GATEWAY](https://github.com/JuanenRac/URTC-GATEWAY)** — gateway davanti al bus CAN di URTC: elenco di identificatori consentiti, limite di frequenza e chiave di sessione; software provato su computer, non ancora su un bus reale.

*Nodo IA Visione (Hailo-8)*
- **[HYDRA-UMC-VISION-NODE](https://github.com/JuanenRac/HYDRA-UMC-VISION-NODE)** — hub di integrazione per la pipeline di visione Hailo-8, con un vero controllo di prontezza hardware per fase.
- **[HYDRA-UMC-DETECTION-HEF](https://github.com/JuanenRac/HYDRA-UMC-DETECTION-HEF)** — registro reale di modelli compilati con verifica di caricamento sicuro per architettura Hailo/checksum.
- **[HYDRA-UMC-VISION-STREAMER](https://github.com/JuanenRac/HYDRA-UMC-VISION-STREAMER)** — generatore reale di pipeline GStreamer + config MediaMTX, con una vera barriera di integrazione HailoRT.
- **[HYDRA-UMC-VISUAL-SERVOING-API](https://github.com/JuanenRac/HYDRA-UMC-VISUAL-SERVOING-API)** — legge di correzione Position-Based Visual Servoing con autorizzazione condizionata allo stato di zona; ancora nessuna stima di posa da telecamera.
- **[HYDRA-UMC-SAFETY-ZONES](https://github.com/JuanenRac/HYDRA-UMC-SAFETY-ZONES)** — logica v0 di violazione zona, freschezza di calibrazione e richiesta E-STOP che legge le posizioni degli oggetti da un file; nessun rilevatore la alimenta e nessun E-STOP fisico è ancora collegato.

*Nodo IA Cognitivo (Hailo-10)*
- **[HYDRA-UMC-COGNITIVE-NODE](https://github.com/JuanenRac/HYDRA-UMC-COGNITIVE-NODE)** — hub di integrazione per la pipeline cognitiva Hailo-10 (orchestrazione LLM/VLA/voce).
- **[HYDRA-UMC-VLA-ENGINE](https://github.com/JuanenRac/HYDRA-UMC-VLA-ENGINE)** — vera codifica/decodifica di token d'azione e generazione di traiettoria per un modello Vision-Language-Action.
- **[HYDRA-UMC-VOICE-UI](https://github.com/JuanenRac/HYDRA-UMC-VOICE-UI)** — vero front-end vocale (VAD + parser di intenti) con un relay verso Watch limitato e soggetto a conferma.
- **[HYDRA-UMC-SEMANTIC-PLANNER](https://github.com/JuanenRac/HYDRA-UMC-SEMANTIC-PLANNER)** — vera scomposizione dei task basata su regole e recupero semantico degli errori sui codici errore MCU.
- **[HYDRA-UMC-DOCS-QA](https://github.com/JuanenRac/HYDRA-UMC-DOCS-QA)** — vera ricerca documentale TF-IDF (solo libreria standard) sui documenti Markdown di questo ecosistema.
- **[HYDRA-UMC-LOCAL-TECHNICIAN](https://github.com/JuanenRac/HYDRA-UMC-LOCAL-TECHNICIAN)** — tecnico di manutenzione IA locale e con cancelli di policy per l'ecosistema stesso - osserva, diagnostica e propone correzioni; i due livelli di rischio più alti non sono deliberatamente ancora implementati.

*Orchestrazione e Sciame*
- **[HYDRA-UMC-ORCHESTRATOR](https://github.com/JuanenRac/HYDRA-UMC-ORCHESTRATOR)** — hub di integrazione con un vero contratto di health-report gRPC/Protobuf e una macchina a stati di missione.
- **[HYDRA-UMC-JOB-DISPATCHER](https://github.com/JuanenRac/HYDRA-UMC-JOB-DISPATCHER)** — vera coda di lavori basata su priorità con deduplicazione, su una vera API HTTP.
- **[HYDRA-UMC-NODE-HEALING](https://github.com/JuanenRac/HYDRA-UMC-NODE-HEALING)** — vero watchdog di salute della flotta basato su gRPC, con retry/backoff e rilevamento di discrepanza d'identità.
- **[HYDRA-UMC-PATH-PLANNER-3D](https://github.com/JuanenRac/HYDRA-UMC-PATH-PLANNER-3D)** — vero pianificatore di percorsi 3D basato su RRT, con vera validazione delle collisioni ostacolo/spazio di lavoro.
- **[HYDRA-UMC-SWARM-SYNC](https://github.com/JuanenRac/HYDRA-UMC-SWARM-SYNC)** — vera sincronizzazione di stato CRDT LWW-Element-Map, con property test per la convergenza multi-cella.

*Gemello Digitale e Simulazione*
- **[HYDRA-UMC-TWIN](https://github.com/JuanenRac/HYDRA-UMC-TWIN)** — hub di integrazione per il motore di gemello digitale, con un vero contratto di sincronizzazione per compatibilità di versione.
- **[HYDRA-UMC-HIL-BRIDGE](https://github.com/JuanenRac/HYDRA-UMC-HIL-BRIDGE)** — router hardware-in-the-loop con un interblocco software di collisione tra simulazione e hardware reale (testato senza hardware reale).
- **[HYDRA-UMC-PHYSICS-REPLICA](https://github.com/JuanenRac/HYDRA-UMC-PHYSICS-REPLICA)** — vera cinematica diretta e validazione dei limiti articolari su un vero sottoinsieme URDF.
- **[HYDRA-UMC-SYNTHETIC-DATA-GEN](https://github.com/JuanenRac/HYDRA-UMC-SYNTHETIC-DATA-GEN)** — vero generatore procedurale di scene 2D con esportazione di annotazioni YOLO/COCO.

*Dati e Analisi*
- **[HYDRA-UMC-DATALAKE](https://github.com/JuanenRac/HYDRA-UMC-DATALAKE)** — vero archivio di serie temporali basato su sqlite3, con una vera API HTTP di ingestione/query.
- **[HYDRA-UMC-ANOMALY-DETECTOR](https://github.com/JuanenRac/HYDRA-UMC-ANOMALY-DETECTOR)** — vero rilevatore di anomalie FFT + baseline statistica, con monitoraggio della deriva.
- **[HYDRA-UMC-PRODUCTION-REPORTS](https://github.com/JuanenRac/HYDRA-UMC-PRODUCTION-REPORTS)** — vero calcolo OEE/disponibilità sullo storico di DATALAKE, con esportazione CSV riproducibile.
- **[HYDRA-UMC-TELEMETRY-COLLECTOR](https://github.com/JuanenRac/HYDRA-UMC-TELEMETRY-COLLECTOR)** — vera pipeline di ingestione CAN/WebSocket verso DATALAKE, con deduplicazione per sequenza.

*Gateway Industriale*
- **[HYDRA-UMC-GATEWAY-INDUSTRIAL](https://github.com/JuanenRac/HYDRA-UMC-GATEWAY-INDUSTRIAL)** — hub di integrazione che inoltra ai protocolli industriali, con un vero livello di allowlist dei comandi/backpressure.
- **[HYDRA-UMC-OPCUA-SERVER](https://github.com/JuanenRac/HYDRA-UMC-OPCUA-SERVER)** — vero spazio di indirizzi OPC-UA, verificato con una vera sessione client del protocollo binario.
- **[HYDRA-UMC-MQTT-BROKER](https://github.com/JuanenRac/HYDRA-UMC-MQTT-BROKER)** — vero broker MQTT con autenticazione opzionale per client e ACL sui topic.
- **[HYDRA-UMC-MTCONNECT-ADAPTER](https://github.com/JuanenRac/HYDRA-UMC-MTCONNECT-ADAPTER)** — veri endpoint XML `/probe` e `/current` di MTConnect, con output in modalità degradata.

*Strumenti Complementari e Operazioni dell'Ecosistema*
- **[HYDRA-UMC-DASHBOARD-AI](https://github.com/JuanenRac/HYDRA-UMC-DASHBOARD-AI)** — pannelli Smart Summaries e Anomaly Highlighting su DATALAKE/ANOMALY-DETECTOR, con un fallback statistico onesto.
- **[HYDRA-UMC-TOOL-CLI](https://github.com/JuanenRac/HYDRA-UMC-TOOL-CLI)** — CLI di flotta con un vero e stabile contratto di exit-code, un client live reale della stessa API di HYDRA-UMC-SERVER.
- **[HYDRA-UMC-WATCH](https://github.com/JuanenRac/HYDRA-UMC-WATCH)** — app companion WearOS con schemi di avviso aptico e un relay vocale verso il telefono abbinato (non ancora eseguita su un orologio fisico).
- **[URTC-SMART-RACK](https://github.com/JuanenRac/URTC-SMART-RACK)** — firmware per un rack di montaggio schede con decodifica reale dell'ID utensile e logica di preriscaldamento Smart Idle.
- **[URTC-VISION-TOOL](https://github.com/JuanenRac/URTC-VISION-TOOL)** — firmware più un vero companion di visione Python per una testa utensile di ispezione termica/RGB.

## 📚 Documentazione

Dove leggere di più:

* **[`docs/AGENT_REFERENCE.md`](docs/AGENT_REFERENCE.md)** — riferimento reale di comandi/output per `hydra-umc-agent`, la CLI di diagnostica in sola lettura.
* **[`docs/INSTALLATION.md`](docs/INSTALLATION.md)** — design dell'installazione: piattaforma target e sequenza di installazione prevista.
* **[`docs/CM5_PROVISIONING.md`](docs/CM5_PROVISIONING.md)** — la guida completa per trasformare Raspberry Pi OS Lite in HYDRA-UMC-OS.
* **[`docs/CM5_WINDOWS_HOST_FLASHING.md`](docs/CM5_WINDOWS_HOST_FLASHING.md)** — la procedura verificata per flashare una CM5 da un host Windows.
* **[`docs/CM5_FIRST_BOOT_CHECKLIST.md`](docs/CM5_FIRST_BOOT_CHECKLIST.md)** — una checklist di piattaforma BASE per il primo avvio di una CM5.
* **[`docs/CM5_PACKAGE_MANIFEST.md`](docs/CM5_PACKAGE_MANIFEST.md)** — l'elenco reale dei pacchetti per fase di distribuzione.
* **[`docs/CM5_ECOSYSTEM_DEPLOYMENT.md`](docs/CM5_ECOSYSTEM_DEPLOYMENT.md)** — il piano di distribuzione a fasi, ciascuna revocabile indipendentemente, del resto dell'ecosistema su una CM5.
* **[`docs/CM5_SOFTWARE_READINESS.md`](docs/CM5_SOFTWARE_READINESS.md)** — cosa è stato verificato senza hardware CM5 fisico, e dove si ferma tale verifica.
* **[`docs/SERVICE_MODEL.md`](docs/SERVICE_MODEL.md)** — come funzionano i servizi HYDRA-UMC: utenti dedicati, percorsi di configurazione, ordine di dipendenza/disponibilità.
* **[`docs/UPDATE_MODEL.md`](docs/UPDATE_MODEL.md)** — i canali di aggiornamento separati per il SO, i pacchetti HYDRA-UMC, i runtime Hailo e il firmware MCU/URTC.
* **[`docs/SDK_INTEGRATION_BOUNDARY.md`](docs/SDK_INTEGRATION_BOUNDARY.md)** — come questo repo consuma il contratto pubblicato di HYDRA-UMC-SDK senza vendorizzarlo.
* **[`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md)** — regole di sviluppo: interfacce native di Raspberry Pi OS prima di tutto, l'ordine di test richiesto.
* **[`docs/HEADER_CONVENTION.md`](docs/HEADER_CONVENTION.md)** — la convenzione di intestazione copyright/licenza per i nuovi file di codice e documentazione.
* **[`provisioning/ssh_hardening.md`](provisioning/ssh_hardening.md)** — i passaggi reali di hardening SSH per una CM5 (verificare il login con chiave prima di disabilitare l'autenticazione con password).
* [Base di sicurezza dell'ecosistema](https://github.com/JuanenRac/HYDRA-UMC-DOCS/blob/main/docs/SECURITY_BASELINE.md)
* [Modello delle minacce dell'ecosistema](https://github.com/JuanenRac/HYDRA-UMC-DOCS/blob/main/docs/THREAT_MODEL.md)
* [Registro delle modifiche di questo repository](CHANGELOG.md)
* [Licenza di questo repository](LICENSE.md)

## 🤝 Contribuire e comunità

* Prima di una pull request esegui `HYDRA_UMC_CI=1 py -3 tools/ci_validate.py` (oppure `HYDRA_UMC_CI=1 python3 tools/ci_validate.py`): deve stampare `CI_VALIDATION=PASS`. Non eseguire `build.sh` né `build.bat` per questa verifica; compilare non è verificare.
* I otto README sono scritti da un'unica fonte in HYDRA-UMC-DOCS; non modificarli a mano. Cambia la fonte e riscrivili con `tools/make_readmes.py`.
* Non affermare in un README ciò che non è stato eseguito: scrivi «simulato» o «non provato su hardware» quando è la verità.
* Vedi [CONTRIBUTING.md](CONTRIBUTING.md), il [codice di condotta](CODE_OF_CONDUCT.md), [SECURITY.md](SECURITY.md) e [SUPPORT.md](SUPPORT.md).

## 👤 AUTORE

**JuanenRac (Electro Hobby 3D)** · electrohobby3d@gmail.com

## 📜 LICENZA

GPL-3.0-or-later - [LICENSE](LICENSE).
