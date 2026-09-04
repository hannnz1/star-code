# ch04 Agent Loop 当前实现完成度

## 总评

- 功能需求实现状态：**IMPLEMENTED**
- 自动验证状态：**174 项离线测试通过**
- 状态：结构化跨轮历史、统一工具超时、空响应错误、Provider 线程中断和终止配对已补齐；真实 Provider 人工验收不等于代码缺口

## 已完成

- `AgentLoop` 以最多 10 次迭代持续执行工具并回灌，直到自然完成。
- 50 次工具调用上限和连续 2 个未知工具回合上限。
- `AgentOutcome` 区分完成、迭代上限、工具上限、未知工具上限、取消和错误。
- `AgentEvent` 覆盖迭代、文本增量、完整模型回合、工具开始/结束、用量和终态。
- OpenAI/Anthropic 通过共同的 `LlmClient`、`Completion` 和 `ToolExchange` 接口接入。
- 连续只读工具通过 virtual-thread executor 并发，有副作用/未知工具串行。
- 批内结果按原始顺序发布并回灌。
- 权限拒绝、Hook 拦截和普通工具失败作为结构化结果回灌，Loop 可继续。
- 每轮与会话 Token 用量累计。
- Plan Mode 只暴露只读工具，`/do` 切回默认模式并发送执行提示。
- JLine 等待循环可读取 Esc/Ctrl+C；取消 token 会中断 Agent 虚拟线程、Provider 等待和可中断工具。
- `AgentOutcome` 保存全部 `ToolExchange`，主会话、SubAgent 和 Team 成员均按 user → assistant/calls → tool/results → final assistant 保存。
- 所有工具由 Registry 提供默认 30 秒 deadline，可由工具声明更短上限。

## 自动测试证据

`AgentLoopTest` 已覆盖：

- 多轮工具连环与自然完成；
- 迭代上限、工具上限和未知工具上限；
- Provider 错误转为错误结果；
- 启动前取消；
- Plan Mode 只读定义；
- 只读并发和结果保序；
- 权限/Hook 拒绝回灌后继续。

协议测试已覆盖 OpenAI 与 Anthropic 的分片工具参数、当轮回灌和跨用户回合结构化历史重放。当前完整项目测试结果为 51 个测试套件、174 个测试、0 失败。

## 仍需环境验收（不是已知代码缺口）

| 要求 | 状态 | 证据与影响 |
|---|---|---|
| 固定状态栏 | 适配实现 | 当前滚动式 JLine 用 Iteration/Token 状态行展示，符合权威 Spec 的替代约定 |
| Anthropic/OpenAI 真实 Loop E2E | 待人工 | 离线 HTTP 协议服务器和 Fake Loop 已覆盖；真实凭据不进入默认测试 |
| 不响应 interrupt 的第三方 Tool | best-effort | deadline 会返回结构化超时并 interrupt 工作线程；Java 无法安全强杀忽略中断的任意代码 |

## 完成度计算口径

章节状态使用仓库统一状态机：代码目标完成但尚缺真实 Provider 人工证据，因此标记 `IMPLEMENTED`，不标记 `VERIFIED`。
