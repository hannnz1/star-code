# Quoted summary markers: confirmed parser defect

The original long-context batch `2026-09-06T12-37-10.527639900Z` at commit `7d2cb2ba82b4673655a4415d4265ffe13636bdfa` attempted three sessions. All stopped at the first compaction, at 95,654 cumulative estimated tokens. Six model attempts produced five answers and one request failure. All five answers were rejected for MULTIPLE_SUMMARY_BLOCKS. No retention checkpoint was reached; retention is unmeasured, not zero percent.

Four saved answers quote the summary protocol inside paired Markdown inline-code spans. The validator counted these literal examples as actual delimiters. The fix masks paired same-line code spans for delimiter matching while extracting the unchanged original body. Actual duplicate blocks, missing closing markers, invalid headings and oversized summaries remain rejected. Unmatched backticks do not consume subsequent lines. The summary prompt, threshold, section requirements, retry policy and scoring are unchanged.

Offline replay against the unchanged saved answers now accepts four and still rejects one answer with additional unquoted markers. One attempt has no response. This is parser regression evidence, not a new successful end-to-end experiment or a quality improvement percentage. See `summary-marker-replay.json`.

Full regression suite: 214 tests, zero failures/errors/skips. Tests cover quoted examples, different backtick widths, quoted closing markers in truncated output, real duplicate blocks and unmatched backticks, in addition to existing compression tests.

A separate three-session post-fix batch will use the identical preregistered fixture, model configuration, 95K trigger and typed state-retrieval scoring. The original failure batch remains preserved and separately summarized in `long-context-v1-before-marker-fix.*`.
