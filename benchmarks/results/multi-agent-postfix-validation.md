# Team result retrieval fix: verified; full gate remains BLOCKED

Production fix `53ec9ba`: TaskGet can resolve background IDs inside their verified owning Team; optional wait_ms0..60000 waits cancellably without stopping the worker. Spawn results explain asynchronous execution, result retrieval, Worktree branch and parent integration responsibilities. Four new regression tests cover namespace isolation, shared-task compatibility, completion, timeout, cancellation and invalid arguments. Full suite199/199 passed.

Post-fix run `2026-09-06T08-39-16.875494600Z`, same frozen task, model and production10-round limit. Two workers completed with19.128 seconds overlap. Main successfully queried **both completed worker results with Team specified**, then wrote both components and ran the unchanged verifier: PASS21 contract checks. The independent harness verifier also passed. Gate elapsed50.3068494 seconds; this is not a speedup comparison.

The legacy GateBench component check reports PASS, but the terminal parent transcript ends `[Agent run ended with iteration_limit]`. Therefore the stricter complete-run verdict is **BLOCKED**. The offline audit preserves both values and does not overwrite the raw gate. This is an instrumentation limitation found by inspecting the actual transcript: unified tests alone must not hide an abnormal Agent termination.

The query/collection shortcoming is fixed. The10-round parent budget still prevents a normal final completion in this case. No budget was increased to obtain a passing measurement. Only one distinct contract has been exercised, with one pre-fix and one post-fix run; the required three E2E tasks and speed comparisons remain unfinished. Failure handling/conflict integration are not proven by this independent-file fixture.

Known pre-fix23 model attempts included22 completed responses and one child stream closed during teardown after Main termination, with unknown failed-call usage. Preserve that exception. Raw batches, usage and per-agent call records remain locally indexed; summaries can be regenerated offline. No60% performance claim is supported.
