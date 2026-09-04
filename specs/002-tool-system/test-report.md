# Feature 002 自动化测试报告

测试日期：2026-08-25

## 结果

- Gradle 构建：通过
- 测试套件：8
- 测试用例：19
- 失败/错误：0
- Shadow JAR：生成成功
- 版本入口：`Star Code 0.1.0`
- Gradle `--warning-mode all`：无弃用警告

## 自动覆盖

- 工具注册中心包含六个工具。
- Read：行号、文件不存在、1 MiB 上限。
- Write：嵌套目录、覆盖、默认权限关闭、路径越界。
- Edit：唯一匹配、0 匹配、多匹配、默认权限关闭。
- Glob：匹配相对路径、200 条截断。
- Search：文件/行/内容、大小写、200 条截断。
- Bash：成功输出、非零退出、默认权限关闭、超时终止。
- Windows 路径反斜杠保留。
- SSE 多行 data 解析。
- OpenAI Responses：工具定义、分片参数、调用 ID、`function_call_output` 回灌、最终正文。
- Anthropic Messages：工具定义、分片参数、调用 ID、`tool_result` 回灌、最终正文。
- 缺失配置文件显示可读错误。
- Markdown 标题、列表、行内代码与代码块基础渲染。

## 未由自动化覆盖

- 真实 OpenAI/Anthropic 服务的工具事件细节与模型选择行为。
- Windows Terminal 的 Ctrl+J、Alt+Enter、多行粘贴、resize、滚动。
- 长流式回复结束后的 ANSI 原位清除；目前已观察到长列表可能残留流式版本并与最终 Markdown 重复。
- 请求进行中 Ctrl+C 的 HTTP 取消和进程清理。
- Bash 的完整 OS 沙箱；当前只有权限开关、工作目录和超时，不是安全隔离环境。
- Anthropic thinking/reasoning 不透明状态跨轮保留。

## 人工验收建议

1. OpenAI：分别触发 Read、Glob、Search、Write、Edit、Bash，确认真实端到端调用。
2. Anthropic：至少完成一次 Read + 回灌 + 最终回答。
3. 粘贴含 CRLF、中文、代码块的多行内容，只提交一次。
4. 长列表回复观察是否重复；该项当前预期暴露已知 UI 缺陷。
5. 请求流式期间按 Ctrl+C，确认程序退出且 PowerShell 状态恢复。
6. 调整终端宽度并滚动长回复，确认无输入区损坏。
