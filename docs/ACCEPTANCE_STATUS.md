# 验收逐项状态 · 0.2.0

日期：2026-11-17。以原 ACCEPTANCE.md 为基线，PASS只限表内实测范围。全部测试输入为合成。正式RC门槛未通过，不将本地可用核心版冒充全规格生产交付。

REQUIRED: PARTIAL 8, PASS 24, TODO 4。
CONDITIONAL: BLOCKED 5, UNSUPPORTED 1。

| 项目 | 级别 | 状态 | 范围/证据说明 |
| --- | --- | --- | --- |
| AC-001 | REQUIRED | PARTIAL | 离线镜像新卷启动/seed通过；新主机源码完整bootstrap构建未重验 |
| AC-002 | REQUIRED | PASS | 77 Python、3 Vitest、3源码E2E、3成品E2E、27安全子集；lint通过 |
| AC-003 | REQUIRED | PARTIAL | 基础digest/成品内容ID锁定、配置不入包；完整secret/OS供应链审计未完成 |
| AC-004 | REQUIRED | PASS | 已实现OpenAPI生成/漂移与权限/分页集成；目标契约中的未实现模块另列 |
| AC-101 | REQUIRED | PASS | 三种格式、原件SHA与可用媒体测试 |
| AC-102 | REQUIRED | PASS | 三次同批次幂等、重复文本独立保留 |
| AC-103 | REQUIRED | PASS | 损坏JSONL行隔离，其余行保存，原字节保留 |
| AC-104 | REQUIRED | PASS | manifest/声明来源/时区/字段映射与来源详情 |
| AC-105 | REQUIRED | PASS | 70.18MB，100000条，RSS293648KiB |
| AC-106 | CONDITIONAL | BLOCKED | 未提供获授权的真实设备/导出器样本 |
| AC-107 | CONDITIONAL | UNSUPPORTED | 不解析微信官方加密原生备份 |
| AC-201 | REQUIRED | PASS | 仅经认证的synthetic-v1命名空间实测跨设备多观测 |
| AC-202 | REQUIRED | PASS | 相同时间和文字的两条收到保留；合成反例 |
| AC-203 | REQUIRED | PASS | 弱匹配复核，同昵称身份审批前不自动关联 |
| AC-204 | REQUIRED | PARTIAL | 原件/冲突/事件模型已实现；撤回编辑组合回归尚不完整 |
| AC-205 | REQUIRED | PASS | UTC/秒毫微秒、DST歧义拒绝、缺日期、Unicode/emoji测试 |
| AC-206 | REQUIRED | PASS | 附件存在/缺失、授权下载、实际PNG解码 |
| AC-207 | REQUIRED | PASS | 来源观测约束、报价每字段证据与拒绝虚构更改 |
| AC-301 | REQUIRED | PASS | 中文/全角型号、日期/设备/类型等筛选API及网页 |
| AC-302 | REQUIRED | PASS | 服务端游标分页、真实容器浏览 |
| AC-303 | REQUIRED | PASS | merge/reject/defer集成和审核审计，网页reject流程 |
| AC-304 | REQUIRED | PASS | 角色与workspace负向测试 |
| AC-305 | REQUIRED | PASS | 授权附件下载/路径与ZIP攻击测试 |
| AC-306 | REQUIRED | PASS | admin导出、审计、CSV公式防护 |
| AC-401 | REQUIRED | PASS | 所有提供方默认关闭，核心及本地规则运行 |
| AC-402 | REQUIRED | TODO | OCR provider未实现 |
| AC-403 | REQUIRED | TODO | ASR provider未实现 |
| AC-404 | REQUIRED | TODO | embedding/RAG未实现 |
| AC-405 | REQUIRED | PARTIAL | 报价规则候选schema/证据/审批通过；完整客户产品LLM模块未实现 |
| AC-406 | CONDITIONAL | BLOCKED | 无获授权云提供方，默认零外部调用 |
| AC-501 | REQUIRED | PASS | 模块禁用核心可用，本地dry-run明确remote_writes=false |
| AC-502 | REQUIRED | PARTIAL | 本地dry-run拒绝未批准/私人实体；真实outbox未实现 |
| AC-503 | REQUIRED | TODO | 真实同步outbox/超时重试未实现 |
| AC-504 | CONDITIONAL | BLOCKED | 无获授权Odoo19CE实例 |
| AC-505 | CONDITIONAL | BLOCKED | 没有执行远端写入 |
| AC-601 | REQUIRED | PASS | 上传攻击、MIME/XSS边界、CSV、登录限制、CSRF安全子集27通过 |
| AC-602 | REQUIRED | PASS | 默认只绑定127.0.0.1，PG无宿主端口 |
| AC-603 | REQUIRED | PASS | PG100k关键词30次P95 0.299391s；进程内HTTP计时 |
| AC-604 | REQUIRED | PARTIAL | 新PG/新原件目标恢复及哈希/旧会话/媒体通过；不同物理主机/生产计划未演练 |
| AC-605 | REQUIRED | PARTIAL | 运行依赖审计0；SBOM/许可有据，开发picomatch high及OS审计待完 |
| AC-606 | REQUIRED | PARTIAL | 本地核心包有SHA256、镜像ID、说明与恢复手册；正式RC/tag未发布 |
| AC-607 | CONDITIONAL | BLOCKED | 真实微信设备兼容覆盖未测试 |

具体命令/日志见 TEST_EVIDENCE.md。源码关键提交c37a470/8cef071；镜像内容ID见 ../images.lock；交付快照完整commit与包hash见随包 DELIVERY_MANIFEST.json / 校验文件。

Actual source devices verified: 0。Odoo CE test result: BLOCKED。Security unresolved HIGH/CRITICAL: 开发picomatch根因1项HIGH（5个派生报告），运行依赖审计未检出；完整OS审计未完成。Release owner signoff: 未进行正式发布签署。
