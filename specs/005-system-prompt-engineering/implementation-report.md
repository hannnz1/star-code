# Feature 005 实现报告

## 已实现

- 优先级驱动的系统提示装配和三个可选空槽。
- 独立动态环境块，Git 探测具有 500ms 上限并可降级。
- Anthropic 显式缓存标记和 OpenAI 稳定前缀布局。
- 两协议缓存 token 解析及运行期调试输出。
- 不持久化的 `<system-reminder>` 与 Plan Mode 完整/精简节奏。
- 工具描述和系统提示双重强化关键约定。

## 规格校正

原始 Spec 中的 Maven/Spotless 与本仓库不符；项目实际使用 Java 21 + Gradle，因此使用 `gradlew test` 和 `shadowJar` 验收。

## 人工验证

- 真实 Anthropic 连续请求：首次 cache write、后续 cache read 应大于零。
- 真实 OpenAI/兼容端点返回 `cached_tokens` 时应显示 cache read。
- `/plan` 多轮时 reminder 不应被复述，`/do` 应恢复写工具。
