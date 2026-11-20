# WeChat Data Hub · 0.4.0 采集接口与审批同步版

把已合法导出的聊天文件保存在自己的电脑：导入、会话浏览、中文搜索、来源追溯、附件预览、重复候选复核、导出和加密备份。默认不接外部 AI，不暴露公网，不提供默认管理员密码。

## 下载完整成品

[下载 0.4.0 完整运行包（含三个运行镜像）](https://github.com/simplemind121/wechat-data-hub/releases/download/delivery-v0.4.0/WeChat_Data_Hub_v0.4.0.zip) · [版本与校验文件](https://github.com/simplemind121/wechat-data-hub/releases/tag/delivery-v0.4.0)

包内含源码和三个离线运行镜像。启动 Docker，解压后执行 `bash start-offline.sh`，打开 http://127.0.0.1:5173 创建管理员。OCR 模型已提供；语音/语义/AI 模型首次需在设置页下载。完整 AI 建议至少8GB内存。

## 从 GitHub 获取并运行源码

先安装并启动 Docker Desktop / Docker Engine + Compose v2，再执行：

```sh
git clone https://github.com/simplemind121/wechat-data-hub.git
cd wechat-data-hub
bash start.sh
```

首次构建需要联网。启动后打开 http://127.0.0.1:5173，创建管理员。
也可从 [0.4.0 源码发布页](https://github.com/simplemind121/wechat-data-hub/releases/tag/delivery-v0.4.0) 下载 Source code ZIP，解压后执行 `bash start.sh`。

完整离线运行包已提供于上方下载入口；下述 `start-offline.sh` 用于含镜像的完整运行包。

## 直接使用

1. 安装并启动 Docker Desktop（或 Docker Engine + Compose v2）。完整 AI 建议至少 8GB 内存、5GB 可用磁盘，另为聊天和备份预留空间。
2. 解压完整运行包，在解压目录运行：

```sh
bash start-offline.sh
```

3. 打开 **http://127.0.0.1:5173**，创建自己的管理员账号和密码。
4. 进入「数据导入」，可以先下载页面提供的**合成演示 ZIP**，再上传体验整个流程；演示文件不是任何人的真实聊天。
5. 上传自己的 JSONL / JSON / CSV；没有 manifest 时填写账号别名、设备、来源软件版本、时区及字段映射。带媒体的 ZIP 需在根目录包含 `manifest.json`，格式见 `examples/manifest.json` 和 `examples/`。

运行包已包含 Linux amd64 镜像，启动无需联网安装 Python/Node 或依赖；已在 Linux x86_64 Docker 验证。macOS/Windows 使用 Docker Desktop；Windows 可在 WSL 中执行。Apple Silicon 的 amd64 模拟、Windows/macOS 实机尚未验证，本版原生 AI 二进制锁定 amd64，其他架构未验证。

只有源码包时，运行 `bash start.sh`，首次需联网构建。开发步骤见 [运行手册](docs/RUNBOOK.md)。

## 已能使用

- 首次管理员初始化、本地登录、admin/reviewer/reader、工作空间隔离和审计。
- JSONL、JSON 数组/`messages` 对象、显式字段映射 CSV；异步持久任务、进度、错误隔离、重试、取消、重复批次幂等。
- 原文件和 manifest 的 SHA-256 不可变归档；每条消息可回查原始来源、设备、行号/定位及哈希。
- 会话/联系人浏览、分页、中文型号搜索和多条件筛选；安全图片/音频预览，缺失附件明确显示。
- 相似消息和身份映射人工复核；保留两条真实重复文字，不自动吞并；冲突保留各来源。
- 管理员 CSV/JSONL 导出、当前工作空间加密备份；CLI 恢复到全新空数据库和目录。
- 将会话明确批准为业务用途后，本地规则可识别带原文证据的报价候选，审核后查看 Odoo 映射预览。本地规则和可选 LLM 分别保留版本，本地预览不写 Odoo；实际投递另需管理员批准与连接配置。

- 图片 OCR：文字、原图词框定位、版本/哈希证据导出与派生检索。
- 语音转录：WAV/OGG/FLAC/MP3 的真实本地模型、片段时间和原音频核对。
- 语义与关键词融合检索、带原消息引用的证据问答；本地 AI 摘录摘要与待审核业务候选。

## 0.4 新增：采集与 Odoo 草稿

- 在「数据导入 → 自动同步数据源」创建个人微信文件或企业微信官方存档数据源，下载一次性采集配置。
- 个人微信：保存配置到 `collector/personal.json`，将**已经导出的完整文件**放入 `collector/inbox`，执行 `bash start-collector.sh files`。采集端自动上传、记收据、重试；网页可暂停同步或更换凭据。本程序不提供个人微信扫码登录/原生聊天提取。
- 企业微信：保存配置到 `collector/wecom.json`，填写企业存档 Secret、按版本匹配的私钥与官方 SDK 路径，执行 `bash start-collector.sh wecom`。按 seq 拉取消息与媒体；需要先开通官方会话存档，SDK及实号尚待验证。
- Odoo：安装随包 `integrations/odoo_addons/wdh_bridge` 到获授权的 Odoo19CE测试实例，配置连接与 ENABLE_ODOO_WRITES=true；在业务实体批准后选择已有资料/草稿映射、预览并批准入队，在设置查看投递回读。默认不写外部系统，实际实例尚待联调。
- [采集端操作与 API](docs/CONNECTORS.md) · [Odoo 模块安装与投递](docs/ODOO_BRIDGE.md)。Docker共享库与平台/文件权限需按目标机器验证，Windows/macOS仍未实机认证。

## 启用新模块

进入「设置 → 本地识别模块」，启用图片识别；按需下载并启用语音/语义/AI 模型。在消息的「查看证据」中执行识别并核对原图/原音频。管理员先允许会话进行业务处理后，才能索引或提取 AI 候选；候选到「业务实体」人工审核。搜索页可建立业务消息索引并问答，无证据时明确返回无法确定。

升级自0.2/0.3时先备份，保留旧包，并把旧 `.env` 复制到新目录再启动，沿用原数据卷。详细操作与模型边界见 [运行手册](docs/RUNBOOK.md)，真实数据与 Odoo 分别验证见 [独立验证说明](docs/REAL_VALIDATION.md)。

## 当前支持边界

真实 iPhone/Mac/Windows 导出样本未提供，具体微信/导出器版本全部 **NOT TESTED**；支持的是已验证的通用文件合同，不承诺任意导出文件开箱兼容。SQLite、HTML/TXT、微信原生加密备份尚无解析适配器。

OCR、ASR、语义/关键词融合检索、带引用问答和本地 LLM 候选已实现，默认关闭。运行包自带 OCR 模型；语音、语义、LLM 模型需在设置页主动下载一次（约99MB、26MB、469MB），之后可离线推理。Odoo 提供只读握手入口和本地 dry-run；已增加需显式启用的 outbox、远端桥接幂等和草稿回读；没有真实实例，安装/权限/实写联调尚未验证。重处理目前提供无损差异预览，尚无批准后的派生版本切换。

这是可使用的预发布接入版本，**尚未达到原规格全部 REQUIRED 验收和正式生产 RC 门槛**。安全扫描、容量和恢复结果见 [测试证据](docs/TEST_EVIDENCE.md)、[交付状态](docs/DELIVERY_STATUS.md)。

## 数据与运维

停止但保留数据：`docker compose -f compose.yaml -f compose.offline.yaml down`。不要添加 `-v`，它会删除数据卷。不要丢失 `.env`；已有配置不会被启动脚本覆盖。不要把聊天、密码和备份上传到代码仓库。

备份入口在「审计与备份」，使用至少16字符的独立口令，并把下载的 `.wdhbak` 存到另一块磁盘；丢失口令无法恢复。恢复及升级步骤见 [RECOVERY](docs/RECOVERY.md)。

[规格](SPEC.md) · [任务状态](TASKS.md) · [来源兼容矩阵](SOURCE_COMPATIBILITY.md) · [依赖与许可](docs/DEPENDENCIES.md) · [变更记录](CHANGELOG.md)
