# Streamed rate limits were misclassified as summary format failures

The third planned long-context run reached its 100K and 200K checkpoints, then failed its third compaction at 225,331 cumulative estimated tokens. Both attempts returned a provider token-per-minute limit error without a model answer. The raw source is `raw/long-context-v1/2026-09-07T04-20-43.970037300Z/run-3`. The earlier interrupted run2 also contains a rate-limit failure followed by a request of unknown final outcome.

HTTP429 already mapped to RATE_LIMIT. However, HTTP200 SSE error events passed only a message to a classifier that recognized context-length errors and otherwise returned PROTOCOL. ContextManager intentionally retries PROTOCOL errors to recover malformed summaries, so an SSE rate limit caused an inappropriate immediate full-input retry. This is error-classification failure, not evidence of lost facts.

The HTTP clients now preserve structured stream error code/type/message, handle Responses nested/top-level error envelopes, recognize rate-limit codes and the observed fallback message, and emit RATE_LIMIT. Anthropic streamed rate limits use the same classifier. ContextManager's existing policy then exits without a format-repair retry and keeps original history. No summary prompt, compression threshold, retry budget or retention scoring was changed. This fix does not implement automatic rate-limit backoff or guarantee the next request succeeds.

Local mock HTTP/SSE tests exercise four Responses envelopes and Anthropic's typed error. A ContextManager test verifies one call, zero format retries, propagated RATE_LIMIT, failed diagnostics and unchanged input history. Full suite:217 tests, zero failures/errors/skips. See stream-rate-limit-tests.json/log.

No new paid-model experiment has been run against this classification fix. The preserved long-context outcome remains one complete session, one interrupted session and one rate-limited session. Its conditional state-retrieval scores must not be presented as general long-session reliability.
