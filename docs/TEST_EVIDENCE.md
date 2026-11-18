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

# 0.2.0 本地核心成品验收 · 2026-11-17

以下是新的业务应用证据；上方0.1.0历史记录不代表当前能力。核心源码 `c37a470`，补链/审核修复 `8cef071`。所有输入为合成数据，真实微信设备和真实 Odoo 实例仍未测试。

## 最终验证

| 命令/场景 | 实际结果 | 证据 |
| --- | --- | --- |
| `TEST_POSTGRES_URL=<new schema_validation DB> PRODUCT_POSTGRES_URL=<isolated control DB> .venv/bin/pytest -q` | **77 passed，32.37s，0 skip**，产品测试逐项建立新 PostgreSQL 库；含迁移、错误隔离、幂等、权限、恢复、引用/身份/证据约束 | `evidence/product-final-postgres-tests.log` |
| `make lint` | Ruff/check/format、mypy20文件、TypeScript、已实现 OpenAPI 漂移检查通过 | `evidence/product-lint.log` |
| `make test-security` | **27 passed，10.00s**；Bandit exit0，无排除规则；27是77的子集，不额外相加 | `evidence/product-security-tests.log` |
| `npm --prefix apps/web test` | Vitest5.1.0，**3 passed** | `evidence/product-web-unit-tests.log` |
| 隔离源码 E2E，独立SQLite+worker，实际Chromium | **3 passed，23.5s** | `evidence/product-browser-tests.log` |
| 全新 Compose 项目/PG卷/原件卷，自包含 API+Nginx 镜像，`playwright test --config playwright.installed.config.ts` | **3 passed，28.2s**；首次建号→下载样例→上传→独立worker→重复导入→双“收到”保留→来源/缺附件→业务批准→规则候选→检索/审核→导出→审批/Odoo dry-run→备份下载→注销；390px移动端、有效PNG实际解码预览 | `evidence/product-installed-browser-tests.log`、`evidence/product-installed-runtime.json` |
| 安装镜像内 `python -m wdh_api.seed` 两次 | 两次完成，同一演示批次未重复入库，不预设/重置现有密码 | `evidence/product-installed-runtime.json` |
| 成品镜像内部加密备份→新PostgreSQL空库 | 成功，所有表计数/对象校验，旧会话作废；无源码/额外依赖挂载 | `evidence/product-image-restore.json` |
| 默认本地交付实例 `bash start-offline.sh` | 镜像内容ID校验通过，3服务健康；仅127.0.0.1:5173/8000，数据库无宿主端口，无默认管理员 | `images.lock`；最终交付运行清单 |

最终浏览器运行截图：`product-empty.png`、`product-imports.png`、`product-conversations.png`、`product-evidence.png`、`product-search.png`、`product-mobile.png`、`product-odoo-preview.png`。截图仅合成内容。Playwright 启动的 Vite 仅用于源码回归；成品回归走 Nginx 静态页面和真实 PostgreSQL，二者明确区分。

Python 有一个上游 Starlette TestClient→httpx 弃用告警，不是失败；实际产品容器使用 Uvicorn，不依赖 TestClient。CI文件已提供，尚未声称远端 CI 服务执行成功。

## 十万条容量与检索

实测 PostgreSQL17.6，3逻辑CPU的 Linux x86_64 Cloud：100,000/100,000条规范化，原文件 **70,177,780字节**，导入 **1097.28秒**，进程峰值RSS **293,648KiB（约287MiB）**。30次关键词请求 P95 **0.299391秒**，中位 **0.165938秒**，达到此环境中AC-105/603目标。样本、原始时间、硬件信息见 `evidence/benchmark-100k.json`。

检索计时包括真实PG查询/API序列化，通过进程内HTTP TestClient执行，不含外部网络RTT；不宣称任意电脑或真实微信全量媒体都达到同样指标。导入并行构建时受磁盘竞争影响，报告保留实际耗时，未重写为理想值。Cloud仅7.9GB、Docker VFS层复制开销大，不适合长期全量聊天；交付单层镜像避免本环境的重复构建层，但数据和备份仍需另规划容量。监控/完整故障注入验收未全部完成。

## 恢复与安全

PostgreSQL→新PostgreSQL的恢复演练：备份0.129秒、恢复0.524秒（微型合成集），4个原件逐一SHA-256验证，恢复媒体下载字节一致，重新登录/检索/来源可用，旧会话失效。`evidence/restore-drill.json`记录实际表计数；`counts.login_sessions=0`，`source_counts`保留备份时数量。没有生产备份调度，不承诺生产RPO/RTO。成品容器的第二次独立恢复证据见 `product-image-restore.json`。WDHBK02封装尚需独立密码学审查。

