# 实际部署与交互

这是独立实验实现，原有 `jiuwen-ops-lab` 不在此部署中。Mac 只运行 Lima 和浏览器；所有新服务及沙箱位于专用 Ubuntu ARM64 VM。

## 哪些组件常驻

| 组件 | 部署方式 | 角色 |
|---|---|---|
| 运维控制器 + execution broker | 同一 Python 进程，独立8080/8082监听；Compose control | 事件、attempt、阶段、短期授权、选择并激活 ADX Binding；工作台19780 |
| ADX API / Activator / Coordinator / ADXlet / Redis | 固定官方包，systemd supervisor | 管理模板、Binding、Environment、路由和生命周期；HTTPS19443 |
| sandboxd + runsc | VM systemd，固定独立后端包 | 真正创建、隔离和销毁沙箱，ACL与cgroup保留 |
| execution host + Process SDK/CLI/Swarm/Core | **任务到来后由 ADX 在 runsc 沙箱创建** | 接收去重请求、官方真实模型与主机工具循环；没有常驻 runner daemon |
| 可信交付 delivery | 独立 Compose 服务 | GitHub、候选工作区、受限源文件工具、可信测试、PR/CI/合并/构建与发布；持有 GitHub 凭证和 Docker socket |
| evidence / probe / collector | 独立 Compose 服务 | 指标日志证据、持续真实订单和SQL检查、独立发布验证 |
| 原生观测 native-web | 独立 Compose 服务，19781 | 固定版本原版前端 + 自有只读传输/按case读取进程/跟随栏；不执行 Agent |
| 订单应用与 PostgreSQL、Prometheus、Loki、Alertmanager、Registry | 独立服务及持久卷 | 故障对象、业务数据、遥测、告警及镜像 |

“控制器”和“broker”目前共享一个产品进程和SQLite锁，但通过不同监听和沙箱ACL隔离接口。ADX平台、每个执行沙箱、交付、验证与观测都是独立部署单元。本版并非高可用多副本控制平面。

## 一个订单事件怎么走

1. 普通下单实际返回500，探针保留该版本的HTTP/金额/数据库证据；Prometheus/Alertmanager创建运维case。
2. **控制器决定归属**：同一故障发布身份归入现有case；新case分配不可变模板版本、`case-e1` Binding和attempt，持久化后才发请求。
3. 控制器发送官方 `POST /agent/http/runs?target=urn:adx:binding:ops-order:<version>:<binding>`；`workspace=case_id`仅作为安全模板路径参数。ADX认证与业务授权使用不同请求头。
4. Binding首次收到请求，ADX按模板创建Environment；sandboxd创建runsc沙箱，ADX注入自己的Execd，继承镜像入口启动execution host。`/ready`通过官方SDK能力检查后才接收任务。
5. execution host用短期授权向broker确认case/attempt/phase，校验沙箱固定case身份，按attempt和请求摘要去重。它启动**官方SDK** `Client(command=[python,-m,jiuwenswarm.channels.process_cli.main])`，调用`query(protocol.capabilities)`和`run(...)`；没有自写模型循环。
6. 官方SDK的`run.started`返回真正SessionID，事件立即保存到工作台。模型的工具请求经SDK `on_tool_call`回到host，再由broker按阶段白名单调用evidence/delivery。repair允许源码修复，verify只有只读工具。
7. Agent自己写修复和回归测试，运行可信测试并创建真实PR。产品组件处理CI、授权、合并、构建和digest发布；这些是平台事件，**不会伪造Core Span**。
8. 独立probe通过HTTP下单、读回、金额及SQL验证后，控制器创建verify attempt。**复用同一case Binding和Environment**，再次调用真实SDK；SDK生成自己的第二个Session。观测跟随栏自动切到这个Session。
9. 结果必须同时满足真实SDK成功、可信交付和独立验证才能达到`RESOLVED_FIXED`。host确认SDK已结束，observer确认两轮原生记录已落盘，控制器才删除Binding。ADX确认Environment删除后标记`RELEASED/CONFIRMED`；case目录与数据库卷继续保留。

## Session与沙箱的关系

| 身份 | 谁生成 | 生命周期 |
|---|---|---|
| case_id | 运维控制器 | 一次事故，持久化到结束后 |
| attempt_id | 运维控制器 | 一次repair或verify调用；去重、授权、回执关联 |
| Binding | 控制器选标识，ADX存储 | case的一次资源承载；失效重建须新incarnation并保留历史 |
| Environment / backend sandbox | ADX / sandboxd | 真实运行资源；成功结束后删除 |
| SDK SessionID / request_id | 官方Process SDK | 一次真实执行；repair与verify各自独立，不能伪装为同一Session |

