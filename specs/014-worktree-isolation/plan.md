# Worktree 隔离 Plan

## 架构

- `com.starcode.worktree`：slug、Git helper、session store、post-create setup、manager 与生命周期报告。
- `com.starcode.tool.ToolContext`：增加不可变 executionRoot；六个内置工具读取该根。
- `com.starcode.permission.PermissionManager`：沙箱检查接收本次执行 ToolContext。
- `com.starcode.subagent`：定义解析 isolation；`SubAgentTool` 编排 create/run/cleanup。
- `com.starcode.command`：slash parser 支持受控参数命令；`WorktreeAccessor` 隔离命令层和 Git 实现。
- `com.starcode.ChatApplication`：恢复 active cwd、切换主 AgentLoop、保留累计 usage。
- `com.starcode.Main`：可选构造 manager，后台 sweep，失败降级。

## 关键流程

### 隔离 SubAgent

1. 主 Agent 调用稳定的 `Agent` 工具。
2. 角色 `isolation=worktree` 时生成临时名并创建 Worktree。
3. `ToolContext.withCwd(wt.path)` 构造子 AgentLoop。
4. 在任务前注入 `<worktree-context>`。
5. 子 Agent 前台跑到底。
6. 无变更自动删除；有变更保留并回传路径/分支。

### 手动进入

1. `/worktree enter` 持久化 session。
2. ChatApplication 用 active ToolContext 重建 AgentLoop，并转移累计 usage。
3. 所有工具相对路径以 Worktree 为根。
4. `/worktree exit` 恢复基础 ToolContext。

### 删除保护

1. 检查 porcelain 未提交状态。
2. 检查创建基线到 HEAD 的新提交。
3. 检查失败按“有变更”处理。
4. 仅显式 `--discard` 绕过。

## 依赖方向

`command -> WorktreeAccessor <- ChatApplication -> worktree`，worktree 包不依赖 Agent、TUI 或 command，避免循环依赖。
