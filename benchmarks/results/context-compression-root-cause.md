# Context Compression Root Cause Analysis

Generated from baseline production code `014808a0b0942f25bc4f1c3f415fa63262f98176` and raw batch `results/raw/context-retention/2026-09-04T17-10-27.317233700Z-3dcb344e`. This phase made no production change.

## Current Compression Flow

1. `ChatApplication.executeTurn()` snapshots the committed `Conversation`, gets mode-specific tool definitions, and calls `ContextManager.shouldAutoCompact()` before appending the new user input. The threshold is `contextWindow - SUMMARY_OUTPUT_RESERVE - AUTO_SAFETY_MARGIN`; with the current provider this is `128000 - 20000 - 13000 = 95000`.
2. `ChatApplication.compactWithHooks()` emits `PRE_COMPACT`, calls `ContextManager.compact()`, then emits `POST_COMPACT` only after success. Manual `/compact` enters through `ChatApplication.compact()`. `AgentLoop.run()` can also invoke `compact(..., EMERGENCY, ...)` once after a provider context-length error.
3. `ContextManager.compact()` calculates the before estimate, then calls `summarizeWithRetries()`. The compression prompt is constructed by the private `summaryPrompt()` method.
4. `summarizeWithRetries()` sends the entire remaining history plus the summary prompt through `LlmClient.stream(..., tools=List.of())`. On `CONTEXT_LENGTH` only, it drops complete oldest user-led message groups and retries. There is no format-validation retry.
5. For the configured `openai-responses` provider, `OpenAiResponsesClient.stream()` serializes the regular assembled system prompt as `instructions`, adds dynamic environment context, adds all history messages, and adds the compression prompt as the final user message. The response is SSE. Text comes from `response.output_text.delta`; usage and protocol output are populated only on `response.completed`.
6. `SseReader.read()` stops on stream EOF. `OpenAiResponsesClient.sendTurn()` does not require a `response.completed` terminal event, so EOF after deltas returns a `Completion` containing partial text and zero/fallback usage.
7. `ContextManager.extractSummary()` expects a literal `<summary>` followed later by literal `</summary>`. Missing either marker or an empty/reversed pair throws `LlmException(PROTOCOL, "Summary response did not contain a complete <summary> block")` at `ContextManager.java:297-301` in the baseline.
8. No context replacement occurs until summary parsing, recovery construction, and recent-message selection all succeed. On failure, `ContextManager` increments `automaticFailures` for AUTO and rethrows. `ChatApplication.executeTurn()` catches the error before appending the new input and does not call `Conversation.replace()`. Normally the last old message is ASSISTANT, so `closeRunHistory()` changes nothing; if the last committed role were USER, it could append an assistant run-ended marker. The old context and session records remain. The failed user input is not committed, that turn is aborted, and a later turn can continue. AUTO retries on later turns until three automatic failures, after which `shouldAutoCompact()` is disabled for that `ContextManager`. Manual failure also preserves the old context. Emergency failure propagates out of the current Agent run while its original managed history remains.
9. On success, the replacement is: a USER boundary note; an ASSISTANT message containing parsed summary plus `<context-recovery>`; then recent original messages selected backwards until at least 10000 estimated tokens and five messages. `Conversation.replace()` swaps memory state, and `SessionWriter.replace()` appends a compact marker plus replacement messages durably to JSONL.
10. Recovery contains up to five most recently tracked successful file reads, the available tool schemas, and a reminder to re-read exact sources. The configured system identity, project instructions, memory, skill catalog, and active skills are outside the compressed message list: the same client assembles them into subsequent request instructions through `SystemPromptAssembler` and `PromptContext`. Recent messages stay verbatim in the replacement. In the benchmark, memory/instructions/active skills were deliberately empty and no file snapshots existed.

## Failure Evidence

### Repeat 1

- HTTP status: 200; wall time: 410.65 seconds.
- Decoded model text: 166244 characters, begins with `<summary>`, has no `<analysis>` and no `</summary>`.
- It reached sections 1 through 6, then ended in `All User Messages` while reproducing “Discussion note 59”. Sections 7 through 9 never appeared.
- The wire stream had no `response.completed`, `response.failed`, or `error`; its last event was `response.output_text.delta`.
- Parser expected one complete non-empty `<summary>...</summary>` block. Failure was thrown by `ContextManager.extractSummary()`.

### Repeat 3

