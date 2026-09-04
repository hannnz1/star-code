# Star Code AI Coding Agent Tasks

> **状态：SUPERSEDED。** 这是初始 V1 任务稿。当前任务以各章节 `tasks.md` 与 [`specs/README.md`](specs/README.md) 为准。

## 文档状态

- 状态：任务草案
- 依据：[spec.md](spec.md)、[plan.md](plan.md)
- 原则：每个任务形成可验证、可回滚的行为切片
- 本文档只规划，不代表已经实现

## 文件清单

| 操作 | 路径/区域 | 职责 |
|---|---|---|
| 新建 | `settings.gradle.kts`、`build.gradle.kts` | Java 21、依赖、测试和可执行 Jar |
| 新建 | `AGENTS.md`、`README.md`、`config.example.yaml` | 项目规则、使用说明和配置示例 |
| 新建 | `src/main/java/com/starcode/bootstrap` | 依赖组合和生命周期 |
| 新建 | `src/main/java/com/starcode/config` | 配置、凭据和代理 |
| 新建 | `src/main/java/com/starcode/agent` | Agent Loop、终止与取消 |
| 新建 | `src/main/java/com/starcode/conversation` | 会话项和工具调用关联 |
| 新建 | `src/main/java/com/starcode/llm` | 模型端口、内部模型与错误 |
| 新建 | `src/main/java/com/starcode/llm/openai` | Responses API 适配器 |
| 新建 | `src/main/java/com/starcode/tool` | 工具协议、注册、输出预算 |
| 新建 | `src/main/java/com/starcode/tool/impl` | 五个 V1 工具 |
| 新建 | `src/main/java/com/starcode/workspace` | 工作区路径安全 |
| 新建 | `src/main/java/com/starcode/permission` | 风险和审批策略 |
| 新建 | `src/main/java/com/starcode/process` | 进程执行、超时和取消 |
| 新建 | `src/main/java/com/starcode/event` | 事件、日志和脱敏 |
| 新建 | `src/main/java/com/starcode/cli` | 行式 CLI 和批准交互 |
| 新建 | `src/test/java/com/starcode/**` | 单元、集成和端到端测试 |
| 新建 | `src/test/resources/fixtures/**` | 安全、补丁、命令和 E2E fixture |

## 任务列表

## T1：建立可构建项目骨架

**目标：** 创建 Java 21 Gradle 项目，提供最小入口和测试基线。

**对应需求：** F1、N5、N6  
**涉及文件：** Gradle 文件、`Main.java`、`.gitignore`、基础测试  
**依赖：** 无

**步骤：**

1. 配置 Java 21 toolchain、JUnit 5、Jackson、YAML 和 OpenAI SDK。
2. 配置 application 入口和可执行 fat Jar。
3. 创建只显示应用名称和版本的入口。
4. 创建一个 smoke test。
5. 添加忽略构建产物、配置密钥和事件日志的规则。

**不在本任务中：** API 调用、工具、完整 CLI。

**验证：**

```powershell
.\gradlew.bat clean test
.\gradlew.bat shadowJar
java -jar build\libs\star-code.jar --version
```

**预期：** 测试通过、Jar 生成、版本命令退出码为 0。

## T2：实现配置与秘密管理

**目标：** 加载并验证非敏感配置，从环境变量安全读取 API Key。

**对应需求：** F2、F13、N8  
**涉及文件：** `config/**`、`config.example.yaml`、配置测试  
**依赖：** T1

**步骤：**

1. 定义 `AgentConfig`、默认限制和代理配置。
2. 实现 YAML 加载、命令行配置路径和默认路径规则。
3. 实现 `CredentialProvider` 读取 `OPENAI_API_KEY`。
4. 实现缺少字段、非法 URI、非正数限制和无效工作区的错误分类。
5. 确保 `toString`、日志和错误不包含密钥。

**验证：** 配置单元测试覆盖有效配置、默认值、无效配置和密钥缺失；运行全部测试。

