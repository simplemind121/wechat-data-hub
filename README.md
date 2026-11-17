# WeChat Data Hub — Codex 工程交付包

版本：1.0.0（2026-11-17）  
状态：**0.1.0 工程基础切片已实现；完整导入平台与真实设备兼容性尚未验收。**

## 当前代码与运行

已提供 FastAPI 健康检查、React 工作台、PostgreSQL 17 Bronze 迁移、原件 CAS 库、35 类合成边界样例、CI 与锁定依赖。当前不提供消息导入/浏览、身份认证、AI 或 Odoo。可验收范围和实际证据见 [实施状态](docs/IMPLEMENTATION_STATUS.md) 和 [测试记录](docs/TEST_EVIDENCE.md)。

```sh
make bootstrap
make lint
make test
make test-security
make up
```

Web：http://127.0.0.1:5173；API：http://127.0.0.1:8000/api/v1/health/live。完整运行方式、浏览器测试和未实现命令的行为见 [运行手册](docs/RUNBOOK.md)。`make down` 保留数据卷。

原交付包的 `CHECKSUMS.sha256` 是规格包基线校验单，不能用于校验已进入开发迭代的工作树；后续版本发布另生成制品清单。

## 一键交给 Codex

1. 在本地新建一个空仓库，将本交付包的所有文件复制到仓库根目录（保留目录结构）。
2. 在仓库根目录启动 Codex，提交 `CODEX_START_PROMPT.md` 的全部内容。
3. Codex 必须遵守根目录 `AGENTS.md`，按 `TASKS.md` 顺序交付。
4. 每一阶段执行 `ACCEPTANCE.md` 对应测试，提交证据和变更日志；不得跳过 P0 数据源兼容性检查。

## 文件导航

| 文件 | 用途 |
| --- | --- |
| `SPEC.md` | 主开发规格：范围、架构、数据模型、功能、API、安全、部署和交付定义 |
| `AGENTS.md` | Codex 持续执行约束：编码规范、禁止项、每轮汇报格式、质量门槛 |
| `CODEX_START_PROMPT.md` | 第一轮直接复制给 Codex 的任务指令 |
| `CODEX_CONTINUE_PROMPT.md` | Codex 断点续开发/后续任务轮次指令 |
| `TASKS.md` | 逐阶段可领取的任务分解和依赖关系 |
| `ACCEPTANCE.md` | 功能、安全、性能、数据质量、灾备、交付验收矩阵 |
| `SOURCE_COMPATIBILITY.md` | 三平台导出适配器、依赖评估和许可证审查门槛 |
| `contracts/openapi.yaml` | API 契约起始定义（开发时扩展并生成契约测试） |
| `contracts/reference_schema.sql` | PostgreSQL 表/约束/索引参考 DDL；以 Alembic 迁移为正式来源 |
| `examples/` | 双设备合成导入清单、消息和实体样例；**绝不是真实聊天记录** |
| `.env.example` | 非敏感配置模板 |
| `docs/SOURCES.md` | 经核对的上游参考来源与待验证项 |

## 产品分级

- **MVP（P0–P3）**：可在本地完成导入、原始归档、确定性去重、浏览、全文检索、导出和审计。
- **Release Candidate（P4–P5）**：OCR/ASR、离线 AI、业务实体审核、可选 Odoo 对接、备份恢复。
- **正式交付（P6）**：真实设备兼容测试、性能基准、安全检查、恢复演练、操作手册和版本化发布均通过。

**核心边界：**本系统接收用户自主提供的合法导出文件，不负责开发、捆绑或运行微信客户端数据库解密/密钥提取代码。外部工具导出能力须在隔离环境独立评估；原生备份≠可解析备份。

详细验收标准以 `ACCEPTANCE.md` 为准。没有真实导出样本或缺少合法可用的解析路线时，只能宣称“导入和处理平台已完成”，不得宣称“已支持某微信版本全量导出”。
