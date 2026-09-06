# Star Code validation inventory

Inventory date: 2026-09-06. This is a pre-implementation inventory, not the final validation report. Historical resume numbers are unverified hypotheses. Production code has not been changed during this inventory.

## Frozen state and environment

- Main HEAD / original baseline: `014808a0b0942f25bc4f1c3f415fa63262f98176`; tag `benchmark-baseline-v1`.
- Main working tree contains the earlier, uncommitted ContextManager/ContextManagerTest changes, new SummaryValidator/CompressionReliabilityTest, and untracked benchmarks. HEAD alone does **not** identify the current implementation or harness.
- A/B OLD checkout: baseline above. Independently compiled NEW snapshot commit: `4f26fa7552e72a54d85a262255a2aff243042181` (in `benchmarks/.work/quality-v1/new`, not main history). Freeze/build/source manifests remain under `quality-v1/`.
- Java: Microsoft OpenJDK 21.0.11+10-LTS; Windows 11 Enterprise 10.0.22631, amd64.
- CPU: Intel Core i7-12700H, 14 cores / 20 logical processors. Physical RAM: 42,749,087,744 bytes (about 39.81 GiB).
- Existing A/B provider label: OpenAI; model `gpt-5.4-mini`; protocol `openai-responses`; thinking=false; context window=128000. Configured endpoint is recorded by hash in `quality-v1/model-config.json`; provider label does not authenticate the backend as official OpenAI.
- A/B temperature/max output/sampling seed: UNSET, provider defaults. Fixture/pair sampling seed: 20260905. Historical original batch starts 2026-09-04 UTC; reliability and controlled A/B 2026-09-05 UTC. Preserve raw timestamps rather than pooling studies.
- Planned independent reviewer: fresh stateless requests, configured provider/model, temperature=0, max_output_tokens=2048; actual metadata recorded before execution. No review labels existed at inventory time (0/160).
- Current test artifacts contain only the two context suites from the previous targeted run (23 tests); this is **not** evidence of a current full Gradle test pass.

## Five-feature status

| Feature | Production implementation | Unit tests | E2E tested | Benchmark exists | Sample size | Current result | Blocking issue | Resume status |
|---|---|---|---|---|---|---|---|---|
| Context Compression / evaluation | Tool-result offload and model compact; output validation, bounded retry, failure preserves history | ContextManagerTest, CompressionReliabilityTest; prior 23 pass | Real production shouldAutoCompact/compact; no long workflow | Original, reliability, controlled OLD/NEW, evaluator audit | 5 original; 10 NEW reliability; 20+20 HTTP200 A/B; 58 all-started | IMPLEMENTED_NEEDS_MORE_TESTING; OLD20/20, NEW19/20 internal compact success; model blind audit 0/160 | Semantic/exact validation and reviewer agreement unfinished; transport interruption; evaluator-v1 defect | FUNCTION_ONLY for mechanisms; no 17%→100% or confirmed retention improvement |
| MCP Lazy Loading | Ordinary MCP integration exists; complete schemas eagerly registered and passed into model requests; no lazy discovery/activation | McpClientFeatureTest; ToolSystemTest | MCP fixture discovery occurred; existing measurement blocked before request serialization | Full-loading harness exists | 10/25/50/100 ×5 attempted; 0 valid at each | NOT_IMPLEMENTED (lazy); full schema token overhead NOT_MEASURED | Production lazy feature absent; existing Java path permission error | REMOVE lazy/85%; ordinary integration may be described without optimization claim |
| Permission System | Path checks, immutable dangerous-command blacklist, local/project/user rules, mode fallback, interactive once/always/deny | PermissionSystemTest, ValueMatcherTest | No measured coding-session safety/approval benchmark | Not yet | 0 sessions | PARTIALLY_IMPLEMENTED against original five-layer/OS-isolation claim | No explicit allow-session choice; no OS sandbox; bypass/dontAsk and rule precedence require adversarial tests | FUNCTION_ONLY for actual controls; remove 30→5 and kernel-isolation claims |
| Long-Horizon Context | JSONL session writer/loader, resume, memory, instructions, auto compact, recovery and persisted offload decisions | SessionPersistenceTest, MemoryManagerTest, InstructionLoaderTest, context suites | Individual paths tested; no repeated-compaction workload | Single-compaction fixture only | 0 long-horizon runs | IMPLEMENTED_NEEDS_MORE_TESTING for foundations | Repeated compaction, resume, latest state, stale memory and real tool results unmeasured | FUNCTION_ONLY for persistence/compaction; remove 8 hours |
| Multi-Agent | Main/sub-agent, background tasks, worktrees, team tasks/mailbox/backend mechanisms exist | Subagent/task/team/worktree suites present | Prior gate never started Main Agent because of AccessDeniedException | Small independent-repo gate exists | 0 completed E2E; 0 speed comparisons | PARTIALLY_IMPLEMENTED against isolated parallel E2E claim | Isolated SubAgentTool waits on future; non-readonly Agent calls serialized by AgentLoop; no proven parent integration/conflict handling | FUNCTION_ONLY for delegation/worktrees; remove 60% |

