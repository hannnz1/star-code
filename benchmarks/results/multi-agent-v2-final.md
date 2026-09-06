# Multi-Agent v2 complete workflow gate

**PASS** — 3/3 required distinct contracts passed. Speedup NOT_MEASURED.

Implementation commit `efe4a4211f78dd4a9da10925e60ee245b861092d`; Main budget 40 turns/100 tool calls.

| Case | Strict status | Main complete | Main verifier | Unified test | Workers / trees | Overlap seconds | Wall seconds | Calls |
|---|---|---|---|---|---|---:|---:|---:|
| checkout | PASS | True | True | True | 2 / 2 | 14.243 | 53.827 | 28 |
| numeric | PASS | True | True | True | 2 / 2 | 14.217 | 50.730 | 27 |
| text | PASS | True | True | True | 2 / 2 | 11.931 | 57.314 | 32 |

Raw requests/responses, per-agent lifecycle, collection, Worktree diffs, main changes, unchanged verifier and independent test output are retained under the recorded raw directories. Actual provider usage coverage and exceptions are in CSV/JSON. No harness decomposition, code implementation or integration occurred.

## Limits

- Three synthetic independent-file tasks, one attempt each; no speed comparison or confidence claim.
- Parent40/100 default budget differs from old10/50; previous failures retained, not paired timing controls.
- Conflicting edits, coupled changes, long-run reliability and OS sandbox are not tested.
- Explicit TaskGet collection is required by this gate; notification-only collection is not credited.
- No model seed is set; seed20260905 describes fixture provenance only.

## Reproduce

After committing production and compiling all sources using benchmarks/run.ps1 compile, invoke bench.GateSuiteCurrent with bench.root/bench.harness.sha and generated classes + dependency JAR. Uses paid configured model calls. Regenerate summary offline with python benchmarks/multi-agent-v2/summarize.py. Preserve raw/build hashes/frozen fixtures and artifact index together.
