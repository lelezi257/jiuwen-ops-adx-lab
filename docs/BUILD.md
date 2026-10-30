# 基础包来源与构建

[锁文件](../config/infrastructure.lock.json)给出本实验Release的精确SHA256。GitHub资产摘要已核对；安装器再验证包内后端逐文件摘要。包中保留上游许可证与清单，不含模型、GitHub或本实验平台凭证。

ADX固定官方源码`a88659db6779538fba5337025c8bc09f530b044d`。使用Linux ARM64构建环境：Rust1.95.0、Go1.25.5、Python3.11.14、Redis7.2.5、erofs-utils1.8.10和musl-gcc。干净源码未打补丁，命令如下（路径指向自己的工具与输出目录）：

```sh
export CARGO_TARGET_DIR=/cache/target-release
export ADX_WITH_AFS=0
export ADX_REDIS_SERVER=/usr/local/bin/redis-server
export ADX_REDIS_CLI=/usr/local/bin/redis-cli
export ADX_RELEASE_TARGET=aarch64-unknown-linux-gnu
export ADX_RELEASE_OUTPUT=/out/adx-release-a88659db
export JOBS=2
export PYTHON=/opt/adx-build-tools/python/bin/python3.11
export CC_aarch64_unknown_linux_musl=musl-gcc
export CARGO_TARGET_AARCH64_UNKNOWN_LINUX_MUSL_LINKER=musl-gcc
export CARGO_NET_GIT_FETCH_WITH_CLI=true
export CARGO_HTTP_MULTIPLEXING=false
make platform-release
```

本次环境的crates.io索引曾超时，使用独立Cargo缓存中的校验和保护rsproxy sparse替代源；未修改Cargo.lock。产物包含静态musl Execd与EROFS运行时，官方assemble/verify通过34文件检查。

sandboxd固定`b5dab2958183faa8bcf04955eef7b0ae1c9b10ef`，官方Makefile目标`release-binary release-cli runc-shim sandbox-logger`，`RELEASE_GOARCH=arm64 GOFLAGS=-p=1`。runc1.5.1及gVisor`release-20260817.0-akernel.5`完整发布包依照该源码的`third_party/runtime-versions.env`验证，SHA512记录在后端manifest中。必须保留runsc wrapper及相邻gvisor-bin全部文件，不能只拷贝一个二进制。

普通OCI镜像路径使用真实OverlayFS，不需要distill-fs；本实验没有声称通过Nydus/S3/FUSE路径或构建出distill-fs。runc在所选后端版本不支持所需网络ACL，实际使用runsc systrap，未关闭ACL绕过。

SDK/Swarm/Core从[框架锁](../config/framework.lock.json)的官方仓库构建。`deploy/Runner.Dockerfile`与`deploy/Observer.Dockerfile`是完整源码构建路径。`*.cached.Dockerfile`仅是本机加速选项，必须匹配框架锁；它们不是首次安装依赖，不能把旧项目缓存或旧PASS当作本项目资格验证。
