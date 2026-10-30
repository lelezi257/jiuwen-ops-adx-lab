# Jiuwen Ops ADX Lab

独立的 ADX 按需运维 Agent 实验项目。当前正在实现，尚未完成 ADX + 真实 SDK + 原生轨迹或完整订单闭环验收。

目标：事件到来后通过 ADX Binding 按需创建独立沙箱；沙箱内使用官方 Process SDK → Swarm Runtime → Core 的真实模型和工具；保留真实 Session 及原生轨迹，完成订单故障的 PR/CI/发布/独立验证。

[接入设计](docs/design.html) · [实施状态](docs/STATUS.md)

本仓库从 lelezi257/jiuwen-ops-lab 的 `5e0b01389a32480c0a20831aca595631c10f9f4a` 复用订单应用、可信交付和观测基础代码；旧项目的通过结论不属于本项目。两者使用不同仓库、状态、VM 与端口。凭据均为本地配置，不上传。
