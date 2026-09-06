# MCP Lazy Loading final validation

**IMPLEMENTED_AND_VERIFIED** (scope: fixed synthetic fixtures; not general noninferiority).

## Production implementation

Commit64e4c92f5b623a166879ee5aa86f23fd09d50867. Tool.deferred marks MCP adapters; ModelToolCatalog builds the allowed short index, searches/activates schemas; AgentLoop refreshes each request and owns activation state. Permissions and hooks remain on execution. STAR_CODE_MCP_LOADING=full restores full exposure. MCP tools/list still downloads schemas upfront; only model-facing exposure is lazy.

## Initial schema overhead

estimated: tiktoken0.12.0/o200k_base; compact JSON arrays; not provider-official schema tokens. Includes MCP schemas or discovery schema/index, excludes the six common builtins. All-tools and complete-request estimates are separately in CSV.

| MCP tools | FULL estimate | LAZY estimate | Initial reduction | Repeats/mode |
|---|---:|---:|---:|---:|
| 10 | 703 | 323 | 54.05% | 5 |
| 25 | 1817 | 663 | 63.51% | 5 |
| 50 | 3640 | 1246 | 65.77% | 5 |
| 100 | 7377 | 2420 | 67.20% | 5 |

Token SD=0 for identical deterministic fixture/request schema content; five repeats test the serialization path, not independent statistical evidence about models. Schemas are synthetic copies of six production builtin definitions, not representative of real MCP marketplace schema sizes. The valid pre-change full baseline is separately preserved under results/raw/mcp-full-current/2026-09-06T07-32-04.514852900Z.

## Real model tool selection

Ten fixed service questions,100 synthetic tools including90 distractors; both modes use identical prompts/config and independently fresh Agents, pair order seeded20260905. True local MCP server validates actual selected tool/entity argument, then returns a fixed answer. Final answer must include that exact value and no unexpected remote call. These are real model calls to synthetic services, not live business endpoints.

| Mode | Task success | Correct selection | Median calls | Median Agent seconds | Median provider total tokens |
|---|---:|---:|---:|---:|---:|
| FULL | 10/10 | 10/10 | 2.0 | 5.43214955 | 8606.0 |
| LAZY | 10/10 | 10/10 | 3.0 | 4.697794099999999 | 7433.0 |

Paired mean extra model calls: 1.00; paired median latency difference LAZY−FULL: 0.02s.
Paired median total-schema reduction (sum of MCP/index tool-array estimates over all requests): 56.97%. This differs from both initial reduction and whole-task provider token usage.

Unique activated schema size, cumulative schema token cost, model calls, usage coverage, errors and raw paths are in the per-run CSV. Schema-only runs have no actual loading or task and must not be used for cumulative task-cost savings.

## Validation and limitations

- Full Gradle test passed195 tests across53 suites,0 failures/errors/skips; logs mcp-lazy-full-tests.txt/json. Unit tests cover activation, session isolation, mode filtering, malformed search and actual permission denial. The benchmark exercises real stdio SDK discovery/call and actual model HTTP serialization.
- No model sampling seed was set; fixture/order seed is not a model seed. Same model/config fields do not guarantee a fixed backend snapshot.
- Simple single-operation tasks, one run per task/mode. Even10/10 does not establish statistical noninferiority, robustness to malicious tool metadata or broad third-party coverage.
- Search is lexical, bounded to5 matches; a short index still grows linearly. Loaded schemas persist for the Agent lifetime, no eviction. Restart loses activation and requires rediscovery.
- Both model protocols share the catalog path; this real-model benchmark exercises Responses only. No Anthropic E2E result is implied.
- Raw failures are retained. Reported task success requires correctness, not just Agent completion. Null usage is not zero cost. No85% target or whole-task-token-saving claim.

## Reproduce

Run current benchmarks/run.ps1 compile using PowerShell7 (old Windows PowerShell may promote javac notes to errors); classpath is .work/classes-<first12 build-manifest SHA>; invoke bench.McpLazyBench schema or selection with -Dbench.root and -Dbench.harness.sha. selection makes paid model calls. Offline regenerate: python benchmarks/mcp-lazy-v1/summarize.py (bundled .work/python tiktoken dependency required). Preserve raw batch directories, build manifests and fixture files together.

## Resume wording

Describe the measured initial schema reduction only with the100-tool synthetic-fixture scope and tool-selection sample size. Do not substitute85%, generalize ten tasks to universal correctness, or describe this as reducing all task tokens.
