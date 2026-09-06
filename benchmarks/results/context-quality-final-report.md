# Context Compression Reliability & Quality Study

## 1. Original Problem

Original five attempts: 2/5 compact success (40%). Three long outputs lacked a closing summary marker. Current study status: 40/40 attempts recorded. Study id: 2026-09-05T07-51-54Z.

## 2. Reliability Fix

The previous revision added structure validation, at most one retry and failure preserving the original context. It also changed summaryPrompt to a concise/deduplicated nine-section summary, with a 12000-character target and 28000-character acceptance bound. It was **not merely a parser change**. This study makes no further production changes.

OLD commit 014808a0b0942f25bc4f1c3f415fa63262f98176; NEW snapshot commit 4f26fa7552e72a54d85a262255a2aff243042181. Independent clean checkouts and separately compiled full production sources; same dependency jar. Main repository HEAD/tag unchanged. Manifests and real prompt sources are frozen under quality-v1; the snapshot commit exists in the independent NEW repository, not the main repository.

## 3. Why 81% vs 70.8% Could Not Be Compared Directly

81% came from two selected successful OLD outputs, 70.8% from ten successful NEW outputs. Parseability and quality may be associated, but the direction is not known from five attempts. This is selection/survivorship-bias risk, not proof that the old figure was inflated. Conditioning on successful output is a different estimand from all-attempt latent quality. The two historical groups also were not randomized contemporaneously.

New OLD success/failure forensic distributions test association within this study, not historical causal attribution. Long failed raw outputs can contain many facts even though production could not use them. Conversely a hypothetical forensic effective context must never be counted as operational success.

In the completed HTTP200 cohort OLD had no parsing failures, so its failed-output quality distribution is unavailable (n=0). This study cannot establish the proposed association between OLD parsing failure and lower quality, nor prove that historical81% was inflated.

| Arm | Group | Forensic effective evidence-screen distribution |
|---|---|---|
| old | successful | 88.30 / 89.00 / 77.80 / 83.50 / 94.00 / 94.00 / 76.00 / 100.00 / 6.88 (n=20) |
| old | failed | N/A (n=0) |
| old | retry | N/A (n=0) |
| old | no_retry | 88.30 / 89.00 / 77.80 / 83.50 / 94.00 / 94.00 / 76.00 / 100.00 / 6.88 (n=20) |
| new | successful | 86.63 / 90.00 / 71.60 / 85.00 / 94.00 / 94.80 / 52.00 / 100.00 / 11.57 (n=19) |
| new | failed | 84.00 / 84.00 / 84.00 / 84.00 / 84.00 / 84.00 / 84.00 / 84.00 / N/A (n=1) |
| new | retry | 84.00 / 84.00 / 84.00 / 84.00 / 84.00 / 84.00 / 84.00 / 84.00 / N/A (n=1) |
| new | no_retry | 86.63 / 90.00 / 71.60 / 85.00 / 94.00 / 94.80 / 52.00 / 100.00 / 11.57 (n=19) |

## 4. Evaluator Audit

See evaluator-audit.md. Exact literal retention and semantic evidence screening are distinct. Original scorer has demonstrated unit/action false positives and verbatim evidence false negatives. The predeclared screen passed12 authored controls, but a broader post-freeze audit found a punctuation-boundary defect:47/50 original semantic controls and10/30 exact controls. Frozen-v1 exact percentages below are retained only as diagnostic provenance, **not valid exact-retention estimates**. A separate punctuation-corrected v2 passes50/50 semantic and30/30 exact original controls; no production or model output changed. Both evaluator versions are kept separately. User-revised160-of-800 true human audit is pending; no human disagreement number is fabricated. **Actual semantic retention and quality noninferiority remain unestablished.**

Supplemental v2 means (not human-validated): {"old": {"summary_semantic_screen_percent": 92.5, "effective_semantic_screen_percent": 93.1, "summary_exact_percent": 94.33333333333333, "effective_exact_percent": 94.33333333333333}, "new": {"summary_semantic_screen_percent": 89.6, "effective_semantic_screen_percent": 89.6, "summary_exact_percent": 90.83333333333333, "effective_exact_percent": 90.83333333333333}}

## 5. Controlled A/B Results