- Python **运行依赖** pip-audit 未发现已知漏洞（cryptography已升级50.0.2，修复47系列告警）；`evidence/python-runtime-audit.json`。
- npm **运行依赖** audit 为0漏洞；`evidence/npm-runtime-audit.json`。
- 完整开发/构建依赖 audit：5条HIGH派生报告，一个根因 [GHSA-fc5q-39xc-vjpf](https://github.com/advisories/GHSA-fc5q-39xc-vjpf)，picomatch<=4.0.7 ReDoS；`evidence/npm-all-audit.json`。审计时上游最新4.0.7，4.0.8查询404；不能用未发布版本伪造修复，也不接受回退到存在其他critical的旧Vitest建议。缓解范围：构建只处理可信仓库/配置glob，上传不进入构建目录；成品Nginx不含Node/Vite/Vitest，不运行开发服务器。上游修复及正式安全复审仍待办，不能宣称全依赖干净。
- SBOM `evidence/sbom.cdx.json` 和 `DEPENDENCIES.md` 是安装Python元数据+完整npm锁，包含开发/可选依赖，**不包括OS镜像软件包**。`THIRD_PARTY_NOTICES.md`保留运行JS许可。未整合外部微信提取器源码，未改变其许可边界。
- 上传攻击/路径/压缩比/symlink/MIME、CSRF/登录限速、角色与workspace越权、私有会话不可业务处理、CSV公式、workspace备份隔离都有自动测试。SQL引擎隐藏参数，不在审计中保存消息体/密码；这不替代独立渗透审计。

## 安装包和发布限制

镜像从无数据卷、无凭据的专用构建容器封装，包含安装后的wheel、依赖、迁移和静态页面。`product-installed-runtime.json`确认API只有原件volume、Web无源码bind挂载；Linux amd64镜像内容ID在 `images.lock`。默认源码 Dockerfile仍锁定上游digest，可重新构建；离线Compose使用本地tag并由脚本先核对确切ID、禁止拉取。

合成验证项目及其明确命名的测试卷已清理，交付实例的原件/PostgreSQL卷保留，不打入压缩包。之前自动审批曾拒绝宽范围 `docker system prune --force`，未执行；后续仅清理了明确属于本任务的构建/测试资源，未影响用户数据卷。

完整规格 REQUIRED 未全部通过，尤其OCR/ASR/RAG/LLM/真实Odoo outbox和真实兼容覆盖；参见 `ACCEPTANCE_STATUS.md`。当前交付为可用本地核心版本，不是正式RC，不把合成兼容结果冒充真实微信实机验收。

# 2026-11-18 OCR增量

WDH-040：新增图片验证/识别/证据表、真实本地Tesseract5.5.0 + tessdata_fast中文/英文。合成图片成功识别“八方/M620/报价/3200”，坐标/原图SHA与模型hash留存。7项新集成覆盖真实识别、关闭/取消/重试、损坏/像素超限、缺模型、角色/workspace、租约fencing。模型固定上游commit87416418657359cb625c412a48b6e1d6d41c29bd，资产SHA在model_assets.json。

全套：专用新PG库84 passed/47.40s，见evidence/ocr-postgres-tests.log；SQLite局部全套78 passed/6 skipped，见evidence/ocr-python-tests.log。新增真实Chromium OCR流程后4 passed/30.6s，包含原图框选/证据下载/派生搜索；截图evidence/ocr-coordinates.png。首次浏览器测试发现异步批次完成后时间线未刷新，已修复缓存失效通知后实测通过，未跳过失败断言。Ruff、mypy22文件、Bandit通过。

PostgreSQL测试通过本任务明确命名、仅127.0.0.1:18032的轻量TCP代理执行，不改变默认交付编排；新库前缀wdhai_control/wdhai_schema，结束只删除其自身测试库。原交付库和数据卷未修改。此为源码切片证据，当前0.2.0包尚未包含新模块；本轮结束统一打包。

## 2026-11-18 · 0.3.0 最终本地识别与AI验证

所有输入均为自制合成数据；未使用真实微信聊天，没有Odoo真实实例操作。最新执行日志优先于上述早期切片日志。

- Python3.12.14、PostgreSQL17.6 + 实际编译安装的pgvector0.8.7：完整回归 **109 passed / 0 failed / 0 skipped**，129.55秒。每个产品测试使用随机新库；`evidence/ai-postgres-tests.log`。运行入口是 `pytest -q`，设置 `PRODUCT_POSTGRES_URL`（专用可创建库的控制库）及 `TEST_POSTGRES_URL`（新的空库）；不连接用户聊天库。
- Chromium真实界面与独立worker：**6 passed**，包含初始化/导入/幂等/来源/审核/导出、手机宽度、图片预览、中文OCR词框/导出/搜索、语音片段/原音频、语义与混合搜索/引用问答/未知问题/AI待审候选。命令 `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium WDH_CAPTURE_SCREENSHOTS=1 npm --prefix apps/web run test:e2e`；日志 `evidence/ai-browser-tests.log`，截图 `ocr-coordinates.png`、`asr-timestamps.png`、`semantic-cited-answer.png`、`ai-source-candidates.png`。
- 模型不是HTTP模拟：真实Tesseract中文图片，真实Whisper tiny在WAV/OGG/FLAC/MP3转录，真实BGE512维余弦，真实Qwen JSON候选/问答均有正向集成。另有明确标注的恶意提供方输出契约样例，验证无原文字段拒绝；不能把这些fixture当真实来源验证。
- 实际发布容器的四类引擎/官方权重再次执行，结果 `evidence/packaged-model-proof.json`。Tesseract5.3与固定tessdata读取24个词框，Whisper音频1个片段，BGE512维，标准合成报价产生3个机器候选。另一个短句的模型字段跨度无法通过校验，返回0个候选；此局限如实保留，不宣称准确率或每条必有候选。LLM权重以内存传入验证，不进入默认镜像。
- 新增恢复回归：OCR与embedding结果、识别文字搜索、附件字节一致；恢复后所有模块关闭，重新允许embedding后从核心JSON重建新的PG向量缓存。已有会话作废/加密篡改防护继续通过。
- `ruff check`、`ruff format --check`、`mypy`（28个源码文件）、生成OpenAPI漂移检查、Bandit通过；Vitest3项通过，Vite生产构建通过。启动脚本 `bash -n` 通过。
- 发布前pip-audit检出Pillow12.3.0的42条公开记录，已升级**13.0.0**，全套PG/浏览器回归与复审通过。`uvx pip-audit --disable-pip --no-deps -r .local/runtime-requirements-03.txt -f json`：完整核心/AI锁定运行依赖未检出已知漏洞，`evidence/python-runtime-audit.json`。npm运行依赖0；开发工具链仍为picomatch根因导致5个HIGH派生报告，`npm-all-audit.json`，不进入nginx静态成品。完整OS审计尚未完成。
- SBOM更新为202组件，明确包含Python开发/运行、npm锁、固定原生/模型目录；完整OS范围排除。原生许可证与源码commit在 `licenses/`，模型SHA和许可在 `apps/api/wdh_api/model_assets.json`；libsndfile保留动态库和上游许可。
- 早期100k核心关键词测量沿用0.2证据（P95 .299391秒，RSS293648KiB），不是0.3十万向量/问答性能测量，不据此承诺AI吞吐。
- 真实导出WDH-003/063、Odoo真实握手/写入WDH-050/052、完整RC继续BLOCKED；只读Odoo HTTP fixture仅证明调用方法约束、配置缺失状态和零外部写入。分开验收见REAL_VALIDATION.md。

### 成品镜像的新卷复验与打包修复

最终三镜像在独立 Compose 项目、全新 PostgreSQL 数据库/原件子目录上运行，同一套6项浏览器流程 **6 passed（1.5分钟）**；`evidence/installed-03-browser-tests.log`。权重为校验后的官方公开文件，显式预置在仅供合成测试的私有卷；测试后已清理该验证卷，不进入运行包。实际版本/可用性/余弦同向量结果见 `evidence/installed-03-runtime.json`（Pillow13.0.0，pgvector0.8.7，四模型可用，cosine distance=0）。主实例继续保持无预置管理员、可选模块默认关闭。

首次成品复验发现pgvector SQL/control文件在宿主暂存后权限为0600，数据库角色不能读取；这不是源码模型测试能覆盖的。已将发布镜像和Dockerfile明确设置0644，生成新的数据库内容ID，再在实际新库创建扩展、重跑全部成品流程通过。初次升级/验证还遇到开发机VFS磁盘不足，回收本任务旧镜像和合成副本后重新执行；没有清理主数据卷或修改源原件。

最终 `make lint`、27项安全测试/Bandit、3项Vitest通过，日志分别为 `ai-final-lint.log`、`ai-security-tests.log`、`ai-web-unit-tests.log`。此前因磁盘不足失败的安全执行已在容量恢复后完整重跑。默认项目及自定义项目的「已有数据库卷但无.env」升级保护实测2项通过，`upgrade-guard-tests.log`。

打包脚本 `scripts/package_delivery.py` 从已提交源码和 `images.lock` 指定的三个镜像流式生成完整ZIP，排除本地配置/原件/数据卷/可选权重；提供Git提交、镜像内容ID、内层镜像压缩流SHA、完整包/源码包SHA和ZIP CRC核验。不把已有测试账号或数据卷封装到镜像。
