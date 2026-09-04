# Feature 012 Hook 系统实现报告

## 已实现

- exact、glob、regex、not 四种共享 Matcher，并保持旧权限 glob 规则兼容。
- 权限表达式 `=value`、`~regex`、`!inner` 前缀及解析失败 stderr 降级。
- 项目级与用户级 hooks.yaml 加载、规则校验、重名隔离和来源记录。
- 11 个生命周期事件、稳定有序 payload、点路径条件和 ALL/ANY 组合。
- shell、prompt、HTTP 三种真实动作及 subagent 固定占位行为。
- shell/HTTP 超时与取消、shell exit 2 拦截、HTTP block JSON 响应。
- only-once 会话状态、virtual-thread 异步执行和关闭等待。
- UserPromptSubmit 拦截并把文本放回输入框。
- 权限放行后的 PreToolUse 拦截、`HOOK_BLOCKED` 结构化结果和 PostToolUse。
- Session、Stop、PreUserMessage、Compact、Notification 事件接入。
- prompt reminder 单次消费且不进入 Conversation/JSONL。
- `/hooks` 命令和 `.mewcode/hooks.example.yaml`。

## 与原稿相比的安全校准

- 工具调用采用“权限系统 → Hook → 工具实现”，Hook 不能绕过黑名单、沙箱、规则或审批。
- fork Skill 子 Agent 默认不继承主 HookEngine，防止自动动作重复执行。
- HTTP 不跟随重定向，设置响应体和时间限制；日志不输出 headers。
- Windows 使用 PowerShell，Unix 使用 `sh -c`，payload 都经 stdin 传入而不是拼入命令。

## 尚未实现

- subagent Hook 的真实运行。
- Hook 配置热加载、only-once 持久化、重试、依赖和独立审计日志。
- 企业级 HTTP 域名 allowlist、代理和 OAuth 策略。
