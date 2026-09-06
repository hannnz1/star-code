# Benchmark claim ledger

Updated 2026-09-06. This ledger distinguishes implemented mechanisms, measured data, and untested resume hypotheses. Unfinished stages have no invented result. See STAR_CODE_VALIDATION_STATUS.md for the initial inventory and current stage notes.

| Claim | Implementation commit | Benchmark commit | Dataset / sample size | Model / config | Metric and current interpretation | Raw result / report | Known limitations | Resume-safe wording |
|---|---|---|---|---|---|---|---|---|
| Context reliability and retention evaluation | Main `63cade05f8dec1e5b33a948dfcd05eb69f291aa3`; A/B NEW independent snapshot `4f26fa7552e72a54d85a262255a2aff243042181`; OLD `014808a0b0942f25bc4f1c3f415fa63262f98176` | Pending benchmark artifact commit; frozen source/class manifests in quality-v1 | Fixed 50 facts, 240 messages, ~109749 production-estimated tokens; OLD20 + NEW20 HTTP200 trials; 58 all-started; independent model review160 records pending | gpt-5.4-mini/openai-responses; production temperature/maxoutput unset; seed20260905 fixture/pairing only; reviewer temp0/max2048 | Internal compact OLD20/20, NEW19/20; all-started OLD20/29, NEW19/29; semantic/exact final interpretation pending review | results/raw/context-quality-ab/2026-09-05T07-51-54Z; quality-v1/freeze.json, build.json; selected batch recovery-selection.json; results/context-quality-final-report.md; results/raw/llm-blind-review-v1 | Transport-only supplemental runs; missing OLD usage; evaluator-v1 punctuation defect; v2 supplemental; correlated synthetic facts; no human annotation | Implemented validated context compaction with bounded retries and reproducible context-evaluation fixtures. No retention-improvement percentage yet. |
| MCP lazy initial schema overhead reduction | 64e4c92 | b80f9be evidence | 4 sizes ×2 modes ×5;10 real selection tasks/mode | gpt-5.4-mini Responses; tokenizer estimates | 100 tools7377→2420 estimated67.20%; both selection10/10; extra1 call/task | results/mcp-lazy-loading-final.md; mcp-validation-artifact-index.json | Synthetic fixtures; not overall task tokens or85%; initial network discovery remains eager | Implemented MCP schema discovery/activation; qualify measured initial overhead by fixture. |
| Isolated Multi-Agent correctness and speed | Team result fix53ec9ba | Failed gate14c2d27; post-fix7afb97e | One distinct contract; pre-fix and post-fix attempts | gpt-5.4-mini Responses, original10 rounds | BLOCKED complete run; post-fix collection and Main21-check verifier pass, then iteration_limit | results/multi-agent-postfix-validation.md | Three E2E tasks and speed comparison unfinished; no conflict proof | Delegation, isolated Team worktrees and bounded result retrieval; no speed claim. |
| Permission prompt reduction with safety | Session grantba607a3 | permission-v1 frozen fixture/harness | 10 traces ×2 policies;180 actions/policy | No model; injected ALLOW_ONCE vs ALLOW_SESSION choices | Median12→8 confirmations;50 risky probes denied per policy, zero unsafe automatic allows in corpus | results/permission-v1-final.md and raw/index/CSV | Synthetic decision replay, no commands or real sessions executed; no OS sandbox | Implemented scoped session approvals and reproducible policy replay; do not generalize30→5. |
| Repeated compaction and cross-session long context | Baseline foundations plus context fix above | NOT_RUN | 0 repeated-compaction workloads | ~100K/200K/300K cumulative-token levels planned with original thresholds | NOT_MEASURED; no eight-hour endurance | Phase5 pending | Single-compaction fixture is not a long-horizon evaluation | Session persistence and auto-compaction mechanisms only; no duration/retention guarantee. |
| SWE-bench-Live evaluation pipeline | NOT_IMPLEMENTED | NOT_RUN | 0 real cases | Unselected until dataset/harness feasibility verified | No checkout/patch/test/resolved pipeline evidence | Phase6 pending | Custom context fixture does not establish SWE-bench integration | Remove SWE-bench-Live claim until real E2E cases run. |

## Test gate and provenance

The full Gradle test command `gradlew.bat test --rerun-tasks --console=plain` passed on 2026-09-06: 52 suites, 190 tests, zero failures/errors/skips. Log: results/validation-full-tests-step1.txt; aggregate: results/validation-full-tests-step1.json. This validates existing tests, not the pending feature benchmarks.

The context fix implementation commit uses the existing baseline identity `Star Code Benchmark <benchmark@localhost>` as a per-command override because this environment lacks configured Git identity. The baseline tag is unchanged. No global Git settings were modified.

