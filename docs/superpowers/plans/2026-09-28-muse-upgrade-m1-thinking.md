# MUSE M1 Thinking Protocol Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** U02 原 thinking 开关实际生效，展示服务摘要，正确回传私有协议状态。

**Architecture:** ProviderSettings 显式声明支持的 thinking_capability，未知组合在网络前拒绝；不猜模型名称。ModelEvent 增加 summary 和仅内部 protocol_state；完整轮次成功后私有状态保存到 checkpoint 独立字段，以非敏感 turn ID 关联消息，只在传输副本中加入原始协议块。

**Tech Stack:** httpx SSE、原三协议 adapter、SQLite checkpoint、pytest MockTransport；沿用选定 provider/model。

**Official references (2026-09-28 checked):** OpenAI reasoning https://developers.openai.com/api/docs/guides/reasoning （stateless replay/summary）；Claude extended thinking https://platform.claude.com/docs/en/build-with-claude/extended-thinking （manual budget < max_tokens/adaptive，signed thinking）。

## Task 1 — 能力与 payload

- [x] 写三协议开启/关闭、未知能力、预算不足 MockTransport 测试，观察失败。
- [x] 显式能力 unsupported/openai-reasoning/anthropic-manual/anthropic-adaptive；关闭不加参数，开启不支持返回 UNSUPPORTED_THINKING。
- [x] Responses reasoning effort/summary auto + encrypted include，Chat reasoning_effort，Anthropic manual/adaptive；manual 至少1024且小于输出上限。

## Task 2 — 流、状态与隔离

- [x] 测试摘要/工具混合分片、签名/encrypted 回传、缺失摘要、截断或错误不发工具。
- [x] 完整结束且工具参数全部有效后才提交原始状态；Agent Worker 私有 checkpoint 保存并在下一轮传输附加，不进 trace/报告/日志。
- [x] 保留输出/缓存/推理 Token 的一致统计；推理已计入总输出时不重复计费。
- [x] 摘要显示在 Web/终端，服务不提供显示“未返回摘要”，不展示自行推断或私有完整推理。

## Task 3 — 恢复与验证

- [x] Worker 重启后原始状态仍可回传；fork 只复制所需私有状态，保持公共历史无 opaque 内容。
- [x] provider/agent/context/入口回归、API 类型/Web 构建、Ruff；最终整体分支独立审查。
- [ ] 当前开发仅离线传输；实际所选服务冒烟独立记录，在剩余授权预算内执行，不能用 mock 代替真实验收。
