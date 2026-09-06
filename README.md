# Star Code

Star Code 是一个基于 Java 21 + Gradle 的终端 AI 助手，支持对话、工具调用和多步 Agent Loop。

## 功能概览

- 基础对话能力
- 文件检索与代码浏览工具
- Bash 执行能力（受开关与超时限制）
- 多步 Agent Loop：模型可在“观察 → 调用工具 → 查看结果 → 调整”之间自动循环
- SubAgent 委派：定义式角色、Fork 子会话和进程内后台任务
- Git Worktree 隔离：让指定 SubAgent 或主会话在独立工作副本中修改文件
- Agent Team：持久化团队、共享任务、邮箱、in-process/tmux/iTerm2 队友
- `/plan` 与 `/do` 两种工作模式

## 工作模式

### MCP 按需加载

默认以 `search_mcp_tools` 提供精简的工具名称/描述索引。模型搜索后，匹配工具的完整 schema 才加入下一轮请求；实际调用仍经过权限与 Hook 检查。加载状态属于每个 Agent，各子 Agent 独立。

设置环境变量 `STAR_CODE_MCP_LOADING=full` 可恢复全量 schema 模式；默认值为 `lazy`。服务端连接和 `tools/list` 仍在启动时执行，这项优化减少的是模型请求中的 schema 暴露，不减少 MCP 协议发现量。精简索引仍随工具数增长，按需搜索可能增加模型轮次；具体开销以 `benchmarks/mcp-lazy-v1/` 的对照实验为准。

### Agent Loop

Agent Loop 会在模型返回工具调用后自动继续执行下一轮：

1. 模型先生成一轮回复
2. 如果包含工具调用，系统执行这些工具
3. 工具结果回灌给模型
4. 模型根据结果继续推理，直到自然完成或触发停止条件

这样可以让任务自动完成，而不需要用户在每一步手动催促。

### SubAgent 委派

主 Agent 可以通过稳定的 `Agent` 工具把独立任务交给子 Agent：

- 内置 `general-purpose`、`explore`、`plan` 三种角色
- 支持 `~/.mewcode/agents/*.md` 和项目 `.mewcode/agents/*.md` 自定义角色，项目级同名定义优先
- 定义式子 Agent 使用独立上下文和受角色限制的工具集
- Fork 子 Agent 继承当前会话历史并强制进入后台执行
- `TaskList`、`TaskGet`、`TaskStop`、`SendMessage` 用于查看、取消和继续后台任务
- 子 Agent 复用危险命令、路径沙箱和权限规则，但保持独立的权限模式、上下文和 token 统计

可在配置中用 `enable_subagent_background: false` 禁止显式后台任务和 Fork。详细设计见 `specs/013-subagent-system/`。

### Git Worktree 隔离

在自定义 Agent frontmatter 中设置 `isolation: worktree` 后，该子 Agent 会在临时 Git Worktree 中运行：

- 子 Agent 的 Read/Write/Edit/Glob/Search/Bash 以独立副本为执行根目录
- 没有文件变更时自动删除临时 Worktree
- 有修改或新提交时保留目录和分支，并把位置返回给主 Agent review
- `/worktree create/list/enter/exit/remove` 可手动管理 Worktree
- 删除默认保护未提交修改和新提交，只有显式 `--discard` 才强制删除

Worktree 功能要求启动目录已经是至少有一个提交的 Git 仓库；否则 Star Code 正常启动，但该功能会显示为未启用。它是并发开发隔离，不是 Bash 的 OS 安全沙箱。详细设计见 `specs/014-worktree-isolation/`。

### Agent Team

`TeamCreate` 创建持久化团队，随后可通过 `Agent` 工具传入 `team_name` 派生队友。队友在独立 Git Worktree 中运行，并使用 `TaskCreate`、`TaskUpdate`、`TaskList`、`TaskGet` 与 `SendMessage` 协作。

- Windows/普通终端自动使用进程内 virtual thread 后端。
- tmux 与 iTerm2 环境使用 `--team-member` 无界面 runner；成员完成后保持空闲，等待邮箱续派。
- Lead 在后台轮询 mailbox，消息会显示在终端，并在下一次模型迭代作为结构化提醒注入。
- Plan 队友完成计划后发送审批请求；Lead 用 `SendMessage` 发送 `plan_approval_response` 后才切到默认权限继续执行。
- `/team list`、`/team info <name>`、`/team delete <name> [--force]` 是不消耗 token 的本地命令。

Coordinator Mode 默认关闭，需要配置与环境变量同时开启：

```yaml
features:
  coordinator_mode: true
  fork_teammate: false
```

PowerShell 启动前设置 `$env:STAR_CODE_COORDINATOR_MODE = "1"`。开启后 Lead 不能直接使用 `write_file`/`edit_file`，应把实现任务委派给团队成员。详细设计见 `specs/015-agent-team/`。

### `/plan` 与 `/do`

Star Code 提供两种常用模式：

| 命令 | 作用 | 工具范围 | 典型用途 |
|---|---|---|---|
| `/plan` | 生成计划 | 只读工具 | 分析代码、搜索信息、查看结构 |
| `/do` | 执行计划 | 全工具 | 修改代码、落地实现、验证结果 |

#### `/plan`

- 只暴露只读工具：`Read`、`Glob`、`Search`
- 适合先做分析、梳理思路、输出方案
- 不会执行写入操作

#### `/do`