Test-file presence is not a claim that the full suite passes today. Feature labels refer to the stated scope; component existence does not establish end-to-end correctness.

## Code-path findings

### Context and long-session

`context.ContextManager.offloadAndSnip` persists large tool outputs and replacement decisions. `shouldAutoCompact` uses the production threshold; `compact` assembles validated summary, recovery and recent messages. `ChatApplication` calls automatic compaction and `SessionLoader` on resume. This supports describing two mechanisms, not an eight-hour guarantee. Memory and instruction loading exist, but the fixed 50-fact fixture deliberately isolated memory and did not exercise successive compressions.

The supplemental punctuation-corrected evaluator-v2 gives OLD/NEW forensic effective evidence-screen means 93.1%/89.6%. These are **not independent semantic-retention estimates**: they include forensic contexts for unusable compact output, are automatic scores and remain subject to blind review. Frozen-v1 exact scores are invalid after a demonstrated punctuation defect. Keep both versions and all raw data. Selected model cohort excludes transport-only attempts; all-started operational results are OLD20/29 and NEW19/29. Do not relabel network failures as algorithm failures.

### MCP

`McpConfigLoader` loads server configuration. `SdkMcpSession.connect` initializes transport, paginates tools/list, captures tool names/descriptions/input schema. `McpManager.register` creates `mcp__server__tool` adapters in `ToolRegistry`. `ToolRegistry.definitions` returns complete schemas; `AgentLoop.definitionsFor` and the run path pass a fixed definitions list to `OpenAiResponsesClient`/`AnthropicClient`. No production schema-search or activation mechanism was found. `definitions(allowed)` is a reusable filter, not lazy loading. Existing full benchmark summary reports BLOCKED with null bytes/tokens, so no numeric overhead can honestly be supplied yet.

Planned Phase 2 changes: `mcp` (catalog/discovery policy), `tool.ToolRegistry` (session-scoped exposed definitions), `agent.AgentLoop` (refresh activated definitions between calls), application/config wiring and tests. Prefer searchable short metadata and per-session schema activation; preserve full mode, permissions, allowed-tool filters and concurrency boundaries. MCP wire discovery may still fetch schemas eagerly while model-context exposure is lazy; distinguish these costs explicitly.

### Permissions

`PermissionManager.authorize`: blacklist → path boundary → local/project/user rules → mode → dontAsk → approval. `ApprovalChoice` contains ALLOW_ONCE/ALLOW_ALWAYS/DENY, no session-specific choice. Persistent always-rules are not session approval caching. `DangerousCommandPolicy` is pattern-based. `BashTool` launches powershell.exe directly with workspace cwd, with no OS sandbox wrapper. A cwd is not shell confinement. `team.filelock.FileLock` locks task-store persistence; it does not prove per-source-file edit isolation.

Phase 4 first measures current production policy using injected approvers and isolated configs in benchmarks/test sources. Any discovered safety defect must be reported and fixed separately, not hidden to reduce prompts. No decision to build artificial five layers or an OS sandbox has been made.

