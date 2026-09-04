# Feature 007 MCP 客户端实现报告

## 已实现

- 官方 MCP Java SDK 2.0.1，stdio 与 JDK Streamable HTTP。
- 用户/项目两层 YAML 配置及 server 级覆盖。
- env/header `${VAR}` 展开和安全告警。
- 并发启动、单 server 失败隔离、30 秒请求与启动等待。
- initialize、分页 tools/list、tools/call。
- `mcp__server__tool` 适配、Schema 透传、readOnlyHint、纯文本结果与结构化错误。
- 启动时固定工具快照和退出时 5 秒并发关闭。
- MCP 通配权限规则、只读并发和有副作用工具审批。
- Shadow JAR ServiceLoader 合并。

## 自动验证

- 本地 HTTP 测试实际跑通官方 SDK initialize/list/call，并验证 Authorization header。
- Windows stdio 测试实际拉起 PowerShell MCP 子进程，验证环境注入、工具发现、调用和关闭。
- 配置、适配器、命名、权限和全部既有回归测试覆盖。

## 人工验证

复制 `.mewcode.yaml.example` 为 `.mewcode.yaml`，配置一个可信 MCP server，启动时应在 stderr 看到连接与工具数量；随后要求模型调用只读和有副作用工具，确认权限行为。