- 恢复完整工具集
- 用于执行最近一次计划
- 适合真正修改代码并完成任务

## 系统提示工程化

Star Code 的系统提示不是单一长文本，而是按职责拆分后再统一组装。这样做的好处是：

- 更容易维护和扩展
- 不同职责之间边界清晰
- 更容易为不同模式注入不同约束
- 减少提示冲突，提高行为稳定性

### 组成方式

系统提示由 `SystemPromptAssembler` 负责组装，当前包含这些模块：

| 模块 | 作用 |
|---|---|
| `identity` | 运行时配置的基础身份/角色说明 |
| `system-constraints` | 安全边界与行为底线 |
| `task-mode` | 终端编码代理的任务方式 |
| `action-execution` | 先读后改、修改后验证 |
| `tool-use` | 优先使用专用文件工具 |
| `tone` | 输出风格要求 |
| `text-output` | Markdown 与输出规范 |
| `custom-instructions` | 预留的自定义指令槽位 |
| `skills-catalog` | 已发现 Skill 的名称与描述索引 |
| `long-term-memory` | 预留的长期记忆槽位 |

### 使用说明

在实际使用中，这意味着模型会被持续引导去遵守以下规则：

- 先观察，再决定下一步
- 改文件之前先读当前内容
- 优先使用专用工具，而不是直接依赖 Bash
- 发现问题要如实报告，而不是猜测
- 输出保持简洁，并尽量使用 Markdown

### 计划模式提醒

`/plan` 模式下还会注入周期性的系统提醒，由 `SystemReminder` 生成。它会强调：

- 只使用只读工具
- 产出具体计划
- 不修改文件，不运行命令
- 不直接回答提醒本身

这个提醒会在首轮和后续固定间隔再次出现，用来防止模型在计划阶段偏离任务边界。

### 如何扩展

如果你要继续增强系统提示工程化能力，通常有三种入口：

1. **新增提示模块**：在 `SystemPromptAssembler` 中增加新的 `PromptModule`
2. **调整计划提醒**：修改 `SystemReminder` 的提醒文本或节奏
3. **补充测试**：在 `SystemPromptEngineeringTest` 中增加覆盖，保证排序、稳定性和模式行为不回退

### 实际使用建议

- 如果你还不确定怎么做，先用 `/plan`
- 如果你已经有明确方案，再切到 `/do`
- 如果任务涉及修改文件，优先要求模型先读取目标文件，再给出编辑方案
- 如果你在排查行为问题，可以先检查系统提示模块和提醒逻辑是否生效

## Hook 生命周期自动化

Star Code 会在会话、用户提交、模型请求、工具调用、上下文压缩和自然停止等固定时刻分派 Hook。项目级配置位于 `.mewcode/hooks.yaml`，用户级配置位于 `~/.mewcode/hooks.yaml`；示例见 `.mewcode/hooks.example.yaml`。

Hook 由事件、可选条件和动作组成，支持：

- exact、glob、regex、not 条件匹配
- shell、prompt、HTTP 动作，以及暂未执行的 subagent 占位动作
- `only_once`、`async` 和 `timeout`
- 对用户提交和已获权限的工具调用进行明确拦截
- 把工具拦截作为 `HOOK_BLOCKED` 结果回灌模型，而不是终止 Agent Loop

使用 `/hooks` 可查看当前加载的规则和配置来源。Hook 不会绕过危险命令黑名单、路径沙箱、权限规则或人在回路审批。


## 安全边界

Agent Loop 不会放宽现有安全限制：

- 文件工具只能访问启动工作区
- 不允许绝对路径、`..` 逃逸或符号链接逃逸
- 写入/编辑需要 `STAR_CODE_ALLOW_WRITES=true`
- Bash 需要 `STAR_CODE_ALLOW_BASH=true`
- Bash 仍受超时限制，不是完整 OS 沙箱

## 执行上限与停止条件

为了避免无限循环，Agent Loop 会在以下条件下停止：

- 迭代上限：10
- 工具调用上限：50
- 连续未知工具阈值：2
- 用户取消
- Provider / 协议错误

## 事件与进度

运行过程中会输出：

- 迭代开始
- 文本增量
- 工具开始 / 工具结束
- 每轮与会话 Token 用量
- 完成 / 取消 / 错误

## 已知限制

- 不支持完整 OS 沙箱
- 不支持计划审批门
- 不支持跨会话持久化计划
- 后台 SubAgent 不跨进程持久化，也不提供 Worktree 文件隔离
- 当前 TUI 的 Esc 仍用于取消主轮，不支持把前台 SubAgent 手动移交后台
- 不支持多模态
- 工具结果不会流式输出

## 开发说明

更多实现细节可参考 `specs/003-agent-loop/spec.md` 和 `specs/003-agent-loop/implementation-report.md`。
# Session permission grants

The permission dialog supports Allow once, a persistent local rule, Deny once, and Allow for this session (key4). Session approval applies to the same tool and file path, or exact command/remote arguments, within the same execution directory, actor and permission mode. File content may change under a granted file-edit scope. It does not grant other files, commands, tools or Worktrees.

Session grants are held in memory and cleared when starting or resuming a session. Path checks, the command blacklist and configured rules still run before a cached grant. An explicit session grant permits repeating its scope; it is not a general classifier of safe commands. Shell execution is not an OS sandbox. See `benchmarks/permission-v1/PLAN.md` for the limited deterministic policy replay.
