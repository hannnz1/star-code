# Long-context component pilot

Raw batches: `benchmarks\results\raw\long-context-v1\2026-09-06T12-48-46.787895100Z`, `benchmarks\results\raw\long-context-v1\2026-09-07T04-20-43.970037300Z`

Workflow completed: 1/3 sessions.

| Run | Workflow | Compactions successful / attempted | Model calls | Known total tokens | Seconds |
|---|---|---|---|---|---|
| run-1 | COMPLETED_COMPONENT_WORKFLOW | 4/4 | 11 | 412663 | 76.10 |
| run-2 | INCOMPLETE_NO_TERMINAL_RECORD | 0/1 | 2 | UNAVAILABLE | UNAVAILABLE |
| run-3 | FAILURE | 2/3 | 8 | 232473 | 34.65 |

## State retrieval (only stages reached)

| Run | Cumulative estimate | View | Correct fields | Retention |
|---|---|---|---|---|
| run-1 | 103283 | summary | 11/11 | 100.00% |
| run-1 | 103283 | complete | 11/11 | 100.00% |
| run-1 | 202337 | summary | 17/17 | 100.00% |
| run-1 | 202337 | complete | 17/17 | 100.00% |
| run-1 | 301411 | summary | 23/23 | 100.00% |
| run-1 | 301411 | complete | 23/23 | 100.00% |
| run-3 | 103283 | summary | 11/11 | 100.00% |
| run-3 | 103283 | complete | 11/11 | 100.00% |
| run-3 | 202337 | summary | 17/17 | 100.00% |
| run-3 | 202337 | complete | 17/17 | 100.00% |

## Failures

- run-2: No terminal run.json; inspect interruption observation and raw calls.
- run-3: com.starcode.llm.LlmException: Rate limit reached for gpt-5.4-mini in organization [organization redacted] on tokens per min (TPM): Limit 200000, Used 133013, Requested 72207. Please try again in 1.566s. Visit https://platform.openai.com/account/rate-limits to learn more.

## Limits

- Scripted production components, not autonomous coding or eight elapsed hours.
- 100K/200K/300K are cumulative new-history chars/3.5 estimates, not resident or provider tokens.
- Repeated synthetic fixture; three sessions do not establish general retention reliability.
- Strict typed structured-state retrieval, not semantic quality or independent human review.
- Field observations repeat across stages and sessions; they are not independent unique facts.
- A failed session contributes no later-stage score; missing stages are not silently successes.
- Known usage sums exclude unavailable failed-call usage; such totals are lower bounds.
- No speedup, historical-template improvement or eight-hour claim is measured.
