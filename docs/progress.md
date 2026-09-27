# SDD ledger — plan: ../MUSE基于mewcode-python的替代方案.md

2026-09-27 开发记录。

采用 executing-plans / TDD，在独立 outputs/muse-next 仓库的 muse-integration 分支实施。原 Java、mewcode-python、已有 MUSE 工程均未覆盖。

Ruling: 源目录没有独立 Git 仓库，当前任务无可用附加 worktree；建立独立副本并初始化 Git，避免修改来源目录。只复制包、测试和构建文件，不复制 .mewcode 的本机配置及技能；技能资源后续逐项审查来源与许可再导入。

共享接口：原 provider 配置 → 新模型客户端，先处理协议与密钥来源；工具 → Worker/权限/验证，尚待统一；扩展 → 持久化子任务，尚待接入。

## 本轮

- 锁文件依赖已安装，Python 3.12.14；初次沙箱网络失败，批准联网后成功。原锁文件未修改。
- 原测试实测：656 PASS / 4 FAIL / 3 SKIP，见 reports/baseline.xml。真实外部模型测试禁用，未向外部发送项目源码。
- 两项 provider 回归先 RED：openai-responses 不支持、忽略显式 api_key_env 导致误用 OPENAI_API_KEY。修复后 GREEN，配置与相关模块定向测试 57 PASS。
- provider 支持 StarCode Responses 别名及指定环境变量；指定变量缺失不降级为其他凭据，密钥字段从 repr 隐藏。代理、预算及完整启动兼容尚未完成，不能宣称原配置已经完整接入。
- 原失败用例修复：Agent 测试改用 tmp_path；空指令测试增加独立仓库边界；空技能测试隔离用户技能目录。保持原断言。
- 受限路径检查在 ancestor.exists() 抛 PermissionError，现将该步骤纳入 OSError 拒绝分支，不让路径权限检查崩溃。

## 待完成

阶段 1：逐文件 Java 映射、测试覆盖矩阵和完整源快照清单。
阶段 2：配置代理/预算兼容、结构化退出码、Windows 进程树和统一审批。
阶段 3：整合现有 MUSE Worker、数据库、API、工作台、研究与资料功能。
阶段 4：扩展统一接入并验证崩溃恢复及团队协作。
阶段 5：正式 Benchmark、干净主机、无 Java 发布和回滚演练。

当前是开发基线，不是全量替代发行版；尚未执行新的真实模型 Benchmark。原基线失败报告保留，不由新报告覆盖。

最终本轮全量回归：662 PASS / 3 SKIP，1 条未注册 timeout 标记警告；证据 reports/integrated.xml。跳过项不计通过。

2026-09-27 continuing toward full replacement (not complete):
- Imported prior MUSE src/muse, frontend, benchmarks, PowerShell launchers and 143-test suite into mewcode baseline. New distribution contains both packages. Test import mode is importlib because upstream and MUSE share test filenames.
- Config RED 4 -> GREEN 61 combined checks: original explicit config env, protocol alias, named credential validation, proxy/timeout, no SDK auto retry. Limits loaded; legacy mewcode Agent loop still needs full enforcement/unification.
- Shell RED 4 -> GREEN 4: structured exit code; suspended Windows Job Object assignment, bounded output, descendant cleanup on timeout/cancel/parent exit. Uses imported MUSE ProcessTree.
- Merged initial run: 811 passed, 1 failed, 3 skipped. Failure was second browser test overriding browser path after relocated tests. Fixed path; full rerun pending. Launcher tests excluded from that run (need normal process-query access).
- Durable MCP: discovery and call require separate persisted approvals, bound by HMAC of resolved config; explicit config only. 3 tests passed including real local stdio server. HTTP and additional negative cases pending.
- Durable delegation: schema v2 task_delegations/execution_budgets; shared model/tool counts and active-time checks; parent auto-pauses until children terminal then reviews results; parent cancel/failure cancels descendants. 18 combined lifecycle tests passed. Crash-after-spawn reconciliation and concurrent-budget edges pending.
- Terminal service: muse terminal uses existing HTTP API/Worker; plan/review read_only enforced by registry, config --workspace support; schema v3 adds read_only. 19 combined terminal/storage/delegation tests passed. Native old Textual entry remains separately executable pending full command/UI convergence.
- Anthropic via baseline serializer + raw MUSE HTTP/SSE boundary: complete-call-only and max_tokens rejection, 8 provider tests passed; no live Anthropic account used.
- Workspace Skill list/load/fork through shared parser and durable child creation. 8 skill/delegation/terminal tests passed. Snapshot parser followup test RED -> implementation, targeted suite running. YAML skill layouts/install/model-selection parity still pending.
- User has a clean Windows test environment and will provide details later. No external files sent during this increment. No formal benchmark rerun yet.
- Java mapping/report inventory is next. Hook/worktree/team still not integrated into durable Worker. Source module presence is not accepted as feature parity.

