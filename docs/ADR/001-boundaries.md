# ADR 001 — 本地文件边界与首个工程切片

日期：2026-11-17。决策：采用。任务：WDH-000 / 001 / 002 / 010 / 011。

系统只接收用户合法取得的导出文件。不运行、复制或捆绑上游密钥提取、注入、内存扫描或解密逻辑。上游 README 的导出能力只作为格式评估线索，不能替代真实导出回归。

本轮只提供工程基础、合成数据工厂、Bronze 迁移和本地 CAS 库。只有健康检查 HTTP 路由开放；数据接口须在 WDH-030 权限完成后开放。原件 CAS 直接保留字节，源 manifest 的业务注册与任务持久化留给 WDH-012 至 014，不提前宣称完整导入链路。

主键统一为应用生成 UUIDv4，SQLAlchemy `Uuid(as_uuid=False)` 在 PostgreSQL 为原生 UUID。复合外键在数据库层约束 workspace/account/device/blob/batch 归属。生产迁移只用 Alembic，禁止启动时 create_all；自动 downgrade 明确拒绝，回滚需要经过验证的备份恢复流程。

CAS 依赖服务账户独占的私有目录；临时文件 fsync 后使用硬链接原子提交（不覆盖目标），原件 0400，目录 0700。相同哈希的已有对象再次校验，损坏则报错而不覆盖。它不防御拥有服务账户权限或 root 的攻击者。ZIP 仅检查元数据，不解压；实际导入时仍须对解压流实行数量、大小、路径和 MIME 白名单约束。

JSONL、JSON、CSV 的首个 adapter 只实现自有明确契约，不因后缀猜测上游格式。强 ID 语义在真实 adapter 认证前不可信；工厂只声明 synthetic namespace 的预期。官方加密备份不具备解析支持。

## 来源评估（只读核对于 2026-11-17）

| 来源 / 固定提交 | 已阅读 | 格式线索与限制 | 许可及决策 |
| --- | --- | --- | --- |
| [ChatVault](https://github.com/soundadam/chatvault/tree/018492b4e996b6cba8a6233059176a8250c49668) `018492b4e996b6cba8a6233059176a8250c49668` | README.md / LICENSE | 自述 macOS 12+、Mac 微信 4.x；SQLite vault / 按聊天和月份导出 JSON Lines、Markdown；3.x 不支持。未取得真实导出 schema | LICENSE 为 Apache-2.0。仅评估导出结果，未运行工具或复制实现。字段映射 NOT TESTED |
| [WeFlow Fork](https://github.com/334456777/WeFlow/tree/1afa30ac7809f526d55d55a0ae56d0c7e747a879) `1afa30ac7809f526d55d55a0ae56d0c7e747a879` | README.md / LICENSE | 自述微信 4.0+；txt/json/arkme-json/chatlab/chatlab-jsonl/excel/weclone/html/sql；命令 JSON 不能直接当自有 JSON 契约 | LICENSE 为 Unlicense，README §3 明确限制学习研究以外商业活动。冲突未解决，禁止捆绑，商业许可 BLOCKED |
| [WechatExport-iOS](https://github.com/pengw0048/WechatExport-iOS/tree/b22148f2a3d189fcffb6ac5f289f891ae36f7f21) `b22148f2a3d189fcffb6ac5f289f891ae36f7f21` | README.md；根 LICENSE 请求 404 | 自述 iTunes 备份导出 HTML/TXT 和媒体；未给出现代 iOS 版本覆盖，不推断兼容 | 根 LICENSE 未找到，许可 UNKNOWN；未审计完整源树，禁止复制/分发源码。只考虑用户提供的导出结果 |
| 官方 / Finder 备份 | 交付包说明 | 非开放结构化接口 | `unparsed_backup`，未实现解析 |

这些提交是本轮只读查询 HEAD 后固定的参考点。没有下载或执行第三方提取器，也没有认证它们的隐私、构建行为或真实设备覆盖率。进一步 adapter 实施必须获取合法导出样本并单独验证。

## 依赖与供应链

Python 使用 3.12，Node 使用 24 LTS（容器 24.11.1），安装来源为 PyPI/npm，精确版本和校验信息见 `uv.lock`、`apps/web/package-lock.json`。容器基础镜像固定 digest。CI actions 暂锁主版本，发布前 WDH-060 应固定 commit 并做 SBOM/漏洞全量复核。

| 组件 | 必要性 / 维护策略 | 许可与风险 |
| --- | --- | --- |
| FastAPI / Uvicorn / Pydantic / pydantic-settings | 指定栈；健康接口、类型化配置。升级须回归 OpenAPI | MIT / BSD-3-Clause；HTTP 解析与配置是敏感边界 |
| SQLAlchemy / Alembic | 指定栈；数据约束和显式迁移；禁止生产自动降级 | MIT；迁移须在 PostgreSQL 回归 |
| psycopg[binary] | 指定 PostgreSQL 驱动；本轮使用锁定预编译包 | psycopg LGPL-3.0-only；binary 包含本地库，分发义务及漏洞需完整 SBOM 审查 |
| React / TypeScript / Vite / TanStack Query | 指定前端；健康查询及响应式外壳，无业务 mock 数据 | MIT / Apache-2.0（TypeScript）；开发服务器仅回环绑定 |
| Hatchling / uv | wheel 构建与跨平台锁文件；uv 容器及 CI 固定 0.9.17 | MIT / MIT-or-Apache-2.0；仅构建时联网 |
| pytest / HTTPX / Ruff / mypy / Bandit | 指定测试与质量门禁 | MIT / BSD-3-Clause / Apache-2.0；不能以扫描代替威胁测试 |
| Vitest / Playwright / @vitejs/plugin-react / @types | 单元、浏览器测试和构建必需；只在开发依赖安装 | MIT / Apache-2.0；浏览器下载仅安装阶段，合成测试不触及真实个人数据 |

本轮无新增运行时第三方集成。Polars/PyArrow、对象存储、AI、Odoo、n8n 在对应任务需要时再引入。依赖许可列表是初步记录，不代表 WDH-060 已通过。
