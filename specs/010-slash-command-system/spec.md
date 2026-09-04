# Slash 命令体系 Spec

> 状态：IMPLEMENTED  
> Feature：010  
> 覆盖说明：ch14 F30 在本章零参数规则上增加 `acceptsArguments` 显式扩展。

## 背景与目标

- G1：使用统一注册中心管理命令元数据、查找、帮助和补全。
- G2：本地操作绕过普通 LLM 请求。
- G3：handler 依赖命令 UI 抽象，不依赖 JLine 具体类型。
- G4：启动期检测名称与别名冲突。

## 功能需求

- F1：每条命令包含规范名称、别名、描述、Kind（LOCAL/UI/PROMPT）、hidden、`acceptsArguments` 和 handler。
- F2：名称和别名大小写不敏感；注册冲突立即失败并指出冲突键。
- F3：非 `/` 输入进入 Agent；slash 输入只走本地 Dispatcher，不先写 Conversation。
- F4：ch10 内置命令均为零参数，尾随非空参数按未知/参数错误处理。ch14 之后只有 `acceptsArguments=true` 的命令可接收原始参数尾巴。
- F5：LOCAL 不修改历史、不耗 token；UI 修改本地状态；PROMPT 生成 user 消息并走与普通输入相同的持久化和 Agent 路径。
- F6：LOCAL 可在任何不会造成数据竞争的状态读取快照；UI/PROMPT 仅在 IDLE 执行，否则提示等待。
- F7：`/help`、未知提示和补全候选只查询同一 Registry；hidden 命令可分发但不显示。
- F8：补全只匹配规范名称前缀，不匹配别名或描述；支持方向键、Tab/Enter、Esc、无匹配和固定最大高度。
- F9：输入不再以 `/` 开头或变为多行时立即关闭补全；菜单关闭后空格、退格和其他编辑键回到输入框默认行为。
- F10：内置命令为 `/exit`、`/plan`、`/do`、`/compact`、`/resume`、`/clear`、`/help`、`/status`、`/memory`、`/permission`、`/session`、`/review`。
- F11：`/clear` 事务式关闭旧 Writer、创建新 SessionContext/Writer/Conversation/ContextManager，重置用量和回合状态；旧会话仍可恢复。
- F12：`/do` 与 `/review` 生成的文本按普通 user 消息保存并立即触发 Agent。

## 非功能需求

- N1：LOCAL 命令不执行网络或 Provider 请求。
- N2：帮助和补全排序稳定，内容来自 Registry，禁止维护第二份硬编码清单。
- N3：命令异常转换为 UI 错误，不退出进程。
- N4：状态栏现有布局不因补全菜单改变。

## 验收标准

- AC1：`/help` 按名称排序显示 12 条 ch10 内置命令。
- AC2：`/Help` 与 `/help` 等价；未知命令只提示 `/help` 且不调用 LLM。
- AC3：重复名称或别名在注册期抛出含冲突键的异常。
- AC4：`/status` 固定顺序显示权限、token、工具、记忆、模型和工作目录。
- AC5：`/memory`、`/permission`、`/session` 只读本地状态。
- AC6：`/clear` 后内存与累计量归零，旧 JSONL 可在 `/resume` 中看到。
- AC7：`/review` 和 `/do` 的生成消息进入 Conversation 与 JSONL，并触发 Agent。
- AC8：输入 `/` 显示候选，前缀过滤、方向键、Tab/Enter、Esc 和零匹配行为正确。
- AC9：补全菜单关闭后可以正常输入、删除空格和编辑普通文本。
- AC10：未声明参数的命令拒绝尾随参数；ch14 `/worktree` 与 ch15 `/team` 可接收参数。
- AC11：原有五条命令行为不退化。
- AC12：完整命令测试和 Shadow JAR 构建通过。
