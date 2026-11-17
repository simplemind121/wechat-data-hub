# WeChat Data Hub — 端到端研发规格与交付标准

> **项目代号**：WDH  
> **版本**：1.0.0  
> **日期**：2026-11-17  
> **定位**：私有部署、原始证据保全、可追溯 ETL、AI 辅助知识整理、可审核的 Odoo 19 CE 业务同步  
> **文档状态**：工程实现基线；不代表已完成实现、真实设备兼容或合规审查

## 0. 项目结论及不可妥协事项

建设一套 **WeChat Data Hub**，处理用户自行从 iPhone、Mac、Windows 合法取得的微信会话导出文件及媒体。系统允许跨设备/批次归档与复核去重，保留原始文件、来源证明与版本变化；提供网页浏览、全文/语义搜索、OCR/ASR、经证据约束的业务实体提取；经过人工审批后将客户、产品、报价、订单草稿写入 Odoo 19 CE。

**不做微信客户端的密钥提取、内存扫描、程序注入、绕过加密或未获授权的实时监控。** 微信官方原生加密备份只当恢复资产；除非能提供明确、合法、受支持的解析方案，否则不得承诺将其直接导入系统。源端解析通过适配器隔离，第三方工具的可靠性、版本支持、许可与隐私风险由 P0 实证确定。系统通用功能不得依赖某个非官方提取项目。

### 0.1 范围分层

- **必须完成（Core）**：单机登录、工作空间、批次导入、无损原件保管、结构化索引、按会话浏览、联系人映射、源追溯、去重候选、冲突人工复核、附件浏览、全文筛选、可导出 JSONL/CSV、任务状态、操作审计、加密备份/恢复、Docker 部署与运行手册。
- **必须完成且可禁用（Optional Modules）**：图片 OCR、语音 ASR、AI 摘要与业务实体抽取、向量检索、Odoo 草稿同步。各模块必须能以 feature flag 关闭，缺模型或密钥时不得影响核心功能。
- **阶段性/受现实条件限制**：iPhone、Mac、Windows 微信原生数据读取是否可行；第三方导出工具特定版本支持；视频转码、实时增量采集；企业微信官方存档独立适配。没有真实样本就不可承诺。
- **明确不做**：破解微信账号、读取他人设备、聊天发消息、自动发送订单/付款、自动覆盖真实业务资料、未经审批的外部 AI 出境处理、公共多租户 SaaS。

### 0.2 用户故事

| ID | 用户故事 | 必须可验证的结果 |
| --- | --- | --- |
| US-01 | 作为管理员，把多台设备导出的聊天文件安全导入 | 数据批次具有设备、账户、时间、校验码、来源工具和版本 |
| US-02 | 重复导入同一批记录 | 系统报告 already_ingested，没有新增规范消息 |
| US-03 | 查询某联系人跨设备的历史记录 | 时间线统一，来源可展开，且不会吞掉相似的真实消息 |
| US-04 | 某图片只在一台设备上存在 | 可从已保存的媒体对象检索到，并标注可用源 |
| US-05 | 搜索“八方 M620 报价” | 返回结果及可点击的原始消息/附件证据 |
| US-06 | 图片中包含价格、MOQ | OCR 后提供结构化候选与原文来源，允许修改和否决 |
| US-07 | 将审核后的客户/报价写入 Odoo | 先 dry-run 和人工审批；再次重试不重复创建 |
| US-08 | 硬盘故障后恢复 | 从加密备份恢复数据库和媒体，验证数目/哈希和检索 |

## 1. 系统环境、版本和边界

### 1.1 目标环境

- 开发：macOS（Apple Silicon/Intel）、Linux；Python 3.12、Node.js LTS（锁定项目支持版本）、Docker Compose v2。
- 生产：Ubuntu 24.04 LTS 或等效受支持 Linux；建议初始 4 vCPU / 8–16 GB 内存 + 独立加密存储。该配置只是起点，正式容量由性能测试决定。
- PostgreSQL：17；`pgvector` 用于可选语义检索。所有容器镜像在发布时锁定 digest；不要生产中使用浮动 `latest`。
- 微信客户端兼容性不写死：采集流程要记录 iOS/macOS/Windows、微信版本、导出器版本、样本时间范围和媒体覆盖率；每次升级做兼容回归。

