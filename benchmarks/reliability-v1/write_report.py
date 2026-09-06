"""Regenerate the human report from saved comparison data, without paid calls."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
data=json.loads((ROOT/'results/summary/context-reliability-comparison.json').read_text(encoding='utf-8'))
b=data['before']['summary'];a=data['after']['summary']
def cell(s,k):
    v=s.get(k)
    return 'unavailable' if v is None else f"{v['mean']:.2f} / {v['median']:.2f} / {v['min']:.2f}–{v['max']:.2f} (n={v['n']})"
metrics=[('原评分器：summary-only (%)','legacy_summary_percent'),('原评分器：完整上下文 (%)','legacy_complete_percent'),('逐字完整事实：summary-only (%)','summary_exact_percent'),('逐字完整事实：完整上下文 (%)','complete_exact_percent'),('规则语义：summary-only (%)','summary_semantic_percent'),('规则语义：完整上下文 (%)','complete_semantic_percent'),('成功压缩耗时 (s)','compact_wall_clock_seconds'),('整轮耗时，包含失败和评分 (s)','wall_clock_seconds'),('成功压缩 input tokens','compact_input_tokens'),('成功压缩 output tokens','compact_output_tokens'),('成功压缩 total tokens','compact_total_tokens'),('成功整轮 total tokens，含提取评分','total_tokens')]
table='\n'.join(f'| {label} | {cell(b,k)} | {cell(a,k)} |' for label,k in metrics)
runs='\n'.join(f"| {r['run']} | {r['compact_status']} | {r['retries']} | {r['legacy_summary_percent']:.0f} | {r['legacy_complete_percent']:.0f} | {r['summary_exact_percent']:.0f} | {r['summary_semantic_percent']:.0f} | {r['complete_semantic_percent']:.0f} |" for r in data['after']['runs'])
text=f'''# Context Compression Reliability Improvement

结论：**NEEDS_MORE_TESTING**。固定实验中执行成功由 2/5 提升到 10/10，但不能据此宣称普遍 100% 成功或信息保留质量不下降。原评分器的完整上下文均分下降；辅助规则评分也未证明质量不劣于修复前。未追加付费运行到 20 次。

## Before

Runs: {b['attempts']}；Successful: {b['successful']}；Failed: {b['failed']}；Success Rate: {b['success_percent']:.0f}%。

固定 baseline commit/tag：`014808a0b0942f25bc4f1c3f415fa63262f98176` / `benchmark-baseline-v1`。修复后仍在该 HEAD 上，是未提交的工作区改动；不能用同一个 HEAD 冒充相同代码。after 批次保存 production-diff.patch、包含新增 validator 的 source-snapshot、build-manifest 和源文件哈希。

before 原始数据：`{data['before']['runs'][0]['raw_path'].rsplit('/',1)[0] if '/' in data['before']['runs'][0]['raw_path'] else str(Path(data['before']['runs'][0]['raw_path']).parent)}`。

before repeat 1/3/5 都有 opening summary tag，却在第六节复述原会话过程中结束，缺少 closing tag 和后续章节。响应分别约 166244 / 249724 / 155316 字符。repeat 3/5 的记录器报告 IOException closed；终止事件和完整 usage 不可用。没有证据将它们断言为 provider 的特定 token limit。repeat 3 的 898 秒结束不是 900 秒 watchdog 触发；harness_timeout=false。另有一个无完整 run.json 的 interrupted repeat 3 文件夹，未纳入五个完成尝试，额外调用的完整用量不可得。

## Root Cause

详细调用链与逐次证据见 [Phase 1 report](context-compression-root-cause.md)。原 prompt 要求第六节保留所有用户消息的原文，又要求 analysis；模型将压缩变成大段复述。未完成的长响应不是轻微格式差异，不能补一个 closing tag 就当成功。旧 parser 必须拒绝这些输出，但缺少输出结构验证和针对格式错误的有限重试。Responses client 可能在没有 response.completed 的 EOF 返回 Completion，不能只检查返回对象存在。

## Fix

生产路径只修改 ContextManager 并新增 SummaryValidator。

- ContextManager.summaryPrompt：保留原九个章节，要求去重摘要而非逐条复制全部历史，目标不超过 12000 字符；强调精确标识、数字、否定、原因、失败尝试和待办。没有写入任何 benchmark facts。未修改触发阈值、recent retention 或 recovery 机制。
- SummaryValidator.parse：接受外围说明、Markdown fence、大小写/空白和允许的标题排版；完整 closing summary tag、九个有序非空章节仍必需。重复 summary block、缺章节、空内容、超过 28000 字符等明确拒绝。可缺失的是非关键 Markdown closing fence，不能缺 summary closing tag。
- ContextManager 的总结调用：最多两次总尝试，即最多一次重试。格式失败重新使用原输入生成，不将坏摘要替换成历史。Responses 协议额外要求现有 protocolState 中的 completed 输出数组。其他协议标记截断状态未知。没有更改 LLM client 全局实现。
- compact 只在结果完整验证之后返回新上下文并重置 usage anchor；失败抛出异常，保留旧上下文。原调用方失败会中断当前 turn，并不自动继续本次请求；session 仍可用于后续操作。没有承诺磁盘会话的崩溃原子性。
- 新增 lastCompression 和 metadata-only compression-events.jsonl：时间、模型、触发原因、输入估算、每次响应长度、验证原因、截断信号、重试、摘要/保留消息大小、结局和异常类型。不默认记录生产原始对话、响应或 API key。

## After

Runs: {a['attempts']}；Successful: {a['successful']}；Failed: {a['failed']}；Success Rate: {a['success_percent']:.0f}%。

10/10 使用生产 shouldAutoCompact 触发：50 facts、240 messages、384123 字符、109749 生产估算 tokens、95000 threshold。Java 21.0.11、Windows 11、gpt-5.4-mini、openai-responses、128000 context window、thinking=false。模型采样使用相同 provider default；seed=20260905 固定数据，不保证模型确定性。Memory 隔离。

重试率 {a['retry_percent']:.0f}%，平均每轮重试 {a['average_retries']:.1f}。repeat 6 首次返回 MULTIPLE_SUMMARY_BLOCKS，第二次有效；因此总压缩调用 11 次，另外 20 次原评分提取调用，总共 31 次模型调用。其他九轮首次通过。自动化测试覆盖重试耗尽等失败路径，真实 after 批次没有重试耗尽样本。

下表每格为 **均值 / 中位数 / 最小–最大 (有效样本数)**。保留率只对成功且评分完成的样本计算，不能把失败当作 0% 保留，也不能将失败排除后称总体可靠性。

| 指标 | Before | After |
|---|---|---|
{table}

| After run | 压缩 | 重试 | 原 summary % | 原 full % | summary exact % | summary 规则语义 % | full 规则语义 % |
|---|---|---:|---:|---:|---:|---:|---:|
{runs}

## Evaluator reliability

原 extraction prompt、原 report.py、generator 和三份 fixture 均通过冻结 SHA256 校验，没有修改原分数以取得更好结果。旧评分依赖模型返回 typed value 与逐字 evidence，并校验主体和否定；引用稍有改写就会失败。before repeat 4 的 0% 不能解释为摘要没有事实。

新增离线 evaluate.py 独立输出每个事实的 exact_match（JSON 中 summary_exact / complete_exact）和 semantic_match（summary_semantic / complete_semantic），并保存逐个来源和证据：summary / retained recent messages / recovery attachment / missing/unverified。机器结果 `summary/context-reliability-comparison.json` 包含 before/after 每轮指标与全部事实证据；不覆盖旧结果。

Exact 要求完整原事实句，区分大小写、只规范空白；不是原评分器的“evidence 逐字引用”。规则语义要求同一短句内覆盖原命题的主体、实质词项和数值、符合否定关系，并拒绝竞争数字和多个事实主体。只做有限明确规范化，不依赖自由生成的 LLM judge。未匹配的改写是未验证，不是已证实遗忘。不能将此分数称为经过全面验证的语义保留率。

规则从 fixture 命题派生，未写入生产代码。{data['selftest_assertions']} 个确定性断言覆盖所有原命题、无关事实、反转否定、错误数字、错误主体和主体混淆；并不证明规则覆盖全部同义表达。规则实现于生成 after 输出之后，是探索性辅助指标而非预注册的主要终点。没有根据输出逐轮调规则。若要获得可信语义结论，应先冻结更广泛的独立正负评测集，再在未见数据上验证评分器。

## Reliability / Quality Trade-off

格式可靠性有明显样本改善，但质量没有形成不下降证据。原 full 均分 81% → 70.8%；规则 full 88% → 85%；逐字 full 81% → 40.4%。更简短的改写会自然降低逐字率，原提取器也有假阴性，仍不能据此抹去质量风险。两个 before 成功样本不足以稳定估计修复前质量分布。不能把辅助评分中的单轮 100% 当作整体 100%。

本批重试带来一次额外压缩调用；成功压缩平均耗时见表，不能泛化为产品速度提升。旧样本一次异常长输出使均值非常不稳定；记录器保存流内容也会增加大响应的 IO 成本，早期/恢复运行的记录方式差异进一步限制耗时因果比较。没有交错随机 before/after，provider 服务负载和缓存状态也没有控制。

Token 来自可完成响应的 usage：成功压缩输入均值约 66923 → 73768（after 含重试），输出约 19104 → 2536.3。before 失败请求没有完整 usage，不能估算成零，也不能声称整批节省了某个百分比成本。after 含原评分调用共计 {sum(r['total_tokens'] for r in data['after']['runs'])} provider total tokens；未换算货币，缓存计费与服务商价格未核实。不要把生产字符估算 109749 当作 provider 官方 input tokens。

## Tests and reproducibility

离线 Context JUnit 23/23 通过，日志 `reliability-unit-tests.txt`；包含正确/包裹/fence/非关键 fence 缺失、缺 closing、空白、截断、malformed、章节顺序、重复、长度、重试成功/耗尽、旧 context 和 usage 保留、协议未完成、认证不重试与敏感信息不入日志等。

早期沙箱中的标准 javac/Gradle 遇到 Windows AccessDenied，真实实验通过 JavaCompiler.getTask 返回成功的全量生产源编译类运行；文件管理器关闭时仍报 AccessDenied，已保存 build-manifest/compile.log。随后在获准的标准环境执行 `gradlew.bat test --tests com.starcode.context.* --console=plain`，结果 **BUILD SUCCESSFUL**（12 秒），日志 `reliability-gradle-tests.txt`。此独立验证通过，不改写真实批次所用构建来源。

复现入口：`benchmarks/run-context-reliability.ps1 -Mode Report -Python <python-path>` 只读取 raw，重新生成评分 JSON 和本文，不调用付费模型。`-Mode Verify` 执行标准 Context Gradle 测试和全量源编译；`-Mode Run` 先验证再新增 10 次真实运行，会产生 API 费用。需要 JDK 21、可用 Gradle 依赖和 build/libs/star-code.jar，以及用户本地配置；脚本不复制 key。新 runner 的 Report 模式在本轮执行；Run 不重复执行已经完成的 10 次。原 run.ps1 遇编译错误会停止，不能静默使用旧 class。

## Files and scope

| 文件 | 用途 / 范围 |
|---|---|
| src/main/java/com/starcode/context/ContextManager.java | 生产：prompt、验证调用、有限重试、fail-safe、诊断 |
| src/main/java/com/starcode/context/SummaryValidator.java | 生产：结构解析和验证 |
| src/test/java/com/starcode/context/CompressionReliabilityTest.java | 新增确定性可靠性测试 |
| src/test/java/com/starcode/context/ContextManagerTest.java | 原 mock 改用原 prompt 已要求的完整章节名 |
| benchmarks/src/bench/ReliabilityMain.java | 独立 benchmark：冻结检查、源码/环境快照、新批次 |
| benchmarks/src/bench/ReliabilityContextBench.java | 独立 benchmark：原实验的可靠性版本，分开保存 compact status 和评分 status、生产诊断 |
| benchmarks/reliability-v1/comparison-manifest.json, protocol.md, frozen/* | 固定比较协议、原评分/数据生成逻辑与哈希 |
| benchmarks/reliability-v1/evaluate.py | 新增离线独立评分与反例断言 |
| benchmarks/reliability-v1/write_report.py | 从机器结果重新生成报告 |
| benchmarks/run-context-reliability.ps1 | Report / Verify / Run 复现入口 |
| benchmarks/results/context-compression-root-cause.md | 修改前根因报告 |
| benchmarks/results/raw/context-reliability/* | 10 次输入、响应、wire、usage、诊断、源快照 |
| benchmarks/results/summary/context-reliability-comparison.json | 全部前后指标、逐事实评分和证据 |
| benchmarks/results/context-compression-fix-report.md | 本报告 |
| benchmarks/.work/* | 忽略的本地编译工具/产物，不进入生产路径 |

现有 benchmarks 目录在 baseline 中未跟踪，所以 git status 会显示整个目录为新增；不能将第一阶段已有全部基础设施都称为本轮新增。MCP 和 Multi-Agent 生产代码未修改。没有新增提交或改动 baseline tag。

## Remaining Problems

- 九个非空章节只能证明结构，不能证明事实完整、无幻觉或正确处理矛盾。其他模型可能使用不同标题而被拒绝。
- 28k 接受上限和 12k prompt 目标可能丢失长会话细节；尚未做多轮反复压缩与 8 小时互动测试。
- 最大两次尝试限制了旧 CONTEXT_LENGTH 多轮剔除行为；现在最多剔除一个最旧用户消息组后再试，可能更早明确失败。该路径的事实损失须另测。
- 没有新增生产流的 idle timeout/硬输出取消；限制重试次数不等于限制每次请求的等待时长。其他协议不能确定截断，Responses 依赖当前客户端的 completed-state 约定。
- Memory 隔离且 dataset 无真实文件 recovery，未验证文件恢复与多轮 session 持久化/崩溃一致性。
- 只有 5 个 before / 10 个 after，10/10 的成功样本不支持一般性 100% 保证；也不足以验证所有 provider。
- 评分规则保守、覆盖有限，模型提取也不稳定；需要独立评审低分/冲突事实，并用未见样本验证评分器。

## Resume decision

**NEEDS_MORE_TESTING**。可以准确描述已实现“结构验证、一次有限重试、失败保留旧上下文与元数据诊断”，并将 **固定 50-fact/240-message 实验中 2/5 → 10/10 压缩完成，1/10 使用重试** 作为带范围的实验观察。暂不建议将其包装为稳定性能承诺。

不能写：100% 信息保留、17% → 100% 信息保留、8 小时不丢上下文，或本轮证明 MCP Token 降低 85%、权限弹窗 30 → 5、多 Agent 加速 60%。本轮也没有实施 MCP Lazy Loading。
'''
(ROOT/'results/context-compression-fix-report.md').write_text(text,encoding='utf-8')
print('REPORT='+str(ROOT/'results/context-compression-fix-report.md'))
