# ch14 Worktree 隔离实现报告

## 完成内容

- 新增 `com.starcode.worktree`，实现 slug、元数据、session、Git helper、创建后初始化和完整生命周期。
- Worktree 固定落在 `.mewcode/worktrees/<flatSlug>`，使用 `worktree-<flatSlug>` 独立分支。
- 新增纯文件系统快速恢复，并在 Git 管理目录保存不污染工作区的 sidecar 元数据。
- Read/Write/Edit/Glob/Search/Bash 支持不可变 explicit cwd；相对路径被限制在 active Worktree 根。
- PermissionManager 使用每次 AgentLoop 的执行上下文完成路径沙箱检查。
- SubAgent frontmatter 支持 `isolation: worktree`，自动完成 create、notice、run、autoCleanup。
- 隔离 SubAgent 强制前台；无变更自动清理，有变更或清理失败时保留并报告目录/分支。
- Slash 注册中心新增受控参数命令元数据和 `/worktree create/list/enter/exit/remove`。
- ChatApplication 恢复/切换 Worktree session 时重建 AgentLoop，并保留累计 token usage。
- Main 对非 Git 项目安全降级，并异步清理超过 24 小时的干净临时 Worktree。

## 安全校准

- 使用 `git worktree add -b` 并拒绝已有分支，避免 `-B` 重置用户分支。
- 继续拒绝工具绝对路径；cwd 注入不会绕过既有路径沙箱。
- 快速恢复拒绝符号链接目录，并验证真实目录、slug 和分支 sidecar。
- Git 检查错误 fail-closed；删除默认保护变更，只有 `--discard` 绕过。
- hooks 只在 `extensions.worktreeConfig=true` 时写 `--worktree` 配置，不修改共享配置。

## 自动验证

- `gradlew clean test shadowJar --warning-mode all`：成功。
- 当前全仓 51 个测试套件，174 项测试，0 失败、0 错误、0 跳过。
- 测试使用真实临时 Git 仓库覆盖创建、恢复、session、删除保护、autoCleanup、sweep 和 hooks。
- 集成测试证明 `isolation: worktree` 子 Agent 写入只落在副本，主目录文件不受影响。
- Shadow JAR 包含全部 `com.starcode.worktree` 类。

## 环境说明

当前 `C:\Users\Administrator\Desktop\project\star code` 还不是 Git 仓库，因此此目录启动时 Worktree 会显示为未启用。执行 `git init`、配置身份并产生至少一个提交后，才能进行真实 TUI 人工测试。

## 未包含

- Worktree 合并/冲突解决。
- Bash 级 OS 沙箱。
- 后台 Worktree SubAgent、Agent Team、跨进程任务持久化。
- 真实 Provider/TUI 人工端到端测试。