### 1.2 技术组件

| 层 | 首选实现 | 备选与约束 |
| --- | --- | --- |
| HTTP API | FastAPI / Pydantic v2 | OpenAPI-first，错误统一 |
| 批处理 | Python / Polars / PyArrow | 大文件逐块，避免全量载入 RAM |
| ORM / 迁移 | SQLAlchemy 2 / Alembic | 不允许生产环境 `create_all` 替代迁移 |
| 数据库 | PostgreSQL 17、`pgvector` | 本地开发测试可用 PostgreSQL 容器 |
| 文件存储 | content-addressed 本地磁盘 | S3 兼容后端作为可选扩展；默认不外传 |
| 后台作业 | DB-backed durable jobs + 独立 Worker | 初版不强制 Redis；确保并发租约/重试 |
| 文字检索 | PostgreSQL + `pg_trgm` + 字段过滤 | 中日韩文本使用实测分词/规范化，不假设默认 FTS 足够 |
| AI | 可插拔本地 OCR/ASR/embedding/LLM Provider | 默认不调用云 API，不允许无证据补全 |
| 前端 | React / TypeScript / Vite | 响应式界面、审计与纠错 |
| 编排 | n8n（可选，非系统核心依赖） | 仅通过专用 API 与 Webhook 集成 |
| 业务连接 | Odoo Adapter | 真实 CE 实例必须做功能握手/权限测试 |

### 1.3 架构分层

```
[用户提供导出/备份副本]
         |
  [Adapter Registry]
   /    |        \
 JSONL JSON CSV / SQLite(只读且合法) / 外部工具结果
         |
 [Ingest API -> Quarantine -> Validation]
         |
 [Bronze: immutable raw bytes + manifests]
         |
 [Silver: canonical messages + observation provenance]
         |            \
 [Media CAS]           [Review Queue]
         |                |
 [OCR/ASR -> Evidence-backed entities]
         |
 [Gold: approved business entities]
     /           \
[Search/RAG]        [Odoo draft sync]
     \\             /
      [Web UI / API]
```

- **Bronze** 不可变。保存原始文件/行、原始哈希、来源标识，异常也保留。
- **Silver** 为规范化消息及结构化关系，支持重算（parser_version / normalization_version）。
- **Gold** 为人工批准的业务事实，必须有证据链；AI 候选与批准事实分离。

## 2. 多设备数据输入契约与可行性门槛（P0）

### 2.1 支持的输入模式

1. **JSONL v1（第一优先）**：一行一条消息；UTF-8；外加 `manifest.json`，标明导出设备、原始账号、工具版本和时间范围。支持可选相对媒体路径。
2. **JSON 数组或对象（第一优先）**：严格指定 adapter ID；不得仅靠文件后缀自动猜测危险结构。
3. **CSV（第一优先）**：显式字段映射；时间格式、时区、方向、联系人必须可配置。
4. **SQLite（第二优先）**：仅对用户提供的未加密、授权副本中已知/声明 schema 进行只读读取。不得尝试密码破解、逆向数据库加密。
5. **HTML/TXT（降级导入）**：可存原件并全文索引；缺失可靠消息级身份时只建立有限结构，`completeness=partial`。
6. **iOS Finder/微信官方加密备份**：归档与验证哈希可做；默认标为 `unparsed_backup`；不能声称可解析。

### 2.2 来源适配器接口

```
AdapterManifest:
  adapter_id: str
  adapter_version: semver
  input_formats: list[str]
  supported_exporters: list[str]
  required_fields: list[str]
  optional_fields: list[str]
  time_semantics: str
  identity_semantics: str
  supports_media: bool
  known_limitations: list[str]

Protocol SourceAdapter:
  probe(file, manifest) -> ProbeResult
  iter_records(file, manifest) -> Iterator[RawRecord]
  map_record(raw) -> CanonicalCandidate
  collect_media(raw) -> Iterator[MediaReference]
```

- `probe` 不得改变源文件，检查格式签名和 manifest；不识别时明确错误。
- `iter_records` 必须流式处理，单条解析失败计入 quarantine 并继续导入（达到配置阈值才中止）。
- `map_record` 输出字段 provenance（来自哪个原始 key）；空值不能猜填。
- 所有 adapter 版本锁定，在回归样本通过前不得替换旧版本。

