# Test Evidence

日期：2026-11-17 UTC。应用版本：0.1.0。任务：WDH-000 / 001 / 002 / 010 / 011。

本轮开始时仓库只有规格文档，没有应用实现。所有本轮输入均为合成数据，没有真实微信数据、设备或 Odoo 连接。源代码提交见 `docs/IMPLEMENTATION_STATUS.md`；部署修正提交由 Git 历史记录，日志与截图随证据提交保存。

## 运行环境及实测结果

Linux x86_64 Cloud，Python 3.12.14，Node 24.22.1，npm 11.9.0，Docker 29.9.2 / Compose 2.40.3；实际数据库 postgres:17.6-alpine（digest 已固定），浏览器为 `/usr/bin/chromium`。容器 Python 为 3.12.12、构建 Node 为 24.11.1。

| 命令 / 时间 UTC | 结果 | 证据 |
| --- | --- | --- |
| `make bootstrap`（首次 13:53；14:01 复验） | PASS，锁文件安装成功；首次 .env 0600，复跑不覆盖配置 | `evidence/bootstrap.log`；另有自动化配置文件保护测试 |
| `TEST_POSTGRES_URL=<新的专用空测试库 URL> make lint test test-security`（13:56:41–13:56:49） | PASS：Ruff / format / mypy / TS / 已实现 OpenAPI 漂移检查；Python **33 passed**（含 PG 六项，无 skip）；Vitest **3 passed**；安全子集 **20 passed**；Bandit exit 0 | `evidence/foundation-checks.log` |
| `WDH_CAPTURE_SCREENSHOTS=1 PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium make test-e2e`（最终约13:59–14:00，19.2s） | **3 passed**；真实 API 活性、隔离空库未就绪、导航；390px 无横向溢出；服务错误状态 | `evidence/browser-tests.log`；`evidence/workspace-desktop.png`、`evidence/workspace-mobile.png` |
| `npm --prefix apps/web run build`（14:01） | PASS，75 modules，Vite 6.4.6，1.94s，构建无警告 | `evidence/web-build.log` |
| `pytest tests/security/test_compose.py -q`（部署修正后） | **2 passed**；新增 tmpfs flow-list 路径断言 | 单独复验终端记录；最终部署证据附后 |

安全 20 项是33项 Python 测试的子集，未重复算作额外覆盖。完整平台业务 E2E 尚不存在，不能把本轮3项外壳 E2E 视为 AC-002 全平台通过。CI 工作流已编写但未提交远端执行。

## PostgreSQL / 原件 / 合成样例

- 使用专用、回环随机端口映射的临时 PostgreSQL 17.6 实例；最终在新的 `wdh_final` 空库运行了 `upgrade head` 两次、`alembic check`，无 schema 漂移。
- 六项 PG 测试覆盖实际版本/表结构、workspace 越权关联、同 workspace 跨账号设备写入、重复 batch 幂等键拒绝、同字节不同 raw locator 保留及重复 locator 拒绝、foreign workspace raw record 拒绝。它们是数据库约束测试，不是尚未实现的 RBAC API 测试。
- CAS 测试先因模块未实现产生一次收集错误（RED），实现后16项存储测试通过。覆盖16次并发保存仅一个对象、原始中文/emoji/CRLF/NUL 字节往返、0400、大小限制清理、损坏对象不覆盖、哈希路径限制、符号链接、Zip Slip、绝对/Windows 路径、压缩比与合法 ZIP 元数据读取。
- 工厂在两个独立新目录生成结果，整树文件 SHA-256 相同；manifest 大小/哈希实算；已有目录禁止覆盖。版本化样例有35类预期。时间/Unicode/去重等后续业务处理未实现，生成样例不等于这些业务规则通过。

## Docker 实测过程

初次 `make up` 因 Cloud 代理 CA 在容器中未受信任而失败。使用临时 Dockerfile/Compose override，通过 BuildKit secret 挂载 `/etc/ssl/certs/ca-certificates.crt`，未禁用 TLS、未将证书复制进镜像。

并行构建随后因环境 7.9GB 磁盘 / VFS 多层复制空间不足失败。只读确认全部构建缓存均来自本轮后，清理这些可再生中间层（未删卷），精简 Dockerfile 并改成串行构建。两个镜像均构建成功。

实际启动还发现 tmpfs flow-list 逗号拆项、原文件0600复制后非 root 不可读的问题，已修复为带引号的 tmpfs 项、COPY 数值 chown / nginx 配置 chmod，并进行容器复验。代理信任链仅用于本次临时构建配置，仓库保留可移植常规 Dockerfile。

最终容器复验：**PASS**（14:08 UTC）。`docker compose up -d --no-build --wait` 和 `make migrate` 均 exit 0；db/api/web 均 healthy，迁移容器正常退出。宿主端口 live 返回 `ok`、ready 返回 `ready`，Web 同源代理返回 `ready`。限定字段状态见 `evidence/docker-runtime.log`，实际部署浏览器截图见 `evidence/compose-workspace.png`。数据库运行 UID70，API UID10001，Web UID101，全部 cap_drop ALL；API/Web 为只读根文件系统；宿主只发布127.0.0.1的8000/5173，数据库不映射端口。

还修复了 BusyBox wget 健康请求误走环境代理导致403：仅对固定容器内回环健康 URL 使用 `-Y off`，不改变外部网络信任配置。

最终 API 是完整重建的镜像 `sha256:dbc7332dcaf3f15c557d2ac3b2692c02e91d6f01c8651664077de511343a8800`；Web 初始完整构建成功，但重跑完整多阶段构建仍因 VFS 容量失败，因此在同一既有静态产物上应用等价 nginx 文件权限修正层，实际运行镜像为 `sha256:659f56708d27830a8a9b86786b9fa81dbfbab2c300a27ce9367464fccddd79e0`。这是本地 image ID，不是已推送的 registry digest。最终常规 Dockerfile 的全新多阶段重建仍需在有足够构建空间的环境复验，未掩盖这项环境限制。

最终复验命令（临时信任配置均留在 `/tmp`，不进入源码）：

```sh
# 通过 BuildKit secret 的临时 override 分别构建 API/Web；Web 权限层复用已构建产物
docker compose up -d --no-build --wait
make migrate
curl -fsS http://127.0.0.1:8000/api/v1/health/live
curl -fsS http://127.0.0.1:8000/api/v1/health/ready
curl -fsS http://127.0.0.1:5173/api/v1/health/ready
```

单独用 Chromium 访问5173，等待页面两个健康状态均为“运行正常”后截图成功；这与使用隔离空库、预期未就绪的测试截图区分保存。部署修正提交为 `e304738`。源码只提供构建配置，不打包已安装依赖或容器镜像。

## 未验收的范围

- WDH-003 `BLOCKED: REAL_SOURCE_VALIDATION`：iPhone/Mac/Windows 无授权实机导出；任何真实组合均未标为 SUPPORTED。
- 没有消息上传、解析/规范化、跨设备合并、业务检索/审核、角色/会话授权、AI、Odoo、加密备份恢复或性能基准结果。
- ZIP 目前只做元数据检查，不执行解压；MIME、实际解压流限额、XSS 内容预览、CSRF、登录爆破等完整 HTTP 安全链路未实现。`make test-security` 是当前切片边界回归，不是 AC-601 全部通过。
- 尚未进行完整 SBOM/依赖漏洞审计或灾备演练，未做 Release Candidate / 正式发布。没有删除、覆盖真实数据，未向任何外部系统写数据。
