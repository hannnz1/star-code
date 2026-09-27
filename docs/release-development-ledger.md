# SDD ledger — plan: docs/superpowers/plans/2026-09-27-muse-release-completion.md

## Execution rulings (2026-09-27)

- Ruling: continue in the existing isolated integration checkout on `muse-integration` — original Java and Python source directories remain separate and current changes must be preserved — moving would omit uncommitted work.
- Ruling: use this tracked ledger instead of Bash-only skill helpers — Windows execution and durable handoff — equivalent records are maintained manually.
- Ruling: human Benchmark grading and independent Windows acceptance are deferred to the user, as explicitly requested — do not count them as PASS — release remains an RC until those gates close.
- Ruling: development and automated tests precede paid acceptance campaigns — stabilize the code before spending model usage — no historical result is attributed to the new candidate.
- Ruling: retain original provider/configuration, permission boundaries and default budgets; no public publishing.

## Interface preflight

| Producer → consumer | Contract / decision |
| --- | --- |
| 1–5 → 6,7 | Freeze final source identity before acceptance runs and packaging; results from earlier identities stay historical. |
| 2 → 6 | Archive and retrieval remain task scoped; bounded retention is not permanent memory. |
| 3 → 6 | Schema activation never grants execution permission; FULL adapter stays experiment-only. |
| 7 → 8 | Same artifact hashes go to independent Windows; local venv is not independent-host evidence. |
| 6,8 → 10 | Human and external-environment gates remain pending at development handoff. |

## Progress

- Task 1: in progress. Baseline HEAD `13e9d19b09078dd44c5cb08b66288e4ed8c7c68f`; previous regression 922 passed, 2 skipped, 4 warnings. Inspection found legacy HookEngine drops background task ownership and command cancellation has no process cleanup.
- Development: Hook drain ownership and early-return/cancellation owner tests passed (18 targeted tests including experiment gates); manual same-sequence archive uses schema 8 without rewriting rewind checkpoints; history supports bounded pages and explicit truncation; latest user objective is preferentially retained.
- MCP: old tool/capsule private metadata scrubbed, cumulative activation budget capped, `$id` local resource references rebased; targeted retention/context suite 18 passed.
- Worktrees: explicit approved `integrate` action supports reviewed divergent commits without reset/deletion; actual Git regression passed.
- Experiments: added full long-context mechanical workflow, MCP FULL/LAZY adapter, original three-contract multi-Agent observer and conservative release manifest. Offline original long-context thresholds crossed successfully. Real runs pending final source freeze.
- Whole-branch review: four Important findings (latest request loss, `$id` rebasing, early-return Hook cleanup, false positive child contribution score); all addressed with failing/passing targeted tests. Minor sanitized configuration identity added. No second reviewer dispatched.
- Ruling: preserve full latest user objective even if it exceeds the compaction soft character target — silently changing the task is worse than retaining bounded user input — long oversized input can still require a larger model context.
- Ruling: original multi-Agent fixtures remain Java *target programs*, external to the Python runtime, to keep their verifier unchanged; JDK required only for this historical benchmark, not installation or normal MUSE use.
- Automated acceptance, packaging and final documentation: in progress.
- Task 8 / human part of task 6: user acceptance deferred, not executed.

## RC1 measured results and RC2 corrective work

