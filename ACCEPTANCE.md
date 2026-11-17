# ACCEPTANCE — 交付验收与 QA 证据清单

本文件定义 **REQUIRED** / **CONDITIONAL**：`REQUIRED` 对通用平台正式交付不可省略；`CONDITIONAL` 仅在指定外部系统/真实数据有授权访问时要求执行，但未执行不得宣传相应能力。

## 1. 入口、运行与可复现性

| ID | 级别 | 场景/验收标准 | 证据 |
| --- | --- | --- | --- |
| AC-001 | REQUIRED | 干净仓库执行 `make bootstrap && make up && make migrate && make seed-demo` 后 API/Web 正常 | CI 与终端日志、健康状态 |
| AC-002 | REQUIRED | `make lint && make test && make test-e2e && make test-security` 成功 | 具体命令/版本/通过数 |
| AC-003 | REQUIRED | 全部容器镜像锁版本，非敏感 `.env.example`，没有提交密钥 | secret scan + 依赖清单 |
| AC-004 | REQUIRED | OpenAPI 与 API 行为、字段、错误码、权限、分页一致 | contract tests |

## 2. 导入与数据原真性

| ID | 级别 | 场景/验收标准 | 证据 |
| --- | --- | --- | --- |
| AC-101 | REQUIRED | JSONL/JSON/CSV 合成源导入、保留原始文件字节和 SHA256 | manifest + hash comparison |
| AC-102 | REQUIRED | 同一文件导入 3 次，canonical 消息、物理附件数量不增加 | SQL count before/after |
| AC-103 | REQUIRED | 解析失败部分进 quarantine；其他有效记录仍保存 | 错误样本与覆盖报告 |
| AC-104 | REQUIRED | 设备/账号/工具/版本/时区/覆盖范围均可追溯；缺字段不伪造 | API + DB check |
| AC-105 | REQUIRED | 50MB+ 文件以流式方式导入（内存可观测，至少 10 万条合成样本） | memory profile |
| AC-106 | CONDITIONAL | iPhone/Mac/Windows 的实际导出样本和媒体类型矩阵通过 | 真实来源批准/匿名指标报告 |
| AC-107 | CONDITIONAL | 原生加密备份可解析，仅在合法可靠解析器实证支持时 PASS | 工具版本、测试结果；否则 UNSUPPORTED |

## 3. 去重、时间和证据链

| ID | 级别 | 场景/验收标准 | 证据 |
| --- | --- | --- | --- |
| AC-201 | REQUIRED | 同一 server ID（经 adapter 确认命名空间）跨设备合并成单规范消息、多来源观测 | SQL + UI 来源展开 |
| AC-202 | REQUIRED | 同一会话、同时间、同文本的两条真实消息不自动合并 | adversarial fixture |
| AC-203 | REQUIRED | 无唯一标识的相似记录进入复核，不因昵称相同自动合并 | review queue |
| AC-204 | REQUIRED | 撤回/编辑保留原始文本与事件链，不能覆盖 Bronze | checksum + revision test |
| AC-205 | REQUIRED | 时区、夏令时、秒/毫秒、缺日期、中文/emoji 可往返无损表示 | unit/integration tests |
| AC-206 | REQUIRED | 图片仅一端有文件时仍可引用；文件丢失时标缺失并显示源 | API / UI test |
| AC-207 | REQUIRED | 所有 indexed messages 有 source observation；approved entities 有 evidence ID | SQL invariants |

## 4. 搜索、前端与审核

| ID | 级别 | 场景/验收标准 | 证据 |
| --- | --- | --- | --- |
| AC-301 | REQUIRED | 中文关键词、型号词、时间/群聊/联系人/类型多条件筛选正确 | E2E fixture |
| AC-302 | REQUIRED | 大量消息分页可用，界面不一次性加载所有历史 | browser/network trace |
| AC-303 | REQUIRED | 审核 merge/reject/defer 可操作，审计可回溯 | E2E + audit event |
| AC-304 | REQUIRED | admin/reviewer/reader 权限按接口生效，workspace 越权返回拒绝 | security test |
| AC-305 | REQUIRED | 附件下载有身份/权限校验，不能用路径遍历取得任意文件 | security test |
| AC-306 | REQUIRED | 导出受 admin 权限控制、标记审计，CSV 公式注入已防护 | security test |

## 5. AI、OCR、ASR、业务实体

