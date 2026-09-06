"""Regenerate study reports from machine data; missing evidence stays missing."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def save(name,text):(ROOT/'results'/name).write_text(text,encoding='utf-8')
def fmt(v):return 'N/A' if v is None else f'{v:.2f}' if isinstance(v,float) else str(v)
def dist(d):
 if not d.get('n'):return 'N/A (n=0)'
 return ' / '.join(fmt(d.get(k)) for k in ['mean','median','p10','p25','p75','p90','min','max','sample_sd'])+f" (n={d['n']})"
def main():
 d=read(ROOT/'results/context-quality-study.json');freeze=read(ROOT/'quality-v1/freeze.json');controls=d['request_controls'];audit=read(ROOT/'quality-v1/audit-challenges.json');old=d['arms']['old'];new=d['arms']['new'];n=len(d['runs'])
 all_started=d.get('all_started_arms',d['arms'])
 v2=read(ROOT/'results/context-quality-supplemental-v2.json') if (ROOT/'results/context-quality-supplemental-v2.json').exists() else None
 v2_note=('Supplemental v2 means (not human-validated): '+json.dumps(v2['means'],ensure_ascii=False)) if v2 else 'Supplemental v2 pending.'
 all_table='\n'.join(f"| {arm.upper()} | {x['attempts']} | {x['successful_compactions']} | {x['failed_compactions']} | {fmt(x['success_rate'])}% |" for arm,x in all_started.items())
 labels=[('summary exact %','summary_exact_retention'),('effective exact %','effective_exact_retention'),('forensic summary evidence-screen %','summary_semantic_verified_percent'),('forensic effective evidence-screen %','effective_semantic_verified_percent'),('successful-only effective evidence-screen %','operational_effective_semantic_verified_percent'),('latency s','wall_clock_seconds'),('calls per attempt','model_calls'),('input tokens, complete usage only','input_tokens'),('output tokens, complete usage only','output_tokens'),('total tokens, complete usage only','total_tokens'),('retry total tokens','retry_total_tokens'),('final summary estimated tokens','summary_tokens_estimated'),('first raw response estimated tokens','first_response_tokens_estimated'),('retry raw response estimated tokens','retry_response_tokens_estimated')]
 table='\n'.join(f'| {label} | {dist(old[key])} | {dist(new[key])} |' for label,key in labels)
 reliability='\n'.join(f"| {arm.upper()} | {x['attempts']} | {x['successful_compactions']} | {x['failed_compactions']} | {fmt(x['success_rate'])}% | {fmt(x['retry_rate'])}% |" for arm,x in d['arms'].items())
 metrics=f'''| Arm | Attempts | Success | Failure | Success rate | Retry rate |
|---|---:|---:|---:|---:|---:|
{reliability}

Distribution cells: mean / median / p10 / p25 / p75 / p90 / min / max / sample SD (n). Linear-interpolated percentiles. Failed outputs enter forensic quality when text exists; they never acquire an operational effective context. Usage-missing responses are not zero-filled.

| Metric | OLD | NEW |
|---|---|---|
{table}
'''
 bias='\n'.join(f"| {arm} | {group} | {dist(x[group+'_forensic_quality'])} |" for arm,x in d['arms'].items() for group in ['successful','failed','retry','no_retry'])
 audit_text=f'''# Evaluator audit

Status: **PENDING_HUMAN_REVIEW**. No genuine human annotations have been supplied. Human disagreement rate: **N/A**, never zero. No LLM judge was used, so no judge sampling/temperature claim is made.

## Existing evaluators

The legacy scorer checks a typed expected value and a verbatim evidence quote. This couples quality to extraction formatting. It can reject an accurate paraphrase as non-verbatim evidence. It also accepts wrong units (RetryQueue 730 seconds instead of milliseconds) and unrelated negative actions (AccountMigration not deleting rows instead of not renaming customer_ref). Results from that scorer cannot alone establish quality regression. Authored audit challenges: legacy {audit['legacy_correct']}/{audit['challenge_count']}; new screen {audit['screen_correct']}/{audit['challenge_count']}. These are developer-authored examples, not a random validation set or human audit. Full cases: quality-v1/audit-challenges.json.

The previous secondary evaluator required near-complete lexical propositions, so synonymous wording could be rejected; sentence-exact scores measured copying, not semantic preservation. This study keeps those old outputs intact and freezes a separate screen before A/B generation.

### Additional post-freeze positive-control audit and correction

Checking all50 original fact sentences revealed that frozen v1 supported47/50 semantically and only10/30 applicable exact literals. Its literal boundary rejected sentence-final periods as if they extended an identifier/path. This also blocked three complete API-contract controls. The authored12-case suite had missed the defect. Thus frozen-v1 exact percentages must **not** be interpreted as valid literal-retention estimates.

scorer_v2.py corrects this boundary defect in a separate offline evaluator; the original frozen scorer, generated outputs, primary reports/data and sample allocation remain available. It passes50/50 original semantic controls,30/30 original exact controls and four prefix/decimal/extension negative cases. This is a post-generation bug correction, not a preregistered endpoint or proof of general semantic accuracy. Details: context-quality-supplemental-v2.json. The blind CSV is byte-for-byte unchanged; only the separate key adds v2 results alongside frozen-v1 results. compare_manual.py will report both versions after human labels arrive. Human sampling remains based on frozen-v1 strata, so it is not changed to favor the corrected scorer.

## Current screen

Exact covers literals on applicable fact categories, preserving case, numeric values/relations and API verbs/routes; prose causes, failed attempts, negative constraints and TODOs are not assigned whole-sentence exact scores. The exact denominator is recorded through applicable judgments and differs from all-50 semantic screening.

Semantic screening recognizes limited explicit aliases/action/polarity patterns in owner-scoped clauses. Labels are SUPPORTED / DISTORTED / CONFLICT / UNVERIFIED. Unmatched paraphrases become UNVERIFIED, never a proved loss. Even a SUPPORTED label can be wrong outside rule coverage: coreference, tables, multiple roles in a sentence, competing values, implicit causality and later corrections are not fully understood. These are exploratory evidence-screen percentages, **not a validated semantic retention rate or guaranteed mathematical lower bound**.

Exact-vs-semantic disagreement on the same applicable judgments: {fmt(d['exact_semantic_disagreement']['rate'])} as a fraction, n={d['exact_semantic_disagreement']['n']}. They measure different constructs and share code; agreement does not validate them. Human-vs-screen disagreement remains N/A.

## Required human review (latest user sample size)

{json.dumps(d['human_audit'],ensure_ascii=False,indent=2)}

When the batch is complete, manual-review-blind.csv contains 160 cases sampled from an 800-case pool (4000 total fact/view records). This revised sample is 4% of the total, per the latest user instruction. It is balanced across OLD/NEW, view and represented categories, covering available score bands. The blind CSV contains full original source and compressed text, with no version, automated score, reasoning or final run score. The separate mapping is manual-review-key.csv; do not open it before review. Only the user fills PASS/PARTIAL/FAIL/UNCERTAIN and notes. Run compare_manual.py after actual review to calculate agreement, disagreement, confusion matrix and strict binary kappa. PARTIAL also receives 0.5 in a separately named weighted agreement-credit analysis. Source length/content can still reveal style; this is label-blinding, not a claim of perfect blinding.

**Gate:** evaluator validity is not established. Do not change production compression based on these screen averages. Broad semantic scoring and the requested regression/noninferiority inference remain INCONCLUSIVE until review and, if necessary, independently validated evaluator revision.
'''
 save('evaluator-audit.md',audit_text)
 cats='\n'.join(f"| {r['arm']} | {r['category']} | {r['view']} | {r['retained_count']} | {r['distorted_count']} | {r['conflict_count']} | {r['unverified_count']} | {fmt(r['retention_percent'])} |" for r in d['categories'])
 save('fact-category-analysis.md',f'''# Fact category analysis

These are forensic evidence-screen counts across all analyzable outputs, not human-confirmed loss. `lost_count` in CSV is null pending human review. Each fact's precise evidence and origin are saved in its raw run's forensics/fact-judgments.json. Architectural decisions and real tool-result semantics are not represented as independent categories in this 50-fact fixture; no coverage claim is made for them.

| Arm | Category | View | Supported | Distorted | Conflict | Unverified | Supported % |
|---|---|---|---:|---:|---:|---:|---:|
{cats}

Do not rank unverified categories as confirmed regression. Inspect the human sample and compare OLD/NEW on the same meaning after evaluator validation.
''')
 core=f'''# Context Compression Reliability & Quality Study

## 1. Original Problem

Original five attempts: 2/5 compact success (40%). Three long outputs lacked a closing summary marker. Current study status: {n}/40 attempts recorded. Study id: {d['study_id']}.

## 2. Reliability Fix

The previous revision added structure validation, at most one retry and failure preserving the original context. It also changed summaryPrompt to a concise/deduplicated nine-section summary, with a 12000-character target and 28000-character acceptance bound. It was **not merely a parser change**. This study makes no further production changes.

OLD commit {freeze['arms']['old']['commit']}; NEW snapshot commit {freeze['arms']['new']['commit']}. Independent clean checkouts and separately compiled full production sources; same dependency jar. Main repository HEAD/tag unchanged. Manifests and real prompt sources are frozen under quality-v1; the snapshot commit exists in the independent NEW repository, not the main repository.

## 3. Why 81% vs 70.8% Could Not Be Compared Directly

81% came from two selected successful OLD outputs, 70.8% from ten successful NEW outputs. Parseability and quality may be associated, but the direction is not known from five attempts. This is selection/survivorship-bias risk, not proof that the old figure was inflated. Conditioning on successful output is a different estimand from all-attempt latent quality. The two historical groups also were not randomized contemporaneously.

New OLD success/failure forensic distributions test association within this study, not historical causal attribution. Long failed raw outputs can contain many facts even though production could not use them. Conversely a hypothetical forensic effective context must never be counted as operational success.

In the completed HTTP200 cohort OLD had no parsing failures, so its failed-output quality distribution is unavailable (n=0). This study cannot establish the proposed association between OLD parsing failure and lower quality, nor prove that historical81% was inflated.

| Arm | Group | Forensic effective evidence-screen distribution |
|---|---|---|
{bias}

## 4. Evaluator Audit

See evaluator-audit.md. Exact literal retention and semantic evidence screening are distinct. Original scorer has demonstrated unit/action false positives and verbatim evidence false negatives. The predeclared screen passed12 authored controls, but a broader post-freeze audit found a punctuation-boundary defect:47/50 original semantic controls and10/30 exact controls. Frozen-v1 exact percentages below are retained only as diagnostic provenance, **not valid exact-retention estimates**. A separate punctuation-corrected v2 passes50/50 semantic and30/30 exact original controls; no production or model output changed. Both evaluator versions are kept separately. User-revised160-of-800 true human audit is pending; no human disagreement number is fabricated. **Actual semantic retention and quality noninferiority remain unestablished.**

{v2_note}

## 5. Controlled A/B Results

The same 20 OLD model-response attempts are used for both forensics and A/B. Same 50 facts / 240 messages, production estimate 109749 (character-based, not billed tokens), threshold 95000, gpt-5.4-mini/openai-responses, same host, same source fixture, memory isolation. Sequential random order within 20 pairs. No optional extension to 30. Prompt is the intentional OLD/NEW treatment difference.

### Transport interruption and declared supplemental attempts

After the first seven pairs, both arms encountered repeated SSLHandshakeException before any upstream HTTP response. The harness emitted local502 forwarding errors, which are not upstream model502 responses or parser failures. The original batch was stopped after detection; one raw run remains RUNNING because of operator interruption, separately classified OPERATOR_INTERRUPTED in analysis without rewriting raw. The initial runner's stop condition failed to recognize these wrapped transport exceptions; this instrumentation weakness caused multiple unnecessary connection attempts and is disclosed.

A read-only HEAD probe later received HTTP404, confirming restored TLS/HTTP reachability; the precise cause/recovery of the network failure is unknown. Recovery plan was recorded before supplemental calls in quality-v1/recovery-plan.json. It preserves all earlier attempts, retains the fourteen completed model experiments, and fills logical slots without upstream HTTP200 in the original randomized order. Any HTTP200 production parsing failure is retained and never replaced. Supplemental runner stops immediately on a new transport failure. This is a transparent mid-study infrastructure amendment, not an untouched preregistration or outcome-selected removal of parsing failures.

**All-started end-to-end denominator**, including TLS failures/operator interruption, is preserved in context-ab-all-started.csv:

| Arm | Started | Compact success | Other outcomes | End-to-end success |
|---|---:|---:|---:|---:|
{all_table}

The following primary model-cohort table is **conditional on upstream HTTP200**, targeting20 per arm. It does not represent end-to-end availability; do not hide the all-started table when citing it. Both original and supplemental raw paths and selection manifest are retained. This network incident/time separation further limits causal interpretation.

Observed first-request common configuration identical: {controls['all_first_request_configs_equal']}; first-request history identical: {controls['all_first_request_histories_equal']}. Temperature and max_output_tokens remain UNSET in both actual production requests. Identical unset fields do not prove provider defaults/backend snapshots stay fixed. Raw responses preserve any returned model identifiers. Fixture, class and evaluator hashes checked before execution. Harness bounds: 900 seconds per request; 1860 per run. Identical throttled wire recorder avoids per-chunk cumulative disk rewriting, so historical latency is not pooled with this study.

{metrics}

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

Reliability and screen distributions are reported together above. Token totals come from response.completed usage; known totals by arm are OLD {old['known_total_tokens']}, NEW {new['known_total_tokens']}; complete coverage OLD {old['all_usage_known']}, NEW {new['all_usage_known']}. Missing usage is not zero. Retry input/output/total tokens are recorded separately. Monetary retry cost is N/A because this configured provider's actual rates/cache billing are unavailable; no OpenAI API price is assumed for another endpoint. No paid judge calls occurred.

The reference engineering gate is >=95% operational success on >=20 real attempts AND no material validated semantic degradation. The 5-percentage-point noninferiority reference is project-defined, not a universal standard. Without validated judgments the quality half cannot pass; no significance/noninferiority claim is made from unvalidated screen numbers. Sampling uncertainty, provider/backend variability, one synthetic fixture, no 8-hour or repeated-compaction session, isolated memory and no real file recovery limit generalization.

`model_calls` in raw analysis counts recorded request attempts; a local forwarding failure is not proof of provider model execution or billing. In the selected cohort there are41 request attempts (20 OLD,21 NEW including its retry); network/operator attempts remain separately visible. OLD has only10/20 selected runs with complete reported usage, versus20/20 NEW, so neither a total-cost saving nor equal stream completeness can be assumed from OLD's20/20 parser-success count.

## 10. Resume-safe Claim

**NEEDS_MORE_TESTING**. The previous fixed experiment supports the scoped historical observation: “在固定 50-fact、约 110K 生产估算 token 的长上下文实验中，通过输出校验、有限重试和失败保留原上下文，将压缩完成次数从 2/5 提升至 10/10。” This must remain explicitly tied to that small historical batch; it is not a controlled causal effect or a general 100% guarantee. The new paired results above must also be disclosed if quoting the improvement. Do not use historical 40% and whichever later success rate looks best as a new strict A/B result.

No validated information-retention claim yet. In particular, do not claim 100% information retention, 17% to 100%, 8 hours without context loss, or unrelated MCP/security/multi-agent improvements.

## Reproduction and next required input

Run quality-v1/analyze.py then quality-v1/reports.py to regenerate CSV/JSON/reports offline. Do not rerun prepare.py or freeze_protocol.py over a frozen study. run.py resumes only untouched scheduled attempts and refuses to overwrite raw. build.py/prepare.py are setup scripts, not needed for report regeneration.

Human review is the remaining quality gate: complete manual-review-blind.csv following manual-review-instructions.md, then run compare_manual.py. This report does not pretend that step is complete. See quality-v1 code and results/context-quality-study.json for machine-readable provenance. Raw data and cloned checkouts remain in ignored benchmark directories. No main-repository commit was made.
'''
 save('context-quality-final-report.md',core);save('context-ab-report.md',core)
 print('REPORTS_REGENERATED; '+str(n)+'/40 attempts; INCONCLUSIVE pending human audit')
if __name__=='__main__':main()
