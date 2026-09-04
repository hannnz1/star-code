# Star Code 全局架构契约

这些契约适用于 ch01–ch15。章节需求与本文件冲突时，以本文件和更新日期更晚的显式覆盖条款为准。

## A1：结构化消息是唯一会话事实源

Conversation 必须保存用户消息、普通助手消息、带工具调用的助手消息和工具结果消息。工具调用至少保留 call ID、工具名、参数和 Provider 继续会话所需的不透明状态；工具结果至少保留 call ID、工具名、正文、错误状态、错误码和截断状态。

Agent Loop、Context Manager、Session Writer、Session Loader、Fork SubAgent、Skill fork 和 Team transcript 必须使用同一结构化消息模型，不得分别维护互相不完整的影子历史。

## A2：工具调用必须闭合

每个进入已提交历史的 tool call 必须有且只有一个同 ID tool result。取消、权限拒绝、Hook 拦截、未知工具、超时和迭代/工具上限同样必须产生结构化结果。不得留下 Provider 下一轮无法接受的悬空调用。

## A3：JSONL 必须无损往返

在不考虑损坏尾行的正常场景下：

```text
Conversation snapshot -> JSONL -> SessionLoader -> Conversation snapshot
```

恢复后的角色、正文、工具调用顺序、调用 ID、参数、结果和错误状态必须等价。`compact` 标记只改变恢复起点，不得改变标记之后消息的结构。

## A4：上下文替换决策可恢复

工具结果的保留/替换决定和稳定 replacement 字符串属于会话状态。决定写入后必须追加持久化记录；恢复会话时重建 `seenIds` 和 replacement 映射。同一 ID 不得因进程重启或 `/resume` 产生另一版本预览。

## A5：运行入口共享核心编排

TUI、未来的 print 模式和 remote 模式只能消费统一 AgentEvent；不得复制 Agent Loop、权限、Hook、MCP 或上下文管理逻辑。

## A6：会话切换是事务

`/clear` 和 `/resume` 必须先完成目标 SessionContext、Writer、Conversation 和 ContextManager 的构造/验证，再原子替换当前引用，最后关闭旧 Writer。失败时继续使用原会话。

## A7：后续章节覆盖关系

- ch09 F9 的 `yyyyMMdd-HHmmss-xxxx` 替代 ch08 最初的 Unix 时间戳 session ID。
- ch14 F30 扩展 ch10 的零参数命令规则：只有 `acceptsArguments=true` 的命令可接收参数。
- ch13–ch15 不得降低 ch04 的历史闭合、ch06 的权限流水线或 ch08 的上下文恢复保证。

## A8：验收证据

每条 AC 必须映射到自动测试、人工步骤或明确的 `BLOCKED` 原因。完成度报告必须记录日期、平台、测试命令和结果，不使用无计算依据的主观百分比。
