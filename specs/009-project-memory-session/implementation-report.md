# Feature 009 实现报告

## 已实现

- 三层 `MEWCODE.md` 指令加载，顺序为项目根、项目 `.mewcode/`、用户 `.mewcode/`。
- 独占行 `@include` 展开、5 层深度限制、链路环路检测、边界检查和二进制文件降级。
- 指令与长期记忆索引分别注入系统提示的 `custom-instructions` 和 `long-term-memory` 模块。
- 新格式会话 ID：`YYYYMMDD-HHMMSS-xxxx`，同时供上下文工具结果目录和会话存档使用。
- `conversation.jsonl` 追加写入，记录 user、assistant、tool calls、tool results 与 compact 标记。
- `/resume` 会话列表：按修改时间倒序、方向键选择、字符搜索过滤、Enter 恢复、Esc 取消。
- 恢复时从最后一个 compact 标记后读取，跳过损坏行，截断末尾悬空工具调用；超限时复用上下文压缩。
- 恢复超过 6 小时的会话时追加并持久化时间跨度提醒。
- 启动后台清理超过 30 天的新格式会话，旧格式目录不展示也不自动删除。
- JSONL 无损保存并恢复 user、assistant、assistant tool calls、tool results 与 provider protocol state；不再把工具历史降级成纯文本。
- 项目级与用户级 Markdown 记忆存储、YAML frontmatter、`MEMORY.md` 索引重建、200 行/25KB 限制。
- 每 5 个完成回合或显式记忆关键词触发异步记忆更新；“不要记住”等否定指令抑制本轮更新。
- 记忆更新不携带工具定义，失败只记录错误，不中断主会话。

## 自动验证

- 指令三层顺序、include 展开、深度、环路和路径逃逸。
- Conversation append/replace 回调。
- JSONL 写入、compact 恢复、坏行跳过、列表过滤旧 ID、过期清理。
- 记忆 create/update/delete、索引生成、UTF-8 字节截断、非法 slug 拒绝。
- 显式记忆请求通过 mock provider 异步写入笔记并刷新提示上下文。
- 旧有 Agent Loop、上下文管理、MCP、权限和双协议测试全部回归。
- `gradlew test shadowJar --warning-mode all` 通过。

## 人工验收建议

- 在真实终端中测试 `/resume` 的上下键、中文搜索、Enter 与 Esc。
- 真实 provider 下发送“请记住……”并确认下一轮或重启后的回答遵循该记忆。
- 强制终止进程后重启，检查 JSONL 最后一条损坏时仍可恢复之前的消息。
- 恢复一个超过 6 小时的会话，确认时间跨度提醒写回原会话 JSONL。

## 已知边界

- 启动始终创建新会话，不自动恢复最近会话。
- 记忆使用索引注入，不提供向量检索、全文搜索或跨设备同步。
- 恢复给 Provider 的长期历史包含闭合的结构化工具调用与结果；损坏或未闭合的尾部交换会在恢复时截断。
