# Execution ledger — plan: 2026-10-06-crew-ui-upgrade-plan.md

User approved phases 1–5. Work in existing development copy on muse-integration; preserve previous changes. No paid model calls or remote publishing for UI verification.

Preflight: phase 1 routing supplies project/section to phases 2 and 4. Phase 3 reuses plan identity and existing review version checks. Phase 5 validates navigation, retention and publication boundaries.
Ruling: use existing development copy rather than a clean checkout, because the approved UI builds on extensive uncommitted implementation in this copy. Backup touched frontend files under work/crew-ui-before-20261006.
Ruling: retain mounted business forms and hide inactive sections; pass explicit active flags to task review and assistant to prevent hidden actions.
RED: new browser acceptance fails because login opens generic home and merchant-overview does not exist.

First acceptance run: 7/7 passed (new navigation, draft assistant, five viewport widths, language/refresh routing).
Refresh retention test RED: product CSV was empty after reload. Add project/version scoped session drafts; draft storage is presentation only and grants no authority.

Review Important findings reproduced RED: assistant restores goal but resets launch_products to build_site; task log URL remains merchant team route without task ID. Fixes: persist atomic manager inputs and encode task identity in developer route/history. Scoped draft key rollover now loads corresponding data instead of migrating older revision input.
Existing regression caught startup race: navigation was available before project fetch, suppressing automatic initial store selection. Fix first selection while distinguishing explicit create using ~new route marker.

Phases 1–4 implemented: one merchant navigation and default overview, scoped route/task history, retained developer space and settings memory, build/product flow journeys and version-aware brand editing, board/list toggle and outcome/technical disclosure, context-bound manager side panel creating durable drafts through existing API. No model calls on navigation or draft creation.
Phase 5 core verification: 19/19 passed, work/crew-ui-final-core.xml, frontend build and 854 translations/654 UI calls checked after final UI polish. Existing full browser suite running with updated navigation selectors.
Fresh reviewer: two Important findings reproduced and fixed with RED→GREEN covering tests in the 19-case run. Minor key rollover fixed and covered by project-revision test. No other deferred findings. Review excludes unrelated preexisting work and backend changes.
Screenshots inspected: merchant overview and manager at 1440px (Chinese), website at 1440/390px (English). Additional widths 1280/900/360 covered by acceptance.
Manual merchant feedback and real store/model acceptance remain user activities; this UI change does not relabel those as completed.

Extended browser run: 50 passed, 5 failed (legacy MUSE placeholder and previously always-visible technical ID assertions). Updated selectors/assertions to current UI without removing their behavior checks.
Team form refresh RED: unsaved title was empty. Persist independent new-task inputs by project/version, and clear them only after explicit successful save/start. Existing saved-draft editor stays separate.

Final complete browser suite: 56 passed, 0 failures (work/crew-ui-final-browser.xml); prior obsolete assertions fixed without weakening verification. All tests use local APIs, scripted fixtures and simulated release receipts; no paid model calls or live publication.
Final localization spot check RED: fixed backend proposed-step labels remained Chinese in the English assistant. Translate only these known interface steps; merchant goal/output stays unchanged. Targeted regression/build follow.

Final build passed: 863 translations and 654 explicit UI calls checked. Affected browser regression: 18 passed, 0 failures (work/crew-ui-final-locale.xml); this overlaps the full suite and is not added as unique cases.
Additional long-title/error screenshot test: 1 passed, 0 failures (work/crew-ui-states.xml), covering real persisted long draft title, 390px page overflow and surfaced API 409 error. Screenshots saved alongside overview/manager/responsive captures.
Phases 1–5 development and automatic verification complete. Manual experience measurements remain unmeasured. Latest preview root returned HTTP 200 with the current built asset. No paid API calls, live merchant publishing, commits or GitHub pushes in this UI implementation task.
