# 当前状态

ADX 最小真实链路已通过；完整订单故障闭环待验收。

- 独立公开仓库与专用 VM `jiuwen-ops-adx-lab`，保留原项目和历史。
- VM：4 CPU / 8 GiB / 40 GiB；工作台19780、原生观测19781、业务19080、ADX19443。
- ADX a88659db6779538fba5337025c8bc09f530b044d；sandboxd b5dab2958183faa8bcf04955eef7b0ae1c9b10ef；runsc systrap，网络 ACL 保持启用。
- 40 项产品边界测试通过。平台构建和模型执行是两项独立验证。
- 最小通过案例 `trace-probe-99912656991d46a0`：按需 Binding/Environment → 官方 Process SDK → Swarm/Core → 真实模型5次调用和4次主机工具调用 → 原版轨迹 → ADX确认删除。SDK status=completed / exit_code=0，原生记录 revision=34，底层沙箱列表恢复为空；释放后仍能回看。
- 对应 attempt `attempt-53e04e1ff15f44f0`，Session `process_cli_1a18d2cd3bd_ad7416a4fbe5`，Environment `adx-dfdff743-8e7e-4ca2-9035-54c0c6b884fb`。
- 首次环境资格验证失败（ARM64镜像索引、文件属主、Docker路由）与一次真实模型输出格式失败均保留。未将失败改为通过。

执行 broker 为控制器同进程独立8082监听，沙箱不能访问工作台8080或平台管理接口。原生前端使用固定版本原文件；自有层提供只读传输、按 case 固定的官方读取进程和跟随栏，平台事件不转换为 Core Span。
