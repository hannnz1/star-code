# MCP lazy validation v1

Fixed before model selection runs. No target reduction percentage or favorable sample replacement.

Production: MCP wire initialize/tools-list still obtains full schemas. Model-facing loading uses a short name/description index in search_mcp_tools, search activates up to5 matching schemas for subsequent requests. Discovery returns names only to avoid copying the full schemas twice. Activation persists per Agent instance, never in shared registry state. Each benchmark run uses a fresh Agent. Full mode remains available through STAR_CODE_MCP_LOADING=full or ToolRegistry.lazyMcpLoading(false).

Tradeoffs: index still grows with tool count; small schemas may yield modest savings or extra overhead. Lexical search may miss synonyms. Selected tools accumulate during an Agent lifetime; no eviction or persistence of activation across app restart. Discovery requires an extra model turn. Permissions and hooks apply to discovery and actual tools; discovery does not grant execution approval. The available index is built only from the role/mode-allowed definitions.

## Schema runs

10/25/50/100 external tools × FULL/LAZY ×5 repeats, same existing frozen mcp-loading/tools-N.json used for the valid current Full baseline (20/20 succeeded before production changes). Six builtins remain available. True local stdio MCP → ToolRegistry → AgentLoop → production Responses serializer → deterministic local SSE receiver. No remote model generation, no inference latency or task success claimed for these schema-only runs. Discovery setup time recorded separately.

Count actual serialized tool arrays and complete JSON with tiktoken0.12.0/o200k_base when available; explicitly estimated and not official billed tokens. Include the search index and search schema in lazy overhead. Distinguish MCP-only initial overhead from all-tools and whole-request overhead. Deterministic fixture/schema content means repetition is not independent model evidence and token variance may be zero. Lazy-loaded/total cost only measured where tools are actually selected.

## Real model selection runs

10 fixed synthetic service tasks × FULL/LAZY =20 runs, 100-tool catalog with90 distractors; same prompt/model/config for both arms, fixed seed20260905 randomizes order within pairs. Fixtures and expected answers created before calls. Request parameters use unchanged production provider defaults. No change to task based on outcome.

The fixture exposes real MCP tools/list and tools/call; each call validates tool name/entity_id and returns a fixed service answer. PASS requires actual correct remote call, no unexpected remote call, completed Agent and final exact service answer. Merely mentioning the tool or returning DONE is insufficient. This tests simple single-operation selection, not real third-party service coverage or statistically powered noninferiority.

Save every request/response/usage, remote-call log, outcome, retries/failures and timing. All infrastructure failures retained; stop on failed execution. Task failures are not replaced. Report selection/task success, model calls, latency and known usage separately. Missing provider usage must remain unknown.

For total schema cost, sum serialized tool-array estimates over all model calls; compare matched completed tasks and report failures separately. Also record the union of loaded remote schemas as a different metric. Do not describe initial schema savings as whole-task token savings.

Original static benchmark guard remains immutable; new entry points have their own current-commit checks and build manifests. Context/permission-policy semantics/Team implementation remain unchanged except classification of the new local readonly discovery tool.
