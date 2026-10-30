# Jiuwen Ops ADX Lab

收到订单故障后，控制器通过 ADX 按需创建 runsc 沙箱；里面启动官方 Process SDK → Swarm → Core，调用真实模型和主机工具。Agent 提交修复 PR，可信交付组件负责 CI、合并和 digest 发布；独立组件验证真实订单、金额和数据库，Agent 再只读复核。结束后释放沙箱，事件和原生轨迹留在持久目录。

**当前：最小真实链路已通过，完整订单案例正在验收。** [实际状态与身份](docs/STATUS.md) · [接入设计](docs/design.html) · [部署和交互](docs/IMPLEMENTATION.md) · [操作与复现](docs/RUNBOOK.md) · [最小链路证据](docs/evidence/minimal-acceptance.json)

本仓库从 [jiuwen-ops-lab](https://github.com/lelezi257/jiuwen-ops-lab) 的 `5e0b01389a32480c0a20831aca595631c10f9f4a` 复用订单应用、可信交付和原生观测基础代码。旧项目的通过结论不属于本项目；仓库、VM、容器、数据卷、端口均分开。

## 在 Apple Silicon Mac 上运行

需要 Git、GitHub CLI、Lima，以及自己的模型配置和可写 GitHub 仓库。当前发布的 ADX 基础包仅支持 Linux ARM64；在专用 Ubuntu VM 内运行，不把 macOS Docker 容器当成 ADX 沙箱。

1. Fork 本仓库并 clone 自己的 fork；`gh auth login`，确保可创建分支、PR、读 Actions 和合并。仓库 Actions 必须启用，模型修复只面向本实验订单应用。
2. 在仓库中执行 `./scripts/lab init --github`。编辑 `.local/lab.env` 的 `GITHUB_REPOSITORY` 为自己的 fork；编辑 `.local/model.env`，填写 `API_BASE`、`API_KEY`、`MODEL_NAME` 及模型接口类型。
3. 执行 `./scripts/lab vm-create`、`./scripts/lab vm-sync`、`./scripts/lab vm-install`。脚本创建专用 `jiuwen-ops-adx-lab` VM（4 CPU / 8 GiB / 40 GiB），下载并校验固定基础包、构建官方框架镜像、发布模板和启动服务。它不会重新安装正在运行的平台，也不会清空卷或历史；存在活动任务时拒绝安装。
4. 运行 `./scripts/lab qualify`。在工作台查看此只读任务及原生轨迹，确认模型配置真实可用后，再运行订单案例。
5. 打开工作台 <http://127.0.0.1:19780/>；`./scripts/lab token` 在本地显示操作令牌，粘贴到令牌输入框。点“验证正常基线（各2次）”，再点“制造真实故障”。
6. 从本轮“持续观察”入口打开 <http://127.0.0.1:19781/>，同一页面跟随 repair 和 verify 两个真实 Session；等待 CI/构建/发布时保留上一阶段。成功需到 `RESOLVED_FIXED`，并显示资源清理 `CONFIRMED`。

模型 Key、GitHub Token、平台凭证仅存在 `.local/`、VM 私有配置和 Docker secrets 中，不上传。GitHub 凭证留在可信交付组件，ADX 凭证留在控制器，执行沙箱只有模型配置和本次 case/attempt/phase 的短期工具授权。普通模型调用会消耗配置的模型账户额度。

网络受限时，先解决 VM 的 apt、镜像仓库、Python/npm、GitHub 和模型端点访问；可在 VM `.local/runtime.env` 配置镜像/包源。脚本不默认关闭 TLS 或沙箱 ACL。参见 [RUNBOOK](docs/RUNBOOK.md)。
