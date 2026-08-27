<!--
=================================================================================
HYDRA-UMC-OS - 公共项目概述和实施指南
版权所有 (C) 2026 JuanenRac (Electro Hobby 3D) < electrohobby3d@gmail.com>
CC BY-SA 4.0 - 参见 LICENSE.md
=================================================================================
-->

<p对齐=“中心”>
  <img src="images/HYDRA_UMC_BANNER.svg" alt="HYDRA-UMC-OS 横幅" width="100%">
</p>

<p对齐=“中心”>
  <a href="README.md">???? English</a> |
  <a href="README_spa.md">🇪🇸 西班牙语</a> |
  <a href="README_fra.md">🇫🇷法语</a> |
  <a href="README_ita.md">🇮🇹意大利语</a> |
  <a href="README_deu.md">🇩🇪德语</a> |
  <a href="README_zho.md">🇨🇳简体中文</a> |
  <a href="README_jpn.md">🇯🇵日本语</a>
</p>

<p对齐=“中心”>
  <img src="https://img.shields.io/badge/License-GPL%203.0-blue.svg" alt="许可证：GPL 3.0">
  <img src="https://img.shields.io/badge/Platform-Raspberry%20Pi%20OS%20%7C%20CM5-red.svg" alt="平台：Raspberry Pi OS | CM5">
  <img src="https://img.shields.io/badge/Services-systemd%20%7C%20udev-orange.svg" alt="服务：systemd | udev">
  <img src="https://img.shields.io/badge/Stack-Debian%20%7C%20Python%20%7C%20Shell-blueviolet.svg" alt="堆栈：Debian | Python | Shell">
</p>

# HYDRA-UMC-操作系统

## 🖥️ Raspberry Pi OS 的 HYDRA-UMC 平台层

HYDRA-UMC-OS 是 HYDRA-UMC CM5 节点的可安装平台层。
它基于 Raspberry Pi OS ARM64 构建；它不会取代 Linux，
Raspberry Pi 内核、systemd、NetworkManager、libcamera 或供应商 SDK。

其职责是提供可重复的 HYDRA-UMC 设备配置文件：
配置、服务生命周期、本地身份、诊断、视觉
HYDRA-UMC 组件的品牌和协调更新。

## 🚧 状态

基本代理、经过验证的非秘密配置、强化的 systemd
单元和主机端测试均已实施。经纪人是故意的
只读：保留生产映像组装和 CM5 硬件验证
单独的释放门。

## 🎯 计划的第一个里程碑

1. 为 CM5 构建 Raspberry Pi OS ARM64 配置文件。
2. 安装 `Hydra-umc-platform-b​​ase` 和 `Hydra-umc-agent`。
3. 检测 CM5 接口并报告 `DeviceDescriptor` 和 `HealthReport`。
4. 仅启动通过 systemd 启用的服务。
5. 本地显示 READY、DEGRADED、INHIBITED 或 FAULT。

## 📂 存储库布局

<p对齐=“中心”>
  <img src="images/REPOSITORY_LAYOUT.svg" alt="HYDRA-UMC-OS 存储库布局的可视化地图" width="100%">
</p>

|路径|目的|
| ---| ---|
| `文档/` |架构、安装、服务和更新规范。 |
| `图像生成器/` |官方 Raspberry Pi OS 映像组装边界和再现性说明。 |
| `包/` | “Hydra-umc-platform-b​​ase”的 Debian 软件包元数据。 |
| `代理/` |只读 Python 设备描述符和带有单元测试的运行状况代理。 |
| `systemd/` |强化的“Hydra-umc-agent.service”生命周期单元。 |
| `配置/` |默认模式和非秘密配置。 |

在实现代码之前阅读[架构](docs/ARCHITECTURE.md)。

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

## 📜 许可证

代码为 GPL-3.0 或更高版本，文档为 CC BY-SA 4.0。请参阅[许可证]（许可证）。