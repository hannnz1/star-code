# ch15 Agent Team Plan

1. 建立 `com.starcode.team` 核心模型、原子持久化与后端检测。
2. 建立跨进程 FileLock、Mailbox、AgentNameRegistry 和 TeamTaskStore。
3. 实现四个新工具，并把既有 TaskGet/TaskList/SendMessage 扩展为兼容 Team 的双模式接口。
4. 在 Main 中构造 TeamManager、注册工具，在 ChatApplication 中提供 `/team` 访问器。
5. 增加核心域、工具和命令测试。
6. 第二阶段接入 `Agent(team_name)`、in-process 生命周期、pane 后端与 `--team-member` runner。
7. 接入 Lead watcher、Coordinator 双开关/工具白名单、Plan approval 权限切换。
8. Windows 跑全量自动测试；Linux tmux/macOS iTerm2 保留真实平台人工验收。
