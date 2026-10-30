# 权限、版本和恢复边界

业务使用者访问订单 API；运维人员访问自己的工作台。两者不访问 Swarm Web。业务用户不需要参与修复，但单实例实验环境可能出现故障和重启间隙，不承诺零中断。

## 服务身份

- 控制中心：事件/任务/取消、CI 判定、交付授权和最终结案。
- runner：真实 SDK 调用、工具回调；没有 GitHub Token、DB 密码、Docker socket 或控制服务令牌。
- 取证服务：只读 Prometheus、Loki 和已有证据；查询时间窗与大小受限。
- 工程服务：可信 VM 控制进程，持 GitHub 凭证和 Docker socket。`/tools/*` 只允许候选源码/新增测试/测试/PR；`/ops/*` 另需控制身份，才允许合并/构建/部署/回滚。
- probe：持有单独 PostgreSQL 只读 SELECT 账号，直接核验数据库；独立真实请求与金额/持久化/旧订单/非法输入检查，判据不来自模型。

容器隔离用于限制候选代码；Docker socket 意味着工程服务本身是可信高权限组件。本学习版不提供多租户、生产 RBAC、HA 或对被攻陷工程服务的隔离保证。

## 版本证据

```text
实际运行 B：source SHA + registry digest
 -> 基于 B 的工作区 / 新测试 / 实际 diff
 -> PR head SHA 与 base SHA
 -> 可信 contract workflow / 实际 test-merge SHA / 成功 job
 -> 控制中心授权 / 实际 merge SHA M
 -> 对 M 再执行业务合同 / AMD64 与 ARM64 构建
 -> Actions run / artifact ID / archive SHA256 / 源码与平台
 -> 导入 VM 内 registry / OCI manifest digest D
 -> docker inspect + 运行 /version + 发布账本
 -> 同 release_id 的独立业务验证
```

检查 skipped/neutral 不算通过；PR 新提交或 base 变化使旧检查失效。候选不能修改可信工作流、Dockerfile、验收、依赖和部署策略。部署比较当前 release_id，单应用串行；不部署 `latest`。

## 状态与失败

框架 `completed` 不等于业务恢复。正常自动修复必须同时有真实模型运行、实际 PR/CI、版本链和业务合同。独立业务合同默认连续两个60秒窗口，每条正常路径每窗口至少30请求且全部成功、金额正确、实际数据库读取一致，非法输入语义保持。

回滚目标是最近通过业务合同的已知正常 A，不是仍有故障的 B。回滚成功记 `RECOVERED_ROLLBACK`，不记 `RESOLVED_FIXED`。取消阻止后续新动作，但不能撤销已发生的提交、合并或发布。发出中的外部动作可能完成，需要查询账本。

runner 失联/租约失效不重放写工具；标为需人工。模型或传输失败不产生预置修复。费用缺失不是零；启用 SDK 的 USD 上限时，模型没有费用报告会按官方合同失败，一次请求仍可能先超过上限。

## 本地材料

`.local` 目录0700，密钥不提交；db_password 文件允许 PostgreSQL 容器用户读取，但其宿主父目录仍受保护。候选代码只能读写受限业务目录。日志/源码中的指令视为数据，不能取得额外工具权限。

实验流量和订单是测试数据，不接真实支付。不要把项目连接到生产资源。

证据引用按来源核对：`ev-*` 必须属于本 case 的取证记录；`test-*` 必须匹配工程服务为本 case 保存的当前测试回执，不能凭模型声称测试通过。SDK结果先保存再校验；重复投递不得倒退已进入CI/合并/构建的状态。只读复核失败的显式重试必须仍是独立报告验证的同一 release/source/digest，只开启新的验证会话，不重新合并或发布。
