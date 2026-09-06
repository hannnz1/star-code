# Star Code benchmark 第二阶段报告

**本报告只记录当前生产实现。未修改 Agent、ContextManager、MCP loading 或 Multi-Agent 核心代码。**

## 1. Baseline

- Commit：`014808a0b0942f25bc4f1c3f415fa63262f98176`
- Tag：`benchmark-baseline-v1`
- 每次实验核对 tag，并检查生产源代码与 baseline 的差异。新增文件仅位于 `benchmarks/`。基准测试代码尚未提交；各批次保存源码快照和 build-manifest，不能把 baseline commit 当作 harness commit。

## 2. 架构与文件

- `run.ps1`：使用 Java 21 重新编译生产源码和独立 harness，以现有 fat JAR 提供依赖。运行 classpath 优先加载重新编译的生产类。
- `run-all.ps1`、`requirements-lock.txt`：顺序执行实验、安装固定版本估算工具、重建报告。
- `src/bench/Common.java`、`BenchMain.java`：baseline 校验、环境和原始结果记录。
- `WireRecorder.java`：本地 HTTP 转发记录器；保存生产客户端序列化后的请求与响应，排除认证头，替换已知 API key。MCP 使用明确标记的本地确定性 SSE 接收端。
- `RecordingClient.java`：记录实际 LlmClient 调用、phase、线程、输入、输出、usage、失败和耗时。
- `McpFixture.java`：真实 stdio MCP fixture server；通过生产 McpManager、ToolRegistry、AgentLoop 和 OpenAiResponsesClient。
- `ContextBench.java`、`generate_fixtures.py`、`context-retention/*.json`：冻结 50-fact 数据集、原始触发阈值和真实 compact。
- `GateBench.java`、`generate_gate_fixture.py`、`multi-agent/fixture/`：固定独立 Git 工作区、两个可并行组件、21 项断言的统一 verifier；生产 ChatApplication 负责分解、创建子 Agent 和集成。
- `report.py`、`test_scoring.py`、`write_report.py`：从 raw 重建 JSON/CSV/Markdown；评分器有 12 个负向与正向检查。

原始记录在 `results/raw/<benchmark>/<batch>/`；派生结果在 `results/summary/`。失败批次保留，不覆盖。请求与响应通过相同序号关联；retry 由 compact 阶段实际调用数量及异常记录还原。缺失 usage 使用 null，不能按零计费解释。

## 3. MCP Full Loading

状态：**BLOCKED**。

| MCP 工具数 | 尝试 | 有效样本 | schema bytes 均值 | schema tokens 估算均值 |
|---:|---:|---:|---:|---:|
| 10 | 5 | 0 | 未测得 | 未测得 |
| 25 | 5 | 0 | 未测得 | 未测得 |
| 50 | 5 | 0 | 未测得 | 未测得 |
| 100 | 5 | 0 | 未测得 | 未测得 |

- MCP 数量之外，每个请求还包含 6 个生产内置工具。两者分别统计，不能把总数误写成 MCP 数量。
- 固定 seed 20260905；schema 从生产内置工具描述/结构生成，为合成负载，不能代表真实 MCP 工具市场分布。
- `tiktoken==0.12.0 / o200k_base` 仅为兼容估算；不是 gpt-5.4-mini 官方计费 tokenizer。完整 JSON token 估算包含 JSON 语法，也不同于 provider 输入 usage。
- 本地 SSE 接收端不测模型推理或真实网络延迟；wall-clock 不包含每个规模之前的 MCP discovery。
- Lazy Loading：`NOT_IMPLEMENTED`；改善率没有数值。
- 原始与派生数据：`mcp-runs.json`、`mcp-runs.csv`、`mcp-summary.json`。

## 4. Context Retention

状态：**INCOMPLETE**；真实 compact 成功：2/5，失败：3/5，执行成功率：40.0%；完成评分：2/5。

