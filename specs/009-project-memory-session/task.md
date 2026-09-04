# 项目记忆与会话持久化 Tasks

> 状态：Ready for review。所有路径、类名和命令均按当前 Star Code 仓库修正。

## 文件清单

| 操作 | 实际文件 |
|---|---|
| 新建 | `src/main/java/com/starcode/instructions/InstructionLoader.java` |
| 新建 | `src/main/java/com/starcode/session/SessionContext.java` |
| 新建 | `src/main/java/com/starcode/session/SessionEntry.java` |
| 新建 | `src/main/java/com/starcode/session/SessionWriter.java` |
| 新建 | `src/main/java/com/starcode/session/SessionInfo.java` |
| 新建 | `src/main/java/com/starcode/session/SessionCatalog.java` |
| 新建 | `src/main/java/com/starcode/session/SessionLoader.java` |
| 新建 | `src/main/java/com/starcode/session/SessionCleaner.java` |
| 新建 | `src/main/java/com/starcode/memory/NoteType.java` |
| 新建 | `src/main/java/com/starcode/memory/MemoryNote.java` |
| 新建 | `src/main/java/com/starcode/memory/MemoryUpdateAction.java` |
| 新建 | `src/main/java/com/starcode/memory/MemoryStore.java` |
| 新建 | `src/main/java/com/starcode/memory/MemoryManager.java` |
| 修改 | `src/main/java/com/starcode/llm/Conversation.java` |
| 修改 | `src/main/java/com/starcode/context/ContextManager.java` |
| 修改 | `src/main/java/com/starcode/prompt/SystemPromptAssembler.java` |
| 修改 | `src/main/java/com/starcode/agent/AgentLoop.java` |
| 修改 | `src/main/java/com/starcode/ChatApplication.java` |
| 修改 | `src/main/java/com/starcode/ui/TerminalUi.java` |
| 修改 | `src/main/java/com/starcode/Main.java` |

## 阶段 A：会话基础

### T1 SessionContext

新增 `com.starcode.session.SessionContext`，实现新 ID、create/open/parseTime，并让 ContextManager 使用它。

验证：`.\gradlew.bat test --tests "com.starcode.session.SessionContextTest"`

### T2 Conversation 结构化事件与回调

升级 Conversation，保留兼容构造器；append/replace 在释放内部锁后触发可选回调。

验证：`.\gradlew.bat test --tests "com.starcode.llm.ConversationTest"`

### T3 InstructionLoader

实现三层加载、深度、链级环路集合、真实路径边界和二进制检查。

验证：`.\gradlew.bat test --tests "com.starcode.instructions.InstructionLoaderTest"`

### T4 JSONL Writer

实现 SessionEntry 与 SessionWriter，关键边界刷盘，所有 JSON 单行转义正确。

验证：`.\gradlew.bat test --tests "com.starcode.session.SessionPersistenceTest"`

### T5 会话目录与恢复

实现 SessionInfo、SessionCatalog、SessionLoader、结构修复和 SessionCleaner。

验证：`.\gradlew.bat test --tests "com.starcode.session.SessionRecoveryTest"`

### T6 JLine `/resume`

注册命令，实现选择、过滤、Esc、状态互斥和事务切换。

验证：自动测试路由/事务服务；JLine 上下键、过滤和 Esc 另做人工测试。

## 阶段 B：提示与记忆

### T7 Prompt 参数化

让 SystemPromptAssembler 接收 instructions/memory，并解决模块优先级冲突。

验证：`.\gradlew.bat test --tests "com.starcode.prompt.SystemPromptEngineeringTest"`

### T8 Memory 数据模型与 Store

实现 NoteType、MemoryNote、MemoryUpdateAction、MemoryStore；使用临时文件 + 原子移动更新笔记和索引。

验证：`.\gradlew.bat test --tests "com.starcode.memory.MemoryStoreTest"`

### T9 MemoryManager

实现两级索引加载、UTF-8 25KB 截断、无工具 LLM 请求、JSON schema 校验、单任务异步更新和失败隔离。

验证：`.\gradlew.bat test --tests "com.starcode.memory.MemoryManagerTest"`

### T10 Agent 触发

自然完成后递增回合数；每 5 轮或显式记忆关键词触发，输入仅限最近完整回合和索引。

验证：在 `AgentLoopTest` 中使用 mock LlmClient，验证第 5 轮、关键词、普通轮和工具中间轮。

## 阶段 C：集成

### T11 Main 启动编排

按 Plan 启动顺序注入 InstructionLoader、MemoryManager、SessionContext、Writer 和后台 Cleaner。

验证：`.\gradlew.bat test --tests "com.starcode.integration.PersistenceStartupTest"`

### T12 配置与文档

更新配置示例、README、gitignore，解释 MEWCODE.md、memory、sessions、隐私和清理策略。

### T13 完整验证

运行：

```powershell
.\gradlew.bat clean test shadowJar --warning-mode all
java -jar build\libs\star-code.jar --version
```

随后执行人工 `/resume`、跨进程会话续写、显式“记住”和 JLine 会话选择测试。

## 执行顺序

```text
T1 ─┬─ T4 ─ T5 ─ T6
T2 ─┘
T3 ───────────────┐
T7 ─ T8 ─ T9 ─ T10 ─ T11 ─ T12 ─ T13
```