The same 20 OLD model-response attempts are used for both forensics and A/B. Same 50 facts / 240 messages, production estimate 109749 (character-based, not billed tokens), threshold 95000, gpt-5.4-mini/openai-responses, same host, same source fixture, memory isolation. Sequential random order within 20 pairs. No optional extension to 30. Prompt is the intentional OLD/NEW treatment difference.

### Transport interruption and declared supplemental attempts

After the first seven pairs, both arms encountered repeated SSLHandshakeException before any upstream HTTP response. The harness emitted local502 forwarding errors, which are not upstream model502 responses or parser failures. The original batch was stopped after detection; one raw run remains RUNNING because of operator interruption, separately classified OPERATOR_INTERRUPTED in analysis without rewriting raw. The initial runner's stop condition failed to recognize these wrapped transport exceptions; this instrumentation weakness caused multiple unnecessary connection attempts and is disclosed.

A read-only HEAD probe later received HTTP404, confirming restored TLS/HTTP reachability; the precise cause/recovery of the network failure is unknown. Recovery plan was recorded before supplemental calls in quality-v1/recovery-plan.json. It preserves all earlier attempts, retains the fourteen completed model experiments, and fills logical slots without upstream HTTP200 in the original randomized order. Any HTTP200 production parsing failure is retained and never replaced. Supplemental runner stops immediately on a new transport failure. This is a transparent mid-study infrastructure amendment, not an untouched preregistration or outcome-selected removal of parsing failures.

**All-started end-to-end denominator**, including TLS failures/operator interruption, is preserved in context-ab-all-started.csv:

| Arm | Started | Compact success | Other outcomes | End-to-end success |
|---|---:|---:|---:|---:|
| OLD | 29 | 20 | 9 | 68.97% |
| NEW | 29 | 19 | 10 | 65.52% |

The following primary model-cohort table is **conditional on upstream HTTP200**, targeting20 per arm. It does not represent end-to-end availability; do not hide the all-started table when citing it. Both original and supplemental raw paths and selection manifest are retained. This network incident/time separation further limits causal interpretation.

Observed first-request common configuration identical: True; first-request history identical: True. Temperature and max_output_tokens remain UNSET in both actual production requests. Identical unset fields do not prove provider defaults/backend snapshots stay fixed. Raw responses preserve any returned model identifiers. Fixture, class and evaluator hashes checked before execution. Harness bounds: 900 seconds per request; 1860 per run. Identical throttled wire recorder avoids per-chunk cumulative disk rewriting, so historical latency is not pooled with this study.

| Arm | Attempts | Success | Failure | Success rate | Retry rate |
|---|---:|---:|---:|---:|---:|
| OLD | 20 | 20 | 0 | 100.00% | 0.00% |
| NEW | 20 | 19 | 1 | 95.00% | 5.00% |

Distribution cells: mean / median / p10 / p25 / p75 / p90 / min / max / sample SD (n). Linear-interpolated percentiles. Failed outputs enter forensic quality when text exists; they never acquire an operational effective context. Usage-missing responses are not zero-filled.

