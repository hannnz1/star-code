"""Regenerate the final Context report from sealed review and recorded decision."""
import json,hashlib
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parent;OUT=ROOT/'results'
def main():
 a=json.loads((OUT/'llm-blind-review-analysis.json').read_text(encoding='utf-8'))
 assert a['context_validation'] in ['READY','NEEDS_MORE_TESTING','REGRESSION_FOUND']
 assert a['review_seal_sha256']==hashlib.sha256((HERE/'completed.json').read_bytes()).hexdigest()
 lines=['# Context Compression final validation','',f"**{a['context_validation']}**",'',
  '**This was an independent LLM blind review, not a human audit.**','',
  '## Evidence and implementation','',
  '- Original baseline/tag: `014808a0b0942f25bc4f1c3f415fa63262f98176` / `benchmark-baseline-v1`.',
  '- Current implementation commit: `63cade05f8dec1e5b33a948dfcd05eb69f291aa3`. Controlled NEW snapshot: `4f26fa7552e72a54d85a262255a2aff243042181` in the independent checkout. All 257 Java files match after CRLF→LF normalization; see context-source-equivalence.json.',
  '- Fixed 50-fact, 240-message synthetic conversation: ~109749 production character-estimated tokens, unchanged auto threshold 95000. Model: gpt-5.4-mini / openai-responses, thinking=false, 128000 window; production temperature/maxoutput/seed unset. Fixture and pairing seed20260905.',
  '- Full Gradle rerun passed 52 suites / 190 tests / zero failures, errors or skips; validation-full-tests-step1.txt and .json. No new production modification occurred during blind review.',
  '', '## Four distinct measurements','',
  '| Measurement | OLD | NEW | Interpretation |','|---|---:|---:|---|',
  '| All-started operational success | 20/29 (68.97%) | 19/29 (65.52%) | Includes 17 transport-only failures and one operator-interrupted run across both arms |',
  '| Internal compact success, selected HTTP200 cohort | 20/20 (100%) | 19/20 (95%) | Conditional on model response, not end-to-end availability |',
  '| Internal retry, selected HTTP200 cohort | 0/20 | 1/20 | NEW failed run remains failed after regeneration |',
  '| Supplemental-v2 forensic effective semantic screen mean | 93.1% | 89.6% | Automatic rule evidence screen, not verified semantic truth; includes forensic failed context |',
  '| Supplemental-v2 forensic summary exact literal mean | 94.33% | 90.83% | Only 30 exact-applicable facts; diagnostic, not semantic equivalence |',
  '', 'The historical 2/5 original and 10/10 fixed batches are separate studies, not a contemporaneous causal improvement estimate. OLD20/20 in the controlled cohort did not reproduce historical 40% success. Prior frozen-v1 exact metrics are invalid after its punctuation defect; v2 is a separate post-generation correction, not a silent replacement.',
  '', '## Independent model review results','',
  'All160 reviews were saved and hash-sealed before key access. No resampling: OLD80/NEW80, summary80/effective80, eight categories20 each. This is 160/800 candidates from 4000 fact/view records, not 160 independent compactions. Same model family can share bias. Each external request had no history, treatment, automatic scores or mapping; the orchestrator itself already knew prior study results and did not supply labels.',
  '', '| Version / view | PASS | PARTIAL | FAIL | UNCERTAIN | Strict / weighted |','|---|---:|---:|---:|---:|---:|']
 for arm in ['OLD','NEW']:
  for view in ['summary','effective']:
   v=a['by_version_view'][arm][view];c=v['labels']
   lines.append(f"| {arm} / {view} | {c['PASS']}/{v['total']} | {c['PARTIAL']} | {c['FAIL']} | {c['UNCERTAIN']} | {100*v['strict']:.2f}% / {100*v['weighted']:.2f}% |")
 lines+=['','Both arms have 77/80 PASS (96.25%) when pooling views. NEW40/40 effective-view PASS is a small sampled-record result; it does **not** support 100% production retention. Views from a failed compact run are forensic, not a successful compacted context. No noninferiority or improvement test was preregistered; do not infer equivalence from equal rates or superiority from a 2.5-point view difference.',
  '', '## Automatic evaluator versus independent reviewer','',
  '| Evaluator | Nominal agreement | Disagreement | Strict agreement | Weighted credit | Strict kappa |','|---|---:|---:|---:|---:|---:|']
 for name in ['frozen_v1','supplemental_v2']:
  v=a['evaluator'][name]['overall'];lines.append(f"| {name} | {100*v['raw_agreement']:.2f}% | {100*v['disagreement_rate']:.2f}% | {100*v['strict_agreement']:.2f}% | {100*v['weighted_agreement_credit']:.2f}% | {v['cohens_kappa_strict']:.4f} |")
 lines+=['','No PARTIAL/UNCERTAIN labels occurred, so strict and weighted reviewer scores happen to coincide. The script still implements both conventions. Automatic UNVERIFIED is distinct from FAIL in nominal agreement; strict scoring maps unsupported to zero. Corrected-v2 nominal disagreement is NEW18.75% / OLD16.25%. Full confusion matrices, category and view counts are in llm-blind-review-analysis.json.',
  '', 'V2 disagreement is highest for filename/path35%, TODO/current-state25%, and failed-attempt20%. These are disagreement with this model, not established evaluator error rates. The frozen-v1 API45% disagreement falls to v2 10% after the previously disclosed punctuation fix; the scorer versions must remain separate.',
  '', '## Reviewer fallibility and fact-level follow-up','',
  'Two sealed FAIL judgments conflict with explicit source evidence: R0008 contains “Locale fallback data file: `resources/locale-fallbacks.json`”; R0146 contains the original “The current account summary endpoint is GET /v4/accounts/summary.” Yet the reviewer reports loss/confusion. These are post-unblinding diagnostic observations by Codex, not replacement blind labels or human adjudication. All labels and headline counts remain unchanged. See post-unblinding-diagnostics.json for source offsets and snippets.',
  '', 'The other flagged records concern StreamBuffer65536-byte cap, reconcilePendingTransfers, SearchBackfill240-document batch and RouteCache next-step state. A missing keyword alone does not establish loss; independent review and complete-text checks remain distinct. No confirmed systematic OLD→NEW semantic regression has been established by this audit.',
  '', '## Failures, usage and timing','',
  '- Controlled A/B: 17 TLS failures before upstream response and one operator interruption retained; recovery selection was declared and original records preserved. The wrapper’s local502 is not upstream model502. OLD complete usage exists for only10/20 selected runs; do not claim a whole-study token/cost saving.',
  '- NEW selected failed run: first response missing closing summary marker, retry multiple summary blocks; both response.completed. This is production validation failure, not proven transport truncation.',
  '- Review: 161 attempts, 160 valid labels and one no-output service TPM failure. Raw rate-limit attempt retained. Pacing and later session restart disclosed; 146 labels survived the interrupted Codex session and only14 were resumed.',
  f"- Known reviewer usage: {a['review_calls']['known_usage']['input_tokens']:,} input + {a['review_calls']['known_usage']['output_tokens']:,} output = {a['review_calls']['known_usage']['total_tokens']:,} tokens across160 usage records. One failed-call usage unknown; no monetary total inferred.",
  f"- Sum of request wall time: {a['review_calls']['request_wall_clock_seconds_sum']:.2f}s; recorded pre-request pacing: {a['review_calls']['pacing_seconds_sum']:.2f}s. Observed first-to-last span: {a['review_calls']['observed_batch_span_seconds']:.2f}s including interruptions; not compression latency.",
  '- Pre-run LF/CRLF export-hash defect corrected with CSV/content unchanged and old freeze archived. Rebuild/idempotence/tamper checks passed. Raw indexed files remain locally saved; no key or memory copied into model requests.',
  '', '## Decision and resume status','',a['rationale'],'',
  '**FUNCTION_ONLY** for context reliability mechanisms; **NEEDS_MORE_TESTING** for stable retention-improvement numbers. Safe wording: “Implemented validated context compaction with bounded retries and failure-safe context preservation, backed by a reproducible 50-fact controlled benchmark and independent model-review analysis.”',
  '', 'Do not claim17%→100%, guaranteed100% retention, proven OLD/NEW equivalence, a causal reliability improvement from separate batches, or eight-hour endurance. No E1/E2/E3/E4 production tuning follows from these unconfirmed differences. Phase2 may proceed with MCP while retaining this quality limitation.',
  '', '## Reproduce and locate evidence','',
  '- Offline reports: `python benchmarks/llm-review-v1/analyze.py`, then `python benchmarks/llm-review-v1/finalize.py`. Requires completed.json, unchanged review CSV/raw review hashes and separate key.',
  '- Review raw: `results/raw/llm-blind-review-v1/`; output: `llm-blind-review.csv`, `llm-blind-review-unblinded.csv`, `llm-blind-review-analysis.json`, `llm-blind-review-report.md`.',
  '- A/B raw: `results/raw/context-quality-ab/2026-09-05T07-51-54Z/`, including recovery-selection.json; exact frozen build/source metadata under quality-v1.',
  '- `context-validation-artifact-index.json` hashes local evidence. Git excludes raw; the index and indexed files must be retained together. Implementation commits are above; benchmark artifact commit can be resolved by `git log -1 --format=%H -- benchmarks/llm-review-v1/finalize.py`.',
  '- This closes the requested model-review analysis; it does not mark the other project validation phases complete.']
 (OUT/'context-final-validation.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
 print(a['context_validation'])
if __name__=='__main__':main()