### Multi-Agent

`SubAgentTool` is not readonly. Its isolated path creates a worktree and blocks on `running.future().get()`. `AgentLoop.executeOrdered` serializes non-readonly calls. Background shared-workspace execution exists, but is not proof of isolated parallel execution. `TeamManager`/backends provide additional paths; verify platform availability. Returned text/worktree references are not an automatic merge. Main Agent might integrate through existing tools, but no passing run currently proves it.

Phase 3 first inspects and runs the gate, then determines whether `SubAgentTool`, `SubAgentTaskManager`, `ChatApplication`, `TeamManager`/backend and worktree integration need changes. Do not have the harness decompose or merge. Only after three passing real E2E tasks run matched single/multi performance tests; otherwise record BLOCKED and stop speedup experiments.

### SWE-bench-Live

No dataset loader, SWE-bench-Live runner, checkout/patch/test/resolved pipeline was found in production or benchmark source searches. NOT_IMPLEMENTED. Custom context evaluation is real but is not SWE-bench evaluation. Phase 6 must first verify authoritative dataset/harness requirements and local feasibility before selecting 5–10 actual cases.

## Implementation order and gates

1. Context: execute existing 160 stateless independent model reviews without reading key; seal all labels; only then unblind/analyze strict and weighted agreement, categories, OLD/NEW and uncertainty. Write `results/context-final-validation.md` (READY / NEEDS_MORE_TESTING / REGRESSION_FOUND). Preserve blind CSV and empty human labels. No production change unless quality regression confirmed.
2. MCP: obtain valid full baseline; implement real lazy schema exposure; full/lazy four scales ×5 plus at least 10 real selection tasks, include extra calls/latency/total schema costs. Never preselect 85%.
3. Multi-Agent: three E2E gates before ≥8 tasks ×2 modes ×3 repeats. Failure of integration stops speedup testing.
4. Permissions: ≥10 fixed workflows with a reasonable secure baseline and high-risk checks; report unsafe auto approvals, not only prompt count.
5. Long horizon: ~100K/~200K/~300K cumulative-token workloads, actual repeated compaction/resume/tool results/tasks/instructions/stale-memory tests, preserving production thresholds.
6. SWE-bench-Live: genuine cases and complete patch/test pipeline if feasible; do not label a skeleton as evaluation.

Each completed step: save raw and regenerated report, run full Gradle tests without skipping existing suites, commit reviewed non-sensitive source/artifacts, record exact commits and resume status, then advance. Keep API keys/config/memory/temp/independent checkouts excluded. Raw data remains locally reproducible and hash-linked; no indiscriminate `git add .`.

Context and long-horizon currently need validation first. Permission needs a benchmark plus honest narrowing of the original claim. MCP lazy is absent and requires production work. Multi-Agent E2E may require orchestration changes, not just timing. SWE-bench-Live is absent.

Final deliverables will add BENCHMARK_MANIFEST.md, STAR_CODE_FINAL_VALIDATION.md and evidence-qualified resume bullets. No final readiness score or completed stage is claimed by this inventory.

## Phase 1 progress after inventory

- Full Gradle test rerun: PASS, 52 suites / 190 tests / zero failures, errors or skips. Logs and aggregate are in `results/validation-full-tests-step1.*`.
- Existing four-file context reliability fix committed on main as `63cade05f8dec1e5b33a948dfcd05eb69f291aa3`. Initial baseline/tag and independent A/B snapshots remain unchanged. No production behavior was altered during this new inventory/review work.
- Original blind CSV and rubric hashes verified unchanged. A pre-run Windows newline hash defect in the exported JSON was corrected with archived evidence; no sample content change.
- External destination verified as HTTPS api.openai.com. All 160 fact/source pairs equal the frozen synthetic fixture; current configured API key is absent from the payload. Automatic approval review first refused the batch, then approved after these additional provenance checks. See `llm-review-v1/provenance-check.json`.
- Independent LLM review started. The first 13 labels were saved before R0014 encountered a no-output TPM rate-limit error. Error preserved; conservative scheduling added only to the harness, then recovery resumed. No result labels or unblinding key have been read by the orchestrator before sealing.
- `BENCHMARK_MANIFEST.md` now tracks implemented commits, raw paths, pending stages and wording limits. Stage1 final analysis and benchmark-artifact commit remain pending until all 160 reviews finish.

