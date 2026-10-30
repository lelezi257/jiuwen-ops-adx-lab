# 九问实际接入方式

本版采用**ADX按需沙箱 + 官方Process SDK**。没有常驻runner服务，也没有用REST壳自行实现模型循环。完整组件分工见[实际部署](IMPLEMENTATION.md)。

```text
告警 → 产品控制器（选case / attempt / Binding）
     → ADX公开managed HTTP（第一次请求才创建Environment）
     → runsc沙箱中的execution host
         → 官方Process SDK Client
         → 官方Process CLI / Swarm Runtime
         → 官方Core / DeepAgent → 真实模型
             ↔ 声明的host tools → scoped broker → 取证 / 可信工程服务
```

## 用的是什么接口

1. `lab/adx_dispatch.py`调用ADX的数字版本模板、Binding查询/删除，以及`/agent/http/runs?target=urn:adx:binding:...`。它负责选择业务承载身份、持久化请求意图和清理，不负责Agent循环。
2. `lab/execution_host.py`在沙箱启动时查询`Client.query('protocol.capabilities')`，检查主机工具、结构化输出、空工具、max_turns和取消能力。查询不需要模型；它通过不代表真实模型验收通过。
3. `lab/runner.py`构造官方`jiuwenswarm_sdk.Client`，command为`[python, -m, jiuwenswarm.channels.process_cli.main]`，调用`Client.run(...)`，传入agent声明、instructions、host_tools、permissions、output_schema与预算/轮次限制。
4. `on_event`记录SDK真实`run.started`里的SessionID和request_id；`on_tool_call`通过本case短期授权调用broker；`on_interaction`不自动回答未知交互。取消由官方SDK的cancel事件传递。
5. 模型配置通过Swarm配置中的`${API_BASE}`/`${API_KEY}`等变量注入。host在启动时从只读私有文件加载，模型调用和工具选择属于官方Runtime/Core。
6. repair、显式重试和verify各自创建新的官方SDK Session，同一case可复用一个ADX Binding/Environment。CI、合并、构建、发布与独立验证属于产品平台状态，不转换成Core Span。

## 工具和交付边界

SDK只声明`lab/tools.py`允许的主机工具。broker在服务端按case/attempt/phase校验、覆盖case归属；repair有受限写工具，verify只读。工程服务拥有GitHub和Docker权限，执行沙箱没有这些凭证。可信测试与PR头/base校验、合并、artifact校验、digest部署和独立SQL验证都不能被模型一句“成功”代替。

SDK回执原样保留。`completed/exit_code=0`不等于业务恢复；还需真实证据、PR/CI/版本链、独立业务验证和复核。输出格式、模型或网络失败会停止或进入核查，不提供固定修复兜底。

## 原生观测

执行侧没有部署完整Gateway/AgentServer Web后端。独立native-web服务复用固定版本的原版前端、官方TrajectoryHost和HTTP读取组件，增加只读会话接线、按case固定读取根与顶部跟随栏。它不能运行新Agent或修改记录。官方Session和SQLite由真实SDK/Core产生，资源释放后仍可回看。边界详见[原生读取实现](IMPLEMENTATION.md#原生轨迹扩展边界)。

`./scripts/lab qualify`现在是只读真实模型任务：指标 → 日志 → 实际发布身份 → 已存证据；最小验收见[证据](evidence/minimal-acceptance.json)。它不代表完整订单恢复验收，也不是旧版常驻runner资格脚本。

## 固定源码

- [Python SDK Client](https://github.com/openJiuwen-ai/jiuwenswarm/blob/32d75d7d3a0b466412ee64d77c29460297515119/sdks/python/src/jiuwenswarm_sdk/client.py)
- [Process CLI机器协议](https://github.com/openJiuwen-ai/jiuwenswarm/tree/32d75d7d3a0b466412ee64d77c29460297515119/jiuwenswarm/channels/process_cli)
- [ADX源码](https://gitcode.com/openJiuwen/agent-dx/tree/a88659db6779538fba5337025c8bc09f530b044d)
- [全部框架固定提交](../config/framework.lock.json)，[基础包锁](../config/infrastructure.lock.json)。
