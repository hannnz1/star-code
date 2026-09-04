# ch15 Agent Team Implementation Report

## 已实现

- `com.starcode.team`：BackendType、TeammateInfo、TeamSnapshot、Team、TeamManager、异常和原子 JSON 持久化。
- `com.starcode.team.backend`：稳定 Backend 接口、SpawnRequest/SpawnResult 与可测试 BackendDetector。
- `com.starcode.team.filelock` / `mailbox`：跨进程锁、stale lock 恢复、消息写入、未读查询和 markRead。
- `com.starcode.team.registry`：Agent 名称与 ID 双向注册。
- `com.starcode.team.tasks`：共享任务 CRUD、过滤、动态 isReady 和依赖图双向维护。
- 工具：TeamCreate、TeamDelete、TaskCreate、TaskUpdate；TaskGet、TaskList、SendMessage 扩展为 Team/原后台任务双模式。
- 命令：`/team list`、`/team info <name>`、`/team delete <name> [--force]`。
- Main：启动时加载 `~/.mewcode/teams/`，注册七个协作工具并传入 ChatApplication。

## 验证

- `gradlew clean test shadowJar --warning-mode all`：通过（51 个测试套件、174 项测试、0 失败）。
- 新增测试覆盖 Team 生命周期、跨实例重读、后端检测、邮箱并发、stale lock、名称注册、共享任务依赖和七工具工作流。

## 第二阶段新增

- `Agent` schema 新增 `team_name`，通过 `TeamHook` 分流为正式 teammate spawn；普通 SubAgent 路径保持兼容。
- in-process teammate 使用独立 Worktree、后台 Session、完成回调、idle 成员状态和运行中 reminder 注入。
- tmux/iTerm2 实现 spawn/wake/kill；统一 `--team-member` argv 协议与 Base64 prompt。
- `TeamMemberRunner` 为无 TUI 持续工作循环：完成后等 mailbox、支持续派、shutdown 和 Plan approval。
- Lead watcher 每 750ms 收取 mailbox，终端即时显示，并将消息放入主 Agent reminder 队列。
- Coordinator Mode 采用配置 + 环境变量双开关，并从实际工具定义中去掉 Write/Edit。
- Plan 完成消息转换为 approval request；批准后把 `AgentLoop` 权限模式切至 default 再继续。
- force delete 会取消 in-process 后台任务或 kill pane，再清理受管 Worktree。

## 剩余平台验收

当前 Windows 环境已覆盖 in-process 路径和 pane 命令协议单测；真实 Linux tmux 与 macOS iTerm2 的 UI/pane 行为仍需在对应操作系统人工验收。因此实现完成度不宣称 100%。
