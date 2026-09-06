# Independent LLM Blind Review

**This was an independent LLM blind review, not a human audit.**

## Method

The existing 160 records were retained without resampling (seed 20260905): 80 per arm, eight categories with 20 each. These are 20% of the 800-candidate pool and 4% of 4000 fact/view records. The external reviewer receives one record per fresh request, no history/tools/key. Same configured model family as generation can share biases; independence is request isolation, not an independent ground truth.

## Blindness Controls

The orchestrating Codex conversation had prior exposure to treatments/aggregate results and cannot itself be a blind judge. It supplied no labels. External model requests contain only the frozen rubric and blind sample. All 160 valid labels were hash-sealed before this script opened the key. Original CSV and empty human columns remain unchanged. Style, length and contents can reveal treatment indirectly; explicit label blinding cannot prevent that.

## Rubric

PASS preserves the actionable fact; PARTIAL loses important detail; FAIL loses/reverses/confuses the fact; UNCERTAIN lacks sufficient basis. Equivalent wording and numeric units are valid. Failed-attempt reasons are required only when the original supplies them. See llm-review-v1/rubric.txt.

## Label Distribution

{'total': 160, 'labels': {'PASS': 154, 'PARTIAL': 0, 'FAIL': 6, 'UNCERTAIN': 0}, 'scored': 160, 'strict': 0.9625, 'weighted': 0.9625}

## OLD vs NEW

| Arm | N | PASS | PARTIAL | FAIL | UNCERTAIN | Strict | Weighted |
|---|---:|---:|---:|---:|---:|---:|---:|
| NEW | 80 | 77 | 0 | 3 | 0 | 96.25% | 96.25% |
| OLD | 80 | 77 | 0 | 3 | 0 | 96.25% | 96.25% |

These are descriptive scores of sampled records. Summary and effective views may duplicate facts; some failure-context views are forensic, not usable production compact output. Do not quote pooled scores as operational retention or independent run-level success. Version/view breakdowns are in the analysis JSON.

## Category Analysis

| Category | N | PASS | PARTIAL | FAIL | UNCERTAIN | Strict | Weighted |
|---|---:|---:|---:|---:|---:|---:|---:|
| api_contract | 20 | 19 | 0 | 1 | 0 | 95.00% | 95.00% |
| bug_root_cause | 20 | 20 | 0 | 0 | 0 | 100.00% | 100.00% |
| failed_attempt | 20 | 20 | 0 | 0 | 0 | 100.00% | 100.00% |
| filename_path | 20 | 19 | 0 | 1 | 0 | 95.00% | 95.00% |
| identifier_class_method | 20 | 19 | 0 | 1 | 0 | 95.00% | 95.00% |
| numeric_parameter | 20 | 18 | 0 | 2 | 0 | 90.00% | 90.00% |
| todo_current_state | 20 | 19 | 0 | 1 | 0 | 95.00% | 95.00% |
| user_constraint | 20 | 20 | 0 | 0 | 0 | 100.00% | 100.00% |

OLD/NEW by category and each evaluator category/arm disagreement are available in llm-blind-review-analysis.json. No new architectural-decision/tool-result category was invented.

## Agreement

| Evaluator | Raw agreement | Disagreement | Strict agreement | Weighted credit | Strict kappa |
|---|---:|---:|---:|---:|---:|
| frozen_v1 | 78.12% | 21.88% | 81.25% | 81.25% | 0.19893190921228326 |
| supplemental_v2 | 82.50% | 17.50% | 85.00% | 85.00% | 0.20133111480865187 |

Reviewer UNCERTAIN excluded from primary denominator; automatic UNVERIFIED retains its own nominal column. Weighted credit = 1−mean absolute score difference, with PARTIAL=.5. Strict kappa collapses PARTIAL/FAIL to zero; null indicates degenerate marginals. Full confusion matrices are in the JSON. Frozen-v1 exact results are provenance only after its punctuation defect; corrected v2 is supplemental.

## Disagreement Examples

The first disagreement in review_id order from each category is shown, not selected by treatment or magnitude. Reviewer notes are model judgments, not verified truth.

- R0008 / filename_path / NEW: automatic-v2=SUPPORTED; reviewer=FAIL. Fact: Locale fallback data is in resources/locale-fallbacks.json. Notes: The compressed summary mentions `resources/locale-fallbacks.json`, but it does not preserve the exact fact that locale fallback data is in that file as a locatable path-specific requirement.

