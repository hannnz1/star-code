# SubAgent 机制 Spec

> Feature：013  
> 状态：IMPLEMENTED（ESC 手动移交后台已列入本章不做范围）  
> 适用项目：Star Code（Java 21 + Gradle）

## 背景

Star Code 的主 Agent 会把一次任务产生的中间观察都放在同一轮上下文中。独立探索、长时间扫描和并行工作既会污染主任务，也会阻塞用户继续交互。本章引入进程内 SubAgent：主 Agent 只看到一个稳定的 `Agent` 工具，具体角色和任务数量不改变主工具定义。

## 目标

- G1：通过统一 `Agent` 工具启动定义式或 Fork 式 SubAgent。
- G2：每个 SubAgent 拥有独立对话、ContextManager、token 统计、权限模式和取消信号；共享 Provider 配置、工具实现、权限规则、Hook 与工作区。
- G3：从内置、用户、项目三层 Markdown 定义加载角色，项目级覆盖用户级，用户级覆盖内置。
- G4：前台任务跑到底；显式后台与 Fork 立即返回 task ID；前台超过 120 秒时无损转入后台管理。
- G5：通过工具可见性、工具白/黑名单、后台白名单和运行时嵌套拒绝阻止递归委派。
- G6：后台完成结果作为 `<task-notification>` 在主 Agent 下一次模型请求中消费，不伪装成用户输入。
- G7：Skill fork 和 Agent 工具复用同一个 SubAgent Session/AgentLoop 构造底座。

## 角色定义

定义路径：

1. 内置：`classpath:/subagent/builtin/*.md`
2. 用户：`~/.mewcode/agents/*.md`
3. 项目：`<workspace>/.mewcode/agents/*.md`

按以上顺序加载，后者覆盖前者。插件来源枚举保留但本章不加载插件。

```yaml
---
name: explore
description: Read-only code explorer
tools: [read_file, glob, search_text]
disallowedTools: [write_file, edit_file]
model: haiku
maxTurns: 30
permissionMode: default
background: false
---

You are a read-only code exploration specialist.
```

约束：

- `name` 长度 1–32，仅字母、数字、连字符；加载后转小写，查询大小写不敏感。
- `description` 和正文必填。
- `model` 为 `inherit/haiku/sonnet/opus`；无对应配置时告警并继承当前 Provider。
- `maxTurns` 为 1–100。
- `permissionMode` 为现有四档或 SubAgent 专属 `dontAsk`。
- 非法用户/项目文件隔离并告警；内置资源非法则启动失败。

## Agent 工具

参数：

- `prompt`：必填任务文本。
- `description`：必填简短说明。
- `subagent_type`：可选；存在时解析定义角色，缺省时 Fork。
- `model`：可选覆盖角色模型。
- `run_in_background`：可选显式后台。
- `name`：可选稳定名称，供 `SendMessage` 续派。

定义式从空历史启动。Fork 克隆主会话的结构化历史和当前用户消息，包含完整 assistant tool call 与 tool result 配对；首个任务前加 `<fork_boilerplate>`。最近消息切片不得从 tool result 中间开始。

## 工具过滤

构造 SubAgent 时按顺序冻结工具集合：

1. 从主 Registry 全集开始。
2. 定义式移除 `Agent`。
3. 后台任务只保留基础工具、MCP 工具和 Skill 工具。
4. 应用角色 `disallowedTools`。
5. 非空 `tools` 白名单做最终交集。

Fork 为保持父工具定义前缀可以保留 `Agent` 定义，但 AgentLoop 运行时无条件返回 `SUBAGENT_NESTING_DENIED`。主 Agent 的工具集合始终稳定。

## 权限

- 黑名单、路径沙箱、持久 allow/deny 规则仍由共享 PermissionManager 执行。
- 每个子会话持有自己的角色权限模式，不能改变主 TUI 模式。
- `dontAsk` 仅把最终 Ask 转为 Allow，不能覆盖黑名单、沙箱或显式 deny。
- 需要用户确认时沿用主 TerminalUi 审批器，提示包含 `[SubAgent <name>]`。
- “永久允许”写入原有本地权限层，主/子 Agent 后续均能命中。

## 后台任务

- `TaskList`：列出任务 id、name、status、tool_count、last_activity。
- `TaskGet`：返回完整状态、结果、错误、时间和 token。
- `TaskStop`：请求取消运行任务。
- `SendMessage`：给已完成的命名 SubAgent 追加任务并复用原会话。

前台任务一开始就在独立 virtual thread 中运行。120 秒超时只是把同一个 future 注册进 Manager，因此不会取消、重启或丢失中间状态。后台任务仅存活于当前进程。

`enable_subagent_background: false` 时，显式后台和 Fork 返回结构化错误；定义式仍可前台运行。

## 本章边界

- 不实现 Worktree 文件隔离。
- 不实现 Agent Team 或平等多 Agent 编排。
- 不持久化后台任务。
- 不实现插件角色加载。
- 不把子 Agent 用量并入 `/status`。
- 当前滚动式 TerminalUi 中 ESC 仍表示取消当前主轮，不实现“前台子任务手动移交后台”；显式后台和超时转后台已实现。

## 验收标准

- AC1：内置 general-purpose/explore/plan 可解析，三层覆盖和坏文件隔离通过。
- AC2：主 Registry 始终只有一个 `Agent` 工具；定义文件增减不改变 schema。
- AC3：定义式任务返回子 Agent 最终文本；未知类型返回 `UNKNOWN_SUBAGENT_TYPE`。
- AC4：Fork 克隆父历史、注入 Boilerplate、强制后台并阻断嵌套 Agent。
- AC5：角色工具白/黑名单、后台白名单、MCP 前缀保留通过测试。
- AC6：角色 system prompt 通过 TurnContext 覆盖 Provider system prompt。
- AC7：`dontAsk` 不弹审批；default Ask 在主 TUI 显示 SubAgent 来源。
- AC8：显式后台立即返回 `async_launched`；超时返回 `timed_out_to_background`。
- AC9：TaskList/Get/Stop/SendMessage 返回结构化结果，子任务失败不影响主程序。
- AC10：后台终态在下一次主模型请求中出现 `<task-notification>`，不写入用户可见 Conversation。
- AC11：Skill fork 复用 SubAgentSession 与 AgentLoop Builder，既有 Skill 行为不退化。
- AC12：完整单元测试和 Shadow JAR 构建通过。
