# Current production Multi-Agent feasibility gate

Recorded before the first current-production model run. Reuse the frozen checkout fixture and GateBench instrumentation from the initial benchmark. GateCurrent records the actual committed production revision and build hashes; it does not bypass the original baseline harness guard.

The Main Agent reads the two-component checkout contract and chooses its own decomposition. Production Team tools must create at least two independent Worktrees, execute Sub-Agents with a positive observed overlap, return results, and integrate both modified components into the main checkout. The Main Agent must run the unified verifier. The harness independently runs the same unchanged verifier afterwards and preserves transcripts, lifecycle, diffs and outputs. DONE alone is insufficient. The harness never merges or assigns component subtasks.

Use the inherited gpt-5.4-mini / Responses configuration; fixture seed20260905, model seed unset. Isolate home, memory and permissions in the synthetic fixture repository. Existing production iteration limits remain unchanged. Wall-clock limit12 minutes. This is a feasibility test, not a speed comparison.

If any required condition fails, preserve the attempt as BLOCKED, inspect the precise cause, and stop speedup experiments. A successful first case still requires at least two additional fixed, distinct contracts before a speed benchmark can be considered. Any production fix receives its own commit and subsequent attempts are explicitly post-fix, never substituted for this result.

Reproduction: compile with benchmarks/run.ps1 compile in PowerShell7, then invoke bench.GateCurrent with bench.root, bench.harness.sha, the generated classes directory and dependency JAR. Requires configured model credentials; requests contain only the synthetic fixture and production prompts. Raw is under results/raw/multi-agent-current, with the current pointer in results/multi-agent-current-latest.txt.
