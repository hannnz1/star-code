# Star Code AI Coding Agent Plan

> **状态：SUPERSEDED。** 这是初始 V1 设计草案。当前设计按章节维护，入口见 [`specs/README.md`](specs/README.md)。

## 文档状态

- 状态：设计草案
- 依据：[spec.md](spec.md)
- 技术栈：Java 21、Gradle Kotlin DSL、JUnit 5、OpenAI Responses API
- 范围：仅覆盖 V1

## 架构概览

Star Code 采用分层、端口适配器式设计。核心 Agent 循环只依赖项目内部接口，不直接依赖 OpenAI SDK、终端、文件系统实现或具体进程 API。

```text
CLI
 │ user input / approval / output
 ▼
AgentApplication
 │
 ▼
AgentLoop ───────────────► EventSink
 │                           │
 ├── LlmClient               └── ConsoleEventSink / JsonlEventSink
 ├── Conversation
 ├── ToolRegistry
 ├── PermissionGate
 ├── LoopGuard
 └── CancellationToken
       │
       ▼
Tools
 ├── ListFilesTool
 ├── ReadFileTool
 ├── SearchTextTool
 ├── ApplyPatchTool
 └── RunCommandTool
       │
       ▼
WorkspaceBoundary / ProcessRunner
```

依赖方向：

```text
cli/config/openai/tool implementations
                 ↓
           application ports
                 ↓
             agent core
```

核心层不得导入 OpenAI SDK 类型、终端框架类型或平台专属进程类型。

## 技术选择

| 决策点 | 选择 | 理由 |
|---|---|---|
| 语言 | Java 21 | 支持 record、sealed interface、虚拟线程和成熟生态 |
| 构建 | Gradle Kotlin DSL | 可重复构建、依赖与测试管理清晰 |
| 测试 | JUnit 5 | 支持单元、参数化和集成测试 |
| 模型接口 | OpenAI Responses API | 支持文本、多轮状态和自定义函数工具 |
| JSON | Jackson | 统一序列化、Schema 参数和事件日志 |
| 配置 | YAML + 环境变量 | 非敏感配置可读，秘密与项目文件分离 |
| CLI | 简单行式交互 | V1 避免 TUI 复杂度 |
| 工具执行 | V1 串行 | 权限、顺序和失败恢复更易推理 |
| 文件修改 | 结构化 patch | 比整文件覆盖更小、更易审查和恢复 |
| 会话事件 | JSONL | 追加写、易调试、可作为验收证据 |
| 核心测试 | FakeLlmClient | 无真实 API 成本且结果确定 |

## 核心数据结构

### AgentConfig

```java
public record AgentConfig(
        String model,
        URI baseUrl,
        Duration modelTimeout,
        Duration commandTimeout,
        int maxTurns,
        int maxRepeatedCalls,
        int maxToolOutputChars,
        Path workspaceRoot,
        Path eventLog,
        ProxyConfig proxy
) {}
```

API Key 不进入该 record 的可序列化配置；启动时由凭据提供器从 `OPENAI_API_KEY` 读取。

### ConversationItem

```java
public sealed interface ConversationItem
        permits UserMessage, AssistantMessage, ToolCallRecord,
                ToolResultRecord {}
```

每个工具结果保存原始 `callId`，确保同名并发或连续调用不会错配。V1 虽串行执行，协议仍保留调用标识。

### ModelRequest

```java
public record ModelRequest(
        String instructions,
        List<ConversationItem> input,
        List<ToolSchema> tools,
        String previousResponseId,
        boolean parallelToolCalls
) {}
```

### ModelResponse

```java
public record ModelResponse(
        String responseId,
        List<ModelOutputItem> output,
        Usage usage
) {
    public String outputText();
    public List<ToolCall> toolCalls();
}
```

### ToolCall

```java
public record ToolCall(
        String callId,
        String name,
        JsonNode arguments
) {}
```

### ToolResult

