# 开发运行手册 · 0.1.0

要求：Python 3.12、uv 0.9.17+、Node 24 LTS、npm、Docker Compose v2。项目运行时本地优先；首次依赖安装和镜像构建需访问 PyPI/npm/容器注册表。

```sh
make bootstrap
make lint
make test
make test-security
make up
make migrate
```

访问 http://127.0.0.1:5173；API 活性为 http://127.0.0.1:8000/api/v1/health/live，就绪为 `/api/v1/health/ready`。Compose 在 API 启动前完成迁移；再次 `make migrate` 安全幂等。数据库不映射宿主端口。

本轮只开放两个健康接口，Web 展示开发状态。导入、消息浏览、认证、AI、Odoo 尚未提供；不能往当前系统放真实聊天记录。原契约 `contracts/openapi.yaml` 是目标设计，已实现契约是 `contracts/implemented-openapi.json`，CI 检查漂移。

`make bootstrap` 使用锁文件，生成 `.env` 权限 0600、随机独立密钥；已有文件不覆盖。不提供默认管理员或预置密码；WDH-030 会提供安全管理员初始化。不要将 `.env` 上传到仓库，修改数据库密码需要单独迁移已有数据库凭据，不能只改环境文件。

不用 Docker 时，可分别运行 `make dev-api`、`make dev-web`，均只绑定 127.0.0.1；没有 PostgreSQL 或迁移时就绪检查会显示尚未就绪。SQLite 只用于隔离的测试，不能拿 SQLite 测试代替 PostgreSQL 验收。

```sh
# 生成新目录中的合成文件（已有目录禁止覆盖）
.venv/bin/python scripts/generate_fixtures.py --output .local/my-synthetic-corpus
# 安装浏览器一次；已安装 Chromium 可以指定可执行文件
cd apps/web
npx playwright install chromium
cd ../..
make test-e2e
# 或：PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium make test-e2e
make down
```

`make down` 停止服务但保留数据卷。`make seed-demo` 当前只生成合成文件后以非零码说明 WDH-014 未实现，不伪造已导入。`make benchmark/backup/restore-check` 同样明确返回未实现。AC-001 的完整 seed 链路尚未验收。

PostgreSQL 专项测试必须指定 **新的、专用空测试数据库** 的 `TEST_POSTGRES_URL`。测试会执行 migration 两次、Alembic check、事务内合成数据约束测试，不清表、不降级、不自动删除数据库；使用过的测试库应重新创建另一个空库。URL 不打印到测试报告，不应使用真实数据库地址。

如果构建环境有自签代理 CA，使用 BuildKit secret 挂载信任链做临时构建配置，保持 TLS 验证，不把 CA 或认证信息 COPY 到镜像。常规 Dockerfile 不依赖 Cloud 专有配置。