2026-09-27 further integration:
- Hook adapter now persists approvals/results for prompt, command, HTTP and child actions. Session/turn/tool events wired; async and remaining events still pending. Initial RED 2 -> GREEN 11 combined tests.
- Verification now conservatively includes attempted extension write/execute actions, including MCP discovery (can launch code) and Hook commands. Managed artifacts and delegated records exempt; children have their own gate. RED 10 -> GREEN 18 combined tests; prevents unverified Hook success.
- Recursive tool-result metadata redaction added alongside content redaction. Configured MCP credential env/headers and Hook credential headers join runtime redaction. RED 1 -> GREEN 6 combined checks. Additional malformed-service cases pending.
- Durable spawn_task recovery uses committed delegation row as receipt; external uncertain effects remain interrupted. Fault injection after child commit RED -> GREEN 8 recovery/delegation tests. Skill/agent Hook recovery still pending.
- Source inventory: 209 production Java files mapped to candidate Python modules in java-migration-matrix.csv; 407 hashes in source-manifest.json (Java source/test + baseline Python package). Every row remains NOT_FULLY_ACCEPTED until behavior parity is proved.
- Wheel bundles frontend assets and serves them from installed package. Test RED -> GREEN 2. Frontend TypeScript/Vite build passed; offline wheel build succeeded; inspected 195 ZIP entries and found packaged index/assets and no .java/.class/.jar.
- Full regression reports/full-next.xml: 844 PASS / 3 SKIP / 2 dependency deprecation warnings, 66.16 seconds. Includes real local MCP stdio fixture, browser and Windows launcher checks. No external model calls. Skips remain live baseline model test, Unix-only Hook fixture, file symlink fixture.
- Current source remains an integration development build, not full replacement. Pending: durable team/worktree integration, old terminal/runtime convergence, full Hook/Skill parity, shared budget edge cases, formal real benchmark and clean-host validation. User will supply Windows host details later.

2026-09-27 runtime parity follow-up:
- Schema v4 freezes root model/tool/active limits across Worker restarts; v5 adds transactional team inbox. Restart budget RED -> GREEN; concurrent reservation test confirms exactly 2 reservations across 8 competing parent/child requests when root limit is 2.
- Portable Hook regression replaced a Unix-only destructive-looking fixture with a harmless command and an execution spy. It exposed a real baseline streaming bypass. Fixed pre/post Hook processing in streaming and interactive tool paths; 72 Hook/Agent/shell tests passed. Noninteractive tools also inherit Agent work_dir.
- Portable file symlink test now uses test-owned targets. Current machine skips specifically for WinError 1314, not because Unix fixture files are missing. Clean-host gate remains open.
- Hook approvals show expanded command/URL/body/prompt previews, with secrets redacted and source fingerprint bound. 12 Hook/verification tests passed; Ruff src/muse passed.
- Durable spawn_worktree creates an exact-commit branch/checkout through bounded ProcessTree execution, reuses baseline Worktree model, disables Git hooks for these management commands, preserves parent dirty files and retains checkout after completion. Shared child budgets/approvals apply. Windows long-path handling added. Worktree management root is a sibling of protected state, so child file tools can read its own checkout. 9 combined worktree/config-protection/skill tests passed, including actual Worker read result.
- General file tools now protect .mewcode configuration/skills in addition to .muse. Skills are read only through the dedicated validated adapter.
- Durable team status reuses baseline AgentTeam/TeammateInfo; team_message is approved, transactional, idempotent, capped and restricted to the same root group. Inbox delivery is recorded in checkpoints. 21 combined team/budget/storage tests passed. Shared work-item board and full coordinator lifecycle are not yet integrated.
- Child-task API, terminal /children /child ID /back and web child navigation added. 6 terminal/contract tests passed; browser navigation added to full regression in progress.
- Skill YAML + prompt.md support and reload between calls added; both files contribute to source fingerprint. CRLF normalized for parsing only, hash retains exact source bytes. 5 Skill tests passed. Install, explicit global roots and full model routing remain pending.
- New frontend build and src/muse Ruff check passed. Full reports/full-extensions.xml run is in progress; do not assume its result from the previous 844-pass run.
- Ruling: preserve all integration checkouts and baseline capabilities while command/runtime convergence continues; no Java project deletion or publication. Worktree uncertain effects, full team lifecycle and legacy Textual convergence remain open rather than being counted complete.

