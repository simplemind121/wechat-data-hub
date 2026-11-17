# WeChat Data Hub · 0.2.0 本地可用版

把已合法导出的聊天文件保存在自己的电脑：导入、会话浏览、中文搜索、来源追溯、附件预览、重复候选复核、导出和加密备份。默认不接外部 AI，不暴露公网，不提供默认管理员密码。

## 直接使用

1. 安装并启动 Docker Desktop（或 Docker Engine + Compose v2）。建议至少 4GB 可用内存、5GB 可用磁盘，另为聊天和备份预留空间。
2. 解压完整运行包，在解压目录运行：

```sh
bash start-offline.sh
```

3. 打开 **http://127.0.0.1:5173**，创建自己的管理员账号和密码。
4. 进入「数据导入」，可以先下载页面提供的**合成演示 ZIP**，再上传体验整个流程；演示文件不是任何人的真实聊天。
5. 上传自己的 JSONL / JSON / CSV；没有 manifest 时填写账号别名、设备、来源软件版本、时区及字段映射。带媒体的 ZIP 需在根目录包含 `manifest.json`，格式见 `examples/manifest.json` 和 `examples/`。

运行包已包含 Linux amd64 镜像，启动无需联网安装 Python/Node 或依赖；已在 Linux x86_64 Docker 验证。macOS/Windows 使用 Docker Desktop；Windows 可在 WSL 中执行。Apple Silicon 的 amd64 模拟、Windows/macOS 实机尚未验证，可改用源码构建原生镜像。

只有源码包时，运行 `bash start.sh`，首次需联网构建。开发步骤见 [运行手册](docs/RUNBOOK.md)。

## 已能使用

- 首次管理员初始化、本地登录、admin/reviewer/reader、工作空间隔离和审计。
- JSONL、JSON 数组/`messages` 对象、显式字段映射 CSV；异步持久任务、进度、错误隔离、重试、取消、重复批次幂等。
- 原文件和 manifest 的 SHA-256 不可变归档；每条消息可回查原始来源、设备、行号/定位及哈希。
- 会话/联系人浏览、分页、中文型号搜索和多条件筛选；安全图片/音频预览，缺失附件明确显示。
- 相似消息和身份映射人工复核；保留两条真实重复文字，不自动吞并；冲突保留各来源。
- 管理员 CSV/JSONL 导出、当前工作空间加密备份；CLI 恢复到全新空数据库和目录。
- 将会话明确批准为业务用途后，本地规则可识别带原文证据的报价候选，审核后查看 Odoo 映射预览。**规则不是 LLM；预览不写 Odoo。**

## 当前支持边界

真实 iPhone/Mac/Windows 导出样本未提供，具体微信/导出器版本全部 **NOT TESTED**；支持的是已验证的通用文件合同，不承诺任意导出文件开箱兼容。SQLite、HTML/TXT、微信原生加密备份尚无解析适配器。

OCR、ASR、向量/RAG、LLM、真实 Odoo 连接与写入尚未实现；相关开关保持关闭。规则候选和本地 Odoo dry-run 已可操作。重处理目前提供无损差异预览，尚无批准后的派生版本切换。

这是可使用的本地核心版本，**尚未达到原规格全部 REQUIRED 验收和正式生产 RC 门槛**。安全扫描、容量和恢复结果见 [测试证据](docs/TEST_EVIDENCE.md)、[交付状态](docs/DELIVERY_STATUS.md)。

## 数据与运维

停止但保留数据：`docker compose -f compose.yaml -f compose.offline.yaml down`。不要添加 `-v`，它会删除数据卷。不要丢失 `.env`；已有配置不会被启动脚本覆盖。不要把聊天、密码和备份上传到代码仓库。

备份入口在「审计与备份」，使用至少16字符的独立口令，并把下载的 `.wdhbak` 存到另一块磁盘；丢失口令无法恢复。恢复及升级步骤见 [RECOVERY](docs/RECOVERY.md)。

[规格](SPEC.md) · [任务状态](TASKS.md) · [来源兼容矩阵](SOURCE_COMPATIBILITY.md) · [依赖与许可](docs/DEPENDENCIES.md) · [变更记录](CHANGELOG.md)
