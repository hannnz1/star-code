# ch04 Agent Loop 完善 Plan

## 架构边界

```text
ChatApplication / TerminalUi
        │ user input + cancel keys
        ▼
AgentLoop ── AgentEvent ──► UI renderer
   │
   ├─ LlmClient.stream / continueWithTools
   │       ├─ OpenAiResponsesClient
   │       └─ AnthropicClient
   │
   └─ ordered tool scheduler
           ├─ concurrent read-only batch
           └─ serial side-effect call
```

Provider 负责协议编解码和流收集；AgentLoop 负责迭代与工具编排；ToolRegistry 负责执行；UI 只消费事件。后续整改不得把权限、终端或 Provider SDK 细节塞进 AgentLoop。

## 完善阶段

### P1：终止路径一致性

- 在发布 tool-call assistant 回合前完成工具总量校验，或在触顶时为所有调用补 `TOOL_LIMIT` ToolResult。
- 空响应返回结构化错误。
- 为取消时尚未执行的调用统一生成 `CANCELLED` 结果。

### P2：取消传播

- 扩展 `LlmClient` 请求句柄或让异步请求接受 CancellationToken。
- `TerminalUi` 取消时同时设置 token、取消 future 并中断运行线程。
- Bash/远端调用终止子进程或 HTTP 请求；本地工具在中断时快速返回。

### P3：统一工具超时

- 在 Agent 调度层对每个 Future 应用 30 秒 deadline。
- 超时取消任务并产生 `TOOL_TIMEOUT`，不得中断整个 Loop。
- 并发批仍按原始索引回收结果。

### P4：验证矩阵

- 增加 mid-stream、mid-tool、mid-approval 取消测试。
- 增加工具上限无悬空结果测试。
- 用本地 Mock HTTP 分别驱动 OpenAI/Anthropic 完整多轮 AgentLoop。
- 增加高并发批和反复取消后的线程/进程泄漏测试。

### P5：交付证据

- 退出正在运行的旧 JAR 后执行 clean test + shadowJar。
- 按 checklist 完成人工 Esc/Ctrl+C、`/plan`/`/do` 和两个 Provider 冒烟。
- 把验证日期、命令和结果写回 implementation-report/checklist。