## Phase 1 completed analysis

160/160 independent model reviews finished, sealed and then unblinded. OLD and NEW each77/80 PASS; summary OLD38/40, NEW37/40; effective OLD39/40, NEW40/40. No PARTIAL/UNCERTAIN. These are sampled fact/view judgments, not population retention or independent run successes. Two apparently erroneous reviewer FAIL explanations are preserved and documented without relabeling.

Final Context decision: **NEEDS_MORE_TESTING**; feature **IMPLEMENTED_NEEDS_MORE_TESTING**; no confirmed systematic quality regression and no additional compression tuning. See `results/context-final-validation.md`. Corrected-v2 nominal agreement82.5%, strict/weighted85%, strict kappa0.2013. Human annotation was not performed. The model-review stage is completed; stable resume retention percentages remain unverified.

161 review attempts include160 valid outputs and one preserved no-output rate-limit failure. Known provider token usage3,093,360; one failed usage unknown. The prior Codex interruption preserved146 labels; only14 were resumed. Indexed local evidence:2073 files,381359088 bytes at index generation, with SHA256 in `results/context-validation-artifact-index.json`.

Next ordered step: MCP full-loading baseline followed by production lazy schema exposure and matching benchmark. Other subsystems remain unchanged.

Context benchmark evidence committed as `ae2e8c8a403dbf41cc3e680c35d8d2f286920ce5`.

Phase2 start: current Full Loading entry point and local run script prepared, but two clean-build attempts stopped on Java ZIP filesystem/toRealPath AccessDenied for the dependency JAR, despite explicit permissions. No new valid MCP measurements and no lazy implementation yet. Current environment disables command sandbox escalation. See `results/mcp-phase2-start-status.md`; the ordered baseline gate has not been bypassed.

## Phase 2 completed (supersedes the earlier MCP blocker)

Production lazy loading and matching harness committed as `64e4c92f5b623a166879ee5aa86f23fd09d50867`. Escalated compilation resolved the Windows Java access failure; a valid pre-change FULL baseline was captured before production changes. Original baseline tag remains unchanged.

MCP FULL/LAZY schema comparison: 40/40 serialization runs, four sizes with five repeats per mode. At 100 synthetic tools, initial MCP schema/index estimate is 7377 FULL versus 2420 LAZY: 67.20% reduction, estimated with tiktoken o200k_base, not official provider attribution. Ten actual model selection tasks per mode all passed. LAZY required one extra model call per task; paired median latency difference +0.023 seconds. Cumulative schema estimate reduction has a paired median of 56.97%. No 85% claim or general latency improvement is established.

Full Gradle tests: 195 tests / 53 suites, zero failures/errors/skips. Report: `results/mcp-lazy-loading-final.md`; per-run CSV and machine-readable summary accompany captured raw requests/responses. Raw artifact hashes: `results/mcp-validation-artifact-index.json`.

Next: real Team Multi-Agent integration feasibility. Correction to the initial inventory: ordinary isolated SubAgent calls wait synchronously, but ChatApplication Team spawning launches background tasks with independent Worktrees. Thus isolated parallel capability exists in code; E2E completion and speed remain unverified.

## Phase 3 current outcome

Team result retrieval bug fixed in production commit53ec9ba;199 full tests pass. Pre-fix run had UNKNOWN_TEAM_TASK due to execution/shared-task namespace confusion. Post-fix both worker results were collected and Main's unified21-check verifier passed. However parent still terminated with iteration_limit at10 rounds. Legacy component gate PASS is superseded by audited complete-run BLOCKED. Two attempts, one distinct contract; no speed experiment. See results/multi-agent-postfix-validation.md and preserved raw/current summaries. Next lower-priority phase: permission policy and session approval; multi-agent completion budget remains an open product limitation.
