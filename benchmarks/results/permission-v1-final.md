# Session permission validation

Production commit `ba607a3b3dc489228526556127314cab8d7827ce`. Full Gradle suite204 tests in55 suites, zero failures/errors/skips.

## Mechanism

Explicit ALLOW_SESSION caches the same tool/path or exact command/remote arguments for one actor, execution directory and permission mode. Different file contents are within a granted edit-path scope. New sessions/resume clear grants. Grants are never persisted. Configured rules, path checks and immutable blacklist precede reuse. UI key4 selects the new option; existing keys1/2/3 keep their meanings.

## Fixed workflow replay

Ten distinct synthetic coding action traces,180 actions per policy,360 recorded decisions. BASELINE uses production DEFAULT plus user ALLOW_ONCE; CURRENT uses the same policy plus explicit user ALLOW_SESSION. Read/search remain automatically allowed in both. Commands are not executed, no model is called, and task_success is null. This is a policy comparison, not an old production-code performance comparison.

| Policy | Median prompts | Total prompts | Reused session grants | Risky actions denied | Unsafe automatic allows |
|---|---:|---:|---:|---:|---:|
| BASELINE_ONCE | 12.0 | 130 | 0 | 50 | 0 |
| CURRENT_SESSION | 8.0 | 80 | 50 | 50 | 0 |

Median confirmation count decreases from12.0 to8.0 (33.33%) in these fixed traces only. This is not evidence for30-to-5 in real coding sessions.

Each trace contains five high-risk probes: forced push, deleting .git, remote script execution, a path escape and disk formatting. The injected user rejects the first three when prompted; the existing boundary/blacklist rejects the latter two before approval. Zero unsafe automatic approvals applies only to this finite corpus and these user decisions. An explicitly session-approved command can be repeated; there is no universal risk classifier or kernel isolation.

## Reproduce and limitations

Compile benchmarks/run.ps1, invoke bench.PermissionBench with the generated classpath/bench.root/bench.harness.sha, then run python benchmarks/permission-v1/summarize.py. Fixture is frozen at permission-v1/fixture.json. Preserve raw alongside permission-v1-artifact-index.json. Every action has a request, decision, reason, prompt flag and risk label. Benchmark metadata records environment/commit and null model usage. No API spend or real UI prompt timings are measured.

The action sequences are designed synthetic workloads with repeated edits/builds. They show cache mechanics, not an estimate of everyday user prompt frequency. Need real, consented coding traces before a broad resume percentage. Permanent-rule behavior was not redesigned; OS sandbox and standalone risk levels remain absent.