- `7b08f3f` / 0.3.0rc1: 949 passed, 2 skipped, 2 dependency warnings; no resource-cleanup warnings. Fresh venv wheel install, API/web/Worker, CLI entry points and no-Java-PATH process start/stop passed locally.
- Three complete original-threshold long-context runs: every complete/retained view scored 11/11, 17/17, 23/23. This is a component workflow, not eight-hour operation.
- MUSE-Bench full 60 attempts: 57 AUTO_PASS_REVIEW_REQUIRED, 3 P01 file-symlink environment BLOCKED. No human PASS assigned.
- MCP paired attempt 1: FULL 9/10, LAZY 9/10. Attempt 2: FULL 10/10, LAZY 9/10. Both remain evidence; no pooling to manufacture a perfect run.
- Root cause of repeated MCP local-load failures: model copied exposed internal `_connection` into search/load, which correctly rejected extra fields. RC2 removes internal binding from public definitions and discards that non-authoritative field for local operations, while remote fingerprint binding and approval remain enforced. Failing/passing regression added.
- Multi-Agent attempt 1: checkout children could not pass the whole-project verifier with the other module intentionally absent. Parent requested input; the controller was stopped, all state retained. Ruling: permit exact single-component `javac -d build <fixture component>` verification for children, with final whole-project verifier mandatory on the parent. Do not widen to arbitrary commands. Explicitly instruct verification after Git operations because all shell calls conservatively invalidate earlier verification.
- RC2 additionally clears derived JSON state after ambiguous later prose, preserves source excerpts, and exposes installed release identity separately from API contract version. Targeted RC2 suite: 23 passed.
- Ruling: these real-experiment findings require a new candidate and complete automated rerun; RC1 evidence is historical and is not attributed to RC2.

## RC2 observations and RC3 corrective work

- RC2 `0ccc9f3`: 953 passed, 2 skipped, 2 dependency warnings. Installed wheel, API/web/Worker and no-Java-PATH startup/shutdown passed locally.
- RC2 original MCP paired run: FULL 4/10, LAZY 10/10; six FULL failures reported incomplete provider responses. Long context: one complete run, two incomplete provider responses. Do not infer rate limit or quota without a concrete error code.
- RC2 multi-Agent: 0/3. Observed invented role names, invalid metadata arguments, denied Git chaining, and incomplete provider responses. RC3 adds actionable parameter/role diagnostics and safe allowlisted provider error codes without logging response bodies or secrets.
- Ruling: the fixed benchmark controller accepts exactly one `git add ... && git commit ...` pair and exact component compilation through either shell tool — these are normal fixture operations, not implementation assistance — ordinary compilation still does not satisfy the required verification receipt.
- Diagnostic repeat stopped after a child requested input. Parent prompt had omitted the verification tool name from its child instructions. RC3 asks the parent to forward the tool name explicitly; it still owns all delegation and implementation.
- Ruling: stop and record an attempted benchmark when any child needs input — unattended waiting cannot resolve that condition — failure remains in the record instead of spending the entire timeout.
- Targeted regression: 31 passed (`reports/diagnostics-final.xml`), including controller intervention, strict command allowlist, safe provider diagnostics and invalid argument guidance. No source fixture answers changed.
- Ruling: run final paid campaigns serially to reduce concurrent load while diagnosing service failures; this does not establish concurrency as their cause. Preserve every attempted run and do not pool best cases.

## RC3 measured results and approval-flow clarification

- RC3 `3031799`: full regression 956 passed, 2 skipped, 2 dependency deprecations. Fresh installed API/web/Worker/CLI and owned process startup/shutdown passed without Java on PATH. Permission replay: 180 actions, median 9 / total 94, 50/50 risk probes denied, no normal-action errors.
- Three original-threshold long-context runs completed. Multi-Agent 0/3: all six children completed, but each parent ran the final verifier before integrating and asked for redundant confirmation to perform the originally requested integration. This is a real-model workflow failure, not a human-review gate.
- Ruling: clarify the product prompt that calling an in-scope tool starts the runtime's approval flow, and that delegated commits still need the requested parent integration — observed repeat-confirmation failures justify the change — approval enforcement and the right to request missing information remain unchanged.
- RC3 MCP campaign interrupted for this product correction; all partial files retained. No RC3 business campaign started. Final experiments will run on a fresh RC4 identity; no cross-version score pooling.
- Test evidence for prompt behavior: RC3 three real attempts are the failing reproducer; RC4 original three-task run will determine improvement. Existing approval-resume, denial and missing-input regressions remain mandatory; a test matching prompt strings would not prove behavior.

## RC4 measured results and RC5 final correction

