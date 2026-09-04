# Hook 生命周期挂钩系统 Tasks

## 任务

1. T1：新增共享 Matcher，迁移 PermissionRule 与配置解析；验证旧 glob 和新前缀。
2. T2：新增 HookEvent、HookPayload、HookCondition、HookAction、HookRule 和结果类型。
3. T3：实现 HookLoader 两层 YAML 加载、校验、冲突与错误隔离。
4. T4：实现 HookExecutor 的 shell/prompt/http/subagent，占位与超时/取消。
5. T5：实现 HookEngine 的顺序分派、blocking、only-once、async 和关闭。
6. T6：为 AgentLoop 接入 provider、tool、Stop、Notification、紧急压缩事件及 reminder。
7. T7：为 ChatApplication 接入 Session/User/Auto/Manual Compact，clear/resume 状态重置。
8. T8：新增 `/hooks`，Main 完成加载与生命周期接线。
9. T9：补齐 matcher、loader、executor、engine、AgentLoop 和命令测试。
10. T10：运行完整测试、构建 Shadow JAR、记录实现报告。

## 执行顺序

```text
T1 → T2 → T3 → T4 → T5 → T6 → T7 → T8 → T9 → T10
```