## T3：定义核心模型、端口与 Fake

**目标：** 建立与 SDK 无关的模型、工具、权限、事件和进程接口。

**对应需求：** F3、F4、F10、F13、N2、N5  
**涉及文件：** `agent/**`、`conversation/**`、`llm` 内部类型、`tool` 接口、测试 Fake  
**依赖：** T1

**步骤：**

1. 定义 ConversationItem、ModelRequest/Response、ToolCall/Result、AgentResult。
2. 定义 `LlmClient`、`Tool`、`ToolRegistry`、`PermissionGate`、`EventSink` 和 `ProcessRunner`。
3. 定义结构化错误基类及子类。
4. 实现队列式 `FakeLlmClient`、`FakeTool`、`FakePermissionGate` 和内存 EventSink。
5. 测试 callId、错误序列化和 Fake 请求捕获。

**验证：** 核心类型测试通过，生产核心包不导入 OpenAI SDK。

## T4：实现最小 Agent Loop

**目标：** 完成普通文本、单次和多轮串行工具调用。

**对应需求：** F3、F4、F13、N2、N3  
**涉及文件：** `AgentLoop`、`Conversation`、`ToolRegistry`、`AgentLoopTest`  
**依赖：** T3

**步骤：**

1. 用户输入加入 Conversation。
2. 调用 LlmClient，并传递工具 Schema。
3. 无工具调用且有文本时完成。
4. 对每个工具调用执行查找、参数验证和工具执行。
5. 未知工具、非法参数和工具异常形成结构化 Tool Result 并反馈模型。
6. 保证 Tool Result 使用原始 callId。

**验证：** Fake 场景覆盖普通回复、单工具、多轮工具、未知工具、非法参数、工具异常。

## T5：实现循环保护、重试和取消

**目标：** Agent 不因模型或工具异常无限运行，并可取消。

**对应需求：** F12、F13、N3、N7  
**涉及文件：** `LoopGuard`、取消模型、重试策略、Agent 测试  
**依赖：** T4

**步骤：**

1. 实现最大轮数和最大重复失败调用。
2. 对可重试模型错误实施有限、可取消退避。
3. 认证和无效请求直接失败。
4. 取消在模型请求、审批等待和工具执行边界传播。
5. 发出重试、阻塞、取消和失败事件。

**验证：** 测试最大轮数、重复失败、重试耗尽、认证不重试、退避取消。

## T6：实现工作区边界

**目标：** 为全部文件工具提供统一路径安全层。

**对应需求：** F11、N1、N3  
**涉及文件：** `workspace/**`、临时目录 fixture、路径安全测试  
**依赖：** T3

**步骤：**

1. 规范化并验证工作区根目录。
2. 拒绝绝对路径和 `..` 逃逸。
3. 检查已存在目标的真实路径。
4. 对新写入目标检查真实父目录。
5. 拒绝符号链接或 junction 逃逸；不支持可靠判断的平台采用拒绝策略。
6. 只向上层返回工作区相对显示路径。

**验证：** 正常路径、绝对路径、父目录穿越、链接逃逸、目标不存在和嵌套安全路径测试通过。

## T7：实现只读工具

**目标：** 提供 `list_files`、`read_file`、`search_text`。

**对应需求：** F5、F6、F7、F11、N7  
**涉及文件：** 三个工具、Schema、fixture 和测试  
**依赖：** T3、T6

**步骤：**

1. 定义严格输入 Schema 和参数校验。
2. 实现有限递归文件列表和 glob 筛选。
3. 实现带行范围、编码和大小限制的文本读取。
4. 实现有限匹配数的文本搜索。
5. 统一结构化结果和错误代码。
6. 注册工具并验证 Schema 可被模型请求使用。

**验证：** 每个工具的成功、空结果、非法参数、越界和截断测试通过。

## T8：实现权限策略与 CLI 审批端口

**目标：** 在工具执行前统一决定允许、确认或拒绝。

