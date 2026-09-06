# Independent production benchmarks

Baseline: `014808a0b0942f25bc4f1c3f415fa63262f98176`, tag `benchmark-baseline-v1`.

This directory contains instrumentation only. Production AgentLoop, ContextManager, MCP discovery/loading and ChatApplication are compiled from the baseline sources and called directly. No source patching, reflection override, mock compaction, forced thresholds or harness merge is used.

## Run

Requirements: Windows, Git, JDK 21, Python 3.10+, existing `build/libs/star-code.jar` containing production dependencies, normal private `config.yaml` and its API-key environment variable. The current local SSE serialization fixture supports the `openai-responses` protocol. Real context and gate calls use the configured upstream provider and incur normal model usage.

From PowerShell, run `./run-all.ps1`. If Python is not discoverable, provide `-Python 'C:\path\to\python.exe'`. The script stops on compiler failures, including the observed Windows AccessDeniedException that javac can print despite exit code zero. Do not accept an interrupted compile as a clean validation.

Individual runs: `./run.ps1 -Benchmark mcp-loading`, `context-retention` or `multi-agent`. This recompiles baseline production sources and harness without changing the Gradle build. Each batch stores exact Java source snapshots and the dependency JAR/source hashes.

Offline regeneration: run `python report.py` followed by `python write_report.py`. Neither invokes a model. `python test_scoring.py` tests adversarial numeric, polarity, ownership, evidence and missing-value cases.

## Frozen inputs

Do not modify fixtures after viewing results. `generate_fixtures.py` deterministically regenerates the checked-in 50-fact fixture using seed 20260905. `generate_gate_fixture.py` regenerates the independent gate repository fixture. Preserve all raw batches if infrastructure changes require a rerun. Only Java's schema generator creates MCP fixtures at the start of a new MCP run, deterministically from the frozen production built-in schemas.

## Raw records

`results/raw/<benchmark>/<batch>/` contains environment metadata, per-repeat `run.json`, `wire/NNNN-request.json`, `wire/NNNN-response.sse`, `wire/NNNN-meta.json`, and real model `calls/NNNN.json` where applicable. Compact calls, extraction calls and gate calls carry different phase labels. Failure records are never substituted for successful zero-token runs.

Request headers and secrets are excluded. Known API key values are redacted from HTTP content. Raw results remain local and ignored by Git. Fixture expected answers are never sent to the summarizing or extracting model. No long-term memory is loaded by the context harness.

`results/summary/` has JSON and CSV outputs. These are derived files; use raw as the source of truth. Percentages are only produced when both extraction artifacts are present. Missing provider usage is null. `tiktoken/o200k_base` counts are explicitly estimates, not official gpt-5.4-mini billing counts. Main/sub-agent call usage is checked against actual SSE usage; cached input is not added twice.

## Gate

Only the Main Agent can decompose and integrate. The harness supplies the task contract and verifier, starts the actual production ChatApplication and observes task/worktree state. The isolated fixture authorizes named product tools through its existing permission configuration; this is not a safety benchmark or proof of OS isolation. The harness never runs merge, cherry-pick, checkout, or copies worker changes to the main checkout.

A task lifecycle overlap only demonstrates concurrent agent lifetimes, including waiting. PASS also requires changed independent worktrees, both components integrated into the main checkout, unchanged verifier, all workers completed, and final unified verification. A product or environment failure is BLOCKED, with speedup NOT_MEASURED.

## Runtime limits and limitations

Final HTTP instrumentation has a 900-second per-request watchdog; timed-out partial streams cannot count as a successful context run. The gate has a 12-minute total main-run deadline. These are harness execution caps, not production algorithm changes. Raw source snapshots distinguish initial diagnostic versions from final instrumentation.

Synthetic text-only compaction is not an eight-hour coding session. This dataset does not exercise file-recovery snapshots, large tool-result offloading or multiple compaction generations. Fact extraction uses the same model plus a frozen deterministic verifier and may conservatively reject valid unlisted paraphrases. Do not claim 17%-to-100%, 85% savings, 60% speedup or fewer permission prompts from this stage.