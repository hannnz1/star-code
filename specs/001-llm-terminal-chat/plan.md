# Feature 001 Plan

## 架构

```text
Main → ConfigLoader → ProviderSelector → ChatApplication
                                      ├─ Conversation
                                      ├─ LlmClient
                                      │  ├─ AnthropicClient
                                      │  └─ OpenAiResponsesClient
                                      └─ TerminalUi
```

协议层向 UI 统一产生 `TextDelta`、`Completed` 和 `Failed` 事件；thinking/reasoning 事件不展示。会话只在请求成功完成后提交本轮用户与助手消息。HTTP 请求和 SSE 消费运行于虚拟线程，UI 通过线程安全回调接收事件。

## 技术选择

- Java 21、Gradle Kotlin DSL、JUnit 5。
- JLine 负责终端输入、raw mode 与 ANSI 能力。
- Java HttpClient 负责 HTTP/SSE，Jackson 负责 JSON，SnakeYAML 负责配置。
- API Key 通过 Provider 的 `api_key_env` 指向环境变量。
- 代理通过 YAML `proxy` 节点配置。

## 核心接口

```java
interface LlmClient {
    Completion stream(List<ChatMessage> history, String userText,
                      Consumer<StreamEvent> events) throws LlmException;
}
```

`Conversation` 维护已提交历史；`ChatApplication` 管理 idle/requesting 状态、计时、错误恢复与退出；协议实现负责各自 JSON 和 SSE 映射。

## 错误策略

配置错误在 TUI 前终止；请求错误转换为认证、限流、超时、模型、协议、网络和服务错误。错误不提交到模型历史，界面恢复输入状态。

