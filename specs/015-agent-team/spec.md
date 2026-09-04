# ch15 Agent Team Spec（Star Code 适配版）

> 状态：IMPLEMENTED（in-process 自动验证完成；tmux/iTerm2 需对应平台人工验收）

## 背景

ch13 已提供隔离 SubAgent 与后台任务，ch14 已提供 Git Worktree 隔离，但多个 Agent 之间仍缺少持久化团队、共享任务和消息邮箱。ch15 引入 Agent Team：Lead 创建团队、登记成员、维护共享任务并向成员投递消息；不同进程通过磁盘文件协作。

## 目标

- 团队配置持久化到 `~/.mewcode/teams/<team>/config.json`。
- 支持 tmux、iTerm2、in-process 三种后端标识与自动检测。
- 提供进程安全的 mailbox 和共享任务存储。
- 提供 `TeamCreate`、`TeamDelete`、`TaskCreate`、`TaskGet`、`TaskList`、`TaskUpdate`、`SendMessage` 七个协作工具。
- 保持 ch13 已有 `TaskGet`、`TaskList`、`SendMessage` 名字稳定：传 `team` 时访问 Team，未传时访问原后台 SubAgent 任务。
- 提供 `/team list|info|delete` 本地命令，不消耗 LLM token。
- 单个损坏团队、邮箱或任务文件不得阻止程序启动。

## 功能需求

### 团队与成员

- F1：团队名经过安全化，只保留 `[A-Za-z0-9._-]`，其它连续字符替换为 `-`；空结果拒绝。
- F2：同名团队自动使用 `-2`、`-3` 后缀。
- F3：团队快照保存 name、description、backend、createdAt 和 members。
- F4：成员记录 name、agentId、agentType、model、backendType、paneId、worktreePath、sessionDir、active。
- F5：成员更新前重读磁盘快照，避免 Lead 与 pane 子进程相互覆盖。
- F6：非 force 删除有活跃非 Lead 成员的团队时拒绝；force 删除同时清理受管资源。

### 后端

- F7：后端枚举为 `tmux`、`iterm2`、`in-process`。
- F8：检测顺序：已处于 TMUX；iTerm2 且 `it2` 可执行；PATH 中 tmux；否则 in-process。
- F9：后端协议只暴露 spawn、wake、kill；命令构造不得经 shell 拼接。

### Mailbox 与共享任务

- F10：邮箱文件为 `<team>/mailbox/<agentId>.json`，消息包含 from、text、timestamp、read、type、requestId、approve。
- F11：所有 read-modify-write 操作使用 CREATE_NEW 锁文件；10 秒锁视为 stale；最多重试 10 次。
- F12：共享任务保存在 `<team>/tasks.json`，状态为 pending/in_progress/completed/blocked。
- F13：`blockedBy` 与 `blocks` 双向维护；列表返回动态 `isReady`。
- F14：任务 ID 格式为 `task_<6 hex>`。

### 工具与命令

- F15：七个协作工具均返回 JSON；写操作为非只读，查询为只读。
- F16：`TaskGet/TaskList/SendMessage` 使用可选 `team` 参数分流，兼容既有后台 SubAgent 接口。
- F17：`/team list`、`/team info <name>`、`/team delete <name> [--force]` 走本地命令路径。

## 非功能需求

- N1：原子写使用同目录临时文件 + move；不留下半写 JSON。
- N2：内存锁保护同进程并发，锁文件保护跨进程并发。
- N3：路径清理只能发生在受管 Team 目录或 WorktreeManager 已登记目录内。
- N4：未配置/未创建 Team 不影响 ch01-ch14 的既有行为。
- N5：核心域与工具测试不依赖网络、tmux、iTerm2 或真实 provider。

## 分阶段边界

第一阶段包括持久化、邮箱、共享任务、七工具接口和 `/team`。第二阶段在同一工具名 `Agent` 上增加可选 `team_name`，并补齐以下闭环：

- in-process 队友通过 virtual thread 运行，完成后登记 idle，收到新消息可复用原会话续派。
- tmux/iTerm2 后端启动 `Main --team-member`，参数以稳定 argv 协议传递；prompt 使用 Base64，避免 shell 转义和明文拼接。
- pane runner 在任务完成后持续轮询自己的 mailbox，收到新任务继续执行，收到 shutdown 请求确认后退出。
- Lead watcher 周期读取 lead mailbox，立即显示通知，并把结构化 team-update 注入下一次 Agent 迭代。
- Coordinator Mode 必须同时满足配置 `features.coordinator_mode: true` 与环境变量开关；启用时移除直接 Write/Edit 工具。
- Plan 成员先以 plan 权限产生计划并发送 approval request；批准消息把权限切换为 default 后续派执行，拒绝不执行。

## 验收标准

- AC1：团队创建、安全化、同名后缀、重载和删除通过测试。
- AC2：损坏团队配置仅告警并跳过。
- AC3：邮箱并发写不丢消息，markRead 正确，stale lock 可恢复。
- AC4：共享任务 CRUD、状态过滤、依赖双向维护和 isReady 正确。
- AC5：七个工具定义在 registry 中唯一；旧后台任务调用仍工作。
- AC6：`/team` 查询和删除不调用 LLM。
- AC7：`gradlew test` 与 `gradlew shadowJar` 通过。
- AC8：`Agent(team_name=...)` 在 in-process 后端创建 Worktree、成员记录和后台任务，完成后可续派。
- AC9：tmux/iTerm2 命令均包含 `--team-member` 协议；runner 能持续处理 mailbox 与 shutdown。
- AC10：Coordinator 双开关缺一不可，启用后 Write/Edit 不出现在工具定义中。
- AC11：Lead 可收到完成/计划消息；批准计划会真实切换成员 PermissionMode。