**对应需求：** F10、F11、N1  
**涉及文件：** `permission/**`、审批接口、权限测试  
**依赖：** T3、T6

**步骤：**

1. 定义 ToolRisk 和默认风险映射。
2. 工作区只读工具自动允许。
3. 写入和命令默认请求确认。
4. 工作区外或破坏性操作拒绝。
5. 将允许、拒绝和确认结果接入 Agent Loop。
6. 用户拒绝作为 Tool Result 返回模型，不伪装成工具异常。

**验证：** 各风险类别、批准、拒绝和无审批执行防护测试通过。

## T9：实现补丁预览和安全应用

**目标：** Agent 可请求最小代码修改，用户批准后才应用。

**对应需求：** F8、F10、F11、N1、N3  
**涉及文件：** `ApplyPatchTool`、patch 解析/应用组件、fixture 和测试  
**依赖：** T6、T8

**步骤：**

1. 解析受支持的 patch 格式。
2. 验证所有目标均位于工作区。
3. 在内存中预应用并生成 diff。
4. 将 diff 提供给审批界面。
5. 获批后进行安全写入；冲突、拒绝或异常保持原文件不变。
6. 输出修改文件和变更摘要。

**验证：** 新建、修改、多文件、冲突、拒绝、越界和部分失败回滚测试通过。

## T10：实现受控进程执行

**目标：** 安全执行经批准的构建和测试命令。

**对应需求：** F9、F10、F12、N1、N3、N6、N7  
**涉及文件：** `process/**`、`RunCommandTool`、fixture 程序和测试  
**依赖：** T5、T6、T8

**步骤：**

1. 使用可执行程序与参数数组启动进程。
2. 工作目录限制在工作区。
3. 并发读取 stdout/stderr，防止管道阻塞。
4. 实现超时、取消、退出码、耗时和输出限制。
5. 实现平台能力检测和透明错误。
6. 识别明显网络或破坏性命令并升级或拒绝风险。

**验证：** 成功、非零退出、stderr、超时、取消、超长输出、非法工作目录和拒绝执行测试通过。

## T11：实现事件、日志与脱敏

**目标：** 提供完整可观察事件并防止秘密泄漏。

**对应需求：** F14、N4、N8  
**涉及文件：** `event/**`、脱敏测试、JSONL 测试  
**依赖：** T2、T4、T5、T8

**步骤：**

1. 定义关键 AgentEvent 类型。
2. 实现控制台与 JSONL EventSink。
3. 对 API Key、Authorization、代理凭据和配置敏感值脱敏。
4. 对事件参数和输出执行大小限制。
5. 测试事件顺序、合法 JSONL 和日志关闭。

**验证：** 完整事件场景可解析；测试秘密未出现在任何输出中。

## T12：实现 OpenAI Responses API 适配器

**目标：** 用真实模型完成文本和函数工具调用。

**对应需求：** F2、F3、F4、F13、N5  
**涉及文件：** `llm/openai/**`、转换测试、可选真实 API 测试  
**依赖：** T2、T3、T4

**步骤：**

1. 将内部 ModelRequest 转为 Responses API 请求。
2. 每轮设置系统指令、工具和禁用并行工具调用。
3. 转换文本、函数调用、调用参数、usage 和 responseId。
4. 将认证、限流、超时、网络、400 和服务错误分类。
5. 支持代理配置而不记录代理凭据。
6. 单元测试使用 mock HTTP/SDK 边界；真实 API 测试通过环境开关启用。

**验证：** 转换和错误分类测试通过；有凭据时可选测试完成“只回复 OK”。

## T13：实现 CLI 和应用组合

**目标：** 用户可以启动、提交任务、审批、取消和退出。

**对应需求：** F1、F10、F12、F15、N4  
**涉及文件：** `cli/**`、`bootstrap/**`、`Main.java`、CLI 测试  
**依赖：** T2、T5、T8、T11、T12

**步骤：**

