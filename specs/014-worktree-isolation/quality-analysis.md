# ch14 Worktree Spec 质量分析

## 评分

原稿约 **7.8/10**，校准后约 **9.1/10**。

## 优点

- 清楚识别了 SubAgent 状态隔离之后仍存在的共享文件系统冲突。
- lifecycle、变更保护、explicit cwd、自动清理和 TUI 管理形成完整闭环。
- 对路径遍历、失败隔离、prompt cache 稳定和 fail-closed 有明确要求。
- 验收标准大量使用真实 Git 仓库，具备可测试性。

## 原稿问题与修正

- 文档仍使用 ch13，但它依赖已完成的 ch13 SubAgent；本地归档为 ch14。
- 包名、`MewCodeModel`、ToolContext 和 AgentTool 不是 Star Code 的真实接口；已映射为 `com.starcode`、`ChatApplication` 和 `SubAgentTool`。
- `git worktree add -B` 会重置已有分支，可能破坏用户提交；改为 `-b` 并拒绝分支冲突。
- 纯 `.git/HEAD/refs` 恢复无法还原 manual、base commit 和 created；增加 Git 管理目录 sidecar，仍保持无子进程恢复。
- Worktree 的 `core.hooksPath` 默认属于共享仓库配置，直接设置会影响主工作区；仅在 `extensions.worktreeConfig=true` 时写 per-worktree 配置。
- 原稿允许绝对路径直接通过，与既有路径沙箱冲突；继续拒绝绝对路径，并把相对路径限制在 active cwd。
- “所有状态变更持锁”与“Git 操作不持锁”矛盾；用 `creating` 预约名称，锁只保护内存状态，Git 在锁外执行。
- `HEAD --not --remotes` 在无 remote 的仓库会把初始历史全部判为未推送，导致永不清理；以创建基线后的提交为判断依据。
- `isolation + background` 若仍允许 120 秒转后台，会失去确定的清理时点；本章明确强制前台跑到底。

## 风险

- Worktree 隔离不能阻止 Bash 使用绝对路径访问主目录。
- 多个 Star Code 进程同时管理同一仓库不在本章保证范围内。
- Windows 创建符号链接可能需要管理员或 Developer Mode；失败只影响依赖目录复用。
- 保留的临时 Worktree 需要用户 review 后手动删除或合并。