- HTTP status: 200; wall time: 898.28 seconds; 249724 decoded characters.
- Begins with `<summary>`, has no closing marker, and ends mid-sentence in `All User Messages` around “Discussion note 90”. Sections 7 through 9 are absent.
- No terminal success/failure/error SSE event. Last event was a text delta. Harness timeout was false: the stream ended before its 900-second deadline.
- Same parser failure and code location as Repeat 1.

### Repeat 5

- HTTP status: 200; wall time: 718.01 seconds; 155316 decoded characters.
- Begins with `<summary>`, has no closing marker, and ends mid-sentence in `All User Messages` around “Discussion note 80”. Sections 7 through 9 are absent.
- No terminal SSE event and no harness timeout.
- Same parser failure and code location.

The repeated discussion-note counts are much larger than the message count because each long benchmark message repeats its note prefix in padding paragraphs. All three responses attempt broad verbatim reproduction and end before pending/current/next-step sections. These are materially truncated outputs, not harmless Markdown/fence/whitespace deviations.

## Root Cause

1. **Unbounded and internally conflicting prompt requirement.** `summaryPrompt()` says “Summarize the entire conversation” but section 6 says `All User Messages (preserve original wording)`. On a 120-user-message input this invites reproduction of hundreds of thousands of characters. The three failed responses follow that instruction and terminate in section 6.
2. **Terminal SSE state is not validated.** The Responses client accepts EOF without `response.completed`. Partial text is exposed as a normal `Completion`; usage becomes indistinguishable from a legitimate zero/fallback usage. This hides transport/provider truncation until the summary parser happens to reject it.
3. **No output validation/repair retry.** Only provider `CONTEXT_LENGTH` errors cause retry. A protocol-shaped but incomplete summary gets one strict parse attempt, then the entire compact fails.
4. **Parser has no tolerance for harmless wrappers.** Literal markers accept extra surrounding text already, but whitespace variants in tags and fenced output without exact tags fail. This is not the cause of Repeat 1/3/5, yet it is a reliability gap.
5. **Model nondeterminism amplifies the prompt defect.** Identical input produced two successful summaries and three runaway outputs. Repeat 2 was also very large (203724 characters) but happened to close; Repeat 4 was concise (10337 characters). The model/provider decides whether to enumerate the full history.

## Proposed Fix

| Candidate | Advantages | Disadvantages / risk | Provider dependency | Token / latency | Retention impact |
|---|---|---|---|---|---|
| A. Strengthen and bound the prompt | Directly removes the proven runaway trigger; smallest behavioral change | A prompt is not a hard guarantee | Low | Usually reduces both | Must verify that deduplication does not discard explicit constraints |
| B. Structured provider output | Strong schema enforcement where supported | Requires protocol/provider-specific support and broader client changes; long strings can still be truncated | High | Similar or slightly higher | Neutral if schema is well designed |
| C. Robust parser/validator | Accepts fences, wrappers, and whitespace while still rejecting missing close/sections | Cannot repair genuinely truncated content | Low | None | Neutral when acceptance rules are strict |
| D. Validation plus one repair retry | Recovers stochastic formatting failures; bounded | Adds a model call, latency, and cost on invalid output | Low if plain prompt retry | Only on invalid runs | Retry prompt could summarize differently, so benchmark must remeasure |
| E. Parser fallback to opening marker through EOF | Very cheap | Unsafe for these failures: would commit summaries truncated before required sections | Low | None | High risk of silent context loss; reject this design |
| F. Require terminal protocol state | Detects truncated SSE earlier and fixes zero-usage ambiguity | Requires client protocol-state plumbing beyond ContextManager; other providers need equivalent semantics | Medium/high | None | Neutral; improves failure classification |

The minimal reliable fix selected for Phase 2 is A + C + D with fail-safe behavior: bound and clarify section 6, introduce a strict validator that tolerates wrappers/fences/tag whitespace but requires a non-empty complete block and required sections, and perform at most one format-repair retry. Missing closing markers remain hard failures. Context replacement remains after validated success only. F is valuable follow-up but is broader than the smallest Context Compression change and is not required to prevent session corruption.
## Phase 2 implementation follow-up

The Phase 1 analysis above was preserved before production changes. During implementation, inspection showed that the existing Responses client already exposes its completed output array through Completion.protocolState. A small ContextManager-only check was therefore included for option F without changing the LLM client or adding new protocol plumbing. This detects a missing completion signal; it does not establish the upstream cause of truncated responses or recover missing usage. Other protocols remain UNKNOWN. The completed before/after results and compatibility limitations are documented in context-compression-fix-report.md.
