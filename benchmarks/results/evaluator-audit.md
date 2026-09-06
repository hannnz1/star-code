# Evaluator audit

Status: **PENDING_HUMAN_REVIEW**. No genuine human annotations have been supplied. Human disagreement rate: **N/A**, never zero. No LLM judge was used, so no judge sampling/temperature claim is made.

## Existing evaluators

The legacy scorer checks a typed expected value and a verbatim evidence quote. This couples quality to extraction formatting. It can reject an accurate paraphrase as non-verbatim evidence. It also accepts wrong units (RetryQueue 730 seconds instead of milliseconds) and unrelated negative actions (AccountMigration not deleting rows instead of not renaming customer_ref). Results from that scorer cannot alone establish quality regression. Authored audit challenges: legacy 8/12; new screen 12/12. These are developer-authored examples, not a random validation set or human audit. Full cases: quality-v1/audit-challenges.json.

The previous secondary evaluator required near-complete lexical propositions, so synonymous wording could be rejected; sentence-exact scores measured copying, not semantic preservation. This study keeps those old outputs intact and freezes a separate screen before A/B generation.

### Additional post-freeze positive-control audit and correction

Checking all50 original fact sentences revealed that frozen v1 supported47/50 semantically and only10/30 applicable exact literals. Its literal boundary rejected sentence-final periods as if they extended an identifier/path. This also blocked three complete API-contract controls. The authored12-case suite had missed the defect. Thus frozen-v1 exact percentages must **not** be interpreted as valid literal-retention estimates.

scorer_v2.py corrects this boundary defect in a separate offline evaluator; the original frozen scorer, generated outputs, primary reports/data and sample allocation remain available. It passes50/50 original semantic controls,30/30 original exact controls and four prefix/decimal/extension negative cases. This is a post-generation bug correction, not a preregistered endpoint or proof of general semantic accuracy. Details: context-quality-supplemental-v2.json. The blind CSV is byte-for-byte unchanged; only the separate key adds v2 results alongside frozen-v1 results. compare_manual.py will report both versions after human labels arrive. Human sampling remains based on frozen-v1 strata, so it is not changed to favor the corrected scorer.

## Current screen

Exact covers literals on applicable fact categories, preserving case, numeric values/relations and API verbs/routes; prose causes, failed attempts, negative constraints and TODOs are not assigned whole-sentence exact scores. The exact denominator is recorded through applicable judgments and differs from all-50 semantic screening.

Semantic screening recognizes limited explicit aliases/action/polarity patterns in owner-scoped clauses. Labels are SUPPORTED / DISTORTED / CONFLICT / UNVERIFIED. Unmatched paraphrases become UNVERIFIED, never a proved loss. Even a SUPPORTED label can be wrong outside rule coverage: coreference, tables, multiple roles in a sentence, competing values, implicit causality and later corrections are not fully understood. These are exploratory evidence-screen percentages, **not a validated semantic retention rate or guaranteed mathematical lower bound**.

Exact-vs-semantic disagreement on the same applicable judgments: 0.25 as a fraction, n=2400. They measure different constructs and share code; agreement does not validate them. Human-vs-screen disagreement remains N/A.

## Required human review (latest user sample size)

{
  "status": "PENDING",
  "total_fact_view_records": 4000,
  "candidate_pool": 800,
  "human_sample": 160,
  "seed": 20260905,
  "category_counts": {
    "user_constraint": 20,
    "todo_current_state": 20,
    "api_contract": 20,
    "bug_root_cause": 20,
    "failed_attempt": 20,
    "filename_path": 20,
    "numeric_parameter": 20,
    "identifier_class_method": 20
  },
  "arm_counts": {
    "new": 80,
    "old": 80
  },
  "view_counts": {
    "effective": 80,
    "summary": 80
  },
  "score_band_counts": {
    "middle_50_80": 77,
    "high_>=80": 83
  },
  "absent_categories": [
    "architectural_decision",
    "real_tool_result"
  ],
  "human_disagreement_rate": null,
  "blind_csv": "C:\\Users\\Administrator\\Desktop\\project\\star code\\benchmarks\\results\\manual-review-blind.csv",
  "key_csv": "C:\\Users\\Administrator\\Desktop\\project\\star code\\benchmarks\\results\\manual-review-key.csv",
  "sampling_note": "Latest user instruction supersedes original 20% of all judgments: 800 candidates ->160 human sample, 4% of 4000 total. Equal arm/view/category allocation and score-band coverage; not an unstratified population error estimate."
}

When the batch is complete, manual-review-blind.csv contains 160 cases sampled from an 800-case pool (4000 total fact/view records). This revised sample is 4% of the total, per the latest user instruction. It is balanced across OLD/NEW, view and represented categories, covering available score bands. The blind CSV contains full original source and compressed text, with no version, automated score, reasoning or final run score. The separate mapping is manual-review-key.csv; do not open it before review. Only the user fills PASS/PARTIAL/FAIL/UNCERTAIN and notes. Run compare_manual.py after actual review to calculate agreement, disagreement, confusion matrix and strict binary kappa. PARTIAL also receives 0.5 in a separately named weighted agreement-credit analysis. Source length/content can still reveal style; this is label-blinding, not a claim of perfect blinding.

**Gate:** evaluator validity is not established. Do not change production compression based on these screen averages. Broad semantic scoring and the requested regression/noninferiority inference remain INCONCLUSIVE until review and, if necessary, independently validated evaluator revision.