2026-09-27 verification and install checkpoint:
- reports/full-extensions.xml was interrupted after browser failures; it is NOT a passing run. Diagnosis: budget binding in ExecutionContext incorrectly required a lease for read-only file-history API calls. Added a failing API regression and limited binding to Worker construction. Browser/terminal/delegation checks: 13 passed.
- Unexpected exceptions after an external/write effect now preserve INTERRUPTED/UNKNOWN reconciliation state; completed spawn receipts can still recover. RED -> GREEN 11 recovery/delegation tests.
- Fresh full suite reports/full-extensions-fixed.xml: 858 PASS / 2 SKIP / 2 dependency warnings, 71.36 seconds. Windows Hook regression now runs; only baseline live model and Windows file-symlink privilege remain skipped.
- Added muse tui: Textual input/status/results use TerminalClient and the existing HTTP service only. 6 TUI/terminal tests passed; no separate model client. Legacy mewcode command entry remains pending convergence; do not describe all entry points as unified yet.
- Clean editable-install probe failed because force-included frontend/dist was absent. Custom Hatch build hook now skips bundled assets for editable installs, requires compiled assets for standard release wheel. Offline editable probe passed in an isolated target; real wheel rebuilt with TUI and web assets, inspected to contain no Java artifacts. This does not replace independent Windows installation acceptance.
- Clean-host checklist prepared in clean-windows-acceptance.md. No real model request, source upload, Java source removal or publication in this increment.

2026-09-27 original-provider practical replay:
- Reused the explicitly authorized five-file batch from old trial, with the original failing openapi_types.py restored from its verified checkpoint hash. Did not send additional repository files or credentials. Public Python documentation was used for research. Skills credential gate applied; original reuse authorization retained.
- Initial three tasks completed using original gpt-5.4-mini: coding 6 model calls/5 tools, documents 4/7, research 4/5. Evidence reports/practical-integration-20260927, including authorized-inputs.json. Coding verify exit codes 1 then 0; 3 unittest cases passed after changing only the code copy. Test file and three documents retained their hashes.
- Semantic review did NOT accept research solely from SUCCEEDED: missing asyncio cancellation detail and runtime version boundary. Follow-up read two Python 3.12 official pages, kept original evidence, and generated a separate report. Human-reviewed research-reviewed.md corrects an overbroad synchronous-work recommendation and removes unnecessary long quotations. Initial research remains labelled needing revision; no formal 60-case grade is inferred.
- Added builtin role constraints for durable children, retaining StarCode provider rather than builtin model preferences. Explore/plan are read-only, verification has an explicit tool set, child tools cannot broaden parent restrictions, local turn limits stay under root budget. RED 2 -> GREEN 14 combined tests.
- Latest post-full-suite targeted verification: 9 roles/TUI/Agent tests passed, src/muse Ruff passed. Lock check passed. More runtime convergence and final acceptance remain.

2026-09-27 review closure and public entry convergence:
- Fresh whole-integration review found two P2 defects: restricted delegated research/document tasks could never satisfy artifact/source gates; expired pending approvals stranded tasks. Offline reproductions confirmed both. Added seven RED regression cases, then fixed the completion contract only for restricted delegated children (root requirements preserved), and added explicit digest-bound approval renewal with no execution/queue transition. Terminal renewal clears its review cache; web UI shows expired review separately. 20 targeted tests passed.
- Public mewcode console/python-module entry now dispatches to the same API/Worker frontend: TUI, noninteractive prompt and loopback web API. Legacy private helper code remains baseline reference, not a public alternate runtime. Unsupported bypass/teammate flags explicitly fail; full option parity is not claimed. Noninteractive exits preserve waiting/background tasks. 11 initial adapter/terminal/baseline helper tests passed.
- Client connection checks data directory and selected public model/limit configuration against API settings before registering/submitting a workspace. It does not hot-switch Worker configuration.
- Browser test now exercises expiry, renewal, pending status with zero attempts, fresh approval, then actual execution. First fixture failed because page.reload intentionally clears task selection; corrected the fixture to use live detail polling, leaving UI behavior unchanged. Combined browser/API/entry regression: 19 passed (reports/entry-browser.xml).
- Narrow review follow-up confirmed original fixes and found truncated stream-json evidence after the first 1000 events. Added a RED 1008-event regression, then drained stopped-task event pages before exit. 18 targeted tests passed after this final fix (reports/entry-final-delta.xml); src/muse Ruff and generated TypeScript contract checks passed.
- Full suite immediately before pagination fix: 873 PASS / 2 SKIP / 2 dependency warnings, 72.22 seconds (reports/final-entry-regression.xml). Do not describe the new pagination case as part of that earlier full run. Skips remain unconfigured baseline external model test and Windows file-symlink privilege; neither counts as a passing acceptance case.
- Frontend build and offline wheel rebuild passed. No external model requests or source uploads in this increment. Original Desktop source projects unchanged. Clean Windows environment details remain pending from user; other local feature/behavior/benchmark gates also remain open.