### 2.3 真实数据兼容门槛

**P0 测试矩阵**：每台目标设备至少一份获授权样本，涵盖单聊、群聊、文本、图片、语音、视频、文件、表情、引用、撤回（若可得）、跨年份时间戳；记录客户端版本和工具 commit/release。P0 可与核心软件并行，但未完成不得签署“全量历史聊天交付”。

关键输出 `source_coverage_report.json`：会话数、消息数、类型分布、时间范围、附件引用数/实际可读取数/缺失数、无法解析数、来源一致性、已知不支持类型、可用版本、不能读取的备份列表。完整性是以**可观测源数据**为分母，不宣称微信服务器全量完备。

## 3. 核心数据库设计与不可变溯源

### 3.1 主键和关联原则

- 所有内部主键均为 UUIDv7 或数据库生成 UUID（实现时定一种并锁定），**不得**把微信昵称当主键。
- `workspaces` 隔离不同授权数据域。默认本地只有一个 owner，但数据库和 API 必须实现 workspace 过滤。
- `wechat_accounts` 区分登录微信身份；设备和批次必关联一个可确认的账号，无法确认则进入 `unknown_account` 审核状态。
- `contacts` 与 `contact_aliases`：保留微信 ID、历史昵称、备注、来源和时间；同名不自动合并。
- `conversations`：私聊、群聊或公众号等类型；群成员关系独立建表，支持变动。
- `ingest_batches` 记录源归档 manifest、SHA256、来源设备、adapter 与当前处理状态。
- `raw_records` 存原始字节定位符或合法 JSON 视图、行级哈希、原始 PK、错误字段。
- `messages` 是规范化消息；`message_observations` 存来自不同设备/批次的观测，形成多对一证据关系。
- `message_events` 记录撤回、编辑和状态变化，不丢原文。
- `attachments` 按 SHA256 去重物理文件；`message_attachments` 保留引用关系和可见状态。
- `entity_assertions` 保存 AI/规则的提取候选及证据；`review_tasks` 审核其冲突；`approved_entities` 只存获批准事实。
- `sync_outbox`、`odoo_bindings` 保存审批/投递/幂等/远端 ID；`audit_events` 保存操作审计。

详细参考见 `contracts/reference_schema.sql`，正式数据迁移以 Alembic 为准。

### 3.2 必须保留的消息字段

```
message_id              UUID (internal)
workspace_id            UUID
account_id              UUID
conversation_id         UUID
sender_contact_id       UUID nullable
sent_at_utc             timestamptz nullable
original_time_text      text nullable
original_time_precision enum: second/millisecond/minute/day/unknown
message_type            enum + original_type_code
body_text               text nullable
body_format             text/plain|xml|html|unknown
reply_to_message_id     UUID nullable
normalization_version   str
merge_status            verified|candidate|conflicted|single_source
created_at/updated_at   timestamps
```

消息没有发送时间或身份时仍可存入 quarantine / unresolved，不得伪造发送时间或发送者；时间戳采用 UTC 存储，同时保留来源时区假设/原始字符串以供纠错。

### 3.3 幂等与多设备去重

- 批次幂等：`(workspace_id, source_blob_sha256, adapter_id, adapter_version)` 唯一；重复提交返回已有批次 ID。
- 行级幂等：`(batch_id, source_record_locator)` 唯一；`source_record_locator` 必须对同一导出稳定（文件相对路径 + 行号/主键）；内容哈希做验真而不是单独主键。
- 强匹配：仅对经过 adapter 认证“同一账号+会话+原生服务端消息唯一 ID”做自动 canonical 合并；认证规范写入 adapter 文档并有交叉样本测试。
- 弱匹配：`account_id、conversation_id、sender_id、原始时间精度、类型、文本哈希、媒体哈希、方向` 组成候选；默认**不自动合并**，在 UI 审核；即使文本相同也可能是两条消息。
- 发生文本差异/撤回/媒体差异时建立 conflict 与 revisions，禁止覆写原内容。
- 如果消息引用目标未导入，保留源端引用 ID 和 unresolved 标志，支持后续补链接。
- 不允许删除任何 `raw_records` 以达到去重目的；规范层重建必须可复现。

