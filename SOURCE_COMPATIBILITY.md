# 来源兼容性、风险与导入验收

核对时间：2026-11-17。**此表只记录公开项目的自述与待验条件，不构成对用户设备的实际测试结果。**

## 已知外部项目和定位

| 外部来源 | 公开说明 | 当前策略 | 风险/门槛 |
| --- | --- | --- | --- |
| [ChatVault](https://github.com/soundadam/chatvault) | macOS 12+、Mac 微信 4.x；本地 SQLite 归档与 JSONL/MD 导出；仓库标为 Apache-2.0 | **优先做其 JSONL 和 SQLite 导出结果的适配器**，不整合 key 导入功能 | 项目较新，微信升级后格式可能变化；需用户以合规方式先完成导出。macOS 3.x 不支持 |
| [WeFlow Fork](https://github.com/334456777/WeFlow) | 微信 4.x 数据研究/导出工具；Rust CLI；JSON/Excel/SQL/HTML 等多种格式 | 仅针对经授权生成的 JSON/CSV/SQL 结果设计数据导入 | README 对非研究商业使用有限制性声明；仓库显示 Unlicense 与 README 附加限制并存；不得因显示 Unlicense 就断言商业集成许可无问题；先法律/许可审查 |
| [WechatExport-iOS](https://github.com/pengw0048/WechatExport-iOS) | 较老的 iTunes/iOS 备份解析项目 | 可评估其**已导出**的 HTML/TXT/媒体结果；不可假设支持当代 iOS | 版本和备份加密方式存在巨大兼容不确定性，需样本实测 |
| 微信官方备份（微信客户端 / Finder） | 设备恢复/迁移能力，不提供稳定开放 SQL/JSON 接口 | 加密原生备份只保留作灾备原件，不直接参与 ETL | 不得写“官方备份已经结构化导入” |
| 企业微信会话存档 | 独立的官方企业接口，受资质、告知/同意等限制 | V2 可新增独立官方适配器 | 不能声称能补齐私人微信历史消息 |

### 原生数据库与密钥处理原则

本工程的职责从**合法取得的导出文件**开始。外部工具是可替换的输入前置步骤，而不是本工程中的必需或内嵌能力。不得编写或复制微信内存解密密钥提取、客户端注入、绕过数据库保护的逻辑；不得把私密数据库或密钥发送至第三方服务器。每个来源与使用方式的权限和许可，须独立核查。

### 各设备 P0 最小矩阵

| 设备 | OS 版本 | 微信版本 | 导出器版本/commit | 数据格式 | 文本 | 图片 | 语音 | 文件 | 群聊 | 撤回/引用 | 结论 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| iPhone | 待填 | 待填 | 待填 | 待填 | NT | NT | NT | NT | NT | NT | BLOCKED |
| Mac | 待填 | 待填 | 待填 | 待填 | NT | NT | NT | NT | NT | NT | BLOCKED |
| Windows | 待填 | 待填 | 待填 | 待填 | NT | NT | NT | NT | NT | NT | BLOCKED |

缩写：NT=not tested。真实设备未测试之前，不准将本表中的 `BLOCKED` 改成 `PASS`。

## Adapter 验收最小文件合同

每份导出必须附带 `manifest.json`，至少包含：

```
schema_version, export_id, account_ref, device_ref,
platform, os_version, wechat_version,
exporter_name, exporter_version, exported_at,
original_timezone, data_format, payload_files,
media_base_path, consent_scope, coverage_notes
```

- `account_ref` 是自定义不可逆别名，真实微信 ID 只在本地受控元数据中使用。
- `payload_files` 包含路径、大小、SHA256；路径相对 manifest 根目录且禁止 `..`。
- `coverage_notes` 明确“源端可能只包含已同步记录”以及未包含哪些会话/媒体。
- 入口 `probe` 检查 manifest 和每个 payload，不完整时拒绝或进入降级模式。

## 互操作和合规检查

2026-11-17 首轮已只读核对三个项目固定提交的 README/许可文件；准确 SHA、格式边界及未决许可项见 [ADR 001](docs/ADR/001-boundaries.md)。未运行第三方提取器；真实设备仍全部 BLOCKED，指标见 [来源覆盖报告](docs/source_coverage_report.json)。

1. 记录第三方项目完整源码地址、tag/commit SHA、LICENSE、README 限制、依赖与构建行为。
2. 即使许可证允许使用，也先确认其数据处理行为不会外传聊天内容、密钥、设备标识；优先在隔离环境运行，测试需使用副本。
3. 对第三方导出文件执行协议适配，只保留自身的 schema 和独立写法，避免直接复制受限制源码。
4. 对每种导出器提供 5–20 条脱敏合成对照样本和至少一个获授权实测回归样本（如可提供）。
5. 每次微信版本升级后重新记录 Matrix；未通过的组合标识 `UNKNOWN` 或 `UNSUPPORTED`，不得沿用旧版 PASS。

## 发布中的兼容性描述模板

> 本版本支持经过验证的 JSONL/JSON/CSV 文件导入和规范化处理。对来自某微信版本的真实聊天数据，支持程度以附带的“设备与导出器兼容矩阵”为准；微信官方加密备份不等于结构化数据导入能力；附件、撤回和引用的完整性依赖源端是否成功导出。
