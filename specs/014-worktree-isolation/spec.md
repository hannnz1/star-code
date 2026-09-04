# Worktree 隔离 Spec

> Feature：014  
> 状态：IMPLEMENTED（人工 Provider/TUI 验证待完成）  
> 适用项目：Star Code（Java 21 + Gradle）

## 背景

ch13 已隔离 SubAgent 的消息、上下文账本、权限模式、取消信号和 token 统计，但主 Agent 与子 Agent 仍可能同时修改同一工作目录。本章使用 Git Worktree 为需要隔离的定义式 SubAgent 提供独立文件副本，也提供 `/worktree` 命令供用户手动管理。

Worktree 是并发开发隔离，不是安全沙箱：文件工具仍受 Star Code 路径沙箱约束；Bash 只把起始目录设为 Worktree，不能阻止命令主动访问其他 OS 路径。

## 目标

- G1：封装创建、恢复、进入、退出、删除、自动清理和过期清理生命周期。
- G2：严格验证 slug，所有管理目录固定在 `<repo>/.mewcode/worktrees/`。
- G3：不改变 JVM 进程 cwd，通过不可变 `ToolContext` 给文件工具和 Bash 注入执行根目录。
- G4：`isolation: worktree` 的定义式 SubAgent 自动创建隔离副本，结束后无变更删除、有变更保留。
- G5：提供 `/worktree create/list/enter/exit/remove`，不进入对话历史。
- G6：工具 schema 和主 Agent 工具列表保持稳定。

## 功能需求

### Slug 与目录

- F1：slug 非空、最长 64；允许 `/` 分段；每段仅 `[A-Za-z0-9._-]`，拒绝空段、`.`、`..`、首尾 `/`。
- F2：`flatten` 把 `/` 替换为 `+`；目录为 `.mewcode/worktrees/<flat>`，分支为 `worktree-<flat>`。
- F3：创建分支使用 `git worktree add -b`。若同名分支已经存在则拒绝，不允许自动重置已有分支。

### Manager 与恢复

- F4：`WorktreeManager` 只接受 Git 仓库根目录；失败由 Main 降级为未启用。
- F5：内部 `active`/`creating` 状态由单一 `ReentrantLock` 保护，耗时 Git 进程不持锁。
- F6：创建后记录 name/path/branch/base/head/created/manual；元数据写到 Worktree 的 Git 管理目录，不污染工作区。
- F7：启动扫描已有目录，通过 `.git` 指针、HEAD、refs/packed-refs 和 sidecar 元数据纯文件系统恢复，不启动 Git 子进程。
- F8：session 保存到 `.mewcode/worktree_session.json`；原子临时文件替换，不支持原子移动的平台安全降级；`null` 表示无会话。
- F9：session JSON 损坏或目录消失时告警并清空，不阻止启动。

### 创建后初始化

- F10：best-effort 复制 `.mewcode/config.yaml` 和 `.mewcode/settings.local.yaml`。
- F11：best-effort 链接 `node_modules`、`.venv`、`vendor`；平台不支持符号链接时只告警。
- F12：读取 `.worktreeinclude` glob，复制被 Git 忽略且匹配的普通文件。
- F13：只在仓库已启用 `extensions.worktreeConfig` 时设置 `core.hooksPath --worktree`，避免修改共享仓库配置。

### 生命周期与变更保护

- F14：`enter` 记录原目录、原分支/HEAD、Worktree 路径和 UUID，不调用 chdir。
- F15：`exit KEEP` 只退出；`exit REMOVE` 和独立 `remove` 默认检查变更。
- F16：变更定义为 `status --porcelain` 非空或 `baseCommit..HEAD` 有提交；Git 检查失败时 fail-closed，按有变更处理。
- F17：只有显式 `--discard` 可以绕过删除保护。
- F18：临时 Worktree 无变更时自动删除，有变更时保留路径与分支；手动 Worktree 永远不自动删除。
- F19：启动后台扫描超过 24 小时且名字匹配 `agent-a[0-9a-f]{7}` 的干净临时 Worktree；当前会话和有变更目录跳过。

