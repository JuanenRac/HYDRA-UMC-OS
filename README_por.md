<!--
=============================================================================
HYDRA-UMC-OS - Public project overview and implementation guide
Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
CC BY-SA 4.0 - see LICENSE.md
=============================================================================
-->

<p align="center">
  <img src="images/HYDRA_UMC_BANNER.svg" alt="HYDRA-UMC-OS banner" width="100%">
</p>

<p align="center">
  <a href="README.md">🇺🇸 English</a> |
  <a href="README_spa.md">🇪🇸 Español</a> |
  <a href="README_fra.md">🇫🇷 Français</a> |
  <a href="README_ita.md">🇮🇹 Italiano</a> |
  <a href="README_deu.md">🇩🇪 Deutsch</a> |
  <a href="README_zho.md">🇨🇳 简体中文</a> |
  <a href="README_jpn.md">🇯🇵 日本語</a> |
  🇵🇹 <b>Português</b>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/License-GPL%203.0--or--later-blue.svg" alt="License: GPL 3.0 or later">
  <img src="https://img.shields.io/badge/Platform-Raspberry%20Pi%20OS%20%7C%20CM5-red.svg" alt="Platform: Raspberry Pi OS | CM5">
  <img src="https://img.shields.io/badge/Services-systemd%20%7C%20udev-orange.svg" alt="Services: systemd | udev">
  <img src="https://img.shields.io/badge/Stack-Debian%20%7C%20Python%20%7C%20Shell-blueviolet.svg" alt="Stack: Debian | Python | Shell">
</p>

# HYDRA-UMC-OS