| ID | 级别 | 场景/验收标准 | 证据 |
| --- | --- | --- | --- |
| AC-401 | REQUIRED | 相关开关全关时平台完整可用且不会发起外部 AI 请求 | network mock / trace |
| AC-402 | REQUIRED | OCR 结果有来源图片、识别位置/文字、模型版本、失败状态 | fixture + DB |
| AC-403 | REQUIRED | ASR 对支持的本地音频生成带时间段文本，对不支持格式明确报错 | offline fixture |
| AC-404 | REQUIRED | RAG/语义搜索仅访问有权限的数据，回答带原消息引用，无证据时说明不确定 | e2e + negative test |
| AC-405 | REQUIRED | 报价/客户/产品候选符合 JSON Schema，变更可审计，未审批不可同步 | validation + UI test |
| AC-406 | CONDITIONAL | 云模型仅在显式授权条件下处理允许范围，无授权零调用 | provider test |

## 6. Odoo、外部系统与幂等

| ID | 级别 | 场景/验收标准 | 证据 |
| --- | --- | --- | --- |
| AC-501 | REQUIRED | Odoo 模块不开启时系统正常运行；dry-run 返回差异不写外部数据 | fake Odoo adapter |
| AC-502 | REQUIRED | 未通过业务审批的联系人/订单不得进入 outbox | negative test |
| AC-503 | REQUIRED | 人工审批后模拟 Odoo API 超时，重试不生成重复草稿 | mock + outbox invariant |
| AC-504 | CONDITIONAL | Odoo 19 CE 测试实例真实连接、模型权限检查与回读成功 | 脱敏远端 ID 与版本、操作记录 |
| AC-505 | CONDITIONAL | 实写仅限 RFQ/报价/线索草稿，未触发确认/付款动作 | 测试实例记录 |

## 7. 安全、性能、备份与发布

| ID | 级别 | 场景/验收标准 | 证据 |
| --- | --- | --- | --- |
| AC-601 | REQUIRED | 上传 Zip Slip、symlink、过大压缩比、恶意 MIME、XSS、CSV 公式、账号爆破、CSRF 已覆盖 | `make test-security` |
| AC-602 | REQUIRED | 默认所有服务仅 loopback，不暴露 PostgreSQL/Object Store 到公网 | Compose config + network test |
| AC-603 | REQUIRED | 10 万合成文本消息数据集关键字搜索 P95 < 2s（记录硬件） | benchmark raw results |
| AC-604 | REQUIRED | 完整加密备份并在干净环境恢复 DB/媒体/配置，哈希校验通过 | DR exercise report |
| AC-605 | REQUIRED | SBOM、许可证/依赖漏洞评估、安全日志脱敏、无未处置高危问题 | 扫描报告 |
| AC-606 | REQUIRED | 发布 tag、SHA256、镜像 digest、Release Notes、升级和回滚指南 | 发布物清单 |
| AC-607 | CONDITIONAL | 真实设备版兼容验证与范围声明 | P0 矩阵报告 |

## 8. 必须具备的合成测试数据

`tests/fixtures` 至少包含：

1. 两个设备对同一条消息导出不同本地 ID，但相同**已验证语义**的原生服务端 ID。
2. 同一人一分钟内重复发送两次“收到”（不能误去重）。
3. 群成员改昵称、同昵称不同微信 ID、空微信 ID。
4. 北京时间、UTC、含夏令时区的时间戳、毫秒/秒混淆与缺时间字段。
5. 中文、emoji、组合字符、CDATA/XML、HTML、特殊字符、超长文本。
6. 撤回/编辑、多条引用、引用目标缺失。
7. 一台设备有附件另一台无、两个不同文件同名、内容相同不同路径、断链媒体。
8. 只有 HTML/TXT 的降级导入、字段不齐 CSV、损坏 JSONL 行。
9. 大文件、压缩炸弹、`../` 路径、绝对路径、符号链接、XSS、CSV 公式注入。
10. Odoo 业务实体：未获批、供应商同名、MOQ/币种冲突、超时后的幂等重试。

## 9. 发布签字表（Codex 必须输出）

```
Release version:
Git commit:
Docker image digest:
Required tests PASS/FAIL count:
Conditional tests PASS/BLOCKED count:
Actual source devices verified:
Known unsupported WeChat versions:
Data quality coverage evidence:
Security unresolved HIGH/CRITICAL:
Backup restore exercise:
Odoo CE test result:
Release owner signoff:
```

正式验收必须标记未通过项和责任人。不能使用“功能基本完成”“测试应该没问题”之类模糊结论。
