# Feature parity acceptance and performance gate

Implement the four confirmed gaps without changing existing benchmark fixtures or replacing failures. Baseline production before this phase: ae10a0f47a216a3227371f24c12af1318d108726 (verified JAR); repository HEAD before edits:13997ac. The original benchmark-baseline-v1 remains untouched.

| Capability | Implementation acceptance | Remaining environment verification |
|---|---|---|
| Chat Completions | openai-compat config/client; text deltas, indexed tool fragments, canonical history/results, reasoning content, usage/cache breakdown, rate limits, truncation rejection; openai alias maps to Responses | Real compatible endpoint and provider-specific options after local gate |
| Checkpoints | Before each main turn; edit/write capture; persistence/resume; /rewind ID files/conversation/both; preflight external-edit conflicts; Worktree paths included | Full production session E2E on an unrestricted Windows test process |
| Cross-platform shell | PowerShell on Windows, Bash on Linux/macOS; command remains one argument | Actual Bash, timeout/cancellation and tool E2E on Linux/macOS |
| Optional sandbox | required mode; Linux bwrap/macOS sandbox-exec; no unsandboxed fallback; workspace/temp writable, other files read-only; network opt-in | Kernel write/network probes on both supported OSes; Windows must refuse required mode |

Sandbox scope is the bash tool subprocess. File reads are not restricted to the workspace. The main JVM, MCP servers, configured hooks and external Team backends are not contained by this wrapper. Do not claim whole-agent isolation or secret confidentiality. /rewind records dedicated file-tool content, not shell/external file edits; individual captured files are capped at16MiB. It does not restore long-term memory or undo arbitrary external side effects.

Validation order:
1. Full Gradle tests and source SHA256 manifest. No live performance experiment until this passes. run-validation.ps1 creates JSON and logs, never makes paid model calls, and only packages after tests pass when -Package is supplied.
2. Freeze production and harness commits; keep previous implementation results separate. Verify session/worktree/checkpoint E2E, both real protocol backends and OS-specific sandbox probes.
3. Matched fixed-input MCP FULL/LAZY cost measurement; report request/schema and cumulative billed usage separately. Keep tokenizer estimates distinct from provider usage.
4. Register eight independent coding tasks before running single/multi modes, three repeats each (48 episodes). Same task repository, model configuration, permission policy and unified tests. Main Agent performs decomposition/integration. Failures retain elapsed time/usage and do not enter successful-only speed averages without separate reporting. No target 60% result.
5. Long-context repeats with transport errors and interruptions retained, then real SWE-bench-Live environment gate. Never call synthetic gate cases SWE-bench results.

Performance and full parity remain NOT_VERIFIED until these gates complete. A mock protocol test is not evidence for every compatible provider, and a generated sandbox command is not a kernel-isolation measurement.
