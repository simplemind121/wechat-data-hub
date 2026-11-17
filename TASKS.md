# TASKS — Codex 执行任务清单

状态：`TODO` / `IN_PROGRESS` / `PASS` / `FAIL` / `BLOCKED`。**初始均为 TODO；Codex 只能依据真实测试和证据改为 PASS。**

使用方法：按照任务 ID 及依赖关系推进。每完成一项更新本表、`docs/IMPLEMENTATION_STATUS.md`、`docs/TEST_EVIDENCE.md`，记录 commit hash。不能将合成数据通过视为真实微信兼容通过。

| ID | 阶段 | 依赖 | 任务与必须生成的产物 | 可验收退出条件 | 当前状态 |
| --- | --- | --- | --- | --- | --- |
| WDH-000 | P0 | 无 | 建立 monorepo、工具链、CI、Makefile、依赖锁定、README 运行指南 | `make bootstrap`, `make lint`, `make test` 实际成功；新环境启动可复现 | PASS |
| WDH-001 | P0 | 000 | `docs/ADR/001-boundaries.md`、来源格式评估、许可证和兼容矩阵 | 清楚界定不解密、不注入；逐工具记录上游 URL/版本/限制 | PASS |
| WDH-002 | P0 | 000 | 合成数据工厂：两设备、两会话、20+ 边界类型、媒体模拟和导入 manifest | fixture 可复现；确保没有真实个人信息 | PASS |
| WDH-003 | P0 | 001 | 实机/真实导出样本格式验证（仅授权时）；`source_coverage_report.json` | 每设备/版本记录 PASS/FAIL/BLOCKED，不根据猜测标记 PASS | BLOCKED |
| WDH-010 | P1 | 000,002 | PostgreSQL / Alembic、workspace、account、device、batch、raw schema | migration up 可运行；从空库重建一致 | PASS |
| WDH-011 | P1 | 010 | Content-addressed storage、SHA256、原子写与媒体去重 | 同文件多次保存一份；原件只读；路径/zip 攻击测试通过 | PASS |
| WDH-012 | P1 | 010,011 | JSONL/JSON/CSV adapter + registry + schema report | 流式读取、版本化格式错误报告、字段映射有单元测试 | TODO |
| WDH-013 | P1 | 012 | 异步任务状态机、lease、重试、dead-letter、取消 | crash/restart 不丢已归档批次；幂等一致 | TODO |
| WDH-014 | P1 | 013 | 上传 API、导入清单、批次状态、隔离区、覆盖度报告 | 用合成多设备数据重复导入 3 次结果一致 | TODO |
| WDH-020 | P2 | 014 | contact、conversation、messages、observations、events schema | 可查询来源信息，外键和唯一约束生效 | TODO |
| WDH-021 | P2 | 020 | 时间/Unicode/类型/昵称处理、消息规范化与未知类型保留 | 时区、emoji、system、未知类型测试通过 | TODO |
| WDH-022 | P2 | 021 | 强匹配合并 + 弱匹配审核候选 +冲突版本 | 两条同文字消息不被误吞；有来源多对一映射 | TODO |
| WDH-023 | P2 | 022 | 附件关系、媒体引用缺失、引用消息目标补链 | 缺附件能显示缺失而不 500；hash 一致 | TODO |
| WDH-024 | P2 | 023 | parser_version 重算与差异预览 | 旧版本可比对；无破坏性覆盖原件 | TODO |
| WDH-030 | P3 | 020 | 安全认证、admin/reviewer/reader + workspace 授权 | 权限绕过的 API 测试全部拒绝 | TODO |
| WDH-031 | P3 | 023,030 | 会话/消息/联系人/附件 REST API + 游标分页 | OpenAPI 契约与集成测试一致 | TODO |
| WDH-032 | P3 | 031 | React UI：概览、导入、会话、来源详情、附件 | Playwright 端到端可演示，错误/空状态完善 | TODO |
| WDH-033 | P3 | 031 | 关键词搜索、时间/来源/类型筛选、导出 | 中文检索样例正确；100k 样本性能有测试报告 | TODO |
| WDH-034 | P3 | 022,032 | 冲突审核、身份映射审批、操作审计 | merge/reject/defer 均记录审计，支持重跑 | TODO |
| WDH-035 | P3 | 030,032 | 安全配置、数据访问日志、隐私标签 | 私人会话不能进入业务抽取与同步 | TODO |
| WDH-040 | P4 | 023,033 | OCR provider、任务、结果证据与可禁用开关 | 启用/禁用切换、错误处理、图片证据定位通过 | TODO |
| WDH-041 | P4 | 023,033 | ASR provider，音频格式检查/解码能力边界 | 支持格式有转录与时间片；不支持明确报错 | TODO |
| WDH-042 | P4 | 033,035 | embedding + pgvector / 混合搜索 / 权限过滤 | 不外发、workspace 隔离、结果指向消息证据 | TODO |
| WDH-043 | P4 | 040,041,042 | LLM 实体抽取、schema 验证、review workflow | 提取报价/客户/产品候选，不能直接推送 Odoo | TODO |
| WDH-044 | P4 | 043 | 业务实体 UI：审批、拒绝、编辑与证据链 | 批准字段全部来源可追溯，虚构字段测试拦截 | TODO |
| WDH-050 | P5 | 044 | OdooAdapter 连接握手/模型权限检查 | 在授权 CE 测试实例报告可用模型与权限；无实例 BLOCKED | TODO |
| WDH-051 | P5 | 050 | 实体映射与 Odoo dry-run diff | 未审批实体绝不进入待写队列，匹配冲突待审 | TODO |
| WDH-052 | P5 | 051 | 审核后 outbox、重试、远端回读、防重复创建 | 断网/超时重试不产生重复 Odoo 草稿 | TODO |
| WDH-053 | P5 | 013 | n8n webhook 样例（可选）、签名与重放防护 | 无 n8n 仍工作，有 n8n 可在样例中安全触发 | TODO |
| WDH-060 | P6 | 035 | 安全审计、SBOM、依赖许可清单、上传攻击复测 | `make test-security` PASS，阻断高危缺陷 | TODO |
| WDH-061 | P6 | 052 | 加密备份、恢复、升级与回滚手册 | 干净主机恢复成功，DB 和媒体哈希核验 | TODO |
| WDH-062 | P6 | 033,061 | 压测与容量报告、资源监测、故障注入 | 指标测得实值，未达标写明 FAIL | TODO |
| WDH-063 | P6 | 003,062 | 客户端/导出工具真实兼容回归和缺口报告 | 只有实际验证过的组合标记 SUPPORTED；否则 BLOCKED | TODO |
| WDH-064 | P6 | 060,061,062,063 | Release Candidate 发布和交付文档 | 有版本 tag、SHA256、测试报告、部署/恢复/回滚指南和已知限制 | TODO |

