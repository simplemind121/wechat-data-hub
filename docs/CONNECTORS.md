# 0.4 数据源与自动同步

本版本把授权导出文件和企业微信官方存档接入同一归档 API。个人微信客户端登录、数据库密钥提取、原生加密备份解析不在本采集端中。所有真实设备、微信版本和企业账号当前仍为 NOT TESTED。

## 个人微信文件同步

1. 先启动主应用，在「数据导入 → 自动同步数据源」创建个人微信数据源。填写稳定的账号别名、设备标识、实际导出工具及版本。CSV 需要字段映射。
2. 下载一次性配置，保存在解压目录 `collector/personal.json`；不要放到待同步目录。更换凭据会立即使旧凭据失效。
3. 创建 `collector/inbox/`。将**已经取得的完整导出文件**放进去；只读取顶层 JSONL/JSON/CSV/ZIP，不扫描微信进程或其他目录。媒体 ZIP 根目录需有 manifest.json，来源四项须与数据源一致。单文件 JSON 当前选择数组格式；messages 对象可用明确 manifest 的 ZIP。
4. 执行 `bash start-collector.sh files`。Docker 采集端通过 API 容器的本地网络上传，输入目录只读，状态目录单独可写。Linux 使用当前用户 UID/GID；如 Docker 文件映射不同，配置 COLLECTOR_UID/COLLECTOR_GID，使其只能访问该采集端私有目录。Windows 建议在 WSL 运行脚本；实机尚未验证。
5. 在网页查看最近连接、归档位置及下方导入批次。**已归档只代表原件与后台任务已持久化**；解析错误、隔离记录、缺附件请查看批次报告。

导出器应先写 `.part` 文件，完成后原子改名，或导出完成后再移入目录。采集端复制私有快照、检查文件变化、按哈希保存收据；不移动/删除输入。相同文件不重复上传，内容改变视为新批次。不同导出批次缺少经认证的唯一消息 ID 时，仍走相似消息人工复核，不能保证自动合并重叠历史。

坏文件不阻断其他文件，会保留待下轮重试；修改后的正确文件可以重新提交。上传失败不会记成功收据。恢复备份后采集凭据全部撤销，管理员须重新启用并更换凭据。

仅启动微信不能产生这些导出文件。现有导出器是否能持续提供文件，需要按真实设备/版本单独验证。

## 企业微信官方会话存档

1. 企业管理员开通会话内容存档，配置成员/客户授权、官方 SDK 要求的访问条件及存档密钥。
2. 网页创建企业微信数据源，下载至 `collector/wecom.json`。配置企业 ID、**会话存档 Secret**、官方共享库路径及按 publickey_ver 匹配的 RSA 私钥路径；不是普通自建应用 Secret。
3. 官方 SDK 从 [腾讯官方文档](https://developer.work.weixin.qq.com/document/path/91774) 获取，与操作系统/CPU匹配。随包 Docker 是 Linux amd64，SDK 也须为 Linux x86_64。本包不重分发共享库。将库及依赖放入 `collector/secrets/`，配置 `sdk_library` 为容器内实际路径（例如 `/collector/secrets/libWeWorkFinanceSdk_C.so`）。官方文件名可能不同，按实际填写。
4. 私钥按版本配置，例如 `"private_keys":{"1":"/collector/secrets/archive-private.pem"}`；文件仅采集端可读，Unix 下设0600。私钥不传到归档服务，也不写日志。Docker 只读挂载 secrets。
5. 执行 `bash start-collector.sh wecom`，通过后台观察归档和错误状态。保存原始密文信封与解密后的官方消息；文本、图片、语音、视频/文件/表情媒体引用进入现有处理链。未知类型保留原始内容。

按 seq 增量拉取，每页生成不可变待发 ZIP 和本地待确认收据；只有服务端原件归档与任务持久化后才推进服务端游标。响应丢失重发完全相同的 ZIP。缺私钥版本、消息不合约、媒体拉取失败时该页不推进，修复后重试；尚无绕过永久失效媒体的后台补偿流程。单媒体上限32MiB，超限明确失败；SILK/AMR 不承诺可转录。存档可取范围由企业开通、授权和官方接口决定，不能补齐个人微信历史。

官方 SDK 下载在本轮环境收到403；没有执行官方二进制或真实企业拉取。已通过的是协议替身、真实入库和超时重试测试，不是实号联调。

## 直接运行和 API

有 Python3.12 环境也可安装项目依赖后执行：

```sh
python -m wdh_api.collector files --config /private/personal.json --once
python -m wdh_api.collector wecom --config /private/wecom.json
```

宿主运行时将配置的 inbox/state_directory 改成宿主绝对路径，hub_url 指向实际服务地址。配置文件权限0600，状态目录0700。远端地址强制 HTTPS，客户端不跟随重定向，凭据不通过查询参数传输。

| API | 权限/用途 |
| --- | --- |
| POST /api/v1/sources | 管理员创建绑定来源，凭据只返回一次 |
| GET /api/v1/sources | 管理员查看状态，不返回凭据或其哈希 |
| POST /api/v1/sources/{id}/state、/rotate | 管理员暂停/恢复、更换凭据 |
| GET /api/v1/collector/status | Bearer 上传凭据，只读自身配置 |
| POST /api/v1/collector/heartbeat | 连接时间与安全错误代码 |
| POST /api/v1/collector/batches | multipart file + cursor，可选 manifest；返回202、import_id、job_id |

采集凭据没有聊天查询、导出、用户管理或跨来源上传权限。查询和导出沿用已登录角色权限。完整契约见 implemented-openapi.json。

## 私有云

个人微信文件采集端保留在本地；企业存档采集端可在私有服务器运行。后台沿用 Compose + PostgreSQL + 原件卷。远程访问由 VPN 或 HTTPS 反向代理提供；在 .env 设置实际域名 ALLOWED_HOSTS 与 COOKIE_SECURE=true 后重建服务。数据库不发布公网端口。本包不包含托管云服务器、域名或公共多租户 SaaS。
