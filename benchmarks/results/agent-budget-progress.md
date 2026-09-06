# Main Agent budget repair: implemented, validation blocked

Production changes in this stage:

- Configurable `agent.max_turns`1–200 and `agent.max_tool_calls`1–1000, with defaults40/100 for Main Agent. Earlier Main behavior was hardcoded10/50. Child role limits remain unchanged.
- Main Agent uses the settings after new sessions/resume and context changes. Compatibility AppConfig constructors supply defaults; benchmark config copies preserve actual budgets.
- Each model request includes remaining run budget and instructions to report unfinished work honestly. Limits still produce an abnormal outcome when exhausted; tests are not converted into overall success automatically.
- Regression cases check strict config validation, a scripted completion on turn12 and forced stop on turn3. Full test execution has not yet reached the compiler successfully.

Three distinct E2E fixtures are frozen before model execution under multi-agent-v2: original checkout, text normalization/header parsing, exact numeric mean/capped retry delay. The v2 harness additionally requires normal Main completion, two explicitly retrieved results and successful Main verification after its last mutation. It records these separately from independent unified test success. This strict gate is more conservative than paths using only asynchronous notifications; such paths may require a future declared audit, not silent acceptance.

## Environment blocker

The current Codex permission policy disallows shell sandbox escalation. Project and Gradle cache writes were granted, then explicit reads were granted. Tests were retried with a fresh no-daemon Gradle process. Java still raises AccessDeniedException for the jline-terminal-jni dependency JAR. Independent javac compilation likewise fails opening build/libs/star-code.jar. This is not a test assertion failure; no new full-suite PASS is available. Existing204-test evidence and previously packaged JAR refer to the previous production version.

Preserved logs: agent-budget-tests.log, agent-budget-tests-fresh-process.log, agent-budget-independent-compile.log and agent-budget-javac-environment.log. The initial wrapper attempt used C:\.gradle due to the tool environment; later attempts explicitly used the already installed user Gradle cache. No further identical permission request or disabled escalation is attempted.

## Resume validation

Run `benchmarks/resume-agent-budget.ps1` from the user's normal PowerShell. Default: full tests, harness compile and packaging; no model calls. It stops on failures and preserves timestamped logs under results/raw/agent-budget-local. `-RunE2E` additionally invokes three real-model Team tasks using the existing configured provider and may incur API usage; the strict per-task gate decides success. The script never changes source, merges worker changes, modifies ACLs or changes baseline tags.

Status: CODE_PREPARED / VALIDATION_BLOCKED. Three v2 E2E tasks NOT_RUN; no new speedup number. Long-horizon, Context quality, OS sandbox and SWE-bench-Live work have not been represented as completed. Production packaging is deferred until validation passes.

## Validation unblocked and full tests passed

Execution policy was updated to allow reviewed sandbox escalation. Running the authorized Gradle command resolved Java access. The first compiled test run found three child-input compatibility failures from applying Main budget reminders to child Agents; the reminder was narrowed to Main only. Full rerun passed207 tests,55 suites, zero failures/errors/skips. See agent-budget-tests-authorized.log (preserved failures) and agent-budget-tests-final.log/json. Main budget defaults40/100 and strict bounds remain. The earlier environment blocker above is historical, not current.

Next: freeze this implementation and run the three preregistered v2 contracts. No claimed E2E success until raw strict-gate results exist.
