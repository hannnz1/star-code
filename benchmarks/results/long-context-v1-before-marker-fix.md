# Long-context component pilot

Raw batch: `benchmarks\results\raw\long-context-v1\2026-09-06T12-37-10.527639900Z`

Workflow completed: 0/3 sessions.

| Run | Workflow | Compactions successful / attempted | Model calls | Known total tokens | Seconds |
|---|---|---|---|---|---|
| run-1 | FAILURE | 0/1 | 2 | 147661 | 24.32 |
| run-2 | FAILURE | 0/1 | 2 | 147087 | 22.38 |
| run-3 | FAILURE | 0/1 | 2 | 73620 | 19.01 |

## State retrieval (only stages reached)

| Run | Cumulative estimate | View | Correct fields | Retention |
|---|---|---|---|---|

No retrieval checkpoint reached; retention is NOT_MEASURED.

## Failures

- run-1: com.starcode.llm.LlmException: Invalid compression summary: MULTIPLE_SUMMARY_BLOCKS
- run-2: com.starcode.llm.LlmException: Invalid compression summary: MULTIPLE_SUMMARY_BLOCKS
- run-3: com.starcode.llm.LlmException: Invalid compression summary: MULTIPLE_SUMMARY_BLOCKS

## Limits

- Scripted production components, not autonomous coding or eight elapsed hours.
- 100K/200K/300K are cumulative new-history chars/3.5 estimates, not resident or provider tokens.
- Repeated synthetic fixture; three sessions do not establish general retention reliability.
- Strict typed structured-state retrieval, not semantic quality or independent human review.
- A failed session contributes no later-stage score; missing stages are not silently successes.
- Known usage sums exclude unavailable failed-call usage; such totals are lower bounds.
- No speedup, historical-template improvement or eight-hour claim is measured.