- RC4 `b911aee`: full regression 956 passed, 2 skipped, 2 dependency warnings. Three original-threshold long-context runs completed. MCP FULL 9/10 and LAZY 9/10 in one paired run; both remaining failures asked for redundant discovery approval. Business 60 attempts: 56 AUTO_PASS_REVIEW_REQUIRED, 3 P01 environment BLOCKED, 1 R04 fact-coverage FAIL. This is NOT_ACCEPTED; no score pooling.
- Multi-Agent RC4: both children ran in all three cases; checkout children succeeded and both commits integrated but final Java verifier failed on the child-generated discount algorithm. Numeric/text parents completed and unified verifiers passed, but one child failed in each, so neither qualifies as a two-child success.
- Ruling: compare merged contributions by Git committed blob and clean checkout, not raw working-tree bytes — observed Windows CRLF conversion made an already integrated commit look unequal. Red/green test covers true content mismatch separately. This changes scoring only, not production Git safety.
- Ruling: clarify MCP discover's tool description to start the runtime approval directly for in-scope work — two real RC4 requests redundantly asked the user before tool invocation. The approval gate remains unchanged.
- RC5 is required because the MCP public tool description changed. All RC4 evidence remains historical, including its business failure and multi-Agent outcomes.

## RC5 interrupted run and RC6 correction

- RC5 `76b7ce7`: 957 passed, 2 skipped, 2 dependency warnings; fresh wheel installed and API/web/Worker/CLI process smoke passed without Java on PATH. Source ZIP and wheel hashes retained under `dist/rc-76b7ce7`.
- Multi-Agent 0/3 in RC5. Two parents used `ask_user` to emit progress statements with no question, causing WAITING_INPUT. The third parent failed final verification. This is an actionable product input-validation issue, so the subsequent paid batch was stopped after one long-context phase; partial evidence is retained, not counted as a complete RC5 campaign.
- Ruling: `ask_user` requires a direct question ending in `?` or `？`; invalid progress statements return actionable INVALID_ARGUMENTS without pausing. This syntactic guard cannot determine whether an otherwise well-formed question is necessary. Existing valid clarification/resume behavior remains.
- RC6 red/green regression covers observed statement; source and model tests must be rerun because the public tool schema changed. RC5 data cannot be attributed to RC6.

## RC6 final measured candidate and handoff

- `da71920` / 0.3.0rc6: 958 passed, 2 skipped, 2 dependency warnings; Ruff/OpenAPI/lock/frontend checks passed. Fresh wheel API/web/Worker/CLI and owned-process start/stop passed locally without Java on PATH. Known source files unchanged: 407/407.
- Original long-context three complete runs with both views scoring 11/11, 17/17, 23/23 at all thresholds. MCP paired FULL 10/10 and LAZY 10/10, exactly ten expected remote calls per mode. No price claim; actual cost unrecorded.
- Original multi-Agent 1/3: numeric fully passed two-child contribution and unified verifier. Checkout and text did not complete; no score pooling or fixture answer injection. Ruling: retain failed attempts as a real limitation; repeated model stochastic retries or further prompt changes would require another frozen candidate and full campaign, so RC6 handoff remains NOT_ACCEPTED.
- Business full fixed 60: each round 19 AUTO_PASS_REVIEW_REQUIRED, 1 P01 BLOCKED; 0 FAIL and no NOT_RUN. Human semantic reviews and independent Windows symlink remain pending, as requested by user. Export 1,019 scanned evidence files plus 60-line review CSV.
- Permission replay: 180 actions, median 9, total 94, 50/50 risky probes denied. The different contract is documented; original 8 confirmations cannot be claimed.
- RC6 wheel/source ZIP from same candidate commit created, 207 wheel files, fresh local install and no-Java PATH process smoke passed, archive secret and forbidden-file scan zero; SHA-256 manifest validated.
- Ruling: final publication remains NOT_ACCEPTED until failed multi-Agent 3/3, independent host P01 and human review gates close. This is a local reviewable RC, not a public or Java-equivalence release.
- RC6 local performance replay completed: p95 task creation 5.21 ms, event-to-browser 831.43 ms, cancel confirmation 5.78 ms, process tree stop 119.43 ms, expired lease recovery 7.47 ms. No RSS or real-model timing claim. Backup/restore and legacy v1→8 copy preservation are included in the 958-pass regression.

