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
