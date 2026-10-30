# 官方来源与第三方组件

框架固定提交见 `config/framework.lock.json`；构建脚本从官方 `openJiuwen-ai` GitHub 组织下载。上游源码及其 LICENSE 保存在 runner 镜像内 `/app/vendor`；本项目不重新分发上游源码到自己的 Git 仓库。

- JiuwenSwarm / agent-core / agent-protocol：各自上游 LICENSE 和 NOTICE 为准。
- Python、FastAPI、Uvicorn、httpx、psycopg、prometheus-client、jsonschema：固定直接依赖见 requirements。
- PostgreSQL、Prometheus、Alertmanager、Loki、Docker registry、Docker CLI：部署使用各自官方容器镜像。
- Lima：[使用说明](https://lima-vm.io/docs/usage/)。
- GitHub：[Actions runner 平台](https://docs.github.com/en/actions/how-tos/write-workflows/choose-where-workflows-run/choose-the-runner-for-a-job)、[状态检查](https://docs.github.com/en/pull-requests/reference/status-checks)。

源码框架版本冻结不等于所有传递依赖永久冻结；首次构建会输出已安装包清单作为验收证据。后续更新应保留旧基线，并重新资格验证。

ADX与sandboxd基础包由本实验从固定上游源码构建并在本实验Release发布；这不等于上游官方发行版。包中保留上游许可证及清单，源版本和包校验见[infrastructure.lock.json](../config/infrastructure.lock.json)与[BUILD](BUILD.md)。本项目的构建/安装记录与应用E2E验收分别报告。