```java
public record ToolResult(
        boolean success,
        JsonNode data,
        ToolError error,
        boolean truncated
) {}

public record ToolError(String code, String message) {}
```

### AgentResult

```java
public record AgentResult(
        AgentStatus status,
        String finalText,
        int turns,
        List<VerificationEvidence> evidence
) {}

public enum AgentStatus {
    COMPLETED, BLOCKED, CANCELLED, MAX_TURNS, FAILED
}
```

### PermissionDecision

```java
public record PermissionDecision(
        PermissionOutcome outcome,
        String reason
) {}

public enum PermissionOutcome {
    ALLOW, REQUIRE_CONFIRMATION, DENY
}
```

## 核心接口

### LlmClient

```java
public interface LlmClient {
    ModelResponse respond(ModelRequest request, CancellationToken token)
            throws LlmException;
}
```

实现：

- `OpenAiResponsesClient`：生产实现。
- `FakeLlmClient`：测试中按队列返回预设结果。

### Tool

```java
public interface Tool {
    ToolSchema schema();
    ToolRisk risk();
    ValidationResult validate(JsonNode arguments);
    ToolResult execute(JsonNode arguments, ToolContext context)
            throws ToolException;
}
```

### ToolRegistry

```java
public interface ToolRegistry {
    Optional<Tool> find(String name);
    List<ToolSchema> schemas();
}
```

### PermissionGate

```java
public interface PermissionGate {
    PermissionDecision evaluate(
            Tool tool,
            JsonNode arguments,
            AgentContext context
    );
}
```

`ConsoleApprovalPrompt` 只在决定为 `REQUIRE_CONFIRMATION` 时询问用户。

### WorkspaceBoundary

```java
public interface WorkspaceBoundary {
    Path resolveReadable(String relativePath) throws WorkspaceViolation;
    Path resolveWritable(String relativePath) throws WorkspaceViolation;
}
```

必须检查：绝对路径、规范化后的父目录穿越、真实路径、符号链接链、目标父目录及工作区根边界。

### ProcessRunner

```java
public interface ProcessRunner {
    ProcessResult run(
            CommandRequest request,
            CancellationToken token
    ) throws ProcessExecutionException;
}
```

### EventSink

```java
public interface EventSink {
    void emit(AgentEvent event);
}
```

`CompositeEventSink` 同时发送到控制台和脱敏 JSONL 日志。

## 模块设计

### bootstrap

**职责：** 程序入口、组合依赖、关闭资源。

**包含：** `Main`、`AgentApplicationFactory`。

**依赖：** config、cli、agent、具体适配器。

### config

**职责：** YAML 加载、默认值、环境变量凭据、配置验证、代理配置。

启动失败必须区分：配置缺失、字段无效、密钥缺失。禁止打印密钥。

### cli

**职责：** 行式输入、事件展示、审批、取消和退出。

V1 命令：

- 普通文本：提交任务。
- `/exit`：安全退出。
- `/cancel`：取消当前任务。
- `/status`：显示模型、工作区和限制，不显示秘密。

### agent

**职责：** Agent Loop、状态转换、终止条件、错误策略、调用重复检测。

不负责实际文件、网络或进程操作。

### conversation

**职责：** 保存当前进程内的用户消息、模型输出、工具调用和工具结果；产生发送给 LLM 的输入。

V1 不承诺跨进程恢复，但事件日志可用于调试。

### llm

**职责：** 将内部请求转换为 Responses API 请求，将响应转换成内部输出项，分类认证、限流、网络、超时和服务错误。

每轮都显式传递系统指令。V1 禁用并行工具调用。

### tool

**职责：** 工具协议、Schema、注册、参数校验、错误统一格式和输出预算。

工具实现不得自行绕过权限；权限位于执行前的 Agent 流程中。

### workspace

**职责：** 工作区边界、路径解析、文件大小限制、文本编码检查、链接逃逸防护。

### permission

**职责：** 根据风险、参数和运行策略返回允许、确认或拒绝。

默认策略：

