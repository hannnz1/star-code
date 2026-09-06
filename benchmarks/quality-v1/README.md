# Frozen quality study

No production edits in this phase. OLD/NEW are independent Git checkouts, described in freeze.json; build.json records separately compiled full production sources, class hashes, and the shared dependency JAR. User credentials/configuration remain in the original project and environment, not in either checkout or source snapshot.

Setup order (already executed): prepare.py, build.py, audit.py, freeze_protocol.py, then run.py. Do not rerun setup over this completed/frozen study. protocol.json preserves the initial allocation/scoring freeze. The network incident required recover.py under the separately recorded recovery-plan.json; all original network failures remain intact and are analyzed in the all-started denominator. Human sampling follows the user's later manual-sampling-amendment.md (800 candidates to160 human cases, not800 human cases).

## Regenerate results without API calls

Run `python quality-v1/analyze.py`, then `python quality-v1/reports.py` from benchmarks (or use absolute paths). These regenerate CSV/JSON/reports and the same seeded blind sample. Existing human_label/human_notes are never overwritten. The source CSV is UTF-8 BOM with quoted multiline fields, including the entire source and compressed text.

For the separately documented post-generation punctuation correction, run `python quality-v1/rescore_v2.py` between analyze.py and reports.py. It preserves the frozen-v1 primary data and the blind CSV, writes context-quality-supplemental-v2.json, and adds v2 columns only to the private key. Human comparison reports both evaluator versions. The 160-case selection remains frozen-v1-based; no sample was reselected for v2.

## After the user labels the blind CSV

Only then run `python quality-v1/compare_manual.py`. It reads manual-review-blind.csv and the separate key, reports PENDING/INCOMPLETE if necessary, and writes manual-review-comparison.json/.md. It does not call models, modify production or automatically declare noninferiority. Do not use the older import_human_audit.py interface; compare_manual.py implements the user's latest PASS/PARTIAL/FAIL/UNCERTAIN instructions.

## Independently execute either frozen production environment

For a deliberate new paid replication, use an unused output path and the relevant commit/classes from build.json:

```powershell
$benchDir = 'C:\Users\Administrator\Desktop\project\star code\benchmarks'
$manifest = Get-Content -Raw "$benchDir\quality-v1\build.json" | ConvertFrom-Json
$arm = 'old' # or new
$outputDir = "$benchDir\results\raw\explicit-replication\$arm-01"
& java "-Dbench.root=$benchDir" -cp ($manifest.arms.$arm.classes + ';' + $manifest.dependency_jar) bench.ABRun $outputDir $arm $manifest.arms.$arm.commit
```

Do not pool that replication into this study or overwrite its protocol/selection. The main current production tree is not compiled on this execution path; each arm runs its frozen classes. Check hashes before further paid replication. Compilation used JDK21, logged in results/quality-old-compile.log and quality-new-compile.log. No paid replication is necessary to perform the pending human review.
