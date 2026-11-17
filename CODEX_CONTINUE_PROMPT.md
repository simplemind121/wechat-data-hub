# Codex 后续工作会话的续开发指令

不要重新规划或覆盖已完成的实现。先阅读 `AGENTS.md`、`TASKS.md`、`ACCEPTANCE.md`、`docs/IMPLEMENTATION_STATUS.md`、`docs/TEST_EVIDENCE.md`，再查看 git status/log 与当前源码。

根据任务依赖选出最靠前的未完成任务；每次继续实现至少一个可验收的垂直功能切片。写/改代码，执行 lint、测试、E2E（如涉及 UI），更新状态、测试证据和变更日志。遇到真实微信样本、外部 Odoo CE 实例或授权不足的情况，标记 BLOCKED 并继续不受影响的核心平台任务，不得用模拟结果充当真实验收。

当所有可测试项实现时执行 `ACCEPTANCE.md` 全部 REQUIRED 测试和恢复演练；输出发布候选标签、SHA256、部署手册、版本兼容矩阵与阻断清单。任何真实兼容性/外部写入未验证，不得声明完整生产交付。

每轮按 `AGENTS.md` 固定格式汇报：已完成、变更、测试、验证证据、风险/阻断、下一任务。