Raw files are locally preserved under ignored results/raw directories; reports must link their paths and hashes. A Git commit alone is insufficient when raw is excluded: retain the raw artifact index and files together for reproduction. Missing provider usage remains unknown, never zero-filled. Costs require the actual account billing/rates; do not infer monetary savings from incomplete usage.

To resolve the artifact commit after publication, use `git log -1 --format=%H -- benchmarks/BENCHMARK_MANIFEST.md`; avoid a self-referential commit hash inside its own committed file.

## Context final addendum (supersedes pending-review entries above)

Independent model blind review160/160 completed and sealed before unblinding. Both arms77/80 PASS (96.25% sampled-record rate); corrected-v2 nominal agreement82.5%, strict/weighted agreement85%. **NEEDS_MORE_TESTING**, not confirmed improvement/equivalence or regression. No retention-improvement number is resume-ready. See `results/context-final-validation.md`, `llm-blind-review-report.md` and machine-readable analysis/unblinded CSV. No human annotation occurred. Known review usage3,093,360 tokens;161 attempts including one preserved rate-limit failure with unknown usage.

`results/context-validation-artifact-index.json` indexes2073 local evidence files (381359088 bytes). Retain ignored raw files with the index for full reproducibility. `git log -1 --format=%H -- benchmarks/llm-review-v1/finalize.py` identifies the first committed final-report generator independently of future ledger updates.

## Phase 2 completed (supersedes the earlier MCP blocker)

Production lazy loading and matching harness committed as `64e4c92f5b623a166879ee5aa86f23fd09d50867`. Escalated compilation resolved the Windows Java access failure; a valid pre-change FULL baseline was captured before production changes. Original baseline tag remains unchanged.

MCP FULL/LAZY schema comparison: 40/40 serialization runs, four sizes with five repeats per mode. At 100 synthetic tools, initial MCP schema/index estimate is 7377 FULL versus 2420 LAZY: 67.20% reduction, estimated with tiktoken o200k_base, not official provider attribution. Ten actual model selection tasks per mode all passed. LAZY required one extra model call per task; paired median latency difference +0.023 seconds. Cumulative schema estimate reduction has a paired median of 56.97%. No 85% claim or general latency improvement is established.

Full Gradle tests: 195 tests / 53 suites, zero failures/errors/skips. Report: `results/mcp-lazy-loading-final.md`; per-run CSV and machine-readable summary accompany captured raw requests/responses. Raw artifact hashes: `results/mcp-validation-artifact-index.json`.

Next: real Team Multi-Agent integration feasibility. Correction to the initial inventory: ordinary isolated SubAgent calls wait synchronously, but ChatApplication Team spawning launches background tasks with independent Worktrees. Thus isolated parallel capability exists in code; E2E completion and speed remain unverified.

## Phase 3 current outcome

Team result retrieval bug fixed in production commit53ec9ba;199 full tests pass. Pre-fix run had UNKNOWN_TEAM_TASK due to execution/shared-task namespace confusion. Post-fix both worker results were collected and Main's unified21-check verifier passed. However parent still terminated with iteration_limit at10 rounds. Legacy component gate PASS is superseded by audited complete-run BLOCKED. Two attempts, one distinct contract; no speed experiment. See results/multi-agent-postfix-validation.md and preserved raw/current summaries. Next lower-priority phase: permission policy and session approval; multi-agent completion budget remains an open product limitation.

## Phase 4 policy replay completed

Production session grants implemented at ba607a3b3dc489228526556127314cab8d7827ce. Explicit ALLOW_SESSION is isolated by tool/path or exact command/arguments, actor, execution directory and mode; cleared on new/resumed sessions and never persisted. Existing rule/path/blacklist checks precede reuse. Full Gradle204 tests /55 suites pass.

Ten frozen synthetic action traces,180 actions per policy: baseline ALLOW_ONCE median12 prompts versus CURRENT_SESSION median8; total130 versus80;50 session-grant reuses. Each policy denied all50 labeled risky probes, with zero unsafe auto-approvals in this finite corpus. The user choices are injected; no shell commands or models run. This is POLICY_REPLAY_COMPLETE, not real coding-session performance. Do not claim30-to-5 or general OS isolation. See results/permission-v1-final.md, CSV, per-action raw and SHA256 index.

Open stages: normal Multi-Agent completion still limited by10 turns; three distinct E2E tasks/speedup unfinished. Long-horizon repeated compaction and real SWE-bench-Live cases remain NOT_RUN. Context decision remains NEEDS_MORE_TESTING. This ledger is interim, not overall validation completion.
