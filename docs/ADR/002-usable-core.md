# ADR 002 — 可用核心平台、持久任务与恢复

日期：2026-11-17。范围：WDH-012–035 的核心使用链路及备份恢复基础；外部实机与 Odoo 仍受授权实例/样本限制。

沿用指定栈。新增依赖：ijson（BSD-3-Clause AND ISC，流式 JSON 数组解析，避免一次载入整个导出）、python-multipart（Apache-2.0，FastAPI 文件上传）、cryptography（Apache-2.0/BSD-3-Clause，经过维护的 AES-GCM 实现）。精确版本与分发哈希在 uv.lock；不自行实现密码原语。工具链升级需执行导入、错误隔离、权限、恢复及浏览器回归。ASR/模型依赖不会因启动核心平台而自动下载。

JSONL 行保留源行哈希；JSON 数组/CSV 的记录哈希针对解析视图序列化，完整文件原始字节另外由 CAS 保留，通过稳定 item/row 定位回查。它们不是输入字节片段的直接校验和。所有批次另保留 manifest 原字节和每个 payload 的 SHA-256；缺字段不猜测填入。未认证的真实 exporter 的 server ID 不用于自动合并。仅固定 synthetic-v1 合成契约被认证；弱匹配只进审核。

Worker 独立进程，从数据库领取任务，带租约、重试上限和 fencing token。每100条事务提交；原始定位唯一和 observation 唯一约束保证重放幂等。取消不删除原件。PostgreSQL 使用行锁和 SKIP LOCKED；SQLite 只用于隔离测试，不作为生产并发保证。升级过程中不得改写旧迁移或清表重导。

认证采用标准库 scrypt（随机盐）、不可逆会话 token 哈希、HttpOnly/SameSite cookie，CSRF token 与会话绑定，拒绝外部 Origin 和不允许的 Host。初始化用数据库原子一次性 gate，既有管理员不可被再次初始化覆盖。应用查询/对象访问按 workspace 过滤；数据库约束和应用 RBAC 分别测试。SQL 引擎隐藏查询参数，业务源内容不进入操作日志。

上传先鉴权，检查声明大小与流读取上限。ZIP 不使用 extractall；检查文件名、symlink、压缩比、条目数、总大小，按条目流保存到内容寻址目录。附件只按安全嗅探 MIME 下载，不内联执行 HTML/SVG。上传 spool 使用私有 quarantine 目录，避免受容器小型 tmpfs 容量限制。最终仍需安全审计，不以单元测试替代发布检查。

加密备份为 WDHBK02 格式：scrypt 派生 AES-256-GCM 密钥；每帧独立计数 nonce 和绑定格式头的 AAD；显式结束认证帧阻止截断。数据库使用 PostgreSQL repeatable-read 只读快照，原件不可变，按快照引用 SHA 逐个核验。备份文件0600。恢复先验证认证、表清单、计数、原件哈希，再写入全新的空库和新目录；拒绝既有库/目录。恢复后作废旧会话，保留账号密码哈希以重新登录。此格式仍需独立安全审查，不声称已通过第三方密码学审计。

开发环境的 Docker VFS 层数和磁盘很小，允许仅在该环境使用临时只读源码挂载/展平基础镜像来运行；正式源码仍保留可移植 Dockerfile。环境适配不能当成全新主机容器构建验收已通过。

开发工具增加 Prettier 3.6.2（MIT）用于可维护的格式化，Vitest 升级 5.1.0（MIT）修复已知旧测试工具漏洞；两者均不进入 Nginx 运行镜像。完整锁文件/SBOM 和运行时 JS 许可见 docs/DEPENDENCIES.md、THIRD_PARTY_NOTICES.md。

最终交付使用从无用户数据的专用构建容器导出再导入的单层镜像，包含安装后的 wheel/依赖/迁移与静态网页，替代临时源码挂载。images.lock 锁定内容 ID，离线启动校验 ID，Compose 不拉取镜像。构建容器无数据库/归档卷和环境密钥；交付 tar 不含应用数据。源码 Dockerfile 仍可独立构建原生架构镜像。