因此本版是“一个case一次承载环境，可包含多次真实SDK Session”，不是“一个Session永远绑定一台沙箱”。并发上限默认1，其他case排队；没有预建Agent池。失败或结果不明确不会自动重放模型/工具，保留`NEEDS_HUMAN`供核查。

## 原生轨迹扩展边界

原版前端来自Swarm `32d75d7d3a0b466412ee64d77c29460297515119`，编译产物未修改。自有层只有只读RPC/HTTP接线、多case记录路由和顶部持续跟随栏。它不运行Swarm执行后端、不注册可写配置或发起新对话。

轨迹直接由官方Core写入case持久目录的原生SQLite，`TrajectoryHost`、官方HTTP路由和原版前端读取。官方Session生命周期校验拒绝“单Session指向外部目录”的软链；因此每个case使用独立、固定根目录的读取进程，只把其整个`sessions`目录映射到真实只读记录目录。读取进程自己的日志在observer卷中。全局根目录不会随着用户点选来回切换，不复制/拼造Span，也不改SDK Session身份。最多保留3个读取进程，历史按需重新打开。

## 安全与持久化

- control持有ADX租户凭证及签名密钥；delivery持有GitHub和Docker权限；沙箱不持有它们。
- 沙箱只有本case的数据目录和只读模型配置，以及请求中的case/attempt/phase短期授权。服务端校验工具权限和case归属，不能用请求体改查别人的case。
- 沙箱ACL拒绝其他沙箱和内网；显式允许broker8082与桥上DNS，允许公网模型访问。Docker29对未发布容器端口还有raw/filter拦截，本项目只增加必要broker例外和经过sandboxd ACL后的公网往返规则。
- 模型文件在VM私有目录中root:root/0600，替换新文件只影响以后创建的沙箱；不为解决属主问题改为全局可读。
- 状态不明时停止自动重放。`POST /api/cases/<id>/release-allocation`只接受终态事件，通过公开ADX删除确认后记录清理结果；历史保留，不能当作业务修复成功。
- `.local/cases/<case>/swarm`独立于沙箱进程，包含Session与轨迹；Compose卷保存控制器、交付与业务历史。没有自动清空环境的脚本。

## 官方源码和固定边界

- [基础包锁和SHA256](../config/infrastructure.lock.json)：ADX固定a88659db，sandboxd固定b5dab295。本仓库Release里的包是**本实验从固定官方源码构建的产物**，不是声称由上游发布的发行版。
- [ADX源码](https://gitcode.com/openJiuwen/agent-dx/tree/a88659db6779538fba5337025c8bc09f530b044d)：`agent/crates/core/src/lib.rs`模板契约；`agent/activator/src/lib.rs`Binding激活/删除；`gateway/src/ingress/agent_api.rs`托管HTTP入口；`platform/adxlet/src/sandboxd.rs`真实后端适配。
- [Swarm源码](https://github.com/openJiuwen-ai/jiuwenswarm/tree/32d75d7d3a0b466412ee64d77c29460297515119)：`jiuwenswarm/channels/process_cli`机器协议，SDK的`Client.run`/host tools；`jiuwenswarm/server/trajectory/host.py`原生轨迹读取；`gateway/channel_manager/web/trajectory_http.py`原生HTTP；`jiuwenswarm/channels/web/frontend`原版前端。
- [框架全部固定版本](../config/framework.lock.json)，Core固定e0891988。ADX只负责执行环境及路由，Swarm/Core负责Agent循环，产品组件负责运维闭环。

## 本次验收修正的产品边界

发布后复核的输入由broker组合真实PR、CI、merge SHA、构建及部署账本，并与历史修复反馈分开。复核输出里的null PR字段只是只读协议形状，不代表此前没有修复PR。源码读取对已经取得的不可变提交直接读本地Git对象；需要缺失对象时才fetch，保留实际base/running SHA和incident到deployed的修复diff。上述事实和工具接线属于运维产品，模型循环仍完全由九问执行。

每次真实SDK执行保存自己的Binding/Environment身份；历史缺失字段仅从同attempt已记录的ADX接受事件补全，不用当前环境冒充历史环境。显式资源释放先预留REQUESTED状态，未完成核查时禁止并发重试，避免一边销毁环境一边启动模型。
