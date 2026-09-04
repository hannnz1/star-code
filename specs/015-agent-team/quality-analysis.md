# ch15 质量分析

## 结论

原稿的产品方向和故障场景覆盖优秀，约 **8/10**；经 Star Code 适配、分阶段边界和第二阶段协议补全后，当前可实施质量约 **8.5/10**。

## 优点

- 团队、成员、邮箱、共享任务、后端和 Coordinator 的职责划分完整。
- 对跨进程丢更新、stale lock、半成品资源、后台续派和 Lead 自动唤醒考虑充分。
- Checklist 强调可观察行为，适合作为端到端验收依据。
- 明确 Worktree、SubAgent、权限和会话的复用边界。

## 主要问题与修订

1. 附件缺少正式 Spec 主体，开头直接是 Java 草图与架构说明；本目录补齐目标、F/N/AC 和分阶段边界。
2. `com.mewcode.team`、`com.mewcode.teams` 混用，且与项目实际包名不符；统一为 `com.starcode.team`。
3. `TaskList`、`TaskGet`、`SendMessage` 与 ch13 已注册工具冲突；改为可选 `team` 参数的兼容扩展。
4. `TeammateInfo` 和 Team 快照字段在 Tasks 中被引用但未完整定义；适配版明确字段集合。
5. tmux/iTerm2、in-process 与 TUI 自动唤醒的完成条件不同，原稿却放在一个提交单元；拆为核心闭环和进程编排第二阶段。
6. 原稿要求开放 `/tmp`，与 Star Code 当前“工作区内相对路径”沙箱冲突；不在 Team 功能中放宽全局沙箱。
7. Coordinator 的双 feature flag 已落为 `features.coordinator_mode` + 环境变量双开关；Fork 队友另用 `features.fork_teammate` 控制。
8. iTerm2/tmux 已统一到 `--team-member` argv 协议并有命令构造单测；真实终端行为仍必须平台验收。

## 风险

- Pane 后端涉及跨平台可执行文件发现、命令参数转义和子进程退出，必须在 Linux/macOS 真机人工验证。
- Lead watcher 只将消息写入 reminder 队列，不擅自追加用户历史；这避免 400/角色交替问题，但空闲时只即时通知，不会无用户输入自动发起新 LLM 请求。
- force 删除可能破坏未合并工作，必须始终使用 WorktreeManager 的受管删除接口。
- 外部 pane 暂不支持 Fork 父历史传输；`fork_teammate` 仅允许 in-process，避免伪继承。
