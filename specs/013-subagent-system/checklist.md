# SubAgent 机制 Checklist

- [x] 三个内置角色打入 classpath 并可解析。
- [x] 用户/项目目录加载、项目覆盖用户、查找大小写不敏感。
- [x] 坏的用户角色隔离；坏的内置角色 fail-fast。
- [x] Agent schema 含 6 个规定参数且主工具定义稳定。
- [x] 定义式子 Agent 看不到 Agent；Fork 调用 Agent 被运行时拒绝。
- [x] 白名单、黑名单、后台基础/MCP 白名单通过测试。
- [x] 子 Agent 独立对话、ContextManager、取消和 token 用量。
- [x] 角色 system prompt 对 Anthropic/OpenAI 生效。
- [x] dontAsk 位于黑名单、沙箱和显式规则之后。
- [x] SubAgent 审批提示带来源标识。
- [x] 显式后台与 Fork 立即返回 task id。
- [x] 前台 120 秒后无损转后台。
- [ ] ESC 手动移交后台（当前 TUI 不支持，明确延期）。
- [x] TaskList/Get/Stop/SendMessage 注册并返回结构化结果。
- [x] 完成/失败/取消产生仅模型可见 task-notification。
- [x] Skill fork 复用 SubAgentSession/AgentLoop Builder。
- [ ] 人工端到端 Provider 测试。
- [x] 完整测试与 Shadow JAR。
