# Feature 003 实现与测试报告

> 历史快照：本章已由 ch04 及后续全局契约替代。下述“待后续”描述的是当时版本，不代表当前实现。

## 已实现

- 最多 10 轮、50 次工具调用的 ReAct Agent Loop。
- 自然完成、迭代上限、工具上限、连续未知工具、取消令牌和 Provider 错误停止。
- AgentEvent：迭代、文本、模型轮完成、工具开始/结束、用量、完成、取消、错误。
- 虚拟线程异步入口。
- 连续只读工具并发，副作用工具串行；结果按原顺序发布和回灌。
- OpenAI Responses 与 Anthropic Messages 多批 ToolExchange 回灌。
- 双协议输入/输出 Token 用量提取及会话累计。
- `/plan` 只注入 Read/Glob/Search；`/do` 恢复完整工具并触发执行提示。
- Ctrl+C 连接取消令牌，阻止后续迭代。
- 长流式回答不再清除重印，避免重复显示。

## 自动测试

- 测试套件：9
- 测试用例：27
- 失败：0
- `gradlew test shadowJar --warning-mode all`：通过，无弃用警告

覆盖：多步自然完成、迭代/工具/未知工具上限、取消、Provider 错误、Plan Mode、只读并发与结果顺序、Token 累加、双协议工具分片和结果回灌、六工具及安全边界。

## 部分实现或待后续

- Ctrl+C 能停止后续循环，但 Java HttpClient 的正在进行请求没有显式 cancel handle。
- Esc 在请求期间尚不能取消；当前滚动式 JLine 不是持续读取按键的全屏事件 TUI。
- 工具调用/结果在当前 Agent run 内完整回灌；跨下一条用户消息只保存用户文本和最终助手文本。
- Plan Mode 跨当前进程保持，但计划不落盘、没有审批门。
- Token 用量以普通状态行展示，不是固定底栏。
- Anthropic thinking 签名/不透明 reasoning 状态仍未完整跨轮保存。
- Bash 具有开关、工作目录和超时，但不是 OS 沙箱。

## 人工验收

1. OpenAI：要求 Read → Edit → Read，确认自动多轮完成。
2. `/plan` 后提出修改任务，确认只读并产出计划；输入 `/do` 后执行。
3. 长文件列表确认不再出现流式版与 Markdown 版重复。
4. 等待/工具执行期间按 Ctrl+C，确认回到输入状态并可继续对话。
5. 有 Anthropic Key 时完成一次多步工具任务。
