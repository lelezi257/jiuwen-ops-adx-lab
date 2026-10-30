# 当前状态

实施中，尚未完成 ADX 真实执行或完整订单案例验收。

- 独立公开仓库 lelezi257/jiuwen-ops-adx-lab 已建立；原 jiuwen-ops-lab 的 VM、数据和历史保留。
- 专用 VM jiuwen-ops-adx-lab：4 CPU / 8 GiB / 40 GiB 按需磁盘，工作台19780、原生观测19781、业务19080、ADX19443。
- 已实现按事件调度、执行接收去重、短期 case/attempt/phase 授权、服务端工具权限限制与多根原生记录索引；38 项边界测试通过。
- ADX 固定 a88659db6779538fba5337025c8bc09f530b044d；sandboxd 固定 b5dab2958183faa8bcf04955eef7b0ae1c9b10ef，ARM64 构建进行中。
- 后端改用支持网络 ACL 的 runsc systrap；runc 在所选 sandboxd 版本不支持 ACL，未关闭隔离策略以绕过。
- 首次环境创建、实际 SDK/模型/工具、原生轨迹与资源释放仍待真实验收；旧项目的 PASS 不属于本项目。
