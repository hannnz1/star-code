# Feature 010 实现报告

## 已实现

- `com.starcode.command` 注册中心：名称、别名、描述、Kind、hidden、handler。
- 大小写不敏感解析，零参数精确匹配，名称/别名启动期冲突检测。
- `CommandContext` UI 控制抽象，所有 handler 不依赖 `TerminalUi`。
- 12 条内置命令：`/clear`、`/compact`、`/do`、`/exit`、`/help`、`/memory`、
  `/permission`、`/plan`、`/resume`、`/review`、`/session`、`/status`。
- `/help`、未知命令和补全候选均从注册中心生成。
- `/clear` 原子创建新的 session、writer、conversation、context manager 和 AgentLoop，旧会话保留。
- `/status` 固定输出权限、token、工具、记忆、模型、工作目录六项。
- `/memory` 仅列两级记忆文件名；`/session` 显示 ID 与 JSONL 路径。
- `/do`、`/review` 走与普通用户输入相同的 Agent 和 JSONL 持久化路径。
- JLine 命令菜单支持规范名称前缀过滤、8 行滚动、上下键两种转义格式、Tab、Enter、Esc、退格和零匹配。
- Ready 提示仅引导 `/help`。

## 自动验证

- 12 条可见命令及字典序帮助。
- 大小写解析、尾随参数拒绝、未知命令不分发。
- 名称/别名冲突以及 hidden 命令行为。
- 补全仅匹配规范名称，不匹配别名或描述。
- status 六字段顺序、prompt 命令通过抽象接口发送。
- 全部既有 Agent、权限、MCP、上下文、会话和记忆测试回归。

## 终端冒烟

- `/` 显示候选菜单。
- `/s` 过滤到 `/session` 与 `/status`。
- `/help` 输出 12 条命令。
- `/status` 输出六项且 token 保持不变。
- `/exit` 正常退出并恢复终端。

## 架构适配

Star Code 当前使用滚动式 JLine UI，没有 frame-based 状态栏区域，因此候选菜单采用临时全屏选择器；
命令执行后回到正常输入。其输入、过滤、选择和执行语义与 Spec 一致，但位置不是固定 overlay。
当前输入循环在 Agent 执行时同步等待，因此命令只能在 IDLE 输入；Kind 元数据与 CommandContext 已为后续双线程输入模型保留边界。
