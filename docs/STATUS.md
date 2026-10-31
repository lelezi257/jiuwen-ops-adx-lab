# 实际验收状态

## 演示节奏更新 · 2026-10-31

已部署并重新跑通完整真实案例 `case-6e1c4483f98542e2`，最终 `RESOLVED_FIXED`、清理 `CONFIRMED`，两个真实SDK Session在释放后仍可读取。真实PR [#3](https://github.com/lelezi257/jiuwen-ops-adx-lab/pull/3)、CI和双架构构建全部通过；55项产品测试通过。

- 本轮真实500至事件创建4.45秒；按钮至SDK开始38.21秒（故障版本发布及500确认24.87秒，告警4.45秒，case至SDK8.88秒）。
- 演示恢复窗口2×5秒，实耗11.07秒；每窗口普通/优惠码各10次，全部通过，金额、SQL、历史订单及非法输入检查保留。
- 页面明确标记演示恢复验证；这是短窗口演示资格，不代替下方历史2×60秒观察证据或生产可靠性验收。
- 模型、CI、构建、实际产物验证和发布没有跳过；总时长仍随实际计算和网络变化。原项目与现有历史保留。

[本轮时间及交付证据](evidence/demo-waits-acceptance.json) · [实际界面](evidence/demo-waits-recovered.jpg) · [配置说明](RUNBOOK.md)

## 初版真实验收 · 2026-10-30

**真实功能链路 PASS。** 最小按需执行通过，完整订单事件 `case-f9499998ff724bd3` 达到 `RESOLVED_FIXED`；ADX删除已确认，底层沙箱列表为空，四次真实SDK记录在释放后仍可读取。

- 新仓库/VM：`jiuwen-ops-adx-lab`；旧项目仍为HEALTHY、17个历史事件，旧HEAD及原有工作区修改未动。
- VM：4 CPU / 8 GiB / 40 GiB；工作台19780、原生观测19781、业务19080、ADX19443。
- ADX固定a88659db；sandboxd固定b5dab295；runsc systrap，ACL保持启用；SDK/Swarm/Core固定版本见framework.lock。
- 最终部署模板6另跑真实只读探针`trace-probe-3a2dfc8b26d74d08`通过：新Environment按需创建、5次真实模型调用、4次工具调用、SDK completed/exit 0；释放确认后原生revision34仍可读。完整订单案例使用模板5，两次验收边界分别保留。详见[最终部署探针](evidence/final-deployment-minimal.json)。
- 53项产品边界、回执身份、复核上下文和产物完整性测试通过。
- 真实PR [#1](https://github.com/lelezi257/jiuwen-ops-adx-lab/pull/1)；[可信CI](https://github.com/lelezi257/jiuwen-ops-adx-lab/actions/runs/41072564084)通过；merge SHA `fe17caf809f061f8512101b39b173ecfceded158`；[双架构构建](https://github.com/lelezi257/jiuwen-ops-adx-lab/actions/runs/41073187806)通过。
- 实际发布digest `sha256:6f0b9da05b46452445893d8711e021bb206a352b28f990edff6acaa0e389073a`。独立验证两个60秒窗口，各窗口coupon/no_coupon均109次，全部200、金额正确、SQL行一致；历史订单和非法输入语义均通过。
- 四个Session同属Binding `case-f9499998ff724bd3-e1`、Environment `adx-61356fa4-2ae1-4551-82f8-523a5ba69a26`。它们分别是修复停止、修复成功、复核停止、复核成功；没有伪装为一个Session。原生页面已实测自动跟随。
- 模型写出的pricing.py及新回归测试字节哈希与GitHub PR完全一致，修复由真实SDK中的模型生成。

这次资格验收发生过：平台冷启动接线问题、一次故障镜像构建超时、测试DB镜像别名缺失、合并前GitHub读取故障、产物公网限速，以及复核上下文混入历史反馈/源码读工具不必要fetch。均已修正并保留失败/重试记录。真实59MB产物首次下载565.77秒，随后使用经过GitHub摘要校验的私有缓存导入；不把缓存导入当作公网性能。

这不是无人干预或生产可靠性认证；没有证明HA、多租户或零中断。单实例订单实验期间确实发生过500及发布间隙。控制器+broker当前共进程双监听，其他平台/执行/交付/观测组件独立。

[HTML验收](acceptance.html) · [订单证据JSON](evidence/order-acceptance.json) · [最小链路](evidence/minimal-acceptance.json) · [部署/接口](IMPLEMENTATION.md) · [操作](RUNBOOK.md)
