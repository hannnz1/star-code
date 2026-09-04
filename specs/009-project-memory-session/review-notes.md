# Feature 009 决策记录

## 已决策

1. 自动记忆默认开启；本章不增加配置开关。
2. `/memory` 列出当前项目层与用户层文件；编辑/全文展开不在本章范围。
3. “不要记住/别记住/do not remember”抑制本轮更新；“忘记/forget”触发 LLM 产生 delete/update 动作。
4. 新格式 session 默认清理期固定 30 天，旧格式与当前 session 受保护。
5. durability 优先于 10ms 软性能目标；关键 JSONL append 使用 flush/force，性能通过基准观察而非牺牲崩溃安全。

已确定：`custom-instructions=150`、`long-term-memory=120`、`text-output=100`。

## 已按当前项目修订

- Lanterna 改为现有 JLine，不引入第二套 TUI。
- 新增 SessionContext 作为 ContextManager 的目录依赖。
- include 增加真实路径与符号链接逃逸检查。
- JSONL 中间坏行不再完全静默，恢复后必须验证结构。
- 会话恢复改为事务切换，失败时保留原会话。
- 过期清理限定严格 ID 目录、禁止跟随符号链接、保护当前会话。
- 系统内置安全规则明确高于所有项目/用户指令。
- 每条 force(true) 调整为关键边界强制刷盘，工具事件允许批量刷盘。

## 历史拆分建议（已完成）

- Feature 009A：MEWCODE.md + 完整 Conversation 事件模型 + JSONL + `/resume`。
- Feature 009B：自动笔记、索引、注入和管理命令。

009A 与 009B 均已实现；结构化 ToolExchange、自动笔记、索引和注入均有离线测试。