| 风险 | 默认决定 |
|---|---|
| READ_ONLY | 工作区内自动允许 |
| WORKSPACE_WRITE | 请求确认 |
| COMMAND | 请求确认 |
| NETWORK | 请求确认 |
| DESTRUCTIVE | 拒绝 |
| OUTSIDE_WORKSPACE | 拒绝 |

### process

**职责：** 在工作区启动命令、采集 stdout/stderr、超时终止、取消、退出码和输出截断。

V1 使用明确的参数数组；不提供任意 shell 字符串拼接接口。若用户/模型确需 shell 语法，必须通过明确 shell 模式并单独审批。

### event

**职责：** 统一运行事件、控制台呈现、JSONL 保存和敏感信息脱敏。

## 工具设计

### list_files

- 风险：`READ_ONLY`
- 输入：相对目录、可选 glob、最大结果数。
- 输出：相对路径、类型、是否截断。
- 禁止：返回工作区外路径、递归无限跟随链接。

### read_file

- 风险：`READ_ONLY`
- 输入：相对文件路径、可选起止行。
- 输出：文本内容、行范围、是否截断。
- 错误：不存在、非文件、二进制、过大、越界。

### search_text

- 风险：`READ_ONLY`
- 输入：模式、相对范围、可选 glob、最大匹配数。
- 输出：相对路径、行号、有限上下文、是否截断。
- V1 可调用本地搜索组件，但不能依赖用户必然安装某个外部程序；应有清晰的可用性检查或 Java 回退实现。

### apply_patch

- 风险：`WORKSPACE_WRITE`
- 输入：结构化补丁。
- 执行前：解析、工作区验证、预应用、生成 diff、请求确认。
- 执行：原子或尽可能可回滚地应用。
- 冲突：保持文件不变并返回 `PATCH_CONFLICT`。

### run_command

- 风险：`COMMAND`，含网络或危险操作时升级风险。
- 输入：可执行程序、参数数组、可选超时。
- 输出：退出码、stdout、stderr、耗时、超时/取消/截断标志。
- 工作目录固定为 workspaceRoot 或其内部经过验证的子目录。

## Agent Loop 状态机

```text
IDLE
  └─ user task → REQUESTING_MODEL

REQUESTING_MODEL
  ├─ final text → COMPLETED
  ├─ tool calls → VALIDATING_CALLS
  ├─ recoverable model error → RETRY_WAIT
  ├─ fatal model error → FAILED
  └─ cancel → CANCELLED

VALIDATING_CALLS
  ├─ valid → CHECKING_PERMISSION
  └─ invalid → RECORDING_TOOL_RESULT

CHECKING_PERMISSION
  ├─ allow → EXECUTING_TOOL
  ├─ confirm → WAITING_APPROVAL
  └─ deny → RECORDING_TOOL_RESULT

WAITING_APPROVAL
  ├─ allow → EXECUTING_TOOL
  ├─ deny → RECORDING_TOOL_RESULT
  └─ cancel → CANCELLED

EXECUTING_TOOL
  ├─ result/error → RECORDING_TOOL_RESULT
  └─ cancel → CANCELLED

RECORDING_TOOL_RESULT
  ├─ more calls → VALIDATING_CALLS
  └─ calls complete → REQUESTING_MODEL

RETRY_WAIT
  ├─ retry allowed → REQUESTING_MODEL
  └─ exhausted/cancel → FAILED or CANCELLED
```

## Agent Loop 算法

