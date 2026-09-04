# Slash 命令体系 Tasks（Star Code 适配版）

## 适配说明

原始任务稿使用 `com.mewcode`、Lanterna 和 `MewCodeModel` 命名；本仓库实际使用
`com.starcode`、JLine、`ChatApplication` 与 `TerminalUi`。实现以功能契约为准，不重复创建同义类型：

- `Kind` 对应 `CommandKind`。
- `Command` 对应 `CommandSpec`，`Handler` 对应 `CommandHandler`。
- `Ui` 对应 `CommandContext`。
- `Builtins/BuiltinLocal/BuiltinUi/BuiltinPrompt` 当前合并为 `BuiltinCommands`，仍保持 handler 只依赖抽象接口。
- `Dispatch` 对应 `CommandDispatch`。
- `CompletionMenu` 对应无 UI 依赖的 `CommandCompletion`，由 JLine 菜单消费。
- 本仓库没有 `SessionRuntime`；`/clear` 通过重建 `Conversation`、`SessionWriter`、
  `ContextManager` 与 `AgentLoop` 原子地得到等价的全新会话状态。

## 基础任务

- [x] T0a：`MemoryManager.listFiles()` 分项目/用户返回排序后的 Markdown 文件，包含 `MEMORY.md`。
- [x] T0b：`SessionWriter.path()` 返回实际 JSONL 的规范化绝对路径。
- [x] T0c：`ToolRegistry.count()` O(1) 返回已注册工具数；新会话状态由 `/clear` 重建隔离对象。
- [x] T1：统一命令元数据包含名称、别名、描述、类型、hidden 和 handler。
- [x] T2：注册、大小写无关查找、可见命令排序、前缀匹配和启动期冲突检测。
- [x] T3：`CommandDispatch.parse` 独立解析零参数 slash 输入。
- [x] T4：`CommandContext` 提供 handler 所需的最小 UI/运行时能力。

## 内置命令任务

- [x] T5：`/help`、`/status`、`/memory`、`/permission`、`/session`。
- [x] T6：`/exit`、`/plan`、`/compact`、`/resume`、`/clear`。
- [x] T7：`/do`、`/review` 走与普通用户消息相同的 Agent 和持久化路径。
- [x] T8：一次性注册 12 条命令，帮助文本与补全均由同一注册中心生成。

## TUI 集成任务

- [x] T9：`ChatApplication` 实现 `CommandContext` 并通过 `CommandDispatch` 分流。
- [x] T10：`/resume` 复用现有会话选择、恢复和 JSONL 追加流程。
- [x] T11：`CommandCompletion` 管理候选、游标、滚动窗口、零匹配和隐藏。
- [x] T12：JLine 输入支持 `/` 激活、前缀过滤、上下键、Tab、Enter、Esc 和退格。
- [x] T13：滚动式 JLine 使用临时全屏命令菜单；不改现有状态输出区域。
- [x] T14：Ready 文案只以 `/help` 为命令入口；命令、解析、补全和辅助接口均有自动测试。
- [ ] T15：真实 Windows Terminal 中人工验证按键序列、`/clear`→`/resume` 和 prompt 命令。

## 验证命令

```powershell
./gradlew.bat test
./gradlew.bat shadowJar
java -jar build/libs/star-code.jar
```

人工验证重点：输入 `/`、`/s`、方向键、Tab、Enter、Esc、`/status extra`、`/help`、
`/status`、`/memory`、`/permission`、`/session`、`/review`、`/clear`、`/resume` 与 `/exit`。
