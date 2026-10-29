<!-- =============================================================================
HYDRA-UMC-OS - Platform layer for a CM5 node on Raspberry Pi OS
Copyright (C) JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
GPL-3.0-or-later - see LICENSE
============================================================================= -->

<p align="center">
  <img src="images/HYDRA_UMC_BANNER.svg" alt="HYDRA-UMC-OS banner" width="100%">
</p>

# 🖥️ HYDRA-UMC-OS

<p align="center"><a href="README.md">🇺🇸 English</a> | <a href="README_spa.md">🇪🇸 Español</a> | <a href="README_fra.md">🇫🇷 Français</a> | <a href="README_ita.md">🇮🇹 Italiano</a> | <a href="README_deu.md">🇩🇪 Deutsch</a> | 🇨🇳 <b>简体中文</b> | <a href="README_jpn.md">🇯🇵 日本語</a> | <a href="README_por.md">🇵🇹 Português</a></p>

### Raspberry Pi OS 上 HYDRA-UMC 节点的可复现平台层

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

> **安全与安防现状:**本生态系统不是经认证的安全系统。目前尚无硬件 E-STOP 通路,没有由固件强制执行的限位或联锁,也没有经过验证的运动指令;固件映像使用 CRC32 和共享密钥的 HMAC-SHA256 校验,而非非对称签名;TLS 与双向 TLS 均为可选项,默认关闭;自制电路板尚未组装或测试。在依赖此处任何说法来保障人身安全之前,请先阅读[安全基线](https://github.com/JuanenRac/HYDRA-UMC-DOCS/blob/main/docs/SECURITY_BASELINE.md)和[威胁模型](https://github.com/JuanenRac/HYDRA-UMC-DOCS/blob/main/docs/THREAT_MODEL.md)。

---

## 📋 速览

| | |
|---|---|
| 版本 | `0.5.4` |
| 成熟度 | 可用 |
| 测试 | 20 (`python -m unittest discover -s agent/tests`) |
| 技术栈 | Raspberry Pi OS ARM64 / Debian/apt / systemd / udev / NetworkManager |
| 目标 | HYDRA-UMC 工作单元的 Raspberry Pi CM5 |
| 真实硬件 | 尚未：此版本没有在真实硬件上运行的记录 |

**跳转：** [概述](#-概述) · [架构](#-架构) · [快速开始](#-快速开始) · [测试](#-测试) · [仓库结构](#-仓库结构) · [相关项目](#-相关项目)

## 🚦 项目状态

每一行是本仓库的一个部分，灯号表示它今天做到了哪一步。内容依据仓库能够展示的证据（测试、构建、运行），而不是计划。

🟢 已完成并验证 · 🟡 可用，有已知限制 · 🟠 部分完成或尚未验证 · 🔴 未完成或不可用

| 领域 | 状态 | 在这里的含义 |
|---|---|---|
| 软件 | 🟡 | 主要用途可用；上面的诚实性检查列出了仍然缺少的内容 |
| 测试 | 🟢 | 20 项自动测试，每次变更都会运行 |
| 真实硬件 | 🔴 | 尚未：此版本没有在真实硬件上运行的记录 |
| 文档 | 🟢 | 八种语言的 README，每次变更都会与清单核对 |

## 🎯 概述

HYDRA-UMC-OS 是 HYDRA-UMC CM5 节点的可安装平台层。
它基于 Raspberry Pi OS ARM64 构建；它不会取代 Linux，
Raspberry Pi 内核、systemd、NetworkManager、libcamera 或供应商 SDK。

其职责是提供可重复的 HYDRA-UMC 设备配置文件：
配置、服务生命周期、本地身份、诊断、视觉品牌
以及 HYDRA-UMC 组件的协调更新。

**诚实核查——今天真正能跑起来的部分：** 只读设备代理（`agent/src/hydra_umc_os/agent.py`：`DeviceDescriptor`/`HealthReport`，温度/存储/网络检查，配置档案加载）是真实且经过测试的（20 个单元测试，`agent/tests/test_agent.py`，`python -m unittest discover`）。`provisioning/preflight_cm5.py` 通过一个真实测试验证为幂等且无副作用——运行两次并对比输出（`tools/verify_preflight_idempotent.py`），外加 5 项真实的反向路径检查（`tools/verify_preflight_negative.py`）；`provisioning/rollback.py` 的备份/恢复机制由 8 项真实检查验证，其中包括一个真正的部分失败场景（`tools/verify_rollback.py`）；`provisioning/wifi_provision.py` 的 AP 模式回退状态机由针对一个伪造 NetworkManager 的 46 项真实检查验证，其中包括一次通过真实回环套接字完成的端到端 HTTP 往返（`tools/verify_wifi_provision.py`）——这三者都不需要 root 权限或物理 CM5 即可验证。目前唯一没有被验证过的：真实的 CM5 硬件本身。`image-builder/` 目前只是文档（一份关于可复现性说明的 README，还没有镜像组装代码）；`packages/debian/` 包含软件包 `hydra-umc-platform-base` 的维护者脚本和版权文件，`tools/build_deb.py` 会把它构建成真正的 `.deb`（纯 Python，无需 dpkg，每次字节完全相同），`tools/verify_deb_package.py` 会读回并检查；尚未在真实的 CM5 上安装过。已交付的具体内容见 `CHANGELOG.md`，这里已验证的部分与仍需物理硬件的部分之间的确切界线见 `docs/CM5_SOFTWARE_READINESS.md`。

## 🧩 在 HYDRA-UMC 中的角色

**HYDRA-UMC-OS** 是 CM5 节点的平台层：在 Raspberry Pi OS 之上提供配置、服务生命周期、本地身份、诊断、视觉外观和协调更新，并带有只读的设备代理。它不替代 Linux、systemd 或厂商 SDK；镜像由 `HYDRA-UMC-OS-REBUILDER` 构建。

## 🏛️ 架构

<p align="center">
  <img src="images/architecture.svg" alt="HYDRA-UMC-OS architecture" width="100%">
</p>

## 🚀 快速开始

代理测试只需要 Python 3.11 或更高版本；镜像本身由 `HYDRA-UMC-OS-REBUILDER` 构建。

```bash
PYTHONPATH=agent/src python3 -m unittest discover -s agent/tests
./build-test.sh  # non-mutating build check (build-test.bat on Windows)
```

## 🧪 测试

运行 `python -m unittest discover -s agent/tests` 会执行 20 个自动测试。 不需要硬件，也不需要这台机器以外的任何东西。

CI 运行 `HYDRA_UMC_CI=1 python tools/ci_validate.py`，检查清单、文档、八个 README 和图片。

## 🏗️ 构建与发布

请在发布构建前使用不改动版本的构建检查：

| 操作 | Windows | Linux / macOS |
|---|---|---|
| 构建检查（不修改版本或 CHANGELOG） | `build-test.bat` | `./build-test.sh` |
| 运行 / 开发（如提供） | `run*.bat` 或 `dev*.bat` | `./run*.sh` 或 `./dev*.sh` |

`build-test.bat` 和 `build-test.sh` 会编译或验证项目技术栈，但不会递增 `hydra-umc.project.json`，也不会修改 `CHANGELOG.md`。它们仅可能生成正常的编译器输出。现有的 `build*.bat`、`build*.sh`、`run*` 和 `dev*` 脚本保留各自的版本化或运行时行为；需要该行为时请使用它们。

## 📂 仓库结构

<p align="center">
  <img src="images/repository-structure.svg" alt="Repository structure of HYDRA-UMC-OS" width="100%">
</p>

<details>
<summary>目录树的文本版本</summary>

```text
HYDRA-UMC-OS/
├── docs/                      架构、安装、服务和更新规范。
├── image-builder/             官方 Raspberry Pi OS 镜像组装边界和可复现性说明。
├── packages/                  Debian 软件包 `hydra-umc-platform-base` 的维护者脚本和版权文件（由 `tools/build_deb.py` 构建）。
├── agent/                     只读的 Python 设备描述符与健康状态代理，含单元测试。
├── systemd/                   强化的 `hydra-umc-agent.service` 和 `hydra-umc-wifi-provision.service` 生命周期单元。
├── config/                    默认模式和非秘密配置。
├── provisioning/              CM5 的安装程序 (每个服务一个)、首次启动、诊断、恢复、设置的备份与还原、防火墙、MQTT 的 TLS、展台与启动画面、polkit 规则以及安装检查。
├── tools/                     打包与发布工具 (`build_deb.py`、`package_component.py`)、配置脚本的 `verify_*.py` 检查以及共享的 CI 检查。
├── .github/                   CI 工作流和 Issue 模板
├── images/                    横幅和 README 的图片
├── CHANGELOG.md               每个版本的变更
├── build-test.sh              不修改内容的构建检查
├── build.sh                   构建并检查；从不改变版本
├── bump_manifest_version.py   同步清单版本
├── bump_version.py            显式提升版本
├── hydra-umc.project.json     清单：版本、成熟度、系列
├── run.sh                     启动程序
└── test.sh                    运行测试
```

</details>

## 🗺️ 路线图与已知限制

**当前已知限制**

**当前已知限制**

### 状态

基本代理、经过验证的非秘密配置、强化的 systemd
单元和主机端测试均已实施。该代理是刻意
只读的：生产镜像组装和 CM5 硬件验证仍是
独立的发布关卡。

安装预检（`provisioning/preflight_cm5.py`）已通过一项真实测试证明其具有幂等性且无副作用——连续运行两次会产生逐字节相同的输出，并且不会触及此仓库中的任何文件——而一个真实的、与主机无关的备份/回滚机制（`provisioning/rollback.py`）保护着 `install_local_agent.sh` 在每次运行时无条件覆盖的那一个系统文件。两者均已在无需 root 权限或 CM5 的情况下完成验证——参见 `tools/verify_preflight_idempotent.py` 和 `tools/verify_rollback.py`。

**WiFi 首次接触配网同样是真实的**（`provisioning/wifi_provision.py` / `hydra-umc-wifi-provision.service`）——为尚无已知网络的无头 CM5 提供真实的 NetworkManager AP 模式回退：启动一个真实的热点（`nmcli device wifi hotspot`），操作员的手机/笔记本电脑可以加入该热点，通过一个小型本地 HTTP 表单提交真实的目标 SSID/密码，成功后关闭 AP 并加入真实网络，失败时恢复 AP，使设备永远不会被困住。该状态机针对一个伪造的 NetworkManager 进行了完整的单元测试，包括通过真实回环套接字进行的真实端到端 HTTP 往返——参见 `tools/verify_wifi_provision.py`。由 `install_cm5_base.sh` 安装，但刻意未自动启用，因为它只应在确实需要的设备上运行：其接入点密码和一次性设置码会在每台设备首次启动时生成，并只从日志中读取一次——参见 `provisioning/CM5_DEPLOYMENT_SEQUENCE.md` 第 3 节。

**密钥按设备生成，绝不从模板沿用。** `install_server.sh` 和 `install_voice_ui.sh` 在 env 文件缺失时会根据示例创建，并把每个示例值（`JWT_SECRET`、首个管理员密码、语音中继令牌）替换为本设备的随机值（`provisioning/generate_secrets.py`；运维人员已选定的值会保留，管理员密码只显示一次），随后如果仍残留示例值或过短的密钥就拒绝继续；`preflight_cm5.py` 会拒绝仍含有示例值的 `/etc/hydra-umc/*.env`。`install_industrial_gateway.sh` 会把该栈的密钥写到 `/etc/hydra-umc/gateway.env`（仅 root 可读，位于用户的检出之外，由 compose 通过 `--env-file` 读取；旧版本留在检出中的 `.env` 会被移动到那里）（`provisioning/gateway_env.py`：网关密钥，以及每个设备桥接器各一份 MQTT 凭据和 ACL 规则）。Wi-Fi 配置网络的源码中不再有密码：每台设备在首次启动时生成自己的密码和一次性配置码（在日志中读取一次，写到标签上），表单要求输入配置码（连续五次错误后锁定一分钟），配置网络在每次启动后只开放 30 分钟，表单会拒绝过大的请求。由 `tools/verify_generate_secrets.py`、`tools/verify_gateway_env.py` 和 `tools/verify_wifi_provision.py` 验证。 主机名和配网网络名称的末尾也带有取自设备的六个字符（Raspberry Pi 序列号，否则为 MAC 地址），因此用同一镜像烧录的两台设备不再共用同一个名称（`provisioning/device_identity.py`，由 `tools/verify_device_identity.py` 检查）；`HYDRA_UMC_DEVICE_SUFFIX=off` 保留固定名称，您自己选定的名称永远不会被更改。

**签名密钥由安装程序分发。** Voice UI 用来给确认结果签名的密钥(`HYDRA_UMC_VOICE_UI_RESULT_KEY`)由 `install_server.sh` 或 `install_voice_ui.sh`(先运行的那个)为设备生成一次,并写入 `/etc/hydra-umc/server.env` 和 `/etc/hydra-umc/voice-ui.env`(来自旧模板的文件会被补上这一行),同时为服务器设置 `HYDRA_UMC_VOICE_CONFIRM_REQUIRE_SIGNATURE=1`,为 Voice UI 设置 `HYDRA_UMC_VOICE_UI_REQUIRE_SUBJECT=1`(`generate_secrets.py --ensure`;操作员已有的行,无论取值如何,都不会被改动)。`install_local_technician.sh` 在 `/etc/hydra-umc-local-technician/result.key` 中生成给每个工具结果签名的密钥(`provisioning/make_result_key.py`:64 个随机十六进制字符,从第一个字节起权限即为 0600,仅 root 可读,从不打印,一旦存在就不会被替换,也不会跟随符号链接),并让设置文件指向它;`--no-signing`(或 `HYDRA_UMC_LOCAL_TECHNICIAN_SIGNING=off`)则不写这一行。镜像和仓库中从来没有密钥,两台设备也从不共用一个。由 `tools/verify_result_keys.py` 验证。

**审计日志，默认开启。** `install_local_technician.sh` 会开启技术员的只追加、哈希链式审计日志，`install_node_healing.sh` 会开启看门狗的日志（均在 5 MiB 时轮转，保留 5 个文件）：技术员被要求做了什么、看门狗对某个节点做了什么决定，是故障之后真正重要的证据，所以安装器会把该设置以启用状态写入带说明的设置文件（`/etc/hydra-umc-local-technician/local-technician.env`、`/etc/hydra-umc-node-healing/journal.env`）。`--no-audit` / `--no-journal`（或 `HYDRA_UMC_LOCAL_TECHNICIAN_AUDIT=off`、`HYDRA_UMC_NODE_HEALING_JOURNAL=off`）会让日志保持关闭并把已启用的那一行注释掉，绝不删除已记录的内容；已有的设置文件不会被覆盖。`tools/verify_optional_journals.py` 以静态方式检查选项和名称；尚未在真实 CM5 上用它们安装过。

**为 Go 服务固定的 Go 版本。** 作业调度器、节点看门狗和遥测收集器都在设备上构建，它们的 `go.mod` 要求的 Go 比 Debian 软件库里的 `golang-go` 更新，后者无法构建它们。它们的安装器现在会加载 `provisioning/go_toolchain.sh`：来自 go.dev 的一个官方发行版，先用固定的 SHA-256 校验，再解压到 `/usr/local/go-<版本>`（系统自带的 Go 不受影响）。`tools/verify_go_toolchain.py` 用模拟下载（正确的压缩包、损坏的、已安装的）运行该辅助脚本，并把固定版本与同级项目的 `go.mod` 比较；尚未在真实 CM5 上用它安装过。

**统一的服务注册表。** 每个服务的端口、健康路由和 systemd 单元都来自 `provisioning/ports.yaml`(由项目清单生成的 SDK `contracts/ports.yaml` 的副本)。服务的每个安装脚本结束时都会说明运行后在哪里查看,`verify_cm5_runtime.sh --with-services` 会探测每个正在运行的服务的健康路由(只读;未运行的会被跳过)。`tools/verify_service_registry.py` 用桩程序检查辅助脚本、安装脚本和运行时检查;尚未在真实 CM5 上用它安装过任何内容。

### 第一个里程碑

已完成，按照上方"状态"小节所述（真实代码、真实测试，尚未针对真实
CM5 硬件验证）：

1. ✅ 为 CM5 构建 Raspberry Pi OS ARM64 配置文件。
2. ✅ 安装 `hydra-umc-platform-base` 和 `hydra-umc-agent`。
3. ✅ 检测 CM5 接口并报告 `DeviceDescriptor` 和 `HealthReport`。
4. ✅ 仅启动通过 systemd 启用的服务。
5. ✅ 本地显示 READY、DEGRADED 或 FAULT。

## 🌍 语言

本 README 和仓库文档提供八种语言：英语、西班牙语、德语、法语、意大利语、日语、中文和葡萄牙语（葡萄牙）。它们同时编写，并由 CI 检查八个文件拥有相同的章节和相同的链接。 本仓库没有自己的界面或消息目录，因此没有需要翻译的界面文字。

## 🔗 相关项目

本项目是同一作者(JuanenRac / Electro Hobby 3D)打造的 HYDRA-UMC 机器人生态系统的一部分。值得了解,因为某个请求实际上可能是关于这些项目之一,而非本仓库本身。

**子项目**
- **[HYDRA-UMC-SDK](https://github.com/JuanenRac/HYDRA-UMC-SDK)** —— 每个桥接都据此校验自身指令的共享 JSON-Schema 契约与软件作业门限边界(并非经认证的安全功能);本操作系统自身的设备代理所使用的、经过版本管理的契约、轻量客户端与合规性测试夹具。
- **[HYDRA-UMC-OS-REBUILDER](https://github.com/JuanenRac/HYDRA-UMC-OS-REBUILDER)** —— 为 CM5 构建本操作系统即刻可烧录镜像的 Windows/Linux 桌面工具，预装生态系统最新版本，并提供 Raspberry Pi Imager 风格的首次启动配置。

**直接相关**
- **[HYDRA-UMC](https://github.com/JuanenRac/HYDRA-UMC)** —— 机器人手臂主板设计——CM5 主机 + 双核 STM32H745,目标是通过 CAN-OTA/SPI-OTA 协调最多 8 条工具臂(固件处于早期阶段,尚无已组装的电路板);本操作系统层所配置和监管的 CM5/MCU 硬件与固件平台。
- **[HYDRA-UMC-SERVER](https://github.com/JuanenRac/HYDRA-UMC-SERVER)** —— 每个控制客户端真正通信的真实无头后端(REST/WebSocket);本节点受管理集成的认证服务边界。
- **[URTC](https://github.com/JuanenRac/URTC)** —— 面向实体 Universal Robot Tool Controller 板卡的固件,通过 CAN 总线支持 25 种以上工具配置;通过显式的、经过版本管理的适配器集成的独立工具控制器平台。
- **[HYDRA-UMC-UPDATER](https://github.com/JuanenRac/HYDRA-UMC-UPDATER)** —— 发现、克隆并更新本生态系统中每个仓库的管理类桌面工具;其制品注册表、兼容性元数据与协调更新流程。
- **[HYDRA-UMC-CONNECTOR-HUB](https://github.com/JuanenRac/HYDRA-UMC-CONNECTOR-HUB)** — 面向外部机器连接器的声明式适配器清单注册与校验工具；把 SDK 自身的契约理念扩展到外部机器，而不取代工业网关类项目。
- **[HYDRA-UMC-OPS-AGENT](https://github.com/JuanenRac/HYDRA-UMC-OPS-AGENT)** — 维护事件协调器：一个低权限的边缘角色采集经过脱敏的库存/健康快照，一个控制面角色以只读方式渲染它，并请求某个 AI 提供方给出诊断建议——从不应用补丁，也从不部署任何内容。
- **[HYDRA-UMC-DEV-SERVER](https://github.com/JuanenRac/HYDRA-UMC-DEV-SERVER)** — 可复现的开发主机（Raspberry Pi 5 / CM5），保存整个生态系统的源代码，并在持久队列下运行有界的构建/测试任务；这是专用的开发角色，明确区别于运行中的 CM5。

**生态系统中的其他项目**

*核心后端与客户端*
- **[HYDRA-UMC-STUDIO](https://github.com/JuanenRac/HYDRA-UMC-STUDIO)** —— 具有实时多机器人 3D 可视化的网页控制面板。
- **[HYDRA-UMC-SUITE](https://github.com/JuanenRac/HYDRA-UMC-SUITE)** —— 面向多台服务器的桌面(PySide6)集群指挥中心,打包为独立可执行文件。
- **[HYDRA-UMC-ANDROID-CONTROL](https://github.com/JuanenRac/HYDRA-UMC-ANDROID-CONTROL)** —— 具有生物识别登录和配对 Wear OS 伴侣应用的原生 Android 控制应用。
- **[HYDRA-UMC-IOS-CONTROL](https://github.com/JuanenRac/HYDRA-UMC-IOS-CONTROL)** —— 具有实时 WebSocket 同步的 iOS/iPadOS 控制应用(Flutter)。
- **[HYDRA-UMC-DSI](https://github.com/JuanenRac/HYDRA-UMC-DSI)** —— 面向机载 7 英寸 DSI 触摸屏的原生触控界面,直接嵌入 CM5 本体。
- **[HYDRA-UMC-EDITOR-URDF](https://github.com/JuanenRac/HYDRA-UMC-EDITOR-URDF)** —— 将完成的模型推送到 STUDIO 自身目录的桌面版图形化 URDF 创建/编辑工具。
- **[HYDRA-UMC-EDITOR-STL](https://github.com/JuanenRac/HYDRA-UMC-EDITOR-STL)** — 桌面 STL 模型编辑器，在 HYDRA-UMC-EDITOR-URDF 编辑的同一模型目录中变换/替换/移除/添加真实部件。
- **[HYDRA-UMC-BRIDGE-AMR](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-AMR)** —— 通过 VDA 5050 MQTT 发布者为 AGV/AMR 车队提供的协调边界(仅针对仿真车队测试)。
- **[HYDRA-UMC-BRIDGE-CNC](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-CNC)** —— 具备 GRBL 状态/控制字节访问能力的高层 CNC 单元协调器(仅针对模拟器测试)。
- **[HYDRA-UMC-BRIDGE-DROIDS](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-DROIDS)** —— 面向足式/人形机器人的协调边界,带有 Boston Dynamics Spot 指令发送器(仅针对模拟器测试)。
- **[HYDRA-UMC-BRIDGE-LASER](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-LASER)** —— 读取 3 路钥匙/外壳/联锁 GPIO 信号的激光单元协调器(仅针对模拟芯片测试;无法使激光器上膛或发射)。
- **[HYDRA-UMC-BRIDGE-OPENPNP](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-OPENPNP)** —— 面向 OpenPnP 贴片机板级流程的安全高层协调器。
- **[HYDRA-UMC-BRIDGE-PRINTER3D](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-PRINTER3D)** —— 面向 Moonraker/Klipper 3D 打印机的安全协调边界,具备真实的受控作业指令。
- **[HYDRA-UMC-BRIDGE-ROS2](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-ROS2)** —— 带有惰性导入 rclpy ROS 2 传输层的协调器(尚未在 ROS 2 环境中运行)。
- **[HYDRA-UMC-BRIDGE-UAV](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-UAV)** —— 面向搭载摄像头的无人机的协调边界,带有 MAVLink 指令发送器(仅针对模拟器测试)。

*URTC 工具平台*
- **[URTC-FLASHER](https://github.com/JuanenRac/URTC-FLASHER)** —— 面向 URTC 板卡的桌面图形烧录工具,支持 CAN-OTA 以及全芯片 SWD/JTAG。
- **[URTC-TESTER](https://github.com/JuanenRac/URTC-TESTER)** —— 面向 URTC 板卡的桌面实时 CAN 总线诊断工具,每种工具配置对应一个面板。
- **[URTC-WEB-STUDIO](https://github.com/JuanenRac/URTC-WEB-STUDIO)** —— 通过 Web Serial API 实现的浏览器版 URTC-TESTER 替代方案,无需本地安装。
- **[URTC-GATEWAY](https://github.com/JuanenRac/URTC-GATEWAY)** —— URTC CAN 总线前的网关：允许的标识符列表、速率限制和会话密钥；软件已在计算机上测试，尚未在真实总线上测试。

*视觉 AI 节点(Hailo-8)*
- **[HYDRA-UMC-VISION-NODE](https://github.com/JuanenRac/HYDRA-UMC-VISION-NODE)** —— 面向 Hailo-8 视觉流水线的集成中枢,具备逐阶段的真实硬件就绪检测。
- **[HYDRA-UMC-DETECTION-HEF](https://github.com/JuanenRac/HYDRA-UMC-DETECTION-HEF)** —— 具备 Hailo 架构/校验和安全加载验证的真实编译模型注册表。
- **[HYDRA-UMC-VISION-STREAMER](https://github.com/JuanenRac/HYDRA-UMC-VISION-STREAMER)** —— 具备真实 HailoRT 集成边界的真实 GStreamer 流水线 + MediaMTX 配置生成器。
- **[HYDRA-UMC-VISUAL-SERVOING-API](https://github.com/JuanenRac/HYDRA-UMC-VISUAL-SERVOING-API)** —— 以区域状态为授权条件的 Position-Based Visual Servoing 修正律;尚无摄像头位姿估计。
- **[HYDRA-UMC-SAFETY-ZONES](https://github.com/JuanenRac/HYDRA-UMC-SAFETY-ZONES)** —— 从文件读取物体位置的 v0 区域入侵、校准新鲜度与 E-STOP 请求逻辑;没有检测器为其供数,也尚未连接任何物理 E-STOP。

*认知 AI 节点(Hailo-10)*
- **[HYDRA-UMC-COGNITIVE-NODE](https://github.com/JuanenRac/HYDRA-UMC-COGNITIVE-NODE)** —— 面向 Hailo-10 认知流水线(LLM/VLA/语音编排)的集成中枢。
- **[HYDRA-UMC-VLA-ENGINE](https://github.com/JuanenRac/HYDRA-UMC-VLA-ENGINE)** —— 面向 Vision-Language-Action 模型的真实动作 token 编解码与轨迹生成。
- **[HYDRA-UMC-VOICE-UI](https://github.com/JuanenRac/HYDRA-UMC-VOICE-UI)** —— 具备受限、需确认的 Watch 中继的真实语音前端(VAD + 意图解析)。
- **[HYDRA-UMC-SEMANTIC-PLANNER](https://github.com/JuanenRac/HYDRA-UMC-SEMANTIC-PLANNER)** —— 基于真实规则的任务分解,以及针对 MCU 错误码的语义化错误恢复。
- **[HYDRA-UMC-DOCS-QA](https://github.com/JuanenRac/HYDRA-UMC-DOCS-QA)** —— 面向本生态系统自身 Markdown 文档的真实纯标准库 TF-IDF 文档检索。
- **[HYDRA-UMC-LOCAL-TECHNICIAN](https://github.com/JuanenRac/HYDRA-UMC-LOCAL-TECHNICIAN)** — 面向生态系统自身的本地、按策略门控的 AI 维护技师——观察、诊断并提出修复建议;两个最高风险等级目前特意尚未实现。

*编排与集群*
- **[HYDRA-UMC-ORCHESTRATOR](https://github.com/JuanenRac/HYDRA-UMC-ORCHESTRATOR)** —— 具备真实 gRPC/Protobuf 健康报告契约与任务状态机的集成中枢。
- **[HYDRA-UMC-JOB-DISPATCHER](https://github.com/JuanenRac/HYDRA-UMC-JOB-DISPATCHER)** —— 基于真实 HTTP API 的真实优先级任务队列,支持去重。
- **[HYDRA-UMC-NODE-HEALING](https://github.com/JuanenRac/HYDRA-UMC-NODE-HEALING)** —— 具备重试/退避与身份不匹配检测的真实基于 gRPC 的车队健康看门狗。
- **[HYDRA-UMC-PATH-PLANNER-3D](https://github.com/JuanenRac/HYDRA-UMC-PATH-PLANNER-3D)** —— 具备真实障碍物/工作空间碰撞校验的真实基于 RRT 的三维路径规划器。
- **[HYDRA-UMC-SWARM-SYNC](https://github.com/JuanenRac/HYDRA-UMC-SWARM-SYNC)** —— 经过多单元收敛属性测试的真实 CRDT LWW-Element-Map 状态同步。

*数字孪生与仿真*
- **[HYDRA-UMC-TWIN](https://github.com/JuanenRac/HYDRA-UMC-TWIN)** —— 面向数字孪生引擎的集成中枢,具备真实的版本兼容性同步契约。
- **[HYDRA-UMC-HIL-BRIDGE](https://github.com/JuanenRac/HYDRA-UMC-HIL-BRIDGE)** —— 在仿真与真实硬件之间带有软件碰撞联锁的硬件在环路由器(未在真实硬件上测试)。
- **[HYDRA-UMC-PHYSICS-REPLICA](https://github.com/JuanenRac/HYDRA-UMC-PHYSICS-REPLICA)** —— 面向真实 URDF 子集的真实正向运动学与关节限位校验。
- **[HYDRA-UMC-SYNTHETIC-DATA-GEN](https://github.com/JuanenRac/HYDRA-UMC-SYNTHETIC-DATA-GEN)** —— 具备 YOLO/COCO 标注导出功能的真实程序化 2D 场景生成器。

*数据与分析*
- **[HYDRA-UMC-DATALAKE](https://github.com/JuanenRac/HYDRA-UMC-DATALAKE)** —— 具备真实数据摄入/查询 HTTP API 的真实 sqlite3 时序数据存储。
- **[HYDRA-UMC-ANOMALY-DETECTOR](https://github.com/JuanenRac/HYDRA-UMC-ANOMALY-DETECTOR)** —— 具备漂移监测能力的真实 FFT + 统计基线异常检测器。
- **[HYDRA-UMC-PRODUCTION-REPORTS](https://github.com/JuanenRac/HYDRA-UMC-PRODUCTION-REPORTS)** —— 基于 DATALAKE 历史数据的真实 OEE/可用率计算,支持可复现的 CSV 导出。
- **[HYDRA-UMC-TELEMETRY-COLLECTOR](https://github.com/JuanenRac/HYDRA-UMC-TELEMETRY-COLLECTOR)** —— 面向 DATALAKE 的真实 CAN/WebSocket 数据摄入管道,支持序列去重。

*工业网关*
- **[HYDRA-UMC-GATEWAY-INDUSTRIAL](https://github.com/JuanenRac/HYDRA-UMC-GATEWAY-INDUSTRIAL)** —— 中继至工业协议的集成中枢,具备真实的指令白名单/背压控制层。
- **[HYDRA-UMC-OPCUA-SERVER](https://github.com/JuanenRac/HYDRA-UMC-OPCUA-SERVER)** —— 经真实二进制协议客户端会话验证的真实 OPC-UA 地址空间。
- **[HYDRA-UMC-MQTT-BROKER](https://github.com/JuanenRac/HYDRA-UMC-MQTT-BROKER)** —— 具备可选按客户端认证与主题 ACL 的真实 MQTT 代理。
- **[HYDRA-UMC-MTCONNECT-ADAPTER](https://github.com/JuanenRac/HYDRA-UMC-MTCONNECT-ADAPTER)** —— 具备降级模式输出的真实 MTConnect `/probe` 与 `/current` XML 端点。

*辅助工具与生态系统运维*
- **[HYDRA-UMC-DASHBOARD-AI](https://github.com/JuanenRac/HYDRA-UMC-DASHBOARD-AI)** —— 基于 DATALAKE/ANOMALY-DETECTOR 的智能摘要与异常高亮面板,具备诚实的统计回退机制。
- **[HYDRA-UMC-TOOL-CLI](https://github.com/JuanenRac/HYDRA-UMC-TOOL-CLI)** —— 具备真实、稳定退出码契约的车队 CLI,是 HYDRA-UMC-SERVER 自身 API 的真实在线客户端。
- **[HYDRA-UMC-WATCH](https://github.com/JuanenRac/HYDRA-UMC-WATCH)** —— 带有触觉提醒模式与配对手机语音中继的 WearOS 伴侣应用(尚未在实体手表上运行)。
- **[URTC-SMART-RACK](https://github.com/JuanenRac/URTC-SMART-RACK)** —— 面向板卡安装机架的固件,具备真实的工具 ID 解码与 Smart Idle 预热逻辑。
- **[URTC-VISION-TOOL](https://github.com/JuanenRac/URTC-VISION-TOOL)** —— 面向热成像/RGB 检测工具头的固件及真实 Python 视觉伴侣程序。

## 📚 文档

更多阅读：

* **[`docs/AGENT_REFERENCE.md`](docs/AGENT_REFERENCE.md)** —— 只读诊断 CLI `hydra-umc-agent` 的真实命令/输出参考。
* **[`docs/INSTALLATION.md`](docs/INSTALLATION.md)** —— 安装设计:目标平台与预期的安装流程。
* **[`docs/CM5_PROVISIONING.md`](docs/CM5_PROVISIONING.md)** —— 将 Raspberry Pi OS Lite 转变为 HYDRA-UMC-OS 的完整指南。
* **[`docs/CM5_WINDOWS_HOST_FLASHING.md`](docs/CM5_WINDOWS_HOST_FLASHING.md)** —— 从 Windows 主机烧录 CM5 的已验证流程。
* **[`docs/CM5_FIRST_BOOT_CHECKLIST.md`](docs/CM5_FIRST_BOOT_CHECKLIST.md)** —— CM5 首次启动的 BASE 平台检查清单。
* **[`docs/CM5_PACKAGE_MANIFEST.md`](docs/CM5_PACKAGE_MANIFEST.md)** —— 按部署阶段划分的真实软件包清单。
* **[`docs/CM5_ECOSYSTEM_DEPLOYMENT.md`](docs/CM5_ECOSYSTEM_DEPLOYMENT.md)** —— 在 CM5 上分阶段部署生态系统其余部分的计划，每个阶段均可独立回滚。
* **[`docs/CM5_SOFTWARE_READINESS.md`](docs/CM5_SOFTWARE_READINESS.md)** —— 在没有物理 CM5 硬件的情况下已验证的内容，以及验证止步之处。
* **[`docs/SERVICE_MODEL.md`](docs/SERVICE_MODEL.md)** —— HYDRA-UMC 服务的运行方式：专用用户、配置路径、依赖/就绪顺序。
* **[`docs/UPDATE_MODEL.md`](docs/UPDATE_MODEL.md)** —— 操作系统、HYDRA-UMC 软件包、Hailo 运行时与 MCU/URTC 固件各自独立的更新通道。
* **[`docs/SDK_INTEGRATION_BOUNDARY.md`](docs/SDK_INTEGRATION_BOUNDARY.md)** —— 本仓库如何在不内嵌 HYDRA-UMC-SDK 源码的情况下使用其已发布的契约。
* **[`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md)** —— 开发规则：优先使用 Raspberry Pi OS 原生接口，以及必须遵循的测试顺序。
* **[`docs/HEADER_CONVENTION.md`](docs/HEADER_CONVENTION.md)** —— 新源码/文档文件的版权与许可证头部约定。
* **[`provisioning/ssh_hardening.md`](provisioning/ssh_hardening.md)** —— CM5 真实的 SSH 加固步骤（在禁用密码认证前先确认密钥登录可用）。
* [生态系统的安全基线](https://github.com/JuanenRac/HYDRA-UMC-DOCS/blob/main/docs/SECURITY_BASELINE.md)
* [生态系统的威胁模型](https://github.com/JuanenRac/HYDRA-UMC-DOCS/blob/main/docs/THREAT_MODEL.md)
* [本仓库的更新日志](CHANGELOG.md)
* [本仓库的许可证](LICENSE.md)

## 🤝 参与贡献与社区

* 提交 pull request 之前，请运行 `HYDRA_UMC_CI=1 py -3 tools/ci_validate.py`（或 `HYDRA_UMC_CI=1 python3 tools/ci_validate.py`）：它必须输出 `CI_VALIDATION=PASS`。此检查不要运行 `build.sh` 或 `build.bat`；构建不是检查。
* 八个 README 由 HYDRA-UMC-DOCS 中的同一个源生成；请勿手工编辑。修改源文件，再用 `tools/make_readmes.py` 重新生成。
* 不要在 README 中声称尚未运行过的内容：属实时请写“仅模拟”或“尚未在硬件上试过”。
* 请参阅 [CONTRIBUTING.md](CONTRIBUTING.md)、[行为准则](CODE_OF_CONDUCT.md)、[SECURITY.md](SECURITY.md) 和 [SUPPORT.md](SUPPORT.md)。

## 👤 作者

**JuanenRac (Electro Hobby 3D)** · electrohobby3d@gmail.com

## 📜 许可证

GPL-3.0-or-later - [LICENSE](LICENSE).
