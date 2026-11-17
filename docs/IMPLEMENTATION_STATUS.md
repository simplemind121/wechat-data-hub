# Implementation Status

日期：2026-11-17。版本：0.1.0 开发切片。**P0 工程基础、P1 Bronze/CAS 已实现；P1 整体尚未完成，非 MVP / RC / 生产交付。**

| 任务 | 进度 | Commit | 备注 |
| --- | --- | --- | --- |
| WDH-000 | PASS | `104633b`, `e304738` | 单仓库、锁文件、Makefile、CI、API/Web、Compose；bootstrap/lint/test、浏览器与容器启动已通过，见测试证据中的环境适配说明 |
| WDH-001 | PASS | `5796a63` | `docs/ADR/001-boundaries.md`，三个上游固定提交 README/许可只读核对；商业许可冲突和未找到许可项已明确记录 |
| WDH-002 | PASS | `26ecdb2` | 工厂、`tests/fixtures/generated-v1`；两设备、两会话、35 类边界预期；重复生成树哈希相同 |
| WDH-003 | BLOCKED | `5796a63` | `REAL_SOURCE_VALIDATION`，无真实导出；来源报告见 `docs/source_coverage_report.json` |
| WDH-010 | PASS | `104633b` | 初始 Alembic 迁移；PostgreSQL 17.6 重复 upgrade/check，复合外键、批次幂等、行定位唯一性 |
| WDH-011 | PASS | `de1d143` | 原字节 CAS 库；并发只保存一份、SHA-256、0400、原子提交、超限清理、损坏不覆盖、路径/ZIP 检查 |
| WDH-012 至 WDH-064（除上列项） | TODO | — | 适配器、持久任务、上传、Silver、RBAC、业务 UI、AI、Odoo、灾备与正式验收尚未实现 |

WDH-032 未领取。当前 Web 是 WDH-000 的真实健康状态和开发说明外壳，不是已通过业务 E2E 的消息浏览界面。当前公开 API 仅 live/ready；目标 OpenAPI 和已实现契约分别保存。

本轮只验证 CAS 库和 ZIP 元数据检查，不具备完整上传/解压/MIME 预览安全链路。文件入库关联、导入覆盖报告与媒体引用属于后续任务。35 类合成预期不等于35项业务功能已实现。

CI 配置已生成并通过本地等效命令验证；未连接远端仓库，未声称 GitHub Actions 已执行。没有版本 tag、镜像推送、外部数据写入或生产发布。

下一任务：WDH-012，版本化 JSONL/JSON/CSV adapter registry、流式读取、字段映射和解析报告；随后 WDH-013/014，之后才进入 P2。
