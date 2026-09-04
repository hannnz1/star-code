# ch13 Spec 质量分析

## 评分

原稿约 **7.6/10**，校准后约 **9.0/10**。

## 优点

- 对定义式/Fork 式、前台/后台、权限和工具过滤给出了完整闭环。
- 明确要求工具定义稳定、状态隔离、失败隔离和任务通知，工程目标清晰。
- Frontmatter、内置角色、工具 schema 与验收场景足够具体，具备较强可测性。
- 主从模型与 Worktree/Team 的章节边界划分合理。

## 原稿问题

- 名称规则要求小写，却使用 `Explore/Plan`；现统一小写存储、大小写不敏感解析。
- F3 说所有子 Agent 移除 Agent，F24/AC5 又要求 Fork 保留；现拆成定义式隐藏、Fork 保留定义但运行时硬拒绝。
- `adoptRunning` 原方案先取消前台订阅再接管，无法保证原任务继续；改为从开始持有同一个 future，超时仅登记管理。
- `Flow.Publisher`、`BlockingQueue`、`SubmissionPublisher` 的示例 API 互相混用；现统一为 CompletableFuture + BlockingQueue。
- 权限“独立 Engine”与“共享同一 Engine”互相冲突；现定义为共享安全规则与审批器、隔离每个子会话的模式和 dontAsk 状态。
- Agent/Conversation 类型和包名不是 Star Code 现状；已全部映射为 `com.starcode` 的实际接口。
- ESC 手动移交在同步 Tool.execute 和当前 TUI 取消模型下不可可靠实现；从完成定义中移除，避免虚假验收。
- Fork 的悬空 tool-use 修复不适用于当前只持久化最终文本的 ChatMessage；文档改为克隆可表达的完整消息前缀。

## 风险

- 后台任务不持久化，退出时只做尽力取消。
- Provider 正在进行网络请求时，取消要等请求/流回到检查点。
- Fork 会复制较长历史，仍需依赖既有 context manager 防止窗口溢出。
- 后台 Agent 可修改同一工作区；并发写冲突要由后续 Worktree 章节解决。