| 重复 | compact 触发 | 实际状态 | summary 闭合 | SSE completed | summary-only | complete context | compact 重试 |
|---|---|---|---|---|---:|---:|---:|
| repeat-1 | True | FAILURE | False | False | 未测得 | 未测得 | 0 |
| repeat-2 | True | SUCCESS | True | True | 84 | 94 | 0 |
| repeat-3 | True | FAILURE | False | False | 未测得 | 未测得 | 0 |
| repeat-4 | True | SUCCESS | True | True | 0 | 68 | 0 |
| repeat-5 | True | FAILURE | False | False | 未测得 | 未测得 | 0 |

summary-only 均值：42；min/max：0/84。

complete context 均值：81；min/max：68/94。

- 固定 240 条消息、384123 字符、50 个事实，覆盖早/中/晚、路径、类/方法、API、数字、用户约束、原因、失败尝试、否定约束、待办、下一步。生产估算约 109749 tokens，原始 128000 context window 的 auto 阈值为 95000；没有调整阈值。
- 调用生产 `shouldAutoCompact()` 与 `compact(..., AUTO, ...)`。summary prompt、保留近期消息算法和 recovery 逻辑均保持原样。
- 不加载 MemoryManager，不注入用户 memory；每次使用独立 session/工具结果目录和空 PromptContext。
- 评分器读取真实模型的结构化答案和逐字证据，校验类型、数字、否定极性、实体归属、引用是否来自实际上下文。自然语言原因只接受预先列出的语义别名；标识符按精确值匹配。
- summary-only 只使用 summary。complete context 汇总已验证 summary、完整上下文抽取结果及未改动近期消息中的原始事实。逐事实列出 summary / retained recent messages / recovery attachment / missing，可有多个来源。
- 长文本存在性检查只用于验证证据或未改动原始句子，不用单个关键词判定事实保留。
- 每次保存输入、原始模型响应、summary、近期消息、recovery、抽取提示和答案、usage、错误/重试。
- 原始与派生数据：`context-runs.json/csv`、`context-*-facts.json`、`context-facts.csv`、`context-summary.json`。

## 5. Multi-Agent feasibility gate

状态：**BLOCKED**。

原因：`java.nio.file.AccessDeniedException: C:\Users\Administrator\Desktop\project\star code\benchmarks\.work\gate-2026-09-04T17-12-46.919368500Z-94dbacb1`。

Main Agent calls：0；Sub-Agent calls：0；统一测试通过：未执行。

- 基准任务为 shipping quote 与 discount pricing 两个独立组件。主 Agent 读取 README 自行选择分解方式，至少两个实际子 Agent 在独立 Worktrees 并行修改。Harness 不创建任务分解内容，不代替产品 merge。
- PASS 必须同时满足：至少两个子 Agent、独立 Worktrees、执行区间重叠、至少两个 Worktrees 有修改、两个组件都进入主 checkout、子 Agent 完成、verifier 未被修改、最终统一测试成功。
- Harness 仅在产品结束后追加运行相同统一 verifier，不能把子 Agent DONE 当成功。
- 保存父对话、调用记录、任务与 Worktree 生命周期、修改 diff、最终 Git 状态、统一测试输出；若启动阶段就失败，下游字段保持未执行，不伪造空记录为成功。
- 生命周期重叠包含模型等待/工具时间，仅证明任务生命周期重叠；不是 GPU/CPU 同时执行证明。没有 speedup 数字。

## 6. 环境、异常与限制