## 阶段强制顺序与并行

- `WDH-003` 需要真实样本和用户授权，可以 `BLOCKED` 而不妨碍通用导入平台 P1–P5 的开发；但将阻断“多设备真实微信全量导出”的正式承诺。
- P1/P2 的数据正确性优先于 P3 UI；P4 AI 不可早于来源证据机制和 RBAC。
- P5 Odoo 真实写入需要测试实例；无授权实例时 dry-run 和 mock 测试可完成，但 `WDH-050` 不能标记真实联调 PASS。
- P6 可并行做安全与灾备，但最终发布需以 `ACCEPTANCE.md` 的 REQUIRED 状态为准。

## Codex 每个任务的标准循环

```
读取任务与依赖 -> 标记 IN_PROGRESS -> 写失败测试 -> 实现 -> lint/type/test
-> 实际启动服务 -> 生成测试证据 -> 更新文档 -> commit -> 标记 PASS
```

任何测试不能运行时写 `BLOCKED` 并说明环境、复现命令与影响范围，不允许写“应当通过”。

## 2026-11-17 首轮记录

WDH-000/001/002/010/011 PASS；WDH-003 `BLOCKED: REAL_SOURCE_VALIDATION`。代码提交和边界见 `docs/IMPLEMENTATION_STATUS.md`，实测命令、环境限制、日志/截图见 `docs/TEST_EVIDENCE.md`。P1 整体未完成，下一任务 WDH-012。