### explicit cwd

- F20：`ToolContext` 增加 `withCwd`、`cwd`、`executionRoot`、`resolvePath` 和相对显示方法。
- F21：cwd 必须是真实存在且位于原 workspace 沙箱内部的目录。
- F22：绝对工具路径仍然拒绝；相对路径必须同时位于 active cwd 与原 workspace 内，不能借 `..` 回到主目录。
- F23：Read/Write/Edit/Glob/Search/Bash 使用 executionRoot；Bash 使用 `ProcessBuilder.directory`。
- F24：PermissionManager 在路径沙箱层使用本次 AgentLoop 的 ToolContext，规则表达式与 schema 不变。

### SubAgent

- F25：`SubAgentDefinition` 增加 `isolation`，合法值为空或 `worktree`；非法值告警并回落为空。
- F26：隔离角色使用 `agent-a<7hex>` 创建临时 Worktree，把 `<worktree-context>` 提示加到任务前。
- F27：launcher 用 Worktree ToolContext 构造独立 AgentLoop；父目录文件不被子 Agent 的文件工具修改。
- F28：隔离任务本章强制前台跑到底，忽略角色/background 请求及 120 秒自动转后台；取消信号仍然有效。
- F29：成功、失败或取消后都尝试 autoCleanup；有变更或清理失败时把保留位置追加到工具结果。

### Slash 命令

- F30：命令解析器保留参数尾巴，但只有显式声明 `acceptsArguments` 的命令能接收参数；原有零参数命令行为不变。
- F31：`/worktree create <slug>` 创建 manual Worktree。
- F32：`/worktree list` 输出 name/path/branch/active/manual。
- F33：`/worktree enter <slug>` 切换主 Agent 的 ToolContext，并持久化 session。
- F34：`/worktree exit [--remove] [--discard]` 退出当前 Worktree。
- F35：`/worktree remove <slug> [--discard]` 删除非当前 Worktree。

## 非功能需求

- N1：Git 命令禁用交互式凭据提示，30 秒超时；错误不泄漏凭据。
- N2：创建后初始化单项失败不回滚已成功的 Worktree。
- N3：所有删除目标必须验证位于 manager 的 worktreeDir 内。
- N4：Main 不是 Git 仓库时正常启动，只禁用 Worktree。
- N5：现有权限、Hook、MCP、Skill、SubAgent 和上下文测试不退化。
- N6：Windows 符号链接失败允许降级，核心 Worktree 生命周期必须跨平台。

## 不做的事

- Worktree 合并、cherry-pick 或冲突解决。
- Worktree 间文件同步、Watcher 和 Agent Team 编排。
- 把 Worktree 当作 Bash/OS 安全沙箱。
- 后台 `isolation: worktree`；本章隔离 SubAgent 强制前台。
- 跨 Star Code 进程协调同一 session 文件。

## 验收标准

- AC1：slug 合法/非法及 flatten 测试通过。
- AC2：真实临时仓库中创建普通与嵌套 Worktree，目录和分支正确。
- AC3：快速恢复不调用 Git，manual/base/head 元数据保持。
- AC4：配置与 `.worktreeinclude` 文件复制；symlink/hooks 按平台与仓库能力 best-effort。
- AC5：enter 不改变 JVM cwd，session JSON 可恢复和清空。
- AC6：有变更时默认拒绝删除，`--discard` 成功删除目录和分支。
- AC7：autoCleanup 和 sweep 仅删除干净临时 Worktree。
- AC8：六个核心工具在注入 cwd 后只操作 Worktree，schema 不新增 cwd。
- AC9：`isolation: worktree` 子 Agent 写文件不影响主目录，结果包含保留位置。
- AC10：`/worktree` 五个子命令正确分发，其他 slash 命令仍拒绝参数。
- AC11：完整 JUnit 和 Shadow JAR 构建通过。
