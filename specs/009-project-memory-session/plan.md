# 项目记忆与会话持久化 Plan

> 状态：Ready for review。以下设计已适配当前 `com.starcode`、JLine、ContextManager、LlmClient 与 Gradle 项目。

## 当前项目映射

| 原始文档名称 | Star Code 实际名称/处理方式 |
|---|---|
| `com.mewcode.*` | `com.starcode.*` |
| `MewCode.java` | `src/main/java/com/starcode/Main.java` |
| `MewCodeModel` | `src/main/java/com/starcode/ChatApplication.java` |
| `Agent.java` | `src/main/java/com/starcode/agent/AgentLoop.java` |
| `Prompt.java` / `Modules.java` | `src/main/java/com/starcode/prompt/SystemPromptAssembler.java` / `PromptModule.java` |
| `compact.SessionContext` | 新建 `src/main/java/com/starcode/session/SessionContext.java`，再由现有 ContextManager 使用 |
| `SessionRuntime` | 不新增；回合计数放入 `MemoryManager`，会话状态放入 `ChatApplication` |
| Lanterna / tea / ActionListBox | 使用现有 `TerminalUi` + JLine raw-mode 选择器 |
| `Provider` | 使用现有 `LlmClient` |
| Maven `-Dtest` | 使用 Gradle `--tests` |

## 架构概览

| 包 | 职责 |
|---|---|
| `com.starcode.instructions` | 三层 MEWCODE.md 加载和安全 include |
| `com.starcode.session` | SessionContext、JSONL Writer、列表、恢复、清理 |
| `com.starcode.memory` | 笔记 Store、索引、异步 LLM 更新 |

现有模块改动：

- `prompt.SystemPromptAssembler` 接收 instructions/memory。
- `llm.Conversation` 升级为结构化事件与可选回调。
- `context.ContextManager` 改为依赖 SessionContext。
- `agent.AgentLoop` 自然完成后发布可供记忆触发的回合快照。
- `ChatApplication` 增加 `/resume` 和会话原子切换。
- `TerminalUi` 基于 JLine 实现会话选择，不引入 Lanterna。
- `Main` 串联指令、记忆、SessionContext、Writer 和后台清理。

## 核心类型

- `InstructionLoader`：`load()`、`loadFile(file,boundary,depth,chain)`。
- `SessionContext`：sessionId、sessionDir、toolResultDir、conversationPath、create/open/parseTime。
- `SessionEntry`：compact 或 user/assistant/tool JSONL 行。
- `SessionWriter`：create/open/append/writeCompact/appendAll/close。
- `SessionInfo`、`SessionCatalog`、`SessionLoader`、`SessionCleaner`。
- `NoteType`、`MemoryNote`、`MemoryUpdateAction`、`MemoryStore`、`MemoryManager`。
- `Conversation`：结构化消息列表、append/replace 回调、fromMessages。

## 启动流程

1. 加载主配置。
2. 加载三层 MEWCODE.md。
3. 初始化两级 MemoryStore 并读取索引。
4. 创建新的 SessionContext 和 SessionWriter。
5. 创建带 Writer 回调的 Conversation。
6. 后台清理过期新格式会话。
7. 连接 MCP、初始化权限与 TUI。
8. 选中 provider 后让 MemoryManager 复用该 LlmClient。

## 运行流程

- 用户、助手、工具结果事件追加 Conversation，并由回调写 JSONL。
- compact 先写标记，再追加压缩后的消息。
- Agent 自然完成后更新 turnCount；每 5 轮或命中关键词时提交异步记忆任务。
- MemoryManager 串行处理更新，校验 JSON 操作后原子更新笔记和 MEMORY.md。
- 成功更新后刷新内存中的索引快照，下一次请求使用新索引。

## `/resume` 事务

1. 空闲态进入 RESUMING。
2. 扫描并显示有效新格式会话。
3. 读取、校验、截断孤立工具调用。
4. 必要时压缩，必要时追加时间跨度提醒。
5. 先打开目标 Writer，再原子替换 Conversation/SessionContext/Writer。
6. 切换成功后关闭旧 Writer；失败时保留原会话。

## 关键技术决策

- JSONL 使用现有 Jackson。
- 终端选择器使用 JLine。
- include 和 memory 文件均先解析真实路径后验证边界。
- 所有 LLM 输出只能提出 memory 操作，执行层负责 schema、文件名、路径和秘密过滤。
- Writer 不与 Conversation 共用锁；回调在释放 Conversation 锁后执行。
- 恢复和 Agent run 使用同一会话状态锁。
- MemoryManager 只有一个更新任务在执行，退出最多等待 5 秒。

## 已确定的提示模块顺序

```text
identity              700
system-constraints    600
task-mode             500
action-execution      400
tool-use              300
tone                  200
custom-instructions   150
long-term-memory      120
text-output           100
active-skills          20
```

## 仍待产品决策

- 自动记忆默认开关、`/memory` 管理命令和强制忘记语义。
- 会话自动清理是否默认 30 天。
