# Hook 生命周期挂钩系统 Plan

## 架构概览

- `permission`：抽出共享 `ValueMatcher` 及 exact/glob/regex/not 实现，权限规则和 Hook 条件共用。
- `hook`：包含事件、稳定 payload、条件、动作、规则、加载器、执行器和引擎。
- `AgentLoop`：接入 PreUserMessage、PreToolUse、PostToolUse、Stop、紧急压缩与通知事件；维护单次 reminder 队列。
- `ChatApplication`：接入会话、用户提交、自动/手动压缩事件，提供 `/hooks` 查询数据。
- `Main`：启动期加载 HookEngine，传入 ChatApplication；关闭时统一释放异步任务。

## 核心类型

- `ValueMatcher.matches(String, boolean)`：共享匹配接口。
- `HookEvent`：11 个事件和 `blocking()` 属性。
- `HookPayload`：不可变有序 Map、点路径取值、稳定 JSON。
- `HookCondition`：ALL/ANY 原子匹配。
- `HookAction`：Shell、Prompt、Http、Subagent 四种 record。
- `HookRule`：name/event/condition/action/onlyOnce/async/timeout/source。
- `HookExecution`：success/block/reason/prompt。
- `HookDispatchResult`：blocked/hook/reason/prompts。
- `HookLoader.load(workspace)`：两层容错加载。
- `HookEngine.dispatch(event,payload,cancellation)`：匹配、once、同步/异步执行和短路。

## 关键决策

| 决策 | 选择 | 原因 |
|---|---|---|
| 工具顺序 | 权限先于 Hook | Hook 不能观察或影响不可授权调用，保持五层权限硬边界 |
| shell | Windows 用 `powershell -NoProfile -Command`，其他平台用 `sh -c` | 配置沿用字符串命令，同时保持跨平台 |
| reminder | AgentLoop 内线程安全一次性队列 | 不污染 Conversation，且能覆盖下一次 provider 请求 |
| async | virtual-thread executor | 与项目现有并发模型一致 |
| fork | 不继承 HookEngine | 防止父子 Agent 重复触发副作用 |
| 配置冲突 | 项目先加载，用户后加载；后同名跳过 | 严格遵循用户 Java 版 Spec 的“先到者保留” |

## 集成顺序

```text
Main → HookLoader → HookEngine
                  ├─ ChatApplication：Session/User/Compact
                  └─ AgentLoop：Provider/Tool/Stop/Notification

ToolCall → PermissionManager → PreToolUse → ToolRegistry → PostToolUse → ToolResult
```

## 测试策略

- matcher、loader、condition、executor、engine 均脱离真实 provider 测试。
- AgentLoop 用 fake LLM/Tool/Hook executor 验证结构化回灌和 reminder。
- CommandContext fake 验证 `/hooks`。
- 最后运行全量 `gradlew test` 与 `shadowJar`。
