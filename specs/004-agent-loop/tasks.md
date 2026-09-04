# ch04 Agent Loop 完善 Tasks

## T1：空响应分类

- 文件：`agent/AgentLoop.java`、`agent/AgentLoopTest.java`
- 在 `toolCalls().isEmpty()` 分支先检查 `text().isBlank()`。
- 输出 `EMPTY_MODEL_RESPONSE` 事件和 `ERROR` outcome。

## T2：工具上限历史配对

- 文件：`agent/AgentLoop.java`、`ChatApplication.java`、会话测试
- 将总量校验前移到对 assistant tool calls 的持久化之前，或补齐结构化拒绝结果。
- 断言 JSONL 不出现无法配对的末尾 tool call。

## T3：统一工具超时

- 文件：`agent/AgentLoop.java`、`Tool` 抽象、测试 Fake Tool
- 为串行调用和并发批统一应用默认 30 秒 deadline。
- 超时返回 `TOOL_TIMEOUT` 并继续下一轮。
- 取消超时 Future，验证不影响结果顺序。

## T4：Provider 取消句柄

- 文件：`llm/LlmClient.java`、两个 Provider、`AgentLoop.java`、`TerminalUi.java`
- 让正在进行的请求可响应 token/interrupt，而不是只在请求返回后检查。
- 增加阻塞 Mock HTTP 测试，Esc/Ctrl+C 后请求及时结束。

## T5：运行中工具取消

- 文件：`agent/AgentLoop.java`、`BashTool.java`
- 取消尚未完成的并发 Future；Bash 终止进程树。
- 为未完成 call ID 补 `CANCELLED` ToolResult。

## T6：双协议完整 Loop 集成测试

- 文件：`llm/ProtocolToolFlowTest.java` 或新增 `AgentLoopProtocolTest.java`
- OpenAI 和 Anthropic 各模拟至少两轮工具调用再自然完成。
- 验证 tool call ID、参数、结果、用量及事件顺序。

## T7：资源泄漏与压力测试

- 连续运行并取消多批只读工具。
- 验证执行器、virtual thread、HTTP 请求和 Bash 子进程最终结束。

## T8：发布验证

```powershell
cd "C:\Users\Administrator\Desktop\project\star code"
.\gradlew.bat clean test shadowJar --warning-mode all
java -jar build\libs\star-code.jar --version
```

执行前需退出正在使用该 JAR 的 Star Code 进程，避免 Windows 文件锁导致 `clean` 失败。
