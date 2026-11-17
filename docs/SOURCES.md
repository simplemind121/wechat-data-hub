# 公开资料与技术依据（核对日期：2026-11-17）

> 列在这里的链接帮助 Codex 确认版本边界。外部仓库的 README/许可/接口会变化，实施前须重新核对具体 commit，不能把当前说明当作永久兼容保证。

1. ChatVault GitHub： https://github.com/soundadam/chatvault  
   公开 README 陈述：Mac 微信 4.x、macOS 12+、SQLite vault、JSONL/Markdown、key 为前置，Apache-2.0。实机用户环境尚未验证。
2. WeFlow Fork GitHub： https://github.com/334456777/WeFlow  
   公开 README 陈述：Rust CLI、多格式导出；数据只读模式；对个人研究与商业使用有特别免责声明。仓库 license 标签与 README 限制须单独审查。
3. WeFlow 兼容/不支持说明： https://github.com/334456777/WeFlow/blob/main/docs/zh-CN/cli-unsupported.md  
   项目对部分 Windows 版本做过案例测试，不能推断覆盖所有客户端。
4. WechatExport-iOS GitHub： https://github.com/pengw0048/WechatExport-iOS  
   老项目，不能假设当代 iOS/Finder 加密备份可解析。
5. Odoo 19 官方 JSON-2 API： https://www.odoo.com/documentation/19.0/developer/reference/external_api.html  
   JSON-2 接口语义参考；Community 版实际开放情况与模型访问权仍以用户自托管实例联调为准。
6. pgvector GitHub： https://github.com/pgvector/pgvector  
   扩展安装、索引和查询。
7. FastAPI 文档： https://fastapi.tiangolo.com/  
   OpenAPI、请求校验、安全与测试。
8. SQLAlchemy 2 文档： https://docs.sqlalchemy.org/en/20/  
   ORM、异步会话、事务约束。
9. Alembic 文档： https://alembic.sqlalchemy.org/en/latest/  
   数据库迁移。
10. OWASP ASVS： https://owasp.org/www-project-application-security-verification-standard/  
    应用安全验收参考。

## 重要风险备注

- 公开 README 列举的硬件/性能数字不是独立性能实验，不能写入我们的容量承诺。
- 外部工具对数据库的读取方式并不自动成为本产品可合法商用的能力。
- 官方加密备份优先保障恢复，不得把“已备份”说成“已转换成结构化 SQL”。
- Odoo 19 既有文档覆盖不同部署与商业方案；以用户自托管 CE 实例做测试为准。