### 3.4 附件和原始文件

- 物理内容采用 `sha256/<first2>/<fullhash>` 形式保存，内容不可变、同哈希只存一份。
- 索引保留 mime（通过安全嗅探检测）、大小、原始路径、原始扩展名、媒体类型、源设备、可访问状态。
- 已缺失/未下载的图片或语音仅建立引用元数据，`availability=missing`；不能显示虚假的缩略图。
- 媒体上传要阻止路径穿越、ZIP 炸弹、软链接逃逸、超大文件、伪装 MIME。文件预览只支持白名单 MIME，HTML/SVG 不以内联可执行形式提供。
- 生产部署的文件目录对非服务账户不可读；在静态资源层不可直接按磁盘路径猜测下载。

## 4. ETL 流程与作业状态机

### 4.1 导入流程

```
UPLOADED -> QUARANTINED -> VALIDATING -> ARCHIVED -> PARSING
         -> NORMALIZING -> LINKING -> INDEXING -> COMPLETED
                             |            |
                             +-> REVIEW_REQUIRED
失败: FAILED_RETRYABLE / FAILED_PERMANENT
取消: CANCELLED（保留原件和审计）
```

- 导入 API 立即返回 `202 + job_id`，处理在持久 worker 中完成，避免长 HTTP 超时。
- `ARCHIVED` 之前先计算哈希、校验文件清单及可用空间，再对内容寻址存储执行原子提交。
- 数据库每批/每块事务提交；工作失败重试只补处理尚未完成的记录（exactly-once side effects via idempotency，而非虚构 exactly-once 运行语义）。
- 每个 `job` 有 lease、heartbeat、attempts、next_retry_at、dead_letter 原因；重试退避，超过上限显式失败。
- 导入解析失败记录可导出；导入过程中同一批次展示处理总数、成功、跳过、冲突、失败和附件缺失。

### 4.2 标准化规则

1. **Unicode**：保留原始字节和规范化文本；搜索用 NFKC 派生字段；用户可看到原始 emoji/换行。
2. **时间**：识别秒/毫秒/微秒时间戳及字符串，按 adapter 时区配置解析；无时区不擅自按服务器时区解释。
3. **字段清洗**：空串/null/缺字段区分；XML/HTML 作为数据文本，不允许执行；原始表情 code 不得删除。
4. **联系人映射**：微信 ID 优先；昵称/备注仅用于候选，人工确认跨设备别名。
5. **媒体链接**：相对路径按导出根目录解析并检查 containment；重复附件依哈希复用，保留全部消息引用。
6. **消息类型**：text/image/video/audio/file/sticker/system/quote/location/unknown；unknown 保留 `original_type_code` 和 payload。
7. **数据质量**：每批产生 schema 通过率、源消息覆盖、无法解析字段、时间精度缺失、附件缺失、冲突数；质量指标从实际源数据生成。

### 4.3 Parser 升级策略

每次调整 `normalization_version`、adapter、实体抽取 Prompt 或 schema，保留重处理能力：可从 Bronze 重放进入新派生表，差异报告经人工批准后切换读取版本。生产数据表大规模重建前生成并验证备份，不通过“清空重导”解决迁移。

## 5. 后端 API 契约与权限

API 根路径 `/api/v1`；JSON 为默认，导入用 multipart；分页 `limit <= 100` + cursor；错误统一返回 `code/message/request_id/details`，不向用户暴露栈、磁盘路径、密钥。

