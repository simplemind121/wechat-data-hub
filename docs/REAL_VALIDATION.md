# 真实数据适配与 Odoo 联调：两份独立验收

日期：2026-11-18。两项当前均 **BLOCKED**。本地识别/AI 的合成样例和真实模型执行，不能替代真实设备兼容或 Odoo 实例证据。

## A. 授权真实导出样本

尚缺设备/OS/微信版本、导出工具名称及版本、实际文件格式与可测试样本。先以导出副本验证一小批，再扩到全批；本程序不运行客户端提取器，不处理密钥或破解加密备份。

1. 记录 SOURCE_COMPATIBILITY.md 中设备、客户端、导出器版本；明确媒体和历史覆盖边界。
2. 对照 manifest 与实际字段；通用 JSONL/JSON/CSV 可使用网页映射。未经实测的新 exporter 不自动认证 server ID，未知字段保留并记录缺口。
3. 导入后保存批次 coverage/error 报告，核对源记录数、时间、群聊/成员、引用/撤回、中文/emoji、附件引用与实际文件数；人工抽查哈希和消息来源。
4. 重复导入三次，比较 canonical/原件/附件数；跨设备真实 ID 语义需单独证明后才能认证自动强匹配。
5. 图片/语音单独抽样记录正确/错误与不可解码范围；这里尚无真实样本准确率，也不承诺 SILK 解码。

产物分别是匿名统计覆盖报告、设备/版本矩阵及缺口清单。原聊天、姓名、密钥不进入仓库或公开报告。当前实际已验证设备数为 0。

## B. Odoo 19 Community 测试实例

尚缺获授权测试地址、版本/版本类型、数据库及测试账号权限。本版提供**只读握手**和本地 dry-run，不提供真实草稿投递/outbox。

在受保护的本地 `.env` 设置（不要在聊天或日志粘贴密钥）：

```dotenv
ENABLE_ODOO=true
ODOO_URL=https://your-test-instance.example
ODOO_DATABASE=your_test_database
ODOO_USERNAME=your_test_user
ODOO_API_KEY=your_test_api_key
```

重建应用容器配置后，管理员进入「设置 → Odoo 独立联调」，点击只读验证。调用 `/jsonrpc` 的版本、认证、模型字段、`check_access_rights`；可检查客户、产品、采购、销售和 CRM 模型。Community/Enterprise 通过可读的已安装模块查询判定；无权限则返回 unknown，不猜版本类型。Odoo 19 JSON-RPC 的实际部署兼容尚未实测；接口/权限不兼容将如实失败。连接使用 TLS 校验、有限响应与超时，不自动跳转或继承代理。

分别记录：连接/认证、19 CE 目标、各模型字段/读/创建权限、本地已审核实体映射差异。当前 HTTP fixture 只证明适配器使用读方法，不能算实例 PASS。随后真实草稿写入、超时幂等、防重复绑定、回读以及未触发确认/付款，须在后续 outbox 实现和获授权测试实例上另行验收。