> **Estado de segurança (safety e security):** este ecossistema não é um sistema de segurança certificado. Ainda não existe um caminho de E-STOP por hardware, nem limites ou interlocks impostos pelo firmware, nem um comando de movimento verificado; as imagens de firmware são verificadas com CRC32 e um HMAC-SHA256 de chave partilhada, não com uma assinatura assimétrica; TLS e TLS mútuo são opcionais e estão desativados por defeito; nenhuma placa própria foi ainda montada ou testada. Leia a [base de segurança](https://github.com/JuanenRac/HYDRA-UMC-DOCS/blob/main/docs/SECURITY_BASELINE.md) e o [modelo de ameaças](https://github.com/JuanenRac/HYDRA-UMC-DOCS/blob/main/docs/THREAT_MODEL.md) antes de confiar em qualquer afirmação aqui para a segurança de uma pessoa.

## 📋 Num relance

| | |
|---|---|
| Versão | `0.5.3` |
| Maturidade | Funcional |
| Testes | 13 (`python -m unittest`) |
| Tecnologia | Raspberry Pi OS ARM64 / Debian/apt / systemd / udev / NetworkManager |
| Destino | O Raspberry Pi CM5 de uma célula HYDRA-UMC |
| Em hardware real | Ainda não: não há registo de execução em hardware real para esta versão |

## 🖥️ Camada de plataforma HYDRA-UMC para o Raspberry Pi OS

O HYDRA-UMC-OS é a camada de plataforma instalável para um nó CM5 do HYDRA-UMC. Está construído sobre o Raspberry Pi OS ARM64; não substitui o Linux, o kernel do Raspberry Pi, o systemd, o NetworkManager, a libcamera nem os SDK dos fabricantes.

A sua responsabilidade é fornecer um perfil de dispositivo HYDRA-UMC reproduzível: configuração, ciclo de vida dos serviços, identidade local, diagnósticos, imagem de marca visual e atualizações coordenadas dos componentes HYDRA-UMC.

**Verificação de honestidade - o que realmente funciona hoje:** o agente de dispositivo só de leitura (`agent/src/hydra_umc_os/agent.py`: `DeviceDescriptor`/`HealthReport`, verificações de temperatura/armazenamento/rede, carregamento de perfis de configuração) é real e testado (13 testes unitários, `agent/tests/test_agent.py`, `python -m unittest discover`). O `provisioning/preflight_cm5.py` está verificado como idempotente e sem efeitos secundários por um teste real que o executa duas vezes e compara a saída (`tools/verify_preflight_idempotent.py`) mais 5 verificações reais de caminhos negativos (`tools/verify_preflight_negative.py`); o mecanismo de cópia de segurança/restauro de `provisioning/rollback.py` está verificado por 8 verificações reais, incluindo um cenário genuíno de falha parcial (`tools/verify_rollback.py`); a máquina de estados de recurso em modo AP de `provisioning/wifi_provision.py` está verificada por 46 verificações reais contra um NetworkManager simulado, incluindo uma ida e volta HTTP real de ponta a ponta sobre um socket de loopback verdadeiro (`tools/verify_wifi_provision.py`) - nenhuma das três precisa de root nem de um CM5 físico para ser verificada. O que nada disto correu: hardware CM5 real. O `image-builder/` é só documentação (um README de notas de reprodutibilidade, ainda sem código de montagem de imagem); `packages/` contém metadados reais de pacotes Debian (`control`/`rules`) que ainda não foram compilados num `.deb` verdadeiro neste ambiente. Veja o `CHANGELOG.md` para saber exatamente o que já foi entregue, e `docs/CM5_SOFTWARE_READINESS.md` para a linha precisa entre o que está verificado aqui e o que ainda precisa de hardware físico.

## 🚧 Estado

O agente base, a sua configuração validada sem segredos, uma unidade systemd endurecida e testes no anfitrião estão implementados. O agente é deliberadamente só de leitura: a montagem de imagens de produção e a validação em hardware CM5 continuam a ser portas de lançamento separadas.

O preflight de instalação (`provisioning/preflight_cm5.py`) está provado idempotente e sem efeitos secundários por um teste real - duas execuções seguidas produzem uma saída idêntica byte a byte e não tocam em nenhum ficheiro deste repositório - e um mecanismo real de cópia de segurança/reversão independente do anfitrião (`provisioning/rollback.py`) protege o único ficheiro de sistema que o `install_local_agent.sh` sobrescreve incondicionalmente em cada execução. Ambos estão verificados sem root nem CM5 - veja `tools/verify_preflight_idempotent.py` e `tools/verify_rollback.py`.

**O aprovisionamento Wi-Fi de primeiro contacto também é real** (`provisioning/wifi_provision.py` / `hydra-umc-wifi-provision.service`): um recurso real em modo AP do NetworkManager para um CM5 sem monitor e sem rede conhecida - levanta um hotspot real (`nmcli device wifi hotspot`) a que o telemóvel/portátil de um operador se pode ligar para submeter o SSID/palavra-passe reais da rede de destino através de um pequeno formulário HTTP local, desliga o AP e liga-se à rede real em caso de sucesso, restaura-o em caso de falha para que o dispositivo nunca fique encurralado. A máquina de estados está totalmente testada com um NetworkManager simulado, incluindo uma ida e volta HTTP real de ponta a ponta sobre um socket de loopback verdadeiro - veja `tools/verify_wifi_provision.py`. Instalado pelo `install_cm5_base.sh` mas deliberadamente não ativado automaticamente, já que não deve arrancar com a sua própria palavra-passe de AP de marcador num dispositivo real alcançável por ar - veja `provisioning/CM5_DEPLOYMENT_SEQUENCE.md`, secção 3, para o passo real da palavra-passe exigido primeiro.

**Os segredos geram-se por dispositivo, nunca se tomam de um modelo.** O `install_server.sh` e o `install_voice_ui.sh` criam os seus ficheiros env a partir do exemplo quando faltam e substituem cada valor de exemplo (`JWT_SECRET`, a palavra-passe do administrador inicial, o token do relé de voz) por um aleatório deste dispositivo (`provisioning/generate_secrets.py`; o que o operador já escolheu mantém-se, e a palavra-passe do administrador imprime-se uma só vez), e depois recusam continuar se ficar um valor de exemplo ou um segredo curto; o `preflight_cm5.py` recusa um `/etc/hydra-umc/*.env` que ainda leve algum. O `install_industrial_gateway.sh` escreve o `.env` da pilha (`provisioning/gateway_env.py`: o segredo do gateway e uma credencial MQTT e uma regra de ACL por cada ponte de máquina). A rede Wi-Fi de configuração já não tem uma palavra-passe no código-fonte: cada dispositivo gera a sua e um código de configuração de uso único no primeiro arranque (lê-se uma vez no journal, para escrever na etiqueta), o formulário pede o código (bloqueado um minuto após cinco erros), a rede de configuração só fica aberta 30 minutos após cada arranque e o formulário recusa pedidos demasiado grandes. Verificado por `tools/verify_generate_secrets.py`, `tools/verify_gateway_env.py` e `tools/verify_wifi_provision.py`.

## 🎯 Primeiro marco

Concluído, segundo a secção Estado acima (código real, testes reais, ainda não verificado contra hardware CM5 físico):

1. ✅ Construir um perfil Raspberry Pi OS ARM64 para o CM5 (`install_cm5_base.sh` e o resto de `provisioning/`).
2. ✅ Instalar `hydra-umc-platform-base` e `hydra-umc-agent`.
3. ✅ Detetar as interfaces do CM5 e reportar um `DeviceDescriptor` e um `HealthReport`.
4. ✅ Iniciar apenas os serviços ativados através do systemd.
5. ✅ Mostrar localmente READY, DEGRADED, INHIBITED ou FAULT.

## 📂 Estrutura do repositório

<p align="center">
  <img src="images/REPOSITORY_LAYOUT.svg" alt="Visual map of the HYDRA-UMC-OS repository layout" width="100%">
</p>

| Caminho | Finalidade |
| --- | --- |
| `docs/` | Especificações de arquitetura, instalação, serviços e atualização. |
| `image-builder/` | Fronteira oficial de montagem de imagens do Raspberry Pi OS e notas de reprodutibilidade. |
| `packages/` | Metadados de pacotes Debian para `hydra-umc-platform-base`. |
| `agent/` | Agente Python só de leitura de descritor e saúde do dispositivo, com testes unitários. |
| `systemd/` | Unidades de ciclo de vida endurecidas `hydra-umc-agent.service` e `hydra-umc-wifi-provision.service`. |
| `config/` | Esquemas por defeito e configuração sem segredos. |

Leia [a arquitetura](docs/ARCHITECTURE.md) antes de implementar código.

## 📖 Mais documentação

- **[`docs/AGENT_REFERENCE.md`](docs/AGENT_REFERENCE.md)** — referência real de comandos/saída do `hydra-umc-agent`, a CLI de diagnóstico só de leitura.
- **[`docs/INSTALLATION.md`](docs/INSTALLATION.md)** — desenho da instalação: plataforma de destino e sequência de instalação pretendida.
- **[`docs/CM5_PROVISIONING.md`](docs/CM5_PROVISIONING.md)** — o guia completo para converter o Raspberry Pi OS Lite em HYDRA-UMC-OS.
- **[`docs/CM5_WINDOWS_HOST_FLASHING.md`](docs/CM5_WINDOWS_HOST_FLASHING.md)** — o procedimento verificado para flashar um CM5 a partir de um anfitrião Windows.
- **[`docs/CM5_FIRST_BOOT_CHECKLIST.md`](docs/CM5_FIRST_BOOT_CHECKLIST.md)** — uma lista de verificação da plataforma BASE para o primeiro arranque de um CM5.
- **[`docs/CM5_PACKAGE_MANIFEST.md`](docs/CM5_PACKAGE_MANIFEST.md)** — a lista real de pacotes por fase de implantação.
- **[`docs/CM5_ECOSYSTEM_DEPLOYMENT.md`](docs/CM5_ECOSYSTEM_DEPLOYMENT.md)** — o plano de implantação por fases, com reversão independente, do resto do ecossistema num CM5.
- **[`docs/CM5_SOFTWARE_READINESS.md`](docs/CM5_SOFTWARE_READINESS.md)** — o que foi verificado sem hardware CM5 físico, e onde essa verificação termina.
- **[`docs/SERVICE_MODEL.md`](docs/SERVICE_MODEL.md)** — como correm os serviços HYDRA-UMC: utilizadores dedicados, caminhos de configuração, ordem de dependência/prontidão.
- **[`docs/UPDATE_MODEL.md`](docs/UPDATE_MODEL.md)** — os canais de atualização separados para o SO, os pacotes HYDRA-UMC, os runtimes Hailo e o firmware MCU/URTC.
- **[`docs/SDK_INTEGRATION_BOUNDARY.md`](docs/SDK_INTEGRATION_BOUNDARY.md)** — como este repositório consome o contrato publicado do HYDRA-UMC-SDK sem o incorporar.
- **[`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md)** — regras de desenvolvimento: interfaces nativas do Raspberry Pi OS primeiro, a ordem de testes obrigatória.
- **[`docs/HEADER_CONVENTION.md`](docs/HEADER_CONVENTION.md)** — a convenção de cabeçalho de copyright/licença para novos ficheiros de código e documentação.
- **[`provisioning/ssh_hardening.md`](provisioning/ssh_hardening.md)** — os passos reais de endurecimento SSH para um CM5 (verifique o início de sessão por chave antes de desativar a autenticação por palavra-passe).

## 🛠️ COMPILAR E EXECUTAR

Use a verificação de compilação sem versão antes de uma compilação de lançamento:

| Ação | Windows | Linux / macOS |
|---|---|---|
| Verificação de compilação (sem alteração de versão nem de CHANGELOG) | `build-test.bat` | `./build-test.sh` |
| Executar / desenvolvimento (quando existir) | `run*.bat` ou `dev*.bat` | `./run*.sh` ou `./dev*.sh` |

## 🔗 Projetos relacionados

Este projeto faz parte do ecossistema de robótica HYDRA-UMC do mesmo autor (JuanenRac / Electro Hobby 3D). Vale a pena conhecê-los, porque um pedido pode ser, na verdade, sobre um destes e não sobre este repositório.

**Projetos filhos**
- **[HYDRA-UMC-SDK](https://github.com/JuanenRac/HYDRA-UMC-SDK)** — o contrato JSON-Schema partilhado e a fronteira de software de controlo de trabalhos contra a qual cada bridge valida os seus comandos (não é uma função de segurança certificada); contratos versionados, clientes finos e fixtures de conformidade usados pelo agente de dispositivo deste SO.
- **[HYDRA-UMC-CONNECTOR-HUB](https://github.com/JuanenRac/HYDRA-UMC-CONNECTOR-HUB)** — registo declarativo de manifestos de adaptador e validador para conectores de máquinas externas; estende a ideia de contrato do SDK a máquinas externas sem substituir os projetos de gateway industrial.
- **[HYDRA-UMC-OS-REBUILDER](https://github.com/JuanenRac/HYDRA-UMC-OS-REBUILDER)** — ferramenta de desktop Windows/Linux que constrói uma imagem pronta a flashar deste SO para o CM5, pré-carregada com as versões mais recentes do ecossistema e com configuração de primeiro arranque ao estilo do Raspberry Pi Imager.
- **[HYDRA-UMC-OPS-AGENT](https://github.com/JuanenRac/HYDRA-UMC-OPS-AGENT)** — coordenador de incidentes de manutenção: um papel de borda de poucos privilégios recolhe um inventário/estado higienizado, um papel de plano de controlo mostra-o só de leitura e pede a um fornecedor de IA que sugira um diagnóstico; nunca aplica um patch nem implanta nada.
- **[HYDRA-UMC-DEV-SERVER](https://github.com/JuanenRac/HYDRA-UMC-DEV-SERVER)** — anfitrião de desenvolvimento reproduzível (Raspberry Pi 5 / CM5) que guarda o código-fonte do ecossistema e executa tarefas limitadas de compilação/teste numa fila durável; um papel de desenvolvimento dedicado, explicitamente não um CM5 operacional.

**Diretamente relacionados**
- **[HYDRA-UMC](https://github.com/JuanenRac/HYDRA-UMC)** — o desenho da placa-mãe do braço robótico: anfitrião CM5 + STM32H745 de dois núcleos, pensado para orquestrar até 8 braços de ferramenta por CAN-OTA/SPI-OTA (firmware numa fase inicial; ainda sem placa montada); a plataforma de hardware e firmware CM5/MCU que esta camada de SO configura e supervisiona.
- **[HYDRA-UMC-SERVER](https://github.com/JuanenRac/HYDRA-UMC-SERVER)** — o back-end headless real (REST/WebSocket) com que todos os clientes de controlo realmente comunicam; a fronteira de serviço autenticada das integrações geridas deste nó.
- **[URTC](https://github.com/JuanenRac/URTC)** — firmware da placa física Universal Robot Tool Controller, mais de 25 perfis de ferramenta por barramento CAN; uma plataforma independente de controlador de ferramentas integrada através de adaptadores explícitos e versionados.
- **[HYDRA-UMC-UPDATER](https://github.com/JuanenRac/HYDRA-UMC-UPDATER)** — ferramenta de administração para desktop que descobre, clona e atualiza todos os repositórios deste ecossistema; o seu registo de artefactos, os metadados de compatibilidade e o fluxo de atualização coordenado.

**Também fazem parte do ecossistema**

*Backend central e clientes*
- **[HYDRA-UMC-STUDIO](https://github.com/JuanenRac/HYDRA-UMC-STUDIO)** — painel web de controlo com visualização 3D em tempo real de vários robôs.
- **[HYDRA-UMC-SUITE](https://github.com/JuanenRac/HYDRA-UMC-SUITE)** — centro de comando de enxame para desktop (PySide6) para vários servidores ao mesmo tempo, empacotado como executável independente.
- **[HYDRA-UMC-ANDROID-CONTROL](https://github.com/JuanenRac/HYDRA-UMC-ANDROID-CONTROL)** — aplicação Android nativa de controlo, com início de sessão biométrico e um companheiro Wear OS emparelhado.
- **[HYDRA-UMC-IOS-CONTROL](https://github.com/JuanenRac/HYDRA-UMC-IOS-CONTROL)** — aplicação de controlo para iOS/iPadOS (Flutter) com sincronização WebSocket em tempo real.
- **[HYDRA-UMC-DSI](https://github.com/JuanenRac/HYDRA-UMC-DSI)** — interface tátil nativa para o ecrã tátil DSI de 7" integrado, executada no próprio CM5.
- **[HYDRA-UMC-EDITOR-URDF](https://github.com/JuanenRac/HYDRA-UMC-EDITOR-URDF)** — criador/editor gráfico de URDF para desktop que envia os modelos concluídos para o catálogo do STUDIO.
- **[HYDRA-UMC-EDITOR-STL](https://github.com/JuanenRac/HYDRA-UMC-EDITOR-STL)** — editor de modelos STL para desktop que transforma/substitui/remove/adiciona peças reais no mesmo catálogo de modelos que o HYDRA-UMC-EDITOR-URDF também edita.
- **[HYDRA-UMC-BRIDGE-AMR](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-AMR)** — fronteira de coordenação para frotas AGV/AMR através de um publicador MQTT VDA 5050 (testado apenas contra uma frota emulada).
- **[HYDRA-UMC-BRIDGE-CNC](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-CNC)** — coordenador de células CNC de alto nível com acesso ao estado GRBL e aos bytes de controlo (testado apenas contra um emulador).
- **[HYDRA-UMC-BRIDGE-DROIDS](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-DROIDS)** — fronteira de coordenação para droides com patas/humanoides, com um emissor de comandos para o Boston Dynamics Spot (testado apenas contra um emulador).
- **[HYDRA-UMC-BRIDGE-LASER](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-LASER)** — coordenador de células laser que lê 3 sinais GPIO (chave, caixa e interlock) (testado apenas contra um chip simulado; não pode armar nem disparar um laser).
- **[HYDRA-UMC-BRIDGE-OPENPNP](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-OPENPNP)** — coordenador seguro de fluxo de placa de alto nível para pick-and-place com OpenPnP.
- **[HYDRA-UMC-BRIDGE-PRINTER3D](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-PRINTER3D)** — fronteira de coordenação segura para impressoras 3D Moonraker/Klipper, com comandos de trabalho reais protegidos por portas.
- **[HYDRA-UMC-BRIDGE-ROS2](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-ROS2)** — coordenador com um transporte ROS 2 baseado em rclpy importado sob demanda (ainda não executado contra uma instalação ROS 2).
- **[HYDRA-UMC-BRIDGE-UAV](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-UAV)** — fronteira de coordenação para UAV com câmara, com um emissor de comandos MAVLink (testado apenas contra um emulador).

*Plataforma de ferramentas URTC*
- **[URTC-FLASHER](https://github.com/JuanenRac/URTC-FLASHER)** — ferramenta gráfica de gravação para desktop das placas URTC, por CAN-OTA e também SWD/JTAG de chip completo.
- **[URTC-TESTER](https://github.com/JuanenRac/URTC-TESTER)** — ferramenta de diagnóstico CAN em tempo real para desktop das placas URTC, com um painel por perfil de ferramenta.
- **[URTC-WEB-STUDIO](https://github.com/JuanenRac/URTC-WEB-STUDIO)** — alternativa no navegador ao URTC-TESTER através da Web Serial API, sem instalação local.

*Nó de IA de visão (Hailo-8)*
- **[HYDRA-UMC-VISION-NODE](https://github.com/JuanenRac/HYDRA-UMC-VISION-NODE)** — centro de integração do pipeline de visão Hailo-8, com uma verificação real de prontidão de hardware por fase.
- **[HYDRA-UMC-DETECTION-HEF](https://github.com/JuanenRac/HYDRA-UMC-DETECTION-HEF)** — registo real de modelos compilados com verificação segura de carga por arquitetura Hailo e soma de verificação.
- **[HYDRA-UMC-VISION-STREAMER](https://github.com/JuanenRac/HYDRA-UMC-VISION-STREAMER)** — pipeline GStreamer real e gerador de configuração MediaMTX com uma fronteira de integração HailoRT real.
- **[HYDRA-UMC-VISUAL-SERVOING-API](https://github.com/JuanenRac/HYDRA-UMC-VISUAL-SERVOING-API)** — lei de correção de servovisão baseada em posição com autorização condicionada ao estado da zona; ainda sem estimativa de pose por câmara.
- **[HYDRA-UMC-SAFETY-ZONES](https://github.com/JuanenRac/HYDRA-UMC-SAFETY-ZONES)** — lógica v0 de violação de zonas, atualidade da calibração e pedido de E-STOP que lê as posições dos objetos de um ficheiro; nenhum detetor a alimenta e ainda não há E-STOP físico ligado.

*Nó de IA cognitiva (Hailo-10)*
- **[HYDRA-UMC-COGNITIVE-NODE](https://github.com/JuanenRac/HYDRA-UMC-COGNITIVE-NODE)** — centro de integração do pipeline cognitivo do Hailo-10 (orquestração de LLM/VLA/voz).
- **[HYDRA-UMC-VLA-ENGINE](https://github.com/JuanenRac/HYDRA-UMC-VLA-ENGINE)** — codificação/descodificação real de tokens de ação e geração de trajetórias para um modelo Visão-Linguagem-Ação.
- **[HYDRA-UMC-VOICE-UI](https://github.com/JuanenRac/HYDRA-UMC-VOICE-UI)** — front-end de voz real (VAD + analisador de intenções) com um relé para o relógio limitado e protegido por confirmação.
- **[HYDRA-UMC-SEMANTIC-PLANNER](https://github.com/JuanenRac/HYDRA-UMC-SEMANTIC-PLANNER)** — decomposição real de tarefas baseada em regras e recuperação semântica de erros sobre os códigos de erro do MCU.
- **[HYDRA-UMC-DOCS-QA](https://github.com/JuanenRac/HYDRA-UMC-DOCS-QA)** — pesquisa real de documentos TF-IDF só com a biblioteca padrão sobre a documentação Markdown deste ecossistema.
- **[HYDRA-UMC-LOCAL-TECHNICIAN](https://github.com/JuanenRac/HYDRA-UMC-LOCAL-TECHNICIAN)** — técnico de manutenção de IA local, protegido por políticas, para o próprio ecossistema: observa, diagnostica e propõe correções; os dois níveis de maior risco não estão implementados de propósito.

*Orquestração e enxame*
- **[HYDRA-UMC-ORCHESTRATOR](https://github.com/JuanenRac/HYDRA-UMC-ORCHESTRATOR)** — centro de integração com um contrato real de relatório de saúde gRPC/Protobuf e uma máquina de estados de missões.
- **[HYDRA-UMC-JOB-DISPATCHER](https://github.com/JuanenRac/HYDRA-UMC-JOB-DISPATCHER)** — fila real de trabalhos por prioridade com deduplicação, sobre uma API HTTP real.
- **[HYDRA-UMC-NODE-HEALING](https://github.com/JuanenRac/HYDRA-UMC-NODE-HEALING)** — vigilante real de saúde da frota por gRPC com repetição/recuo e deteção de identidade incoerente.
- **[HYDRA-UMC-PATH-PLANNER-3D](https://github.com/JuanenRac/HYDRA-UMC-PATH-PLANNER-3D)** — planeador real de trajetórias 3D baseado em RRT com validação real de colisões com obstáculos e espaço de trabalho.
- **[HYDRA-UMC-SWARM-SYNC](https://github.com/JuanenRac/HYDRA-UMC-SWARM-SYNC)** — sincronização real de estado CRDT LWW-Element-Map, testada por propriedades para a convergência de várias células.

*Gémeo digital e simulação*
- **[HYDRA-UMC-TWIN](https://github.com/JuanenRac/HYDRA-UMC-TWIN)** — centro de integração do motor de gémeo digital, com um contrato real de sincronização de compatibilidade de versões.
- **[HYDRA-UMC-HIL-BRIDGE](https://github.com/JuanenRac/HYDRA-UMC-HIL-BRIDGE)** — encaminhador hardware-in-the-loop com um interlock de software de colisão entre a simulação e o hardware real (testado sem hardware real).
- **[HYDRA-UMC-PHYSICS-REPLICA](https://github.com/JuanenRac/HYDRA-UMC-PHYSICS-REPLICA)** — cinemática direta real e validação de limites de juntas sobre um subconjunto real de URDF.
- **[HYDRA-UMC-SYNTHETIC-DATA-GEN](https://github.com/JuanenRac/HYDRA-UMC-SYNTHETIC-DATA-GEN)** — gerador procedural real de cenas 2D com exportação de anotações YOLO/COCO.

*Dados e análise*
- **[HYDRA-UMC-DATALAKE](https://github.com/JuanenRac/HYDRA-UMC-DATALAKE)** — armazém real de séries temporais sobre sqlite3 com uma API HTTP real de ingestão/consulta.
- **[HYDRA-UMC-ANOMALY-DETECTOR](https://github.com/JuanenRac/HYDRA-UMC-ANOMALY-DETECTOR)** — detetor real de anomalias por FFT e linha de base estatística, com monitorização de deriva.
- **[HYDRA-UMC-PRODUCTION-REPORTS](https://github.com/JuanenRac/HYDRA-UMC-PRODUCTION-REPORTS)** — cálculo real de OEE/disponibilidade sobre o histórico do DATALAKE, com exportação CSV reprodutível.
- **[HYDRA-UMC-TELEMETRY-COLLECTOR](https://github.com/JuanenRac/HYDRA-UMC-TELEMETRY-COLLECTOR)** — pipeline real de ingestão CAN/WebSocket para o DATALAKE, com deduplicação por sequência.

*Gateway industrial*
- **[HYDRA-UMC-GATEWAY-INDUSTRIAL](https://github.com/JuanenRac/HYDRA-UMC-GATEWAY-INDUSTRIAL)** — centro de integração que retransmite para protocolos industriais, com uma camada real de lista de comandos permitidos e contrapressão.
- **[HYDRA-UMC-OPCUA-SERVER](https://github.com/JuanenRac/HYDRA-UMC-OPCUA-SERVER)** — espaço de endereços OPC-UA real, verificado com uma sessão de cliente real do protocolo binário.
- **[HYDRA-UMC-MQTT-BROKER](https://github.com/JuanenRac/HYDRA-UMC-MQTT-BROKER)** — broker MQTT real com autenticação opcional por cliente e ACL de tópicos.
- **[HYDRA-UMC-MTCONNECT-ADAPTER](https://github.com/JuanenRac/HYDRA-UMC-MTCONNECT-ADAPTER)** — endpoints XML MTConnect `/probe` e `/current` reais com saída em modo degradado.

*Ferramentas complementares e operações do ecossistema*
- **[HYDRA-UMC-DASHBOARD-AI](https://github.com/JuanenRac/HYDRA-UMC-DASHBOARD-AI)** — painéis de Resumos Inteligentes e Realce de Anomalias sobre o DATALAKE/ANOMALY-DETECTOR, com um recurso estatístico honesto.
- **[HYDRA-UMC-TOOL-CLI](https://github.com/JuanenRac/HYDRA-UMC-TOOL-CLI)** — CLI da frota com um contrato de códigos de saída real e estável, um cliente vivo genuíno da API do HYDRA-UMC-SERVER.
- **[HYDRA-UMC-WATCH](https://github.com/JuanenRac/HYDRA-UMC-WATCH)** — aplicação companheira WearOS com padrões de alerta tátil e um relé de voz para o telemóvel emparelhado (ainda não executada num relógio físico).
- **[URTC-SMART-RACK](https://github.com/JuanenRac/URTC-SMART-RACK)** — firmware de um rack de montagem de placas com descodificação real do ID da ferramenta e lógica de pré-aquecimento Smart Idle.
- **[URTC-VISION-TOOL](https://github.com/JuanenRac/URTC-VISION-TOOL)** — firmware mais um companheiro de visão em Python real para uma cabeça de ferramenta de inspeção térmica/RGB.

---

## 📚 Documentação e comunidade

- **[CONTRIBUTING.md](CONTRIBUTING.md)** — pilha tecnológica e diretrizes de código para um pull request.
- **[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)** — as normas de comportamento esperadas nesta comunidade.
- **[SECURITY.md](SECURITY.md)** — como comunicar uma vulnerabilidade e as áreas de segurança em que este projeto se concentra.
- **[SUPPORT.md](SUPPORT.md)** — onde fazer perguntas e comunicar erros.
- **[LICENSE.md](LICENSE.md)** — a licença deste projeto.

## 👤 AUTOR
**JuanenRac** (Electro Hobby 3D)
📧 electrohobby3d@gmail.com
📺 [youtube.com/@electrohobby3d](https://youtube.com/@electrohobby3d)

## 📜 LICENÇA

O código é GPL-3.0-or-later e a documentação é CC BY-SA 4.0. Veja [LICENSE](LICENSE).

O `build-test.bat` e o `build-test.sh` compilam ou validam a pilha do projeto sem incrementar o `hydra-umc.project.json` nem modificar o `CHANGELOG.md`. Só podem criar a saída normal do compilador. Os scripts `build*.bat`, `build*.sh`, `run*` e `dev*` existentes mantêm o seu comportamento próprio de projeto, com versão ou de execução; use-os quando esse comportamento for necessário.