| Method | Path | 功能 | 权限 |
| --- | --- | --- | --- |
| POST | `/auth/login` | 本地账户登录（HttpOnly cookie，CSRF） | 公开但限速 |
| POST | `/auth/logout` | 销毁会话 | 登录 |
| GET | `/me` | 用户、权限、workspace | 登录 |
| POST | `/imports` | 上传 manifest+导出文件，启动导入 | admin |
| GET | `/imports` | 批次列表/状态 | reviewer+ |
| GET | `/imports/{id}/coverage` | 来源覆盖与缺失报告 | reviewer+ |
| GET | `/imports/{id}/errors` | 可下载脱敏解析错误 | admin |
| POST | `/imports/{id}/retry` | 失败批次重试，幂等 | admin |
| GET | `/conversations` | 会话列表和筛选 | reader+ |
| GET | `/conversations/{id}/messages` | 游标分页消息时间线 | reader+ |
| GET | `/messages/{id}` | 规范消息+全部 source observations | reader+ |
| GET | `/contacts` | 联系人/别名 | reader+ |
| GET | `/attachments/{id}/download` | 授权附件流 | reader+ |
| GET | `/search` | 全文和过滤搜索 | reader+ |
| POST | `/reviews/{id}/resolve` | 消息/身份/实体冲突确认 | reviewer+ |
| POST | `/process/{kind}` | OCR/ASR/embedding/LLM 作业 | reviewer+ |
| GET | `/jobs/{id}` | 作业状态 | reviewer+ |
| GET | `/entities` | 候选/审核通过实体 | reader+ |
| POST | `/entities/{id}/approve` | 审核实体，保存证据 | reviewer+ |
| POST | `/integrations/odoo/test` | 测试权限、模型可用性 | admin |
| POST | `/integrations/odoo/dry-run` | 模拟待同步数据 | reviewer+ |
| POST | `/integrations/odoo/sync` | 审批后实际投递草稿 | admin |
| GET | `/audit` | 审计日志筛选 | admin |
| GET | `/exports/messages` | 按权限导出 JSONL/CSV | admin |
| GET | `/health/live`、`/health/ready` | 活性/依赖就绪 | 基础健康不泄露隐私 |

`contracts/openapi.yaml` 是起点，Codex 实现时必须补齐字段、错误枚举和权限规则，并生成 contract tests 以防前后端漂移。

### 5.1 RBAC 与隐私域

- `admin`：数据接入、配置、用户管理、外部同步、审计、备份。
- `reviewer`：浏览指定 workspace、解决去重/实体审核、执行 AI 任务；不能更改保密配置或写生产 Odoo。
- `reader`：仅访问获得权限的会话和搜索，不得批量导出原始数据。
- API 所有 SQL 查询必须按 workspace 过滤；附件、搜索、引用跳转和后台任务结果都执行同等授权校验。
- 业务数据域默认 `private`；只有管理员可将会话/联系人标为 `business_approved`，随后才允许 AI 业务提取或向 Odoo 输出。

## 6. 前端信息架构和交互验收

**导航**：概览 / 数据源与导入 / 会话与联系人 / 搜索 / 审核队列 / 业务实体 / AI 作业 / Odoo 集成 / 审计与备份 / 设置。

1. **概览**：消息、会话、媒体、来源设备数（实际统计）；最近导入、异常、待审核、磁盘容量和最近备份时间。
2. **导入向导**：选择 adapter、账户、设备、时区、导出清单；上传前检查格式和空间；展示解析能力、缺字段和隐私提示。
3. **会话浏览**：左侧会话/联系人筛选，中间时间线，右侧原始来源/附件/字段追溯；消息按时间分页；同一消息展示多来源观测数量。
4. **搜索**：时间范围、账户、设备、对话、消息类型、附件、关键字；语义检索未启用时隐藏，不显示空结果欺骗。
5. **冲突审核**：并排展示候选消息的时间、内容、来源及哈希，支持合并/不合并/暂缓；所有操作有 reason、actor、timestamp。
6. **业务提取**：候选报价/产品/客户卡片包含精确字段、原始证据、模型/规则版本；可编辑后批准或拒绝。
7. **Odoo**：连接状态、目标数据库/实例、dry-run 差异、可撤销/不可撤销动作提示、人工审批提交、重试和历史。
8. **管理与隐私**：角色、会话标记、AI 出境开关、备份状态、加密提示、清理申请、导出审计。

UI 必须可用键盘导航，空状态/错误/加载状态可见；对大数据使用服务端分页/虚拟滚动；浏览器控制台不得记录真实会话内容或凭据。

## 7. OCR、ASR、AI 与 RAG

### 7.1 模块与默认行为

