# 九问怎样接进来

先看 `lab/runner.py`，再看 `lab/tools.py`。我们的 runner 是常驻独立服务；一次任务调用官方 SDK 的 `Client.run`，SDK 启动一个官方 `jiuwenswarm-process --run-jsonl` 子进程。子进程内部创建共享 Swarm Runtime，装配 Core/DeepAgent。模型决定调用哪个工具、读取实际结果并继续推理，这个循环属于官方实现。

## 边界

```text
我们的控制中心 --HTTP任务/租约--> 我们的 runner
    runner 内：官方 Process SDK Client
             ⇅ stdin/stdout JSONL
    官方 Swarm Process CLI / Runtime 子进程
             └─ Core / DeepAgent ⇄ 真实模型
             └─ host_tool.requested
                    ⇅ SDK on_tool_call 回调
    runner --带任务身份的HTTP--> 我们的取证/工程服务
```

执行侧不部署完整 Gateway/AgentServer，不通过 WebSocket 消息驱动模型，也不重写 `DeepAgent`。现已增加原版 WebUI 与官方读取组件组成的独立只读观测服务，见 [原生轨迹接线](NATIVE-WEBUI.md)。能力对应既有学习地图的 C3 单 Agent，宿主边界对应 S2 Process SDK。调查/修复任务与部署后验证任务使用不同新 Session；CI 等待和发布状态属于控制中心，不让模型空转等待。

## 一次调用

1. runner 用真实 `Client.query("protocol.capabilities")` 检查 `host_tools`、`structured_output`、`empty_tools`、`max_turns` 和取消能力；查询不需要模型。
2. 只有模型配置完整才领取任务。控制中心分配 case/attempt，runner 持续续租。
3. `Client.run(request, on_event=..., on_tool_call=..., on_interaction=..., cancel=..., deadline_seconds=...)`。
4. 请求含 Agent 定义、按阶段工具白名单、host_tools JSON Schema、权限、报告工作区、结构化结果 Schema 和执行上限。
5. 只有 `host_tool.requested` 执行实际工具。观察性的 `chat.tool_call` 只记录。
6. runner 强制覆盖实际 case_id；模型无法把工具请求切换到另一个事件。工具服务再校验事件状态和路径。
7. `on_interaction` 记录实际问题并停止/转人工；没有通用“yes”或权限自动扩大。
8. SDK 负责协议身份、连续 sequence、终态与 OS 退出码校验。宿主还检查业务结果与真实 PR 账本一致。`chat.final` 和 EOF 都不是成功。
9. 取消传给同一个 run 的 asyncio.Event。已发生的工具副作用保留并对账，不盲目重试。

配置入口是 `.local/model.env` 和单独挂载的 `.local/swarm/config.yaml`。目录实际挂在 `/data/swarm/config`，由 `JIUWENSWARM_DATA_DIR/config/config.yaml` 读取；仅设置 `JIUWENSWARM_CONFIG_DIR` 不足以更改读取位置。模型 Key 不进入 run JSON、不挂入候选测试容器、不进入 Git。官方配置字段为 `models.defaults[].model_client_config`，使用 API_BASE/API_KEY/MODEL_NAME 等环境插值。

## 固定源码

- [Swarm SDK README](https://github.com/openJiuwen-ai/jiuwenswarm/blob/32d75d7d3a0b466412ee64d77c29460297515119/sdks/README.md)
- [Process 协议](https://github.com/openJiuwen-ai/jiuwenswarm/blob/32d75d7d3a0b466412ee64d77c29460297515119/sdks/PROTOCOL.md)
- [SDK Client](https://github.com/openJiuwen-ai/jiuwenswarm/blob/32d75d7d3a0b466412ee64d77c29460297515119/sdks/python/src/jiuwenswarm_sdk/client.py)
- [Runtime 接线](https://github.com/openJiuwen-ai/jiuwenswarm/blob/32d75d7d3a0b466412ee64d77c29460297515119/jiuwenswarm/channels/process_cli/client.py)
- [Core](https://github.com/openJiuwen-ai/agent-core/tree/e089198835426cd7681761b0cc278670cd83031f)

构建从官方 GitHub 下载固定提交的源码。上游元数据声明的部分依赖使用 GitCode Git URL，因此安装脚本只把这些固定依赖的下载通道换成官方 GitHub 快照：先解析非 Git 依赖，再 `--no-deps` 安装原样源码；不修改上游 Agent 实现。上游 Core 对 intelliRouter 使用浮动分支，本项目额外固定了分支当时的 SHA，见 lock。完整下载与包版本记录在构建容器 `/app/vendor/source-manifest.json` 和后续验收材料。

协议能力查询通过，只证明 SDK/CLI 查询通道；真实模型、host tool 循环、Session、取消与清理仍需单独实际验收。不得把接口形状检查当成 G1 完成。


## 配好 Key 后单独验收

执行 `scripts/lab qualify`：真实 SDK 发现、非法输入失败、模型读取实际运行版本的 host tool、结构化结果，以及在实际工具回调后取消同一个 run。结果写入 runner 数据卷的 `/data/qualification/report.json`。这条命令会调用真实模型并产生供应商费用；它还不是订单故障修复 E2E。

不配 Key 也可在 VM 内执行 `sudo docker compose --env-file .local/lab.env --env-file .local/runtime.env exec -T runner python /app/scripts/qualify_jiuwen.py --discovery-only`，只检查协议和非法输入；报告保留 `real_model_qualified=false`。


只读容器部署需显式处理写入目录：SDK 子进程 cwd 使用可写的 `/data`；Core 默认日志随 cwd 写入；Swarm 扩展管理器会确保安装根下的 `application_plugins` 存在，本镜像在构建时预建空目录。会话/日志在独立数据卷，配置在单独挂载目录，框架源码不做运行时修改。
