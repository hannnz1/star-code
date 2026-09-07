# Long-context component pilot

Raw batch: `benchmarks\results\raw\long-context-v1\2026-09-06T12-48-46.787895100Z`

Workflow completed: 1/2 sessions.

| Run | Workflow | Compactions successful / attempted | Model calls | Known total tokens | Seconds |
|---|---|---|---|---|---|
| run-1 | COMPLETED_COMPONENT_WORKFLOW | 4/4 | 11 | 412663 | 76.10 |
| run-2 | INCOMPLETE_NO_TERMINAL_RECORD | 0/1 | 2 | 0 | UNAVAILABLE |

## State retrieval (only stages reached)

| Run | Cumulative estimate | View | Correct fields | Retention |
|---|---|---|---|---|
| run-1 | 103283 | summary | 11/11 | 100.00% |
| run-1 | 103283 | complete | 11/11 | 100.00% |
| run-1 | 202337 | summary | 17/17 | 100.00% |
| run-1 | 202337 | complete | 17/17 | 100.00% |
| run-1 | 301411 | summary | 23/23 | 100.00% |
| run-1 | 301411 | complete | 23/23 | 100.00% |

## Failures

- run-2: No terminal run.json; inspect interruption observation and raw calls.

## Limits

- Scripted production components, not autonomous coding or eight elapsed hours.
- 100K/200K/300K are cumulative new-history chars/3.5 estimates, not resident or provider tokens.
- Repeated synthetic fixture; three sessions do not establish general retention reliability.
- Strict typed structured-state retrieval, not semantic quality or independent human review.
- A failed session contributes no later-stage score; missing stages are not silently successes.
- Known usage sums exclude unavailable failed-call usage; such totals are lower bounds.
- No speedup, historical-template improvement or eight-hour claim is measured.
