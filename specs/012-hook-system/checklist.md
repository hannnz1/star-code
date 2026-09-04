# Hook 生命周期挂钩系统 Checklist

- [ ] 旧权限 glob 规则和 exact/regex/not 新语法均通过测试。
- [ ] 非法权限表达式打印 stderr 且不影响其他规则。
- [ ] 项目/用户 hooks.yaml 正确合并，坏规则和重复 name 被隔离。
- [ ] 11 个 HookEvent 均存在，只有 PreToolUse/UserPromptSubmit 可拦截。
- [ ] 嵌套字段、ALL/ANY、四种 matcher 条件通过测试。
- [ ] shell exit 0/2/其他非零和 timeout 行为正确。
- [ ] prompt 进入下一请求 reminder，消费后清空，不写 Conversation。
- [ ] HTTP block 响应拦截，错误默认放行；subagent 只输出占位日志。
- [ ] only_once 在单会话生效，clear/resume 重置。
- [ ] PreToolUse 拦截产生保留 call ID 的 `HOOK_BLOCKED` 结果。
- [ ] PostToolUse 对成功和失败均触发，只读并发与结果顺序不退化。
- [ ] Session、Stop、Compact、Notification 事件在正确位置触发。
- [ ] `/hooks` 能列出规则、flags 和来源，无规则时友好提示。
- [ ] 完整单元测试无失败。
- [ ] `build/libs/star-code.jar` 构建成功。
