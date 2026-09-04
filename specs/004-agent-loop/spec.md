# ch04 Agent Loop Spec（Star Code 权威版）

> 状态：IMPLEMENTED（自动测试已闭环；真实 Provider 取消路径待人工验收）

## 文档状态

- 章节编号：ch04
- 功能名称：Agent Loop
- 项目：Star Code（Java 21 + Gradle）
- 前置能力：多协议流式对话、六个内置工具、工作区安全基线
- 历史映射：早期实现曾放在 `specs/003-agent-loop/`，本目录是后续维护的唯一权威版本

## 背景

上一阶段只能完成“模型请求一批工具 → 执行 → 回灌 → 再请求一次”的单轮闭环；如果续答继续请求工具，调用会被丢弃。ch04 引入受限 ReAct 循环，让模型能够在一次用户任务中反复执行“思考 → 调用工具 → 观察结果 → 调整”，直到自然完成或触发明确停止条件。

本章只负责 Agent 编排，不降低已有的工作区路径限制、结果体量限制和命令超时。后续权限、上下文、会话、MCP、Skill 与 Hook 可以接入 Loop，但不得反向污染 Provider 适配层。

## 目标

- 支持自主多轮 ReAct 循环，不再丢弃续答工具调用。
- 以异步事件流隔离 Agent 与终端界面。
- 同时实时转发文本增量并收集完整模型回合。
- 连续只读工具并发，有副作用工具串行，结果保持模型原顺序。
- 为循环失控、未知工具、Provider 错误、工具上限和用户取消提供确定性停止条件。
- `/plan` 只暴露只读工具，`/do` 恢复全工具并立即执行计划。
- OpenAI Responses 与 Anthropic Messages 共享同一 Agent Loop。

## 功能需求

### F1：ReAct 主循环

每次迭代携带当轮工具定义请求模型。若返回工具调用，则执行、生成与调用 ID 一一对应的结果、追加到本次运行的协议历史并进入下一轮；若返回不含工具调用的文本，则作为最终答复自然完成。文本与工具调用同时出现时，文本仍作为该 assistant 工具回合的一部分保存，但只有无工具调用的回合可自然完成。

### F2：停止条件

Loop 至少支持以下终止状态，并通过明确事件与 `AgentOutcome` 状态返回：

1. `COMPLETED`：模型不再请求工具；
2. `ITERATION_LIMIT`：达到 10 次迭代上限；
3. `TOOL_LIMIT`：累计工具调用超过 50 次；
4. `UNKNOWN_TOOL_LIMIT`：连续 2 个回合的所有结果均为未知工具；
5. `CANCELLED`：用户取消或运行线程被中断；
6. `ERROR`：Provider、协议或不可恢复流错误。

模型既没有文本也没有工具调用时不得静默伪装成功，应返回可辨识的空响应错误。

### F3：异步事件流

Agent 对外输出以下不可变事件，界面不得依赖 Loop 内部字段：

- `IterationStarted(iteration)`
- `TextDelta(text)`
- `ModelTurnCompleted(text, toolCalls, usage)`
- `ToolStarted(call)`
- `ToolFinished(result)`
- `UsageUpdated(turn, session)`
- `Completed(text, iterations, usage)`
- `Cancelled(iteration)`
- `Error(code, message)`

事件顺序反映真实发生顺序；同一批工具的开始事件和结束事件均按模型调用顺序发布。

### F4：流式双路收集

Provider 适配器一边把文本增量转换为 `TextDelta`，一边组装完整文本、推理状态、Token usage 和分片工具调用。工具调用必须完整保留 call ID、工具名和拼接后的 JSON 参数。解析失败不得执行工具。

### F5：保序分批并发

按模型调用顺序扫描：连续只读工具组成并发批；有副作用或未知工具单独串行。批内可以乱序完成，但 `ToolFinished` 事件、`ToolExchange.results` 和回灌顺序必须恢复为原始调用顺序。不得为了提高并行度跨越写操作重排调用。

### F6：回灌与历史一致性

每个 assistant 工具回合后必须存在覆盖全部 call ID 的工具结果回合。权限拒绝、Hook 拦截、未知工具、参数错误、工具失败、超时和取消均使用结构化 `ToolResult` 回灌，不因单次工具失败中断 Loop。

在迭代上限、工具上限、取消或错误路径上，不得向后续 Provider 请求或持久化会话留下无法配对的工具调用。若调用已经对界面或会话发布但未执行，必须补 `CANCELLED` 或对应停止原因的结果。

### F7：用户取消

Agent 运行期间 Esc 或 Ctrl+C 取消当前 run，回到空闲状态且不退出进程；空闲状态 Ctrl+C 退出应用。取消信号必须阻止新迭代和新工具启动，并尽力中断：