| Metric | OLD | NEW |
|---|---|---|
| summary exact % | 57.50 / 53.33 / 46.00 / 46.67 / 63.33 / 83.67 / 30.00 / 93.33 / 16.36 (n=20) | 64.67 / 58.33 / 43.00 / 46.67 / 87.50 / 93.67 / 36.67 / 96.67 / 20.84 (n=20) |
| effective exact % | 57.50 / 53.33 / 46.00 / 46.67 / 63.33 / 83.67 / 30.00 / 93.33 / 16.36 (n=20) | 64.67 / 58.33 / 43.00 / 46.67 / 87.50 / 93.67 / 36.67 / 96.67 / 20.84 (n=20) |
| forensic summary evidence-screen % | 87.70 / 88.00 / 75.80 / 83.50 / 94.00 / 94.00 / 74.00 / 100.00 / 7.43 (n=20) | 86.50 / 90.00 / 71.80 / 84.00 / 94.00 / 94.40 / 52.00 / 100.00 / 11.27 (n=20) |
| forensic effective evidence-screen % | 88.30 / 89.00 / 77.80 / 83.50 / 94.00 / 94.00 / 76.00 / 100.00 / 6.88 (n=20) | 86.50 / 90.00 / 71.80 / 84.00 / 94.00 / 94.40 / 52.00 / 100.00 / 11.27 (n=20) |
| successful-only effective evidence-screen % | 88.30 / 89.00 / 77.80 / 83.50 / 94.00 / 94.00 / 76.00 / 100.00 / 6.88 (n=20) | 86.63 / 90.00 / 71.60 / 85.00 / 94.00 / 94.80 / 52.00 / 100.00 / 11.57 (n=19) |
| latency s | 197.42 / 207.79 / 29.23 / 31.26 / 368.82 / 414.70 / 25.70 / 437.02 / 166.31 (n=20) | 26.21 / 24.82 / 22.14 / 23.10 / 26.94 / 31.85 / 19.69 / 43.07 / 5.27 (n=20) |
| calls per attempt | 1 / 1.00 / 1.00 / 1.00 / 1.00 / 1.00 / 1 / 1 / 0.00 (n=20) | 1.05 / 1.00 / 1.00 / 1.00 / 1.00 / 1.00 / 1 / 2 / 0.22 (n=20) |
| input tokens, complete usage only | 66923 / 66923.00 / 66923.00 / 66923.00 / 66923.00 / 66923.00 / 66923 / 66923 / 0.00 (n=10) | 70413.30 / 67058.00 / 67058.00 / 67058.00 / 67058.00 / 67058.00 / 67058 / 134164 / 15005.36 (n=20) |
| output tokens, complete usage only | 7170.10 / 2823.50 / 2427.70 / 2475.25 / 3291.00 / 9066.40 / 2344 / 44692 / 13208.68 (n=10) | 2276.30 / 2150.50 / 1857.60 / 2084.50 / 2307.50 / 2559.90 / 1760 / 3906 / 490.38 (n=20) |
| total tokens, complete usage only | 74093.10 / 69746.50 / 69350.70 / 69398.25 / 70214.00 / 75989.40 / 69267 / 111615 / 13208.68 (n=10) | 72689.60 / 69208.50 / 68915.60 / 69142.50 / 69365.50 / 69617.90 / 68818 / 138070 / 15391.98 (n=20) |
| retry total tokens | 0 / 0.00 / 0.00 / 0.00 / 0.00 / 0.00 / 0 / 0 / 0.00 (n=20) | 3441.55 / 0.00 / 0.00 / 0.00 / 0.00 / 0.00 / 0 / 68831 / 15391.08 (n=20) |
| final summary estimated tokens | 46191.65 / 52951.50 / 3287.30 / 3919.25 / 94173.75 / 94769.70 / 3152 / 95056 / 41172.77 (n=20) | 2845.65 / 2797.00 / 2501.90 / 2638.25 / 3025.75 / 3073.50 / 2349 / 3971 / 354.89 (n=20) |
| first raw response estimated tokens | 43389.70 / 28873.00 / 3292.10 / 3719.00 / 93446.00 / 94648.00 / 0 / 95066 / 42271.31 (n=20) | 2877.65 / 2823.50 / 2531.00 / 2722.00 / 3031.75 / 3079.50 / 2355 / 3977 / 337.21 (n=20) |
| retry raw response estimated tokens | N/A (n=0) | 2381 / 2381 / 2381.00 / 2381.00 / 2381.00 / 2381.00 / 2381 / 2381 / N/A (n=1) |


## 6. Fact-Level Failure Analysis

See fact-category-analysis.csv/.md, all per-run forensics/fact-judgments.json and the human review packet. Categories include paths, identifiers, API contracts, numeric parameters, constraints, causes, failed attempts, negative constraints, pending tasks and next steps. SUPPORTED and explicit contradictions are counted; UNVERIFIED is separated. No category's unmatched paraphrases are called proven lost. Original user text that survives in recent messages is a separate source from summary and recovery. Failure effective-context scores are hypothetical forensic unions only.

## 7. Root Cause / Change Mechanism

Quality regression conclusion: **INCONCLUSIVE**. The prompt change and regeneration retry plausibly alter information, but hypotheses are not confirmed causes.

