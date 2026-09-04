# ch13 SubAgent 机制实现报告

## 完成范围

- 新增稳定的 `Agent` 工具，以 `subagent_type` 区分定义式与 Fork 式子 Agent。
- 新增内置、用户、项目三层角色目录与 YAML frontmatter 解析，支持同名覆盖、容错和大小写不敏感查找。
- 子 Agent 使用独立 Conversation、ContextManager、取消信号、token 统计和权限模式。
- 工具集合经过定义式禁嵌套、后台基础白名单、角色黑名单和角色白名单四层过滤；运行时再次拒绝子 Agent 调用 `Agent`。
- 定义式任务支持同步完成、显式后台和 120 秒自动转后台；Fork 强制后台。
- 新增 `TaskList`、`TaskGet`、`TaskStop`、`SendMessage`，并把后台终态作为 `<task-notification>` 注入主 Agent 下一次请求。
- Skill 的 fork 执行复用 `SubAgentSession` 和统一 `AgentLoop` 构造路径。
- 新增 `enable_subagent_background` 配置开关和三个 classpath 内置角色。

## 设计校准

实现没有参考本地 mewcode 项目，仅依据用户提供的 ch13 文档和 Star Code 现有接口完成。原稿中的关键冲突已在 `quality-analysis.md` 记录并修正，包括角色名称大小写、Fork 的 Agent 可见性、前台任务无损接管、异步 API 统一及权限隔离语义。

## 验证结果

- `gradlew clean test shadowJar --warning-mode all`：通过。
- 当前全仓 JUnit：174 项测试，0 失败，0 跳过。
- Shadow JAR：`build/libs/star-code.jar` 已生成。
- JAR 已包含三个内置角色资源和 `com.starcode.subagent`、`com.starcode.task` 实现类。

自动测试覆盖解析/覆盖、工具过滤、Fork 历史、独立状态、权限、后台生命周期、通知、任务工具、前台超时无损转后台及嵌套拒绝。

## 明确延期

- 当前滚动式 TUI 中 Esc 表示取消主轮；“Esc 把前台 SubAgent 移交后台”已在权威 Spec 中列为不做，显式后台和超时转后台仍可用。
- 不提供 Worktree 文件隔离、团队编排、插件角色加载或后台任务跨进程持久化。
- 真实 Provider 的人工端到端验证需要用户本机模型配置和凭据，不在离线 JUnit 中执行。
