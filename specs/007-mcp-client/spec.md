# MCP 客户端 Spec

## 背景

Star Code 目前有六个内置工具。本功能通过 Model Context Protocol 在启动时发现外部工具，将它们适配为现有 `Tool` 并注册进同一个 Registry，使 Agent Loop、Provider 和 UI 无需区分工具来源。

## 规格校正

- 官方 SDK 是 `io.modelcontextprotocol.sdk`，不是 `com.anthropic:anthropic-java`。
- 本实现使用官方 MCP Java SDK 2.0.1 的 `mcp-core` 与 `mcp-json-jackson2`，兼容项目现有 Jackson 2。
- 项目实际使用 Gradle，以 `gradlew test shadowJar --warning-mode all` 验收。
- 原有权限实现不能从未知工具得知 `readOnlyHint`，因此增加通用 `ToolRegistry::isReadOnly` 分类入口；权限包没有 MCP 协议或名称硬编码。

## 功能需求

- F1：读取用户 `~/.mewcode/config.yaml` 和项目 `<root>/.mewcode.yaml` 的 `mcp_servers`；项目同名 server 完整覆盖用户定义。
- F2：stdio 明确要求 `type: stdio` 与 `command`；HTTP 要求 `type: http` 与 `url`；无效 server 告警并跳过。
- F3：仅展开 env/header 值中的 `${VAR}`；未定义变量为空并告警；名字、command 和 args 不展开。
- F4：stdio 使用官方 `StdioClientTransport`，合并宿主环境并透传 server stderr。
- F5：HTTP 使用官方 `HttpClientStreamableHttpTransport`，每次请求携带自定义 headers，不启用可恢复独立流。
- F6：SDK 完成 initialize、分页 tools/list 和 tools/call；本章不接入 resources/prompts/sampling/roots。
- F7：远端工具适配为现有 Tool；Schema 透传；只收集 text content；错误成为结构化 ToolResult。
- F8：工具名为 `mcp__<server>__<tool>`；非法 LLM 工具名跳过；同命名空间重复项以后者替换并告警。
- F9：所有 server 启动连接并发进行，单 server 整体等待上限 30 秒；失败隔离。
- F10：tools/call 请求超时 30 秒，错误不终止 Agent Loop。
- F11：退出时并发关闭全部会话，总等待上限 5 秒。
- F12：MCP 工具走现有规则、模式和人工审批；readOnlyHint=true 自动归只读并可并发，其余安全默认归执行类。

## 非功能需求

- 单 server 失败不影响内置工具、其它 server 或 TUI 启动。
- 缺失 readOnlyHint 默认有副作用；非法配置安全跳过。
- Provider 层零修改，OpenAI/Anthropic 行为一致。
- 环境变量的实际密钥不写配置、不打印日志。
- Shadow JAR 合并 SDK ServiceLoader 元数据，打包后 JSON mapper 可用。
- 工具快照仅在启动时建立，不做热加载和自动重连。

## 不做的事

不实现 MCP resources、prompts、sampling、roots、list-changed 通知、进度通知、健康检查、重连、OAuth、配额、审计日志、非文本内容回灌或 MCP server。

## 验收标准

- 两层覆盖、字段校验、变量展开、无效配置降级有自动测试。
- 官方 SDK 的真实本地 Streamable HTTP initialize/list/call/header 链路通过。
- 官方 SDK 的真实 stdio 子进程 initialize/list/call/env/关闭链路通过。
- 命名空间、Schema、只读提示、错误映射、非法名及重复名行为通过。
- MCP wildcard 权限规则和 readOnly 默认放行通过。
- 全部既有测试、Shadow JAR 与 `--version` 通过。
- 真实社区 server 的人工测试用于最终端到端验收。
