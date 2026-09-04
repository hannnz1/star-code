# Feature 008 上下文管理实现报告

## 质量审计

规格的阈值、UTF-8 字节口径、失败原子性、熔断和验收描述清晰。Star Code 现已使用结构化 `ChatMessage` 保存 assistant tool calls、tool results 和 provider protocol state。

## 已实现

- 独立 `com.starcode.context.ContextManager`，会话级锁保护替换账本、usage 锚点、文件快照和自动失败计数。
- 单条 50,000 UTF-8 字节和单批 200,000 UTF-8 字节的工具结果落盘/稳定替换。
- replacement/keep 决定写入会话级 JSONL 账本，恢复会话时重建 seen/replacement 状态。
- 20 行/2,048 UTF-8 字节预览、会话目录、tool-use-id 安全文件名、幂等文件写入。
- 成功 Read 后从磁盘重新读取无行号原文，最多恢复最近 5 个文件。
- `context_window` 配置与 OpenAI 128K、Anthropic 200K 默认值。
- usage 替换锚点与 3.5 字符/token 增量估算。
- 无工具摘要、`<summary>` 提取、近期消息保留、工具定义与边界提醒恢复段。
- 自动阈值触发、`/compact` 手动触发、上下文错误的一次紧急摘要重试。
- 摘要请求自身 CONTEXT_LENGTH 时按真实“用户提交 + assistant/tool 往返”分组执行 3 次逐组丢弃及后续 20% 丢弃策略。
- 自动摘要连续失败 3 次熔断；手动/紧急路径绕过。
- `/exit`、`/plan`、`/do`、`/compact` 统一 slash 路由，未知命令不发送给模型。
- 自动、手动、紧急压缩状态提示。

## 当前架构说明

- 工具结果在生成时执行第一层处理，并以结构化消息跨用户回合持久化。
- token 估算包含结构化工具结果正文；稳定系统提示及 provider 包装开销由 13K 安全余量吸收。
- `/compact` 在主输入循环空闲时同步执行，天然与 Agent run 互斥。

## 验证

- 新增离线测试覆盖大结果落盘、稳定 String 引用、mtime 幂等、UTF-8 预览、无工具摘要、摘要解析、恢复工具列表和 usage 锚点。
- 配置测试覆盖默认窗口与显式覆盖。
- 完整 Gradle 测试套件通过；51 个测试套件、174 项测试、0 失败。
