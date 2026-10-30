# 操作和复现

## 当前这台Mac

新工作台 http://127.0.0.1:19780/ ，原生观测 http://127.0.0.1:19781/ 。旧工作台18780和旧原生页18781仍属于`jiuwen-ops-lab`，请勿混看。

1. 在新仓库运行`./scripts/lab token`，只在本地工作台输入令牌。
2. 点“验证正常基线（各2次）”，通过后看到普通/优惠码订单200、金额20000/18000分、读回及数据库一致。
3. 点“制造真实故障”。先显示发布中；必须实际测到该故障版本普通订单500，才显示故障已复现。后台Agent立即处理。
4. 打开本轮“持续观察”。顶部是本产品的case/attempt/Binding/Environment对应关系，下方是九问原版轨迹。repair和verify是不同的真实Session，页面自动跟随；CI/构建/发布是等待提示。点历史阶段会停止自动切换，点“继续跟随”恢复。
5. 业务恢复卡说明实际业务通过检测；事件`RESOLVED_FIXED`说明交付和Agent复核也结束；`资源清理CONFIRMED`说明ADX已确认释放。三者含义不同。

正常基线只做各2次请求；正式恢复仍保留两个60秒窗口的独立业务合同，不靠容器running代替业务验收。

## 新clone首次安装

先按[README](../README.md)操作。`vm-install`使用本仓库固定SHA的ARM64基础包和干净框架构建，依赖网络能访问GitHub/GitCode、容器仓库、apt、PyPI/npm和模型端点。可通过`LAB_VM_IMAGE`指定本地Ubuntu24.04 ARM64 cloud image；脚本记录实际镜像摘要。VM无Mac共享目录挂载。

`.local/runtime.env`由首次`vm-sync`生成，配置HOST_REPO和信任源码SHA。自定义镜像/包源写在VM的同名文件中，后续sync保留这些配置。代理只对专用VM配置，不改旧项目。不要把APIKey写入runtime.env或模板。

ADX包来自[本实验Release](https://github.com/lelezi257/jiuwen-ops-adx-lab/releases/tag/infra-20261030-arm64)，`scripts/fetch_infrastructure.py`按[锁文件](../config/infrastructure.lock.json)校验后解压；安装器还校验后端逐文件摘要。平台已运行时安装器拒绝重装；setup检测到活动case/operation则拒绝重启。

首次平台启动后发布数字版本模板，不预建Binding。第一次`qualify`才创建沙箱、调用真实模型和只读工具。原生轨迹与官方SDK状态都通过后再制造业务故障。`ADX_READY`只代表平台模板可访问，不证明任何模型已经成功调用。

## 配置模型、状态和失败恢复

- 更新本地`.local/model.env`后执行`./scripts/lab configure-model`。它把配置原子替换为VM私有root:root/0600文件，用于未来沙箱，不重启活动环境。若首次缺少模型导致`/ready`失败，先核查和结束失败事件，再释放其资源，之后发新任务。
- `./scripts/lab vm-status`查看新Compose组件；`limactl shell jiuwen-ops-adx-lab -- sudo systemctl status ops-adx-platform ops-adx-sandboxd`查看ADX。
- `./scripts/lab qualify`是只读真实模型探针。`NEEDS_HUMAN`不是成功；工作台技术详情保留官方SDK错误和事件。禁止为了让状态通过而手工修改数据库或伪造回执。
- 结果不明不自动重放。先核查真实Session/PR/发布与日志，必要时通过带本地操作令牌的`POST /api/cases/<case>/cancel`停止未来工具动作，再对终态case调用`POST /api/cases/<case>/release-allocation`。释放会终止资源，保留历史；不等于修复。
- 配置/部署前查看`GET /api/overview`，有活动任务不要重启。`vm-sync`只同步源码和明确配置，不删除case目录/卷，且排除VM自己管理的ADX租户令牌。
- 不使用`docker system prune`、`docker compose down -v`或删除VM恢复。历史、模型配置和数据卷都是用户数据。

## 验证边界

产品测试：`python -m unittest discover -s tests/product -v`。可信业务合同：Linux Docker中运行`python scripts/ci.py --candidate . --trusted .`。原生只读传输校验：在native-web容器中运行`python /app/scripts/check_native_observer.py <真实SessionID>`。这些都不能替代完整订单真实模型/PR/CI/发布/独立验证。

最小链路结果见[实际证据](evidence/minimal-acceptance.json)。完整订单验收以[STATUS](STATUS.md)及其证据为准；早期失败任务和旧项目的PASS都不能替代新项目验收。