1. Validation is accompanied by a changed compression prompt; it is not a format-only intervention.
2. Retry explicitly asks for a concise, complete regeneration from history. It is content regeneration, not deterministic format repair.
3. First/retry raw-output token estimates and subgroup retention are shown above. Small retry subgroups cannot establish causality.
   NEW's single failed model-cohort run is new-16-recovery-01: first output lacked a closing marker (10152 characters), retry contained multiple summary blocks (8333 characters). Both had response.completed signals; these validation reasons do not prove transport truncation. It remains a failed operational attempt and is never replaced by a passing sample.
4. Parser extracts the selected closed block, removes optional internal fence wrapping and trims whitespace. It does not intentionally cut validated section bodies to the 28k bound: oversized output is rejected.
5. No repair logic deletes sections; all nine ordered nonempty sections are required by NEW.
6. max_output_tokens is unchanged/unset. The prompt character target and validator bound changed, which is a different kind of output restriction.
7. Prompt changed from full user-message wording preservation to deduplication/conciseness.
8. The recent-message budget is unchanged (production recent selection, >=10000 estimated tokens and >=5 messages).
9. Summary + recovery + recent assembly is unchanged in selection/layout; NEW postpones usage reset until successful assembly. Both are recorded separately.
10. Closing tags do not stop the network generation. NEW rejects multiple blocks rather than accepting an early partial one; no automatic closing marker is appended. Structural completeness does not establish content completeness.

## 8. Final Fix

No second production fix. No MCP or Multi-Agent changes. No E1/E2/E3/E4 optimization runs because CONFIRMED_REGRESSION was not established. Altering the prompt now would contaminate this study and bypass the user's evaluator gate.

## 9. Final Metrics and Limits

Reliability and screen distributions are reported together above. Token totals come from response.completed usage; known totals by arm are OLD 740931, NEW 1453792; complete coverage OLD False, NEW True. Missing usage is not zero. Retry input/output/total tokens are recorded separately. Monetary retry cost is N/A because this configured provider's actual rates/cache billing are unavailable; no OpenAI API price is assumed for another endpoint. No paid judge calls occurred.

The reference engineering gate is >=95% operational success on >=20 real attempts AND no material validated semantic degradation. The 5-percentage-point noninferiority reference is project-defined, not a universal standard. Without validated judgments the quality half cannot pass; no significance/noninferiority claim is made from unvalidated screen numbers. Sampling uncertainty, provider/backend variability, one synthetic fixture, no 8-hour or repeated-compaction session, isolated memory and no real file recovery limit generalization.

`model_calls` in raw analysis counts recorded request attempts; a local forwarding failure is not proof of provider model execution or billing. In the selected cohort there are41 request attempts (20 OLD,21 NEW including its retry); network/operator attempts remain separately visible. OLD has only10/20 selected runs with complete reported usage, versus20/20 NEW, so neither a total-cost saving nor equal stream completeness can be assumed from OLD's20/20 parser-success count.

## 10. Resume-safe Claim

**NEEDS_MORE_TESTING**. The previous fixed experiment supports the scoped historical observation: “在固定 50-fact、约 110K 生产估算 token 的长上下文实验中，通过输出校验、有限重试和失败保留原上下文，将压缩完成次数从 2/5 提升至 10/10。” This must remain explicitly tied to that small historical batch; it is not a controlled causal effect or a general 100% guarantee. The new paired results above must also be disclosed if quoting the improvement. Do not use historical 40% and whichever later success rate looks best as a new strict A/B result.

No validated information-retention claim yet. In particular, do not claim 100% information retention, 17% to 100%, 8 hours without context loss, or unrelated MCP/security/multi-agent improvements.

## Reproduction and next required input

Run quality-v1/analyze.py then quality-v1/reports.py to regenerate CSV/JSON/reports offline. Do not rerun prepare.py or freeze_protocol.py over a frozen study. run.py resumes only untouched scheduled attempts and refuses to overwrite raw. build.py/prepare.py are setup scripts, not needed for report regeneration.

Human review is the remaining quality gate: complete manual-review-blind.csv following manual-review-instructions.md, then run compare_manual.py. This report does not pretend that step is complete. See quality-v1 code and results/context-quality-study.json for machine-readable provenance. Raw data and cloned checkouts remain in ignored benchmark directories. No main-repository commit was made.