1. 组合生产依赖和五个工具。
2. 显示模型、工作区和安全模式。
3. 实现任务输入及单任务运行。
4. 实现 `/status`、`/cancel`、`/exit`。
5. 显示 diff 和明确审批选项。
6. 根据 AgentResult 输出状态、修改、验证和限制。

**验证：** 使用 FakeLlmClient 的 CLI 集成测试覆盖普通任务、审批、拒绝、取消和退出。

## T14：端到端验收 fixture

**目标：** 验证完整“检查—修改—测试—报告”链路。

**对应需求：** F1–F15、N1–N8  
**涉及文件：** `integration/**`、calculator fixture、事件证据  
**依赖：** T7、T9、T10、T11、T13

**步骤：**

1. 创建含有确定性缺陷和测试的 calculator fixture。
2. FakeLlmClient 依次请求搜索、读取、补丁和测试。
3. 模拟批准写入和命令执行。
4. 断言补丁生效、测试通过、事件完整、最终报告有真实证据。
5. 添加权限拒绝、路径逃逸、测试失败和最大轮次 E2E 场景。

**验证：** E2E 测试全部通过，且 fixture 外文件不变。

## T15：文档和发布前验证

**目标：** 让新用户能够安全配置、启动和理解限制。

**对应需求：** F1、F2、F15、N4、N6、N8  
**涉及文件：** `README.md`、`AGENTS.md`、配置示例、文档测试  
**依赖：** T13、T14

**步骤：**

1. 编写环境要求、构建、配置、代理和启动说明。
2. 说明权限、工作区、安全限制和 V1 非目标。
3. 提供 API Key 环境变量示例但不包含真实密钥。
4. 记录常见网络、401、429、超时和模型错误排查。
5. 执行 clean build、全部测试和 Jar smoke test。

**验证：** 新目录按 README 可构建；全部测试通过；仓库扫描不含密钥。

## 执行顺序

```text
T1
├─ T2 ────────────────┬─ T11 ─┐
└─ T3 ─┬─ T4 ─ T5 ───┤       │
       ├─ T6 ─ T7 ────┤       │
       │      └─ T8 ─┬─ T9 ───┤
       │             └─ T10 ──┤
       └─ T12 ────────────────┤
                               ▼
                              T13 → T14 → T15
```

可并行：T2 与 T3；T7、T11、T12 在各自依赖满足且不修改相同核心文件时可并行。首次实现建议顺序执行以减少架构漂移。

## 追踪表

| 任务 | 需求 | 主要组件 | 验证 |
|---|---|---|---|
| T1 | F1、N5、N6 | Build、Main | clean test、Jar smoke |
| T2 | F2、F13、N8 | Config | 配置与秘密测试 |
| T3 | F3、F4、F10、N2、N5 | Core ports/Fakes | 类型与依赖测试 |
| T4 | F3、F4、F13、N2、N3 | AgentLoop | 确定性循环测试 |
| T5 | F12、F13、N3、N7 | LoopGuard/Retry/Cancel | 边界与取消测试 |
| T6 | F11、N1、N3 | WorkspaceBoundary | 路径攻击测试 |
| T7 | F5–F7、F11、N7 | Read tools | 工具测试 |
| T8 | F10、F11、N1 | Permission | 允许/确认/拒绝测试 |
| T9 | F8、F10、F11、N1、N3 | Patch | diff、冲突、回滚测试 |
| T10 | F9、F10、F12、N1、N3、N6、N7 | Process | 进程生命周期测试 |
| T11 | F14、N4、N8 | Events | 顺序、JSONL、脱敏测试 |
| T12 | F2–F4、F13、N5 | OpenAI adapter | 转换、错误分类测试 |
| T13 | F1、F10、F12、F15、N4 | CLI/Bootstrap | CLI 集成测试 |
| T14 | 全部 | E2E | 成功及失败场景 |
| T15 | F1、F2、F15、N4、N6、N8 | Docs/Release | 全量验证和秘密扫描 |
