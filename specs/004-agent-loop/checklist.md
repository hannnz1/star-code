# ch04 Agent Loop 验收 Checklist

## 自动测试

- [x] 多轮工具调用直到自然完成。
- [x] 迭代上限停止。
- [x] 工具调用总量上限停止。
- [x] 连续未知工具停止。
- [x] Provider 错误转为错误事件且不崩溃。
- [x] 文本增量与完整模型回合事件。
- [x] 只读并发、有副作用串行、结果保序。
- [x] Token 跨迭代累计。
- [x] Plan Mode 仅暴露只读工具。
- [x] OpenAI/Anthropic 分片工具参数和结果格式。
- [ ] 空文本且无工具调用返回 `EMPTY_MODEL_RESPONSE`。
- [ ] 工具上限路径没有悬空持久化 call。
- [ ] 运行中的 Provider 请求可以及时取消。
- [ ] 运行中的并发工具可以取消并补齐结果。
- [ ] 任意 Tool 都受到统一 30 秒执行器超时。
- [ ] OpenAI 完整两轮以上 AgentLoop Mock HTTP 测试。
- [ ] Anthropic 完整两轮以上 AgentLoop Mock HTTP 测试。
- [ ] 反复取消后无线程、执行器或子进程泄漏。

## 人工测试

- [ ] 普通多步骤任务无需用户中途催促。
- [ ] 流式响应期间 Esc 取消并可继续对话。
- [ ] 流式响应期间 Ctrl+C 取消但不退出程序。
- [ ] 空闲状态 Ctrl+C 正常退出程序并恢复终端。
- [ ] 长 Bash 执行期间取消后进程树终止。
- [ ] `/plan` 只读规划，`/do` 恢复写入并立即执行。
- [ ] 迭代、工具和 Token 信息按真实顺序显示且最终文本不重复。
- [ ] OpenAI/兼容端点完成多轮工具任务。
- [ ] Anthropic 完成多轮工具任务。

## 构建

- [x] `gradlew test`：29 suites / 110 tests / 0 failures（2026-08-26）。
- [ ] `gradlew clean test shadowJar --warning-mode all`。
- [ ] `java -jar build/libs/star-code.jar --version` 使用本次源码新构建产物通过。

## 当前结论

核心 Loop 可用，但取消传播、统一工具超时、停止路径历史配对和双协议完整 E2E 尚未全部验收，因此 ch04 当前综合完成度约 **86%**。