- OCR：本地 PaddleOCR 或等效本地模型，优先识别图片/文档；保留 bbox、识别文字、模型版本、原图 SHA；失败不丢原件。
- ASR：本地 faster-whisper（若媒体已合法解码成支持格式），保留语言、时间片、模型版本和不确定状态；不具备合法解码能力时 `unsupported_codec` 而非虚构转录。
- LLM：默认**关闭**。接入本地 provider 后对已允许的业务会话做 JSON Schema 严格抽取。云 API 需要管理员显式打开并逐类授权数据范围，记录提供方、调用时间、数据类别。
- 向量化：按对话与来源归属切片，必须记录 message_id 范围、embedding model/version、处理版本。更新来源后只重新生成受影响 chunk。
- RAG：先做权限与时间范围过滤，再检索，最后生成带消息证据引用的回答；没有证据就明确无法确定。

### 7.2 业务实体抽取规则

`entity_assertions` 支持 `customer`, `supplier`, `product`, `quotation`, `purchase_intent`, `order_candidate`, `task`。所有候选字段需保留：

- `value_raw`、`value_normalized`、单位/币种、`evidence_message_ids`、`source_span`、`extractor_version`、`confidence_raw`（只当算法评分，不当事实可靠度）、`review_status`。
- 交货日期如“下月底”，只有能明确定位发送时间和时区时才可计算；否则保留原词，不生成假日期。
- 不允许根据聊天关键词自动推断支付已完成、订单已确认、真实姓名或唯一联系人身份。
- 只有 `approved_entities` 可以进入对外同步队列。

## 8. Odoo 19 CE 集成规范

### 8.1 能力验证

Odoo 19.0 官方文档定义了 JSON-2 外部 API（通常为 `/json/2/<model>/<method>`）。具体到用户的 **自托管 Community Edition、安装模块、权限设置**，必须用测试实例执行 API 权限握手和模型可用性探测，不能仅凭文档假设所有模型开放。参见 `docs/SOURCES.md`。

`OdooAdapter` 要实现 `test_connection`, `discover_models`, `lookup_partner`, `prepare_draft`, `dry_run`, `apply_approved`, `read_back`, `check_idempotency`。认证 token 只放后端 secret store；TLS 验证不可关闭；禁止直接操作 Odoo 数据库。

### 8.2 映射和审批

| 已审批实体 | 目标 Odoo 模型 | 策略 |
| --- | --- | --- |
| 客户/供应商 | `res.partner` | 先做匹配候选，人工确认身份，再创建/关联 |
| 产品 | `product.template` | 同 SKU/型号冲突先复核，不能直接覆盖价格 |
| 采购询价 | `purchase.order` | 仅创建 RFQ 草稿，不批准采购或发付款指令 |
| 销售意向 | `crm.lead`（模块存在时） | 只创建线索，缺模块则报告 unavailable |
| 销售草稿 | `sale.order` | 只创建 quotation 草稿，不确认订单 |
| 附件 | `ir.attachment` | 经授权选择性上传，不能整库灌入 |

- 默认 `dry_run=true`；只有 admin 选择、审核并二次确认才写入。
- 所有外部动作使用 `idempotency_key = workspace + approved_entity_uuid + target_model + action_version`，本地 outbox 记录完整状态、远端 ID、请求指纹和回读结果。
- API 超时后先按绑定及唯一业务键检查远端是否已成功写入，不盲目重复创建。
- 外部写入失败可重试；已创建的真实 Odoo 记录不实施危险的自动删除式回滚，提供人工补偿说明。

## 9. 安全、合规、数据保留

### 9.1 强制安全项

- **隐私优先**：仅导入有权处理的数据；支持逐会话排除、业务域白名单、匿名化导出、删除请求与保留策略（与不可变证据保管规则协调，删除时按审批策略执行加密密钥销毁/安全擦除、审计留痕）。
- **密钥管理**：生产 secret 不写代码和日志、不进 Git，文件权限 0600；默认不提供收集微信加密密钥的功能。
- **网络**：本地部署仅绑定 `127.0.0.1`；远程部署使用 VPN/Zero Trust 或 TLS 反向代理 + MFA；数据库和对象存储不开公网。
- **授权**：workspace 行级隔离、附件鉴权、角色边界、session CSRF 防护、登录限速、会话失效。
- **上传防护**：文件数量/大小/解压比限制、Zip Slip、symlink、SQL 文件/CSV 公式注入、XML 外部实体、XSS/HTML 注入、不可信文件预览；对可执行文件禁止在线预览。
- **运行**：Docker 非 root、只读根文件系统（可行组件）、cap drop、有限资源、健康检查、独立数据卷；不挂宿主 Docker socket。
- **审计**：登录、导出、删除、源数据访问、审批、AI 外发开关、Odoo 写入都记录主体/时间/对象/结果，不存消息内容或秘钥。
- **外部依赖**：输出 SBOM、锁定依赖版本、检查许可证和已知漏洞；高危问题需修复或签署明确风险接受。