- 运行环境：Microsoft Java 21.0.11+10-LTS，Windows 11 amd64，20 个逻辑处理器；模型 gpt-5.4-mini，openai-responses，thinking=false，context_window=128000。temperature 与模型采样 seed 未由生产客户端指定，采用服务默认值；固定 seed 仅保证 fixture。
- 使用 config.yaml 指定的上游服务；本报告不能据模型名称确认其服务实现与官方 OpenAI 完全相同。认证内容不会进入记录。
- 当前 Codex Windows 运行环境的 Java `toRealPath` 发生 AccessDeniedException，目录授权后仍未解除。MCP discovery 能成功，ToolContext 初始化被阻止；gate 的独立 Git commit 成功，Agent 初始化被阻止。属于环境阻塞，不能据此判定产品没有相关能力。
- javac 在关闭 JAR 文件系统时也报告 AccessDeniedException，虽然旧运行返回码为 0 并产生 class 文件，但不能当作无异常构建。最终 runner 已增加日志错误检查，发生该问题会停止。
- 初版试运行的 HTTP 记录器只在响应结束时保存响应；后续版本补充流式落盘、调用开始记录和 900 秒 harness request watchdog。旧批次保留原 harness 源码快照，不能将后续 instrumentation 修复解释为生产优化。
- 首次真实 compact 响应持续约 411 秒，包含 166244 字符（o200k_base 估算 29427 tokens），有 <summary> 但无闭合标签。HTTP 200 的 SSE 结束于 delta，未出现 response.completed/response.failed，也没有 usage。无法仅凭这些证据区分上游截断、输出限制或连接问题；不能断言一定是摘要模板缺陷。
- 上下文 fixture 是合成纯文本、一次压缩。它不覆盖连续多轮压缩、真实工具结果卸载、8 小时会话，也没有文件快照恢复样本。
- 三个失败样本分别在约 411、898、718 秒结束，均有 `<summary>` 开标签但没有闭合标签，也没有 SSE `response.completed`；三次均未触发 harness timeout。生产 `compact()` 正确拒绝了不完整 summary。仅凭记录不能确定是上游输出截断、输出限制或连接结束。
- 两个成功样本的 strict evidence 分数波动很大：其中一个 summary-only 为 0%，原因主要是抽取器给出了释义证据而非逐字证据。该指标混合了摘要保留、问答恢复和证据格式遵循，不能把 0% 解释为 summary 没有事实；本阶段保留率不够可信。
- 同一模型用于生成摘要和抽取答案；确定性评分规则较保守，语义等价但未在冻结别名中的说法可能产生假阴性，仍需人工复核逐事实证据。
- 测试次数不足、请求失败、超时或缺失输出时不发布百分比；五个样本也不能支持普遍性能结论。

## 7. 可用结论与简历限制

足够可信：baseline/tag、源码未侵入、固定 fixture、明确的原始数据结构、实际失败阶段与错误日志；只有取得至少 5 个有效重复且复核证据后，才能引用对应固定数据集的测量值。

**目前不能写入简历的数字**：MCP token 降低 85%；8 小时不丢上下文；权限弹窗从 30 次降至 5 次；信息保留率从 17% 提升至 100%；多 Agent 耗时降低 60%。本阶段没有 Lazy/旧模板/单 Agent 对照实验，也没有安全弹窗和 SWE-bench-Live 评测。

## 8. 下一阶段 MCP Lazy Loading 建议（未实现）

在 Full Loading 至少取得 20 个有效样本后，冻结同一 fixture 和请求构成作为对照。后续设计可分离精简工具索引与完整 schema，通过按需发现/激活加载具体工具；处理工具命名、缓存与失效、会话激活集合、工具变更和调用前校验。评价应同时报告输入 schema 开销、发现调用增加的 token/延迟、实际任务成功率及总 token，而不能只比较首个请求。85% 必须由公平实验得出，不能作为实现验收目标。

## 9. 重跑

在用户 PowerShell 中运行：

```powershell
& 'C:\Users\Administrator\Desktop\project\star code\benchmarks\run-all.ps1'
```

脚本使用环境中已有 API key，不要求把 key 写进命令或提交到 Git。每次创建新 raw batch。复算报告只需运行 `report.py` 和 `write_report.py`，不会再次调用模型。