2026-09-27 unattended continuation (user explicitly requested completing all development plans):
- Continuing inline under executing-plans/TDD; original provider/config and original Desktop repositories remain unchanged. Clean-host details remain unavailable, not an excuse to stop local implementation.
- Schema v6 adds transactional shared work board and action receipts: dependencies, ownership, revisions, create/claim/release/complete/cancel, group isolation, persistence. Added team/board API and terminal commands. Four board/team tests passed.
- Scoped AGENTS/MUSE/MEWCODE/STARCODE project guidance, bounded includes and persisted snapshots; custom workspace roles with source hashes, mapped tool restrictions and model preservation. Eleven role/guidance/completion regressions passed. Ruling: project includes cannot escape the registered workspace, including ancestor/global files; explicit selected global skill directories use skill_roots rather than implicit home scanning.
- Completed database receipts recover Skill/Agent Hook/worktree child creation and team work/messages after crash. External effects without receipts remain UNKNOWN. Seventeen recovery tests passed. Shared running-sibling active time and uncheckpointed expired-lease time are charged; 17 budget/recovery tests passed.
- Hook startup/shutdown/error/compact/permission_request/file_change/command_execute events added; provider failure is persisted before error Hook, avoiding model retry. 26 Hook/Agent tests passed after fixing initial missing pending-event initialization. Ruling: startup/shutdown are task-runtime boundaries in the durable service, not unapproved process-global shell execution.
- MCP stdio now uses suspended process/job containment on Windows and process groups elsewhere, cleanup even after normal parent exit. HTTP disallows implicit environment proxy and redirects. 26 MCP tests passed; real local HTTP MCP discovery/call/approval fixture also passed.
- Terminal /compact, /reload, /skills, /agents, /mcp, /model, /cost, /context and Textual Tab completion added. Context mutation only between turns, preserving original goal/latest input/tool pairing; 11 context/terminal/UI/Hook tests passed after extending API action contract.
- GitHub skill installer accepts only exact commit archives, bounds extraction, rejects links/traversal/sensitive entries, installs atomically without overwriting; explicit skill_roots added. Seven installation/catalog tests passed; no GitHub network request made by these fixtures.
- Worktree review, exact-commit fast-forward merge and clean already-merged checkout retirement added. Dirty/unmerged/active checkouts retained; branches retained. Two real-Git lifecycle tests passed; additional ignored-file guard and no-overwrite-ignore merge protection added afterward, pending next regression.
- Async Hooks are now durable child jobs using the same approval/budget path and no extra model requests. Parent waits for jobs without endless review-hook recursion. Initial combined run reached 21 passing tests; final tool session confirmation pending.
- Still in progress: final async crash/permission boundaries, remaining terminal/history/control parity, explicit uncertain-effect reconciliation, backup/rollback rehearsal, comprehensive Java/test mapping, final full suite/build/review and new 20x3 Benchmark. Clean independent Windows acceptance remains user-environment-dependent. No full replacement claim.
- Current continuation: uncertain external-effect reconciliation now exposed in API/terminal/web; user attestation is never a verified command exit. Memory tools use the single scoped SQLite memory service. Schema v7 adds durable conversation checkpoints and fork-without-replay; terminal /checkpoints and conversation rewind wired.
- Backup/restore uses consistent SQLite backup, checked manifests, new-directory-only recovery, relocated artifact/history paths, paused unfinished work and expired approvals. Six board/backup tests passed including artifact relocation and preservation of original state.
- Async Hook command approval and no-extra-model semantics verified; committed async dispatch receipts recover without duplicate children. Team members release unfinished board ownership on terminal transition; lead completion fails with unfinished board. 12 board/async/delegation tests passed.
- MCP pagination and malformed YAML installer regressions RED→GREEN; combined catalog/recovery suite 34 passed. Restricted roles can execute in approved exact-commit worktrees: four real-Git/project tests passed. Skill reference seeds preserve complete tool exchanges and valid bounded JSON: nine skill tests passed. Ruff src/muse passed.
- First broad continuation regression: 882 passed / 22 failed / 2 skipped. Twenty failures were stale crash-time assertions after conservative active-budget accounting; amended assertions now check exact capped time and no double accounting. Regenerated API types; Windows stop-test error capture uses UTF-8 to expose errors. Escalated focused rerun: 24 passed. Earlier sandboxed launcher failure did not reproduce with authorized process control.
- Java audit enumerates 209 production files, 58 test/support files, 224 Java test intents, with active implementation/regression links and explicit changed contracts. Matrix is traceability, not a substitute for test evidence or clean-host release acceptance.
- Ruling: broad session approval caching, implicit ancestor/home instruction reads, automatic model-changing skill metadata, pane-specific subprocess authority, model-written summary tags, copying ignored private files and automatic worktree cleanup are replaced by explicit durable contracts — preserves original-provider, workspace and approval requirements — costs Java option/UI identity, documented in java-behavior-audit.md.
- Ruling: file and conversation rewind remain separate reviewable actions; backup restores state into a new directory and never rewinds workspace files — prevents accidental file overwrites — costs an extra explicit recovery step.
- Formal Benchmark campaign work/benchmark-python-final retained all 60 records: 32 AUTO_PASS_REVIEW_REQUIRED / 17 FAIL / 11 BLOCKED. Later failures cluster on model transport; P01 lacks file-symlink privilege. Subsequent escalated original-provider synthetic probe completed successfully. No key/provider/proxy changes made; a fresh complete campaign will preserve this failed campaign rather than overwrite it.
- Final fresh reviewer: two Important async Hook completion/verification findings confirmed RED, fixed with descendant waiting/failure propagation, inherited origin-Hook suppression, conservative mutation coverage and verification after job completion. 23 focused regressions passed; five explicit async scenarios verify early vs late verification. No second reviewer dispatched.
- Final: Ruling: UI delayed task-control response regraded from Minor to Important because wrong task detail can influence subsequent control — fixed active-task response guard — browser observer RED→GREEN and full suite cover it. No deferred reviewer minors remain.
- Stop script race reproduced deterministically: taskkill may report a vanished child after the matched process exits. Recheck the same PID/start time before failure; three owned-process tests passed. No unrelated processes targeted.
- Final whole suite after all code/UI changes and old-schema test: 915 PASS / 2 SKIP / 2 dependency deprecation warnings, 87.60s, reports/delivery-ui-final.xml. Skips are disabled baseline external provider test and file-symlink privilege; not acceptance passes. Ruff, generated API, frontend build, offline lock check and wheel smoke passed.
- Final wheel SHA256 64d164f7d418a888b7b3ae36c150986a8c95fafb3bd7549fea255150c2d3d8aa, 207 entries, packaged web HTTP200; local no-JVM PATH smoke is explicitly not clean-host acceptance. Four state backup/migration tests cover v1→v7, artifact relocation and original rollback-copy preservation.
- Campaign2: 34 AUTO_PASS_REVIEW_REQUIRED /18 FAIL/8 BLOCKED raw. Semantic review:35 PASS/17 FAIL/8 BLOCKED, including one explicitly documented R04 word-order detector false negative. Campaign1 retained unchanged; no best-round pooling. Release gate NOT_ACCEPTED due transport failures and Windows symlink/clean-host gate.
- Final: Ruling: reviewer declined clean-host/provider reliability/equivalence claims — keep release gate open and separate exact test evidence from mappings; do not infer complete Java equivalence or stable provider availability. Costs delayed release until independent acceptance.
- Final: Ruling: no adversarial same-privilege filesystem-substitution claim — application path policy is not an OS sandbox; approval boundary remains documented. Costs no guarantee against a concurrently malicious local process.
- Source integrity: 407 enumerated original source hashes unchanged. Existing trial-file authorization preserved; benchmark inputs synthetic only. Package/build exports exclude work/private-state and known credentials.
