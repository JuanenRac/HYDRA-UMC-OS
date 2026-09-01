<!--
=================================================================================
HYDRA-UMC-OS - 公共项目概述和实施指南
版权所有 (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
CC BY-SA 4.0 - 参见 LICENSE.md
=================================================================================
-->

<p align="center">
  <img src="images/HYDRA_UMC_BANNER.svg" alt="HYDRA-UMC-OS 横幅" width="100%">
</p>

<p align="center">
  <a href="README.md">🇺🇸 English</a> |
  <a href="README_spa.md">🇪🇸 西班牙语</a> |
  <a href="README_fra.md">🇫🇷法语</a> |
  <a href="README_ita.md">🇮🇹意大利语</a> |
  <a href="README_deu.md">🇩🇪德语</a> |
  <a href="README_zho.md">🇨🇳简体中文</a> |
  <a href="README_jpn.md">🇯🇵日本语</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/License-GPL%203.0-blue.svg" alt="许可证：GPL 3.0">
  <img src="https://img.shields.io/badge/Platform-Raspberry%20Pi%20OS%20%7C%20CM5-red.svg" alt="平台：Raspberry Pi OS | CM5">
  <img src="https://img.shields.io/badge/Services-systemd%20%7C%20udev-orange.svg" alt="服务：systemd | udev">
  <img src="https://img.shields.io/badge/Stack-Debian%20%7C%20Python%20%7C%20Shell-blueviolet.svg" alt="堆栈：Debian | Python | Shell">
</p>

# HYDRA-UMC-OS

## 🖥️ Raspberry Pi OS 的 HYDRA-UMC 平台层

HYDRA-UMC-OS 是 HYDRA-UMC CM5 节点的可安装平台层。
它基于 Raspberry Pi OS ARM64 构建；它不会取代 Linux，
Raspberry Pi 内核、systemd、NetworkManager、libcamera 或供应商 SDK。

其职责是提供可重复的 HYDRA-UMC 设备配置文件：
配置、服务生命周期、本地身份、诊断、视觉
HYDRA-UMC 组件的品牌和协调更新。

## 🚧 状态

基本代理、经过验证的非秘密配置、强化的 systemd
单元和主机端测试均已实施。该代理是刻意
只读的：生产镜像组装和 CM5 硬件验证仍是
独立的发布关卡。

安装预检（`provisioning/preflight_cm5.py`）已通过一项真实测试证明其具有幂等性且无副作用——连续运行两次会产生逐字节相同的输出，并且不会触及此仓库中的任何文件——而一个真实的、与主机无关的备份/回滚机制（`provisioning/rollback.py`）保护着 `install_local_agent.sh` 在每次运行时无条件覆盖的那一个系统文件。两者均已在无需 root 权限或 CM5 的情况下完成验证——参见 `tools/verify_preflight_idempotent.py` 和 `tools/verify_rollback.py`。

**WiFi 首次接触配网同样是真实的**（`provisioning/wifi_provision.py` / `hydra-umc-wifi-provision.service`）——为尚无已知网络的无头 CM5 提供真实的 NetworkManager AP 模式回退：启动一个真实的热点（`nmcli device wifi hotspot`），操作员的手机/笔记本电脑可以加入该热点，通过一个小型本地 HTTP 表单提交真实的目标 SSID/密码，成功后关闭 AP 并加入真实网络，失败时恢复 AP，使设备永远不会被困住。该状态机针对一个伪造的 NetworkManager 进行了完整的单元测试，包括通过真实回环套接字进行的真实端到端 HTTP 往返——参见 `tools/verify_wifi_provision.py`。由 `install_cm5_base.sh` 安装，但刻意未自动启用，因为它绝不能在真实的、可通过空口访问的设备上以自带的占位 AP 密码启动——需先完成 `provisioning/CM5_DEPLOYMENT_SEQUENCE.md` 第 3 节所述的真实密码设置步骤。

## 🎯 计划的第一个里程碑

1. 为 CM5 构建 Raspberry Pi OS ARM64 配置文件。
2. 安装 `hydra-umc-platform-base` 和 `hydra-umc-agent`。
3. 检测 CM5 接口并报告 `DeviceDescriptor` 和 `HealthReport`。
4. 仅启动通过 systemd 启用的服务。
5. 本地显示 READY、DEGRADED、INHIBITED 或 FAULT。

## 📂 存储库布局

<p align="center">
  <img src="images/REPOSITORY_LAYOUT.svg" alt="HYDRA-UMC-OS 存储库布局的可视化地图" width="100%">
</p>

|路径|目的|
| ---| ---|
| `docs/` |架构、安装、服务和更新规范。 |
| `image-builder/` |官方 Raspberry Pi OS 镜像组装边界和可复现性说明。 |
| `packages/` | `hydra-umc-platform-base` 的 Debian 软件包元数据。 |
| `agent/` |只读的 Python 设备描述符与健康状态代理，含单元测试。 |
| `systemd/` |强化的 `hydra-umc-agent.service` 生命周期单元。 |
| `config/` |默认模式和非秘密配置。 |

在实现代码之前阅读[架构](docs/ARCHITECTURE.md)。

## 🛠️ 构建与运行

请在发布构建前使用不改动版本的构建检查：

| 操作 | Windows | Linux / macOS |
|---|---|---|
| 构建检查（不修改版本或 CHANGELOG） | `build-test.bat` | `./build-test.sh` |
| 运行 / 开发（如提供） | `run*.bat` 或 `dev*.bat` | `./run*.sh` 或 `./dev*.sh` |

`build-test.bat` 和 `build-test.sh` 会编译或验证项目技术栈，但不会递增 `hydra-umc.project.json`，也不会修改 `CHANGELOG.md`。它们仅可能生成正常的编译器输出。现有的 `build*.bat`、`build*.sh`、`run*` 和 `dev*` 脚本保留各自的版本化或运行时行为；需要该行为时请使用它们。

## 🔗 相关项目

> 规范的公共生态系统关系图。

|项目|与 HYDRA-UMC-OS 的关系 |
| ---| ---|
| [HYDRA-UMC-SDK](https://github.com/JuanenRac/HYDRA-UMC-SDK) |设备代理使用的版本化合同、瘦客户端和一致性固定装置。 |
| [HYDRA-UMC-SERVER](https://github.com/JuanenRac/HYDRA-UMC-SERVER) |节点托管集成的经过身份验证的服务边界。 |
| [HYDRA-UMC-UPDATER](https://github.com/JuanenRac/HYDRA-UMC-UPDATER) |工件注册表、兼容性元数据和协调的更新工作流程。 |
| [HYDRA-UMC](https://github.com/JuanenRac/HYDRA-UMC) | OS层配置和管理的CM5/MCU硬件和固件平台。 |
| [URTC](https://github.com/JuanenRac/URTC) |通过明确的版本化适配器集成的独立工具控制器平台。 |

**生态系统的其余部分：** 探索 [JuanenRac 生态系统仪表板](https://juanenrac.github.io/JuanenRac/) 中的七个公共层。

## 👤 作者
**JuanenRac** (Electro Hobby 3D)
📧 electrohobby3d@gmail.com
📺 [youtube.com/@electrohobby3d](https://youtube.com/@electrohobby3d)

## 📜 许可证

代码为 GPL-3.0 或更高版本，文档为 CC BY-SA 4.0。请参阅 [LICENSE](LICENSE)。