```java
conversation.addUser(userInput);
String previousResponseId = null;

for (int turn = 1; turn <= maxTurns; turn++) {
    token.throwIfCancelled();

    ModelResponse response = retryPolicy.execute(() ->
        llm.respond(new ModelRequest(
            systemPrompt,
            conversation.pendingInput(),
            registry.schemas(),
            previousResponseId,
            false
        ), token)
    );

    conversation.record(response);
    previousResponseId = response.responseId();

    if (response.toolCalls().isEmpty()) {
        if (response.outputText().isBlank()) {
            return failed("EMPTY_MODEL_RESPONSE");
        }
        return completed(response.outputText(), turn);
    }

    for (ToolCall call : response.toolCalls()) {
        token.throwIfCancelled();

        ToolResult result = validateFindApproveExecute(call);
        result = outputBudget.limit(result);
        conversation.addToolResult(call.callId(), result);
        events.emit(toolResultEvent(call, result));

        if (loopGuard.repeatedFailureLimitReached(call, result)) {
            return blocked("REPEATED_TOOL_FAILURE");
        }
    }
}

return maxTurnsReached();
```

## 重试策略

- 认证或无效请求：不重试。
- 速率限制：尊重服务建议等待时间，否则指数退避；有上限且可取消。
- 临时服务错误：有限次数指数退避。
- 网络断开或请求超时：有限次数重试；每次产生可观察事件。
- 工具参数错误、未知工具、权限拒绝：作为工具结果返回模型，不做运行时重试。
- 相同工具、相同规范化参数、相同失败连续达到上限：结束为 `BLOCKED`。

## 系统提示词职责

系统提示词规定行为：先检查、最小修改、使用工具证据、不得伪造结果、遵守工作区和权限、遇到重复失败改变策略、完成后报告验证。

安全策略必须由程序执行，不能以系统提示词作为唯一防线。

## 错误模型

统一错误族：

- `CONFIG_*`
- `AUTH_*`
- `MODEL_*`
- `RATE_LIMITED`
- `UNKNOWN_TOOL`
- `INVALID_TOOL_ARGUMENTS`
- `PATH_*`
- `PERMISSION_DENIED`
- `PATCH_*`
- `COMMAND_*`
- `CANCELLED`
- `LIMIT_*`

用户消息提供可操作建议；事件日志保存脱敏后的诊断字段。默认不输出完整堆栈，调试模式仍需脱敏。

## 取消与资源生命周期

- 每个用户任务创建一个 `CancellationTokenSource`。
- CLI 的 `/cancel` 或中断信号触发取消。
- LLM HTTP 请求应响应线程中断或 SDK 取消机制。
- 进程取消先正常终止，等待短暂宽限后强制终止，并处理子进程树。
- 应用退出时关闭 HTTP 客户端、日志 writer 和活动进程。

## 事件模型

关键事件：

- `TaskStarted`
- `ModelRequestStarted/Completed/Failed`
- `ToolCallReceived`
- `PermissionRequested/Resolved`
- `ToolStarted/Completed/Failed`
- `RetryScheduled`
- `TaskCompleted/Blocked/Cancelled/Failed`

事件字段包括时间、taskId、turn、callId、工具名、耗时和状态；参数、输出与异常先经过脱敏和大小限制。

## 文件组织

