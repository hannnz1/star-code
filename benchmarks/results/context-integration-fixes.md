# Context integration corrections

Two defects confirmed during long-context preparation:

1. ContextManager.recordUsage added cache read/write to input_tokens unconditionally. Responses input_tokens already includes cached input, so e.g.60000 input+1000 output+40000 cached was counted as101000, incorrectly crossing the95000 threshold. It now counts61000 for Responses. Anthropic continues adding separate cache categories. Regression tests verify both protocols and actual threshold boundaries.
2. compact recovery attached every provided inputSchema to conversation text. This could undo model-facing MCP lazy exposure after compression. Recovery now lists tool names only and directs the model to current exposed definitions/discovery; schemas remain on the model's tool interface. A regression test verifies a large sentinel schema is absent while tool names remain available.

The summary prompt, summary validator, retry algorithm and auto-compaction threshold are unchanged. Recovery text and usage accounting are production changes; old Context study conclusions remain attached to their frozen versions. This is not a new OLD/NEW summary-template experiment or a measured retention improvement.

Protocol references: [OpenAI Responses usage](https://developers.openai.com/api/reference/cli/resources/responses/methods/retrieve), [Anthropic cache accounting](https://platform.claude.com/docs/en/build-with-claude/prompt-caching). Local serializers are OpenAiResponsesClient and AnthropicClient; they preserve the provider-specific usage fields.

Full Gradle log: context-integration-full-tests.log; count aggregate: context-integration-full-tests.json. Long-context pilot is separately preregistered in long-context-v1/PLAN.md; it must not be described as completed until its raw runs and scores exist.
