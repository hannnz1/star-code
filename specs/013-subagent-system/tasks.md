# SubAgent 机制 Tasks

1. T1：新增 Definition、Source、Parser、Catalog 和三个内置角色。
2. T2：新增 ToolFilter 与 ForkMessages，锁定覆盖和嵌套安全语义。
3. T3：扩展 TurnContext 和两种 Provider，支持角色 system prompt。
4. T4：扩展 AgentLoop Builder、runToCompletion、固定权限模式、dontAsk 和执行硬过滤。
5. T5：新增 SubAgentSession/Launcher，隔离对话、ContextManager 和 token。
6. T6：新增 RunningSubAgent、BackgroundTask、TaskManager 和完成 reminder。
7. T7：实现 Agent、TaskList、TaskGet、TaskStop、SendMessage 五个工具。
8. T8：Main/ChatApplication 接线，注册工具并实现 Provider/Hook/Permission 共享。
9. T9：让 Skill fork 走统一 SubAgentSession 构造底座。
10. T10：新增配置开关、示例、单元测试、完整回归和 Shadow JAR。

```text
T1,T2 -> T3,T4 -> T5 -> T6,T7 -> T8,T9 -> T10
```