- R0014 / user_constraint / OLD: automatic-v2=UNVERIFIED; reviewer=PASS. Fact: The OrderArchive change must not add external dependencies. Notes: The compressed context preserves the BlobUpload checksum cause as hashing before decompression, matching the original fact.

- R0016 / todo_current_state / NEW: automatic-v2=UNVERIFIED; reviewer=PASS. Fact: For RouteCache, inspect the route_generation metric next. Notes: The compressed summary preserves the current-state fact that RouteCache’s next step is to inspect the route_generation metric.

- R0020 / api_contract / NEW: automatic-v2=UNVERIFIED; reviewer=PASS. Fact: Customer suspension uses HTTP PATCH on /v3/customers/suspension. Notes: The summary explicitly preserves the `/v3/customers/suspension` endpoint and HTTP PATCH method.

- R0024 / bug_root_cause / NEW: automatic-v2=UNVERIFIED; reviewer=PASS. Fact: The WebhookAck timeout is caused by synchronous DNS lookup on the event loop. Notes: The summary preserves the bug root cause that WebhookAck timeout is due to synchronous DNS lookup on the event loop.

- R0036 / numeric_parameter / OLD: automatic-v2=UNVERIFIED; reviewer=FAIL. Fact: StreamBuffer must cap payloads at 65536 bytes. Notes: The compressed context omits the 65536-byte cap for StreamBuffer, so the key numeric parameter is not preserved.

- R0042 / failed_attempt / OLD: automatic-v2=UNVERIFIED; reviewer=PASS. Fact: For MetricFlush, switching to a fixed-rate timer was attempted and failed. Notes: The summary preserves that MetricFlush switching to a fixed-rate timer was attempted and failed.

- R0067 / identifier_class_method / NEW: automatic-v2=UNVERIFIED; reviewer=FAIL. Fact: The reconciliation entry point is reconcilePendingTransfers. Notes: The compressed summary does not preserve the specific identifier `reconcilePendingTransfers`, instead replacing it with unrelated preserved facts.

## Limitations

- A single synthetic 50-fact conversation, correlated fact/view samples, two versions and one model family; no human labels or cross-family replication.
- The reviewer can make mistakes and share generator biases. Agreement validates consistency only; it cannot certify true semantic retention.
- Frozen v1 exact punctuation defect; v2 corrected after generation and evaluated separately. No favorable replacement of prior raw outputs.
- Initial export checksum used LF before Windows CRLF translation. Actual bytes were checked against original CSV; correction archived before first review. No sample/rubric change.
- R0014 attempt1 failed with service TPM rate limit and no output delta; raw error retained. Pacing added afterward; same sample retried. Calls and missing usage are included below.
- No noninferiority margin, cluster-powered design or equivalence test. A small score gap is not proof of regression or improvement.

{
  "attempts": 161,
  "status_counts": {
    "VALID_REVIEW": 160,
    "INFRASTRUCTURE_FAILURE": 1
  },
  "usage_records": 160,
  "missing_usage": 1,
  "known_usage": {
    "input_tokens": 3086580,
    "output_tokens": 6780,
    "total_tokens": 3093360
  },
  "request_wall_clock_seconds_sum": 274.302722,
  "pacing_seconds_sum": 1916.213,
  "first_start": "2026-09-06T03:35:34.411802700Z",
  "last_end": "2026-09-06T07:05:45.178400500Z",
  "observed_batch_span_seconds": 12610.766598,
  "span_caveat": "Includes interruption, compilation/recovery and pacing; not compression latency or pure model latency."
}

## Conclusion

**INCONCLUSIVE; Context status NEEDS_MORE_TESTING.** The two arms each have 77/80 model-rated PASS records, with opposing small view-specific differences. This stratified, correlated single-fixture sample has no preregistered noninferiority margin and contains apparent reviewer errors in both arms. It establishes neither semantic improvement/equivalence nor systematic regression. Controlled internal compact success remains OLD20/20 versus NEW19/20; operational failures and evaluator defects remain disclosed. Preserve current production implementation; do not run compression tuning without stronger regression evidence. Mechanism and benchmark descriptions are supportable; historical retention-improvement percentages are not.
