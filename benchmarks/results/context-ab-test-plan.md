# Controlled Context Compression A/B Plan

Frozen before paid A/B generation on 2026-09-05. Production working tree is unchanged.

OLD commit: 014808a0b0942f25bc4f1c3f415fa63262f98176 (benchmark-baseline-v1).
NEW commit: 4f26fa7552e72a54d85a262255a2aff243042181 (independent local snapshot commit; main project HEAD remains OLD).
Independent checkouts: benchmarks/.work/quality-v1/old and new. Both fully compiled from their own production source with the same dependency jar. Compile logs: quality-old-compile.log and quality-new-compile.log. SHA256 source/class/dependency manifests: quality-v1/freeze.json and build.json. No credentials/config/memory copied into either checkout.

## Controlled conditions

20 attempts per arm, not 20 successful outputs. OLD's same 20 attempts supply forensic analysis, avoiding a redundant additional batch. No optional expansion to 30. Each pair has OLD and NEW in seeded randomized order; no concurrency, same host and Java runtime. Schedule and protocol are frozen before generation. Failure remains in denominator. No outcome-based early stopping; configuration/authentication/infrastructure failure stops the batch.

Identical 50-fact/240-message fixture, generator and recorded hashes; model gpt-5.4-mini; openai-responses; context window 128000; thinking=false; production trigger 95000, production input estimate 109749. Provider/sampling configuration: quality-v1/model-config.json. Temperature, top_p, seed and max_output_tokens are UNSET in both production clients; actual provider defaults cannot be asserted beyond identical requests. Both use the same configured endpoint, credentials and system prompt. Provider endpoint/system prompt fingerprints are recorded without exposing secrets.

No runtime edits to prompts, output limits, parser, threshold, selection or assembly. Original and current prompt/assembly source frozen under quality-v1/old-ContextManager.java.txt and new-ContextManager.java.txt. Both retain production-selected recent messages and recovery attachments; memory isolated. Harness reads recent/recovery via reflection for forensic observation only. This does not install recovered output in a conversation.

## Operational and forensic separation

Operational success means production compact returned a result. On failure, effective-context operational quality is unavailable, never a hypothetical success. A forensic extractor may select the text after an opening summary marker through EOF when the close is absent, or raw text when there is no opening. It records the boundary and completeness explicitly. It does not insert a closing marker. A hypothetical forensic context joins that excerpt with production-selected recent/recovery solely for latent-quality analysis. Neither forensic output nor original retained context makes a failed compact operationally successful.

Wire recorder forwards the actual production request, headers are not persisted. Streaming forensic disk snapshots are throttled to once/second identically in both arms, plus a final save; no response generation or serializer changes. Per-request harness watchdog 900 seconds; outer run deadline 1860 seconds. Timeouts remain failures and usage can be missing. This harness bound is not a product timeout guarantee.

## Evaluator and human audit

Original frozen scorer is known to have unit/action false positives and verbatim-quote false negatives. Original percentage figures are descriptive, not ground truth. quality-v1/audit-challenges.json saves 12 authored counterexamples/controls; old scorer matches 8/12. A new deterministic screening scorer matches 12/12 but is not validated by that small authored suite.

Exact measures literal identifiers, paths, numbers with units/relations, API contracts and configuration values only (category-dependent denominator). Full-prose sentence verbatim retention is not used as semantic retention. Semantic screening uses SUPPORTED, DISTORTED, CONFLICT, UNVERIFIED; unmatched paraphrases are not labelled lost. Rates are verified-evidence rates/lower-bound-style screening estimates, not proven semantic truth. Broad synonym coverage and false positives remain unknown.

No additional paid extraction/judge calls. Both arms use identical frozen scorer. Sample >=20% of available fact/view judgments, seeded random, with OLD/NEW labels and automated scores hidden, for actual human annotation. Main assistant inspection is not human annotation. Human disagreements remain null until returned labels exist. Exact-vs-semantic disagreement is calculated only on the same applicable facts and is not itself error rate.

## Analysis and gates

Show all attempts, successful-only operational quality, and all analyzable forensic quality separately. OLD success/failure forensic distributions explore survivorship bias; they cannot prove why the original five attempts had that pattern. Report mean, median, p10,p25,p75,p90,min,max, sample SD; preserve each fact, origin, category and evidence. Unverified is not distorted or proven lost.

Noninferiority reference is 5 percentage points, project-defined, not a universal standard. Without validated semantics/human audit, final quality conclusion is INCONCLUSIVE regardless of the screen averages. Production changes only after CONFIRMED_REGRESSION. Engineering reliability reference: >=95% on >=20 real attempts, reported independently of quality.

## Reproduction

prepare.py freezes independent repositories once; build.py compiles both; audit.py validates authored controls; freeze_protocol.py freezes allocation and scoring before paid runs; run.py executes/resumes without repeating any attempt directory. Offline analysis scripts regenerate CSV/reports from raw. Existing historical raw remains intact and is not pooled into the new randomized study.
