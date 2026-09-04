# Star Code Spec → Code 实现审计

审计日期：2026-08-27  
验证基线：Java 21、Gradle Wrapper、Windows；`clean test shadowJar` 成功。  
自动测试证据：51 个测试套件，174 项测试，0 失败、0 跳过。

## 结论

- ch01–ch15 的权威 Spec 中，仓库内可实现且不依赖外部平台的主功能已完成。
- 当前整体代码实现可评为 **IMPLEMENTED**，但不能评为全项目 **VERIFIED**：真实 Anthropic、真实远程 HTTP MCP、联网 GitHub Skill 安装、真实 Git/TUI Worktree、Linux tmux 和 macOS iTerm2 仍需对应环境人工验收。
- 本轮修复了此前最影响完整性的四条断链：结构化工具历史跨轮丢失、JSONL 恢复降级、replacement 决策无法恢复、取消/工具统一超时不闭环。

## 章节追踪

| 章节 | 代码状态 | 主要实现证据 | 自动验证/剩余证据 |
|---|---|---|---|
| ch01 对话 | IMPLEMENTED | `llm/AnthropicClient`、`OpenAiResponsesClient`、`TerminalUi` | 离线协议测试；真实双 Provider 待人工 |
| ch02 工具 | IMPLEMENTED | `tool/ToolRegistry`、六个 builtin Tool、`ToolContext` | 工具、路径、截断、Bash、统一 deadline 测试 |
| ch03 | SUPERSEDED | — | 由 ch04 替代 |
| ch04 Agent Loop | IMPLEMENTED | `AgentLoop`、`AgentEvent`、`AgentOutcome`、`ToolExchange` | 多轮、并发、上限、空响应、取消中断、双协议历史重放 |
| ch05 Prompt | IMPLEMENTED | `prompt/SystemPromptAssembler`、模块与环境上下文 | Prompt 单元测试 |
| ch06 权限 | IMPLEMENTED | `permission/PermissionManager` 五层流水线 | 模式、规则、沙箱、审批、黑名单测试 |
| ch07 MCP | IMPLEMENTED | `mcp/McpManager`、配置、远端 Tool 适配 | stdio everything 已人工；真实 HTTP server 待人工 |
| ch08 Context | IMPLEMENTED | `context/ContextManager`、会话 replacement ledger | UTF-8 阈值、账本重建、消息分组、摘要与锚点测试 |
| ch09 记忆/会话 | IMPLEMENTED | `instructions`、`session`、`memory`、`Conversation` | 结构化 JSONL roundtrip、坏行、清理、Memory CRUD；Resume TUI 待持续人工 |
| ch10 Slash | IMPLEMENTED | `command` registry/dispatch、`ui/CompletionMenu` | 冲突、大小写、参数拒绝、补全与内置命令测试 |
| ch11 Skill | IMPLEMENTED | `skill`、Load/Install Skill Tool、动态命令、调用审计 | 两格式、覆盖、热重载、fork 边界、安全 URL、审计测试；联网安装待人工 |
| ch12 Hook | IMPLEMENTED | `hook` loader/engine/actions/payload | 匹配、阻断、异步、超时、事件测试 |
| ch13 SubAgent | IMPLEMENTED | `subagent`、`task`、Agent Tool、内置角色 | 隔离、过滤、后台、续派、通知、取消测试；真实 Provider 待人工 |
| ch14 Worktree | IMPLEMENTED | `worktree` manager/session/git helpers、slash 接入 | 临时 Git 仓库自动测试；真实项目 TUI 待人工 |
| ch15 Team | IMPLEMENTED | `team`、mailbox、tasks、backend、Team tools/runner | in-process 和后端 argv 自动测试；tmux/iTerm2 待平台验收 |

## 本轮代码补漏

1. `ChatMessage` 从纯文本二元角色扩展为 USER/ASSISTANT/TOOL，保存 tool calls、tool results 和 provider protocol state。
2. `AgentOutcome` 保存本次 run 的全部 `ToolExchange`；主 Agent、SubAgent、Team member 和 Fork copy 不再丢工具历史。
3. Conversation 在用户提交、完整工具交换和最终答复时实时追加；工具上限也生成覆盖全部 call ID 的结构化失败结果。
4. SessionWriter/Loader 无损写回结构化 JSONL；坏行跳过，悬空 assistant/tool 交换截断。
5. Anthropic 与 OpenAI 新用户回合均可重放历史 tool call/result，不再只重放最终文本。
6. ContextManager 估算结构化工具正文，近期原文不切断工具配对，PTL 按真实用户消息组丢弃。
7. replacement/keep 决定写入 session 账本；重建 ContextManager 时恢复冻结决定。
8. CancellationToken 支持取消回调，异步 Agent 取消会 interrupt Provider 工作线程。
9. ToolRegistry 为所有工具提供默认 30 秒 deadline 和结构化 TOOL_TIMEOUT/CANCELLED。
10. Skill 调用写入 session 级审计 JSONL；recent fork seed 不从 tool result 中间截断。
11. 会话过期清理从错误的 90 天修正为 Spec 要求的 30 天。
12. SubAgentTaskManager 关闭时等待完成回调临界区，修复 Windows 临时目录偶发清理竞态。

## 仍未宣称通过的验收

- 真实 API 凭据下 Anthropic/OpenAI 长流取消及长会话压力。
- 真实 Streamable HTTP MCP server 的 headers/session/DELETE 行为。
- 联网 GitHub Contents API 安装 Skill。
- 非临时真实 Git 仓库中的完整 `/worktree` TUI 流程。
- Linux tmux 与 macOS iTerm2 pane 的 spawn/wake/kill/持续 mailbox 行为。

这些项目属于环境证据缺失，不应伪装成自动测试通过；完成后应把对应章节从 IMPLEMENTED 升级为 VERIFIED。

