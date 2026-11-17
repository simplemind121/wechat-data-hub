# 运行手册 · 0.2.0

## 完整包离线启动

要求 Docker Engine/Desktop + Compose v2 正常运行。镜像为 Linux amd64；Linux x86_64 已实测。Apple Silicon 模拟和 macOS/Windows 实机未实测；源码构建可使用目标架构。建议4GB以上可用内存、5GB空闲磁盘作为起点，数据/备份容量另计；这是建议，不是所有设备的实测保证。

```sh
bash start-offline.sh
```

脚本按 `images.lock` 检查内容 ID，缺镜像时从随附 tar.gz 加载，不向注册表拉取；只在 `.env` 不存在时生成随机数据库密码，权限0600。它不创建默认管理员，也不覆盖已有配置。生成配置可用容器中的 Python，不必安装宿主 Python/Node。

打开 http://127.0.0.1:5173，首次创建管理员。端口冲突时编辑 `.env` 的 `APP_PORT`/`WEB_PORT`，例如8001/5174后重跑；访问对应 WEB_PORT。Web 代理 `/api/v1` 到容器 API，数据库不映射宿主端口。只绑定 loopback，不建议直接开放公网。反向代理/TLS/远端暴露需另做部署配置和安全验证。

```sh
# 状态、最近应用日志（无访问日志正文）
docker compose -f compose.yaml -f compose.offline.yaml ps
docker compose -f compose.yaml -f compose.offline.yaml logs --tail 100 api
# 停止，保留 PostgreSQL 和原件卷
docker compose -f compose.yaml -f compose.offline.yaml down
```

不要运行 `down -v` 或 prune 数据卷。不要直接编辑/清空数据库和 CAS。数据库密码变更要同步已有 PostgreSQL 凭据，不能只改 `.env`。备份独立保管，不靠容器卷替代异盘备份。

## 日常使用

1. 首次进入导入页，下载并上传合成演示 ZIP；后台 worker 处理后概览/时间线出现实际记录。
2. 真实合法导出：JSONL、JSON 或 CSV 可直接上传，填写来源、时区与字段映射；媒体 ZIP 根目录放 manifest，所有路径均相对路径。示例 `examples/manifest.json` 的 payload 哈希必须匹配实际文件，不能照抄示例哈希用于别的导出。
3. 导入批次查看覆盖、缺失媒体和解析错误；错误行保留原件、不会伪造字段。重复同批次返回原批次。来源元数据由用户声明，不等于设备身份经过软件认证。
4. 浏览会话，展开来源详情核查原始消息。关键词搜索使用 NFKC 派生字段，原始 Unicode/emoji 保留。分页从服务端取数。
5. 审核相似消息或身份；可合并、拒绝、暂缓，操作留审计。同昵称、相同文字不直接认定同一人/消息。
6. 默认会话为 private。管理员明确标业务允许后才可做本地报价规则提取，候选含原文跨度，人工审核；Odoo 只展示映射预览，没有真实同步按钮。
7. 审计与备份页：管理员导出 CSV/JSONL 或下载当前工作空间加密备份。至少16字符独立备份口令；旧会话在恢复后无效，重新登录。

默认一个 API 容器内由独立 worker 进程与 API 监督运行（worker 死亡触发容器重启）；PG 持久任务和 lease 保证恢复补处理。需独立伸缩时，源码部署可用 `docker compose -f compose.yaml -f compose.workers.yaml up -d --build --wait`。不要为成品包另外启动第二套相互矛盾的编排。

## 源码开发

Python3.12、uv0.9.17+、Node24、npm；首次下载需要网络。依赖锁在 `uv.lock`/`apps/web/package-lock.json`。

```sh
make bootstrap
make lint
make test
make test-security
PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium make test-e2e
bash start.sh
```

测试 E2E 创建独立合成 SQLite 目录和独立 worker，不读已有聊天库。SQLite 只用于测试；PG 六项专测需要新的空库 `TEST_POSTGRES_URL`，`PRODUCT_POSTGRES_URL` 指向专用可创建测试数据库的 PG 控制库，将每个产品测试放到随机新库，结束只删它自身的测试库。严禁指向含真实数据的数据库。

`make seed-demo` 在正在运行的容器导入合成演示；没有管理员时在终端交互建号，已有用户不重置密码。也可直接在网页下载/上传演示。`make backup` 提示输入口令并在私有卷 exports 写备份；API 网页备份仅当前工作空间，宿主 CLI 为受信任本机全库操作。恢复见 `RECOVERY.md`。

已实现 API 契约是 `contracts/implemented-openapi.json`；原 `contracts/openapi.yaml` 为目标设计，未实现端点不应假定可调用。