- 正在读取 Provider 流的 HTTP 请求；
- 正在等待的权限审批；
- 正在运行的命令及其可控子进程；
- 并发批中尚未完成的任务。

取消后协议历史与 JSONL 会话仍合法，下一条消息可以继续。

### F8：Token 用量

每轮提取输入、输出、缓存创建和缓存读取 token；运行结果保存本轮累计值，Agent 实例维护当前会话累计值。缺失字段按零处理，不得重复累加同一个流尾 usage。

### F9：进度与可观测性

界面至少展示当前迭代、文本增量、工具开始/结束、错误、取消和会话累计 Token。滚动式终端可以用状态行替代固定底栏，但信息必须随迭代更新且不重复打印完整流式回答。

### F10：Plan Mode

`/plan` 将运行模式切到计划态，只向 Provider 传 `readOnly()==true` 的工具定义并注入计划提醒；模式跨轮保持。`/do` 固定切回默认模式，将内置执行提示作为普通 user 消息持久化，并立即启动一个新 run。

### F11：跨协议一致

OpenAI Responses 与 Anthropic Messages 必须通过相同 `LlmClient`、`Completion`、`ToolExchange`、`TokenUsage` 和 `AgentEvent` 契约接入 Loop。Provider 适配层不得包含迭代、并发批、权限或 UI 逻辑。

## 非功能需求

- N1：执行器层为每次工具调用提供默认 30 秒上限；工具可声明更短上限。超时返回结构化结果，不终止 Loop。
- N2：Loop 使用虚拟线程异步运行；界面等待期间仍能刷新并读取取消/审批按键。
- N3：并发批不共享可变结果容器；汇总按稳定索引完成。
- N4：工具结果继续受工具级字符、字节和条数上限约束，截断必须明确标记。
- N5：取消完成后不遗留运行中的虚拟线程、进程或未关闭发布器/执行器。
- N6：API Key、Authorization 和代理凭据不得出现在事件、工具错误或终端输出中。
- N7：默认测试离线，不访问真实 Provider；核心 Loop 使用 Fake `LlmClient` 确定性测试。
- N8：项目实际构建命令为 `gradlew test shadowJar --warning-mode all`；原稿中的 Maven/Spotless/CLAUDE.md 不适用于本仓库。
- N9：已有工作区边界和危险操作限制不得因本章实现而被移除；权限系统可以后续增强，但安全基线不能倒退。

## 不做的事

- 不在本章实现完整权限系统、MCP、Skill、Hook、长期记忆或上下文压缩；这些属于后续章节。
- 不配置化 10/50/2 三个循环上限。
- 不跨副作用调用重排并发。
- 不实现子 Agent、计划持久化、计划审批门或 Token 预算停止。
- 不实现多模态或流式工具结果。
- 不新增 OS 级沙箱，但必须保留既有工作区路径保护、命令工作目录和结果限制。

## 验收标准

- AC1：Read → Edit → Read → 最终文本可以在一次用户任务中自动完成。
- AC2：纯文本回合立即自然完成；空文本且无工具调用返回空响应错误。
- AC3：持续调用工具在迭代上限停止并发出 `ITERATION_LIMIT`。
- AC4：调用总数越过上限时不执行越界调用，并为已发布调用保持合法配对。
- AC5：连续两个全未知工具回合以 `UNKNOWN_TOOL_LIMIT` 停止。
- AC6：Provider 流错误产生错误事件，应用可继续下一条消息。
- AC7：事件覆盖迭代、增量、完整回合、工具开始/结束、用量和终态。
- AC8：两个只读工具实际并发执行，副作用工具不并发，结果顺序不变。
- AC9：工具 JSON 分片能由 OpenAI 与 Anthropic 适配器完整组装。
- AC10：每一批 call ID 与结果 ID 一一匹配；取消和上限路径无悬空调用。
- AC11：运行中的 Provider 请求、权限等待和长命令均可由 Esc/Ctrl+C 取消；取消后可继续对话。
- AC12：Token 按轮次累加且同一 usage 不重复计数。
- AC13：界面按真实顺序展示迭代、流文本、工具与结果，不重复最终文本。
- AC14：`/plan` 仅暴露只读工具，`/do` 恢复全工具并立即执行。
- AC15：OpenAI 与 Anthropic 的完整多轮 Loop、回灌、用量和错误路径均有自动或受控端到端证据。
- AC16：`gradlew test shadowJar --warning-mode all` 通过，默认测试不访问外网且输出不泄密。

## 追踪说明

本 Spec 描述 ch04 的目标行为；当前实现状态和偏差见 [`implementation-report.md`](implementation-report.md)，整改顺序见 [`tasks.md`](tasks.md)。