### 9.2 备份与灾备

- 三套资产分别备份：Postgres、不可变原件/媒体、配置与密钥恢复说明。不能只备份数据库。
- 使用加密备份工具（如 restic/borg），备份目标与运行机隔离；实践 3-2-1 原则。
- 每日数据库+元数据增量、每周全量/一致性校验为默认建议，最终按实际数据量配置。
- **恢复演练 REQUIRED**：在干净环境恢复数据库、媒体、账户和检索；核对对象哈希、消息数、附件可访问性与审计完整性。
- 实测记录 RPO/RTO，不得在没有灾备演练时声称达到了某个恢复时间。

## 10. 非功能指标（验收目标，不是既成事实）

| 维度 | 验收目标 | 测量方式 |
| --- | --- | --- |
| 幂等 | 同一导入文件重复执行 3 次，不新增规范消息/附件物理副本 | E2E + SQL count/hash |
| 去重安全 | 不合并两个相似但实际独立的消息 | 边界 fixture + 审核日志 |
| 大文件 | 10 万文本消息合成样本成功导入，峰值内存受控 | benchmark + `docker stats` |
| 搜索 | 本地 10 万样本中文关键字 P95 < 2 秒（指定硬件） | 固定测试集和测量脚本 |
| 可追溯 | 已索引消息 100% 至少有一条 source observation，获批实体 100% 可追溯 evidence | SQL invariant test |
| 媒体完整性 | 成功归档附件的 SHA-256 校验 100% 通过 | 哈希巡检 |
| 权限 | reader 无法读未授权 workspace/原始下载接口 | API security test |
| 默认隐私 | 所有外部 AI/云对象存储/Odoo 未配置时零外部请求 | egress mock / 网络抓包测试 |
| 备份 | 清洁环境恢复成功，核对记录数和媒体哈希 | DR 演练记录 |
| 兼容性 | 仅宣称 P0 实测通过的客户端/导出器版本 | 真机矩阵 + 样本证据 |

目标不通过时明确标记 FAIL 或给出量化风险；严禁悄悄放宽门槛。有关性能硬件和压测样本必须记入证据报告。

## 11. 仓库与部署结构

```
wechat-data-hub/
├── AGENTS.md
├── README.md
├── SPEC.md / TASKS.md / ACCEPTANCE.md
├── apps/
│   ├── api/                  # FastAPI REST & auth
│   ├── worker/               # durable ETL, OCR/ASR/LLM queue
│   └── web/                  # React/TypeScript
├── packages/
│   ├── domain/               # Pydantic domain contracts
│   ├── adapters/             # file-based input adapters
│   ├── storage/              # raw CAS, media CAS, backup interfaces
│   ├── search/               # exact/keyword/semantic
│   └── integrations/         # Odoo, n8n webhooks
├── migrations/               # Alembic, schema and seed
├── contracts/                # OpenAPI, schema reference
├── tests/
│   ├── fixtures/             # synthetic only
│   ├── unit/
│   ├── integration/
│   ├── e2e/
│   ├── security/
│   └── performance/
├── infra/
│   ├── compose/
│   ├── reverse-proxy/
│   └── backup/
├── docs/
│   ├── ADR/
│   ├── IMPLEMENTATION_STATUS.md
│   ├── TEST_EVIDENCE.md
│   ├── RUNBOOK.md
│   ├── RECOVERY.md
│   └── RELEASE_NOTES.md
├── scripts/
├── examples/
├── .env.example
├── Makefile
└── compose.yaml
```

### 11.1 开发命令契约（Codex 必须实现）