## RC7 runtime state clarification

- Ruling: RC6 showed a parent denying delegation after a failed role attempt even though later spawn calls succeeded. Add a bounded, server-derived child/action status summary to every model request after delegation. It contains no prompts, tool outputs, paths or permissions; it cannot authorize a tool. A later successful action is explicitly distinguishable from an earlier failed attempt. Existing task-scoped approval remains enforced.
- A red/green regression checks the exact failure class, including omitted private prompt/path; targeted agent/worktree suite 15 passed. New candidate and full automated rerun are required. RC6 is preserved as a local reviewable historical candidate, not promoted to PASS.

## RC7 frozen outcome and external service gate

- RC7 `7ccedb5` / 0.3.0rc7: full regression 959 passed, 2 skipped, 2 dependency warnings; Ruff/OpenAPI/lock checks passed. New wheel/source ZIP built and fresh local install plus no-Java PATH process smoke passed. Package hash/known-secret scan passed.
- Original multi-Agent: 1/3, text passed complete contribution/verifier gate; checkout integrated two successful children but final discount boundary verifier failed; numeric did not complete valid integration. This is the remaining automated capability gap, not a human review task.
- Long-context run 1 complete (11/11, 17/17, 23/23 in complete and retained views); runs 2/3 incomplete after provider error. MCP FULL and LAZY all ten each received the same provider error, no completed questions.
- Business run stopped after 11 consecutive provider-error FAILs. Planned 60 slots retained: 11 FAIL, 49 NOT_RUN. No RC6 result attributed to RC7.
- A minimal synthetic request to the original provider returned HTTP 200 with an SSE `error` event. The sanitized event had no recognized code or reason; only a billing-related message category could be established. Do not claim quota, balance or specific spend control. Ruling: stop additional paid calls until account/API status changes — repeated immediate failures cannot advance development and could consume resources. Preserve all attempted evidence.
- Human semantic review, independent clean Windows/file-symlink, original multi-Agent 3/3 and a full RC7 model campaign remain open. Final status NOT_ACCEPTED; historical RC6 full-campaign evidence is a separate comparison only.
- RC7 local engineering-performance replay completed. p95 task creation 6.60 ms, event commit to browser 835.24 ms, cancellation repository acknowledgement 2.98 ms, process tree stop 93.39 ms, expired lease recovery 3.85 ms. UI click latency, independent-host performance, full RSS and 8-hour endurance remain unmeasured.

## Post-RC7 model value experiment

- User replenished the original OpenAI API account and requested a lower-cost model. The original StarCode config remains untouched. MUSE now accepts `MUSE_MODEL` as a launch-time override; `Start-MUSE.ps1` defaults to `gpt-6-luna` and `-Model gpt-5.4-mini` selects the original model.
- Both models passed one synthetic reply and one function-call probe. Luna completed one fixed MUSE-Bench round with 17 automatic prepasses requiring human review, 2 FAIL and 1 local symlink BLOCKED. D01 is a frozen literal-format mismatch despite correct amounts; C01 omitted `settings.py`. Historical RC6 Mini round 1 was 19 prepasses and 1 BLOCKED, but versions and conditions differ; scores are not pooled or called a controlled A/B.
- Standard-list-price estimates with all input counted uncached: Luna USD 0.014167 from 113,846 input and 5,565 output tokens; historical Mini USD 0.100697 from 106,279 input and 4,664 output tokens. These are not bills and exclude tool fees, caching effects and retries. Full details and official citations: `docs/model-cost-selection.md`.
- Full local engineering regression after the model override: 960 passed, 2 skipped, 2 dependency warnings. The one sandbox-blocked process cleanup check passed outside the sandbox on its own test child, then the complete suite passed with a short temporary directory and configured Playwright browsers. This is an economy trial, not a new frozen RC or proof that Luna meets the original multi-Agent and human benchmarks.
