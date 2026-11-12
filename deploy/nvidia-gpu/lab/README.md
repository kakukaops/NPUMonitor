# 无 GPU 夜莺测试环境

当前配置已进入阶段 2：夜莺 + Redis + 独立测试 Prometheus + GPU 指标模拟器 + 测试通知接收器，统一使用 Docker Compose 管理。宿主机不安装 Python、数据库、Prometheus、GPU 驱动或 DCGM。阶段 2 操作与验收见[模拟环境验证指南](../../../modules/devices/nvidia-gpu/rules/docs/05-模拟环境验证指南.md)。下方阶段 1 记录保留作为历史背景。

## 初始验证记录与后续进展

初始提交时（2026-11-06）已完成 Compose 解析、Shell/Python/TOML 语法检查，以及内置时序库关闭和 SQLite 持久路径检查。当前执行会话无法访问 Docker socket，终端代理不可达，直连 DNS 亦不可用，因此尚未拉取镜像、确认镜像标签可用性、启动容器或验证页面和规则执行。不能将配置检查视为环境验收通过。

后续进展：现已获得Docker访问，五个服务健康、真实Prometheus采集和容器测试均通过，六条实验规则已导入，温度触发/恢复通知已验证。更多结果见[规则导入与告警验证](../../../modules/devices/nvidia-gpu/rules/docs/06-规则导入与告警验证.md)。

夜莺以源码 v9.3.0 为配置依据，镜像候选固定为 flashcatcloud/nightingale:9.3.0，实际拉取后需核对版本和 digest；不使用 latest。Prometheus、Redis 也使用固定版本标签。镜像 tag 可变，成功启动后记录实际 digest，作为后续固定发行配置的依据。

## 启动

在项目根目录、能够访问宿主机 Docker 的终端执行：

```bash
bash modules/devices/nvidia-gpu/rules/scripts/lab.sh preflight
bash modules/devices/nvidia-gpu/rules/scripts/lab.sh up
bash modules/devices/nvidia-gpu/rules/scripts/lab.sh status
bash modules/devices/nvidia-gpu/rules/scripts/lab.sh verify
```

`up` 会先预检查，拉取镜像，再等待容器健康；失败不会打印成功。镜像拉取失败时检查 Docker daemon 的网络/代理及标签，不通过更换 latest 绕过版本确认。

`verify` 在夜莺容器内运行仓库中的只读检查脚本，检查夜莺页面、Prometheus 就绪和自采集 up=1；不依赖宿主机 Python，也不修改数据。刚启动尚未完成首次采集时等待约 10 秒后再运行。容器检查不替代下一节人工验证。

## 阶段 1 人工验收

1. `status` 中三个服务均为 running/healthy。
2. 浏览器打开 http://localhost:17000 ，确认能看到夜莺页面并登录。账号初始化以固定版本实际页面及日志为准；登录后修改初始口令。
3. 打开 http://localhost:19090 ，查询 `up{job="prometheus"}`，应为 1。此时没有 GPU 指标属于正常现象，模拟器尚未加入。
4. 在夜莺数据源页面创建测试 Prometheus 数据源，URL 填 `http://prometheus:9090`。注意这里是容器网络地址，不填宿主机的 localhost:19090。告警引擎使用 default（按实际页面选择）。
5. 在夜莺指标查询页面选择这个数据源，查询 `up{job="prometheus"}`，应为 1。该操作用于验证夜莺到数据源的链路，后续将由初始化脚本自动配置。
6. 执行 `bash modules/devices/nvidia-gpu/rules/scripts/lab.sh down`，再执行 `bash modules/devices/nvidia-gpu/rules/scripts/lab.sh up`。账号和测试数据源应保留，验证命名卷持久化。
7. 保存 `bash modules/devices/nvidia-gpu/rules/scripts/lab.sh images` 输出；核对夜莺实际版本，并通过 `docker image inspect flashcatcloud/nightingale:9.3.0 --format '{{json .RepoDigests}}'` 记录拉取摘要。

这些端口仅绑定本机 127.0.0.1，Redis 不映射宿主机端口。若 Docker 位于远程主机，浏览器需在该主机访问，或配置 SSH 端口转发。

## 日常管理

```bash
bash modules/devices/nvidia-gpu/rules/scripts/lab.sh logs nightingale
bash modules/devices/nvidia-gpu/rules/scripts/lab.sh logs prometheus
bash modules/devices/nvidia-gpu/rules/scripts/lab.sh down
```

`down` 保留卷，不删除测试数据。不要使用 `down -v` 作为普通重启方式。SQLite 用于单实例测试，不作为生产或 HA 选型结论；Redis 启用 AOF，夜莺数据库、日志、Prometheus 数据分别使用命名卷。内置 TSDB、采集 agent 接口和 Ibex 均关闭，不挂载宿主机设备或 Docker socket。

## 当前检查点

使用者已确认阶段 1 能访问及登录问题已修复。阶段 2 代码与配置已加入，尚需宿主机启动验收；之后实现首批规则及 API 导入。完整告警测试前不宣称已验证 GPU 覆盖。

## 配置依据

- [夜莺 v9.3.0 默认配置](https://github.com/ccfos/nightingale/blob/v9.3.0/etc/config.toml)
- [夜莺 v9.3.0 Dockerfile](https://github.com/ccfos/nightingale/blob/v9.3.0/docker/Dockerfile.goreleaser)
- [夜莺 v9.3.0 官方 Compose](https://github.com/ccfos/nightingale/blob/v9.3.0/docker/compose-bridge/docker-compose.yaml)

这里采用该版本支持的 SQLite 和外置 Redis，保留镜像内其他模板配置文件，仅覆盖 config.toml；不照搬官方示例中的指标库、采集器与 MySQL。

## 登录后切换菜单自动退出的配置修正

2026-11-06 检查发现本项目的精简 config.toml 遗漏了官方 HTTP.JWTAuth 段。现已补回官方 v9.3.0 的 AccessExpired=1500 分钟、RefreshExpired=10080 分钟及 RedisKeyPrefix=/jwt/。HTTP.TokenAuth 用于 API token，不能代替浏览器会话 JWT 配置。这个遗漏与令牌立即失效的症状相符；由于执行会话无法访问 Docker，尚未通过运行日志或请求确认根因，也未完成在线恢复验证。

应用修改只需重启夜莺，不重建或删除数据卷：

```bash
docker compose -f deploy/nvidia-gpu/lab/compose.yaml restart nightingale
bash modules/devices/nvidia-gpu/rules/scripts/lab.sh verify
```

重启后在同一个地址重新登录一次，连续切换数据源、告警规则、用户等菜单，等待至少 60 秒并刷新页面，预期不再跳回登录页。verify 会检查容器挂载配置中的 JWT 参数，但不能证明进程已重新加载，也不能代替浏览器会话验证。

若仍退出，请在浏览器开发者工具 Network 中定位首个失败请求，记录路径、HTTP 状态码及脱敏错误信息，同时检查 `bash modules/devices/nvidia-gpu/rules/scripts/lab.sh logs nightingale` 和 `bash modules/devices/nvidia-gpu/rules/scripts/lab.sh status`。不要分享密码、Authorization、Cookie 或原始 JWT；后续需排查运行配置是否生效、容器重启、Redis 错误及浏览器令牌过期时间。不要删除数据库、清空 Redis 或关闭认证来绕过问题。
