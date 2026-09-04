# SubAgent 机制 Plan

## 架构

- `subagent`：角色定义、YAML/Markdown 解析、三层 Catalog、Fork 消息、工具过滤、隔离 Session、统一 Agent 工具。
- `task`：运行句柄、后台任务状态、完成提醒以及 TaskList/Get/Stop/SendMessage。
- `agent.AgentLoop`：新增 Builder、角色 system prompt、固定权限模式、dontAsk、工具执行硬过滤和 runToCompletion。
- `llm.TurnContext`：携带可选 system prompt override；Anthropic/OpenAI 两端一致消费。
- `ChatApplication`：实现 SubAgentLauncher，创建隔离 ContextManager，选择 Provider，复用 Hook/Permission/Tool 基础设施。
- `Main`：加载 Catalog，注册任务工具并传入 Manager。

## 生命周期

```text
main Agent -> Agent tool
  -> resolve role/fork
  -> freeze allowed tools
  -> ChatApplication.create(SubAgentSession)
  -> foreground future OR TaskManager.launch
  -> independent AgentLoop + history + ContextManager
  -> final result / task notification
```

## 并发模型

- 子任务使用 Java 21 virtual thread。
- `RunningSubAgent` 把 future、cancel token、metrics 和 session 绑定在一起。
- 超时转后台采用 future adoption，不复制执行。
- Manager 使用 ConcurrentHashMap 与线程安全队列；同名映射采用后启动覆盖。
- SendMessage 仅允许 COMPLETED 状态，并在同一 BackgroundTask id 上启动下一轮。

## 安全模型

- 工具可见性只是第一层；AgentLoop 在执行前再次校验 frozen allow-set。
- 所有子 Agent 调用 `Agent` 都由运行时硬拒绝。
- `dontAsk` 位于危险命令、路径沙箱、规则层之后。
- 后台关闭时取消所有运行任务并关闭持有的专用 LLM client。

## 实现校准

- 原稿中的 Flow Publisher/BlockingQueue API 混用统一为 BlockingQueue + CompletableFuture。
- 原稿的“取消前台后 adopt”改为无损 future adoption。
- 角色名统一转小写，调用查找不区分大小写。
- Fork 保留 Agent 定义与“所有子 Agent 移除 Agent”的冲突，通过定义式移除、Fork 运行时拒绝解决。
- ESC 移交依赖新的 TUI 执行态协议，明确留后续，不与 Ctrl+C/ESC 取消语义混用。