```text
star-code/
├─ build.gradle.kts
├─ settings.gradle.kts
├─ AGENTS.md
├─ README.md
├─ config.example.yaml
├─ src/
│  ├─ main/java/com/starcode/
│  │  ├─ Main.java
│  │  ├─ bootstrap/
│  │  │  └─ AgentApplicationFactory.java
│  │  ├─ agent/
│  │  │  ├─ AgentLoop.java
│  │  │  ├─ AgentContext.java
│  │  │  ├─ AgentResult.java
│  │  │  ├─ LoopGuard.java
│  │  │  └─ CancellationToken.java
│  │  ├─ cli/
│  │  │  ├─ CommandLineApp.java
│  │  │  ├─ ConsoleApprovalPrompt.java
│  │  │  └─ ConsoleEventSink.java
│  │  ├─ config/
│  │  │  ├─ AgentConfig.java
│  │  │  ├─ ConfigLoader.java
│  │  │  └─ CredentialProvider.java
│  │  ├─ conversation/
│  │  │  ├─ Conversation.java
│  │  │  └─ ConversationItem.java
│  │  ├─ llm/
│  │  │  ├─ LlmClient.java
│  │  │  ├─ ModelRequest.java
│  │  │  ├─ ModelResponse.java
│  │  │  ├─ LlmException.java
│  │  │  └─ openai/OpenAiResponsesClient.java
│  │  ├─ tool/
│  │  │  ├─ Tool.java
│  │  │  ├─ ToolRegistry.java
│  │  │  ├─ ToolSchema.java
│  │  │  ├─ ToolResult.java
│  │  │  └─ impl/
│  │  │     ├─ ListFilesTool.java
│  │  │     ├─ ReadFileTool.java
│  │  │     ├─ SearchTextTool.java
│  │  │     ├─ ApplyPatchTool.java
│  │  │     └─ RunCommandTool.java
│  │  ├─ permission/
│  │  │  ├─ PermissionGate.java
│  │  │  └─ DefaultPermissionGate.java
│  │  ├─ workspace/
│  │  │  └─ WorkspaceBoundary.java
│  │  ├─ process/
│  │  │  ├─ ProcessRunner.java
│  │  │  └─ DefaultProcessRunner.java
│  │  └─ event/
│  │     ├─ AgentEvent.java
│  │     ├─ EventSink.java
│  │     ├─ JsonlEventSink.java
│  │     └─ SecretRedactor.java
│  └─ test/java/com/starcode/
│     ├─ agent/AgentLoopTest.java
│     ├─ llm/FakeLlmClient.java
│     ├─ tool/
│     ├─ workspace/
│     ├─ process/
│     └─ integration/
└─ docs/
```

具体实现时允许在不改变模块职责的情况下微调文件数量；架构性改变必须更新本文件。

## 测试接缝

- `FakeLlmClient`：预设响应序列和请求捕获。
- `FakeTool`：控制成功、失败、超时和副作用计数。
- `FakePermissionGate`：允许、拒绝、确认路径。
- 临时工作区：验证路径和补丁行为。
- `FakeProcessRunner`：核心循环测试不启动真实进程。
- 小型真实进程 fixture：进程集成测试验证退出码、输出、超时和取消。
- 内存 EventSink：断言事件顺序和脱敏。

## 需求覆盖

| 需求 | 负责组件 |
|---|---|
| F1 | CLI、AgentApplication |
| F2 | Config、CredentialProvider、OpenAiResponsesClient |
| F3 | AgentLoop、Conversation、LoopGuard |
| F4 | LlmClient、ToolRegistry、Conversation |
| F5 | ListFilesTool、WorkspaceBoundary |
| F6 | ReadFileTool、WorkspaceBoundary |
| F7 | SearchTextTool、WorkspaceBoundary |
| F8 | ApplyPatchTool、PermissionGate、WorkspaceBoundary |
| F9 | RunCommandTool、ProcessRunner、PermissionGate |
| F10 | PermissionGate、ConsoleApprovalPrompt |
| F11 | WorkspaceBoundary、所有工具 |
| F12 | CancellationToken、LoopGuard、ProcessRunner |
| F13 | 错误模型、重试策略、事件系统 |
| F14 | EventSink、JsonlEventSink、SecretRedactor |
| F15 | AgentResult、CLI、验证证据 |
| N1 | Permission、Workspace、Process、Redactor |
| N2 | 所有端口接口与 Fake 实现 |
| N3 | AgentLoop、Patch、Process 生命周期 |
| N4 | EventSink、CLI、结构化错误 |
| N5 | 分层与依赖方向 |
| N6 | ProcessRunner、平台能力检测 |
| N7 | 配置限制、OutputBudget、LoopGuard |
| N8 | CredentialProvider、SecretRedactor |

## 未决实现细节

以下内容不改变 V1 需求，可在实现任务中以最小方案确定并记录：

- YAML 库和 OpenAI Java SDK 的确切版本。
- patch 解析库或内部最小实现。
- Windows 子进程树终止的具体兼容策略。
- 搜索工具采用纯 Java 实现还是在可用时调用 `rg` 并回退。
