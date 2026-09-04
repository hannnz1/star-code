# ch15 Agent Team Checklist

- [x] Team create/sanitize/suffix/reload/delete
- [x] 损坏 config 隔离（加载路径容错，损坏快照单独跳过）
- [x] BackendDetector 环境组合
- [x] Mailbox write/read/unread/markRead/concurrent/stale-lock
- [x] AgentNameRegistry 双向覆盖
- [x] TeamTask CRUD/filter/dependency/isReady
- [x] 七个协作工具唯一注册
- [x] ch13 TaskGet/TaskList/SendMessage 回归
- [x] `/team list|info|delete` 已接入注册中心
- [x] `gradlew test`
- [x] `gradlew shadowJar`

## 第二阶段实现与验证

- [x] tmux pane 命令构造与自治 runner 单测
- [x] iTerm2 pane argv 协议单测
- [x] in-process 完成回调、idle 标记、续派 reminder
- [x] Lead mailbox 750ms watcher、终端通知和 Agent reminder
- [x] Coordinator 双开关和工具白名单
- [x] Plan approval request/response 与权限切换测试
- [x] force delete 对 in-process cancel / pane kill
- [ ] Linux tmux 真实 pane 端到端人工验收
- [ ] macOS iTerm2 真实 pane 端到端人工验收