```
make bootstrap          # 检查并安装开发依赖，生成本地非敏感配置
make up                 # 本地受控服务启动
make migrate            # 执行 Alembic upgrade head
make seed-demo          # 导入合成示例，不使用真实聊天
make lint               # Python+TS 静态检查
make test               # 所有 unit/integration（注明耗时/依赖）
make test-e2e           # 浏览器 E2E
make test-security      # 边界/访问控制/文件安全
make benchmark          # 固定 100k 文本样本性能测量
make backup             # 加密备份示例（需配置合法密钥）
make restore-check      # 在隔离测试环境验证恢复
make down               # 停止服务，但不删除卷
```

`make down` 不得隐式执行 `-v`。操作文档需提供手工的、明确会销毁数据的命令及确认机制。

### 11.2 本地与生产差异

- 本地：单机 Compose，API/前端端口绑定 127.0.0.1，示例用户首次启动必须安全设置密码；不提供硬编码默认密码。
- 生产：分离反向代理和业务网络；显式允许入口；定期证书更新；可接 NAS；备份独立存储；敏感日志脱敏和审计保留。
- 数据目录：`raw/`、`media/`、`exports/`、`quarantine/`、`backup-staging/`；通过绝对路径配置，容器只映射需要的卷。
- `compose.yaml` 必须有健康检查、restart policy、资源限制建议和升级回滚文档；数据迁移升级前必须校验备份。

## 12. 实施顺序、依赖与正式交付

详细任务 ID 和验收命令见 `TASKS.md` 与 `ACCEPTANCE.md`。高层顺序：

1. P0：源格式研究、授权样本兼容矩阵、项目初始化、基线 CI。
2. P1：Bronze 原件/媒体、adapter、批次幂等、quarantine 和状态机。
3. P2：SQL schema、canonical messages、身份映射、去重候选与冲突审核。
4. P3：Web UI、关键词检索、追溯展示、安全导出、审计、RBAC。
5. P4：可选 OCR/ASR/向量/RAG、业务实体候选与人工批准。
6. P5：Odoo CE 联调、dry-run、幂等 outbox、可选 n8n webhook。
7. P6：安全与性能、灾备演练、实机回归、部署升级与交付包。

### 12.1 交付定义 Definition of Done

交付包至少包含：

- 可复现的全部源码与锁定依赖，许可证及第三方依赖清单；
- Docker Compose / `.env.example` / 初始化与管理员创建说明；
- Alembic migration、数据库 ERD、OpenAPI 文档；
- 合成演示数据、自动化测试、CI 配置、实际测试报告；
- 源设备兼容矩阵、缺口列表和真实数据验证结果（如未提供样本则明确 BLOCKED）；
- 运行手册、备份恢复手册、升级/回滚手册、安全基线；
- 发布 tag、变更日志、制品 SHA256、已知问题和未来兼容风险。

**只有 Demo 并非交付，只有 Docker 启动也并非交付。** 验收必须在全新环境跑通一条端到端链路：合成数据导入→原件归档→消息/附件展示→去重审核→搜索→实体审核→Odoo dry-run（测试实例有条件时再实写草稿）→备份恢复，并在报告里列明 PASS/FAIL/BLOCKED。

## 13. 项目决策与待确认条件

| 决策 | 默认选择 | 重新评估条件 |
| --- | --- | --- |
| 运行形式 | 私有、单所有者、多角色 | 实际多用户 SaaS 需要新的安全架构 |
| 外部 AI | 默认关闭、优先本地 | 授权后才启用云端 provider |
| 数据库 | PostgreSQL 17 | 性能测试要求或数据库支持变动 |
| 首个导入格式 | JSONL、JSON、CSV | 实际可用导出样本提供更多格式 |
| Odoo | 先 dry-run，人工批准草稿 | CE 实例验证通过且业务确认 |
| native backup | 官方备份只作保底恢复 | 获得合法、受支持且稳定的解读能力 |
| 第三方工具源码 | 不直接捆绑/复制 | 单独许可、风险和维护评审通过 |

**等待真实数据时仍可开发通用平台**，但报告必须指出：本项目不能保证一份只存在于某设备、未被成功导出的微信历史消息能被完整恢复。可追溯 ≠ 数据源完整，不能将一次导入成功直接表述为“微信聊天全量无损导出成功”。
