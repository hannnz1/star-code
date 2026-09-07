"""Rebuild component-pilot reports from immutable raw files; no model calls."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("batch", type=Path)
parser.add_argument("--prefix", type=Path, required=True)
args = parser.parse_args()
load = lambda p: json.loads(p.read_text(encoding="utf-8-sig"))
runs, stages, failures = [], [], []
for run in sorted(args.batch.glob("run-*")):
    record = load(run / "run.json") if (run / "run.json").exists() else dict(
        run_id=run.name, implementation_commit=load(args.batch / "environment.json")["implementation_commit"],
        status="INCOMPLETE_NO_TERMINAL_RECORD", exception="No terminal run.json; inspect interruption observation and raw calls.",
        compactions=len(list(run.glob("stage-*/compact-*"))))
    calls = [load(p) for p in sorted((run / "calls").glob("*.json"))]
    diagnostics = [load(p) for p in run.glob("stage-*/compact-*/diagnostics.json")]
    row = {k: record.get(k) for k in ("run_id", "implementation_commit", "status", "exception",
           "compactions", "cumulative_new_tokens_estimated", "wall_clock_seconds")}
    row["model_calls"] = len(calls)
    row["calls_without_response"] = sum(not c.get("response_text") for c in calls)
    row["calls_without_terminal_status"] = sum(c.get("status") == "STARTED" for c in calls)
    row["usage_available_calls"] = sum(c.get("total_tokens") is not None for c in calls)
    for field in ("input_tokens", "output_tokens", "total_tokens"):
        row["known_" + field] = sum(c.get(field) or 0 for c in calls)
    row["compression_retries"] = sum(d.get("retryCount", 0) for d in diagnostics)
    row["successful_compactions"] = sum(d.get("finalStatus") == "SUCCESS" for d in diagnostics)
    runs.append(row)
    for stage in sorted(run.glob("stage-*")):
        if not (stage / "stage.json").exists():
            continue
        state = load(stage / "stage.json")
        for view in ("summary", "complete"):
            if not (stage / f"{view}-score.json").exists():
                failures.append(dict(run_id=record["run_id"], phase=state["phase"], view=view,
                                     key="PROBE_NOT_COMPLETED", expected="completed probe", actual=None))
                continue
            score = load(stage / f"{view}-score.json")
            stages.append(dict(run_id=record["run_id"], view=view, **state,
                               score_status=score["status"], passed=score["passed"], total=score["total"],
                               retention=score["passed"] / score["total"], exception=score.get("exception")))
            for field in score.get("fields", []):
                if not field["pass"]:
                    failures.append(dict(run_id=record["run_id"], phase=state["phase"], view=view, **field))

report = dict(environment=load(args.batch / "environment.json"), raw_batch=str(args.batch),
              completed_runs=sum(r["status"] == "COMPLETED_COMPONENT_WORKFLOW" for r in runs),
              attempted_runs=len(runs), runs=runs, stages=stages, retrieval_errors=failures,
              limitations=["Scripted production components, not autonomous coding or eight elapsed hours.",
                  "100K/200K/300K are cumulative new-history chars/3.5 estimates, not resident or provider tokens.",
                  "Repeated synthetic fixture; three sessions do not establish general retention reliability.",
                  "Strict typed structured-state retrieval, not semantic quality or independent human review.",
                  "A failed session contributes no later-stage score; missing stages are not silently successes.",
                  "Known usage sums exclude unavailable failed-call usage; such totals are lower bounds.",
                  "No speedup, historical-template improvement or eight-hour claim is measured."])
report["retrieval_by_view"] = {}
for view in ("summary", "complete"):
    subset = [s for s in stages if s["view"] == view]
    passed, total = sum(s["passed"] for s in subset), sum(s["total"] for s in subset)
    report["retrieval_by_view"][view] = dict(passed=passed, total=total,
                                               retention=passed / total if total else None)
args.prefix.parent.mkdir(parents=True, exist_ok=True)
def write(suffix, content):
    args.prefix.with_name(args.prefix.name + suffix).write_text(content, encoding="utf-8", newline="")
write(".json", json.dumps(report, indent=2, ensure_ascii=False) + "\n")
for name, rows in (("runs", runs), ("stages", stages)):
    with args.prefix.with_name(args.prefix.name + f"-{name}.csv").open("w", encoding="utf-8", newline="") as f:
        if rows:
            writer = csv.DictWriter(f, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
index = [dict(path=str(p.relative_to(args.batch)), bytes=p.stat().st_size,
              sha256=hashlib.sha256(p.read_bytes()).hexdigest())
         for p in sorted(args.batch.rglob("*")) if p.is_file()]
write("-artifact-index.json", json.dumps(index, indent=2) + "\n")
lines = ["# Long-context component pilot", "", f"Raw batch: `{args.batch}`", "",
         f"Workflow completed: {report['completed_runs']}/{len(runs)} sessions.", "",
         "| Run | Workflow | Compactions successful / attempted | Model calls | Known total tokens | Seconds |",
         "|---|---|---|---|---|---|"]
for r in runs:
    seconds = f"{r['wall_clock_seconds']:.2f}" if r['wall_clock_seconds'] is not None else "UNAVAILABLE"
    lines.append(f"| {r['run_id']} | {r['status']} | {r['successful_compactions']}/{r['compactions']} | "
                 f"{r['model_calls']} | {r['known_total_tokens']} | {seconds} |")
lines += ["", "## State retrieval (only stages reached)", "",
          "| Run | Cumulative estimate | View | Correct fields | Retention |", "|---|---|---|---|---|"]
for s in stages:
    lines.append(f"| {s['run_id']} | {s['cumulative_new_tokens_estimated']} | {s['view']} | "
                 f"{s['passed']}/{s['total']} | {s['retention']:.2%} |")
if not stages:
    lines.append("\nNo retrieval checkpoint reached; retention is NOT_MEASURED.")
lines += ["", "## Failures", ""]
lines += [f"- {r['run_id']}: {r['exception']}" for r in runs if r.get("exception")]
lines += [f"- {e['run_id']} phase {e['phase']} {e['view']} {e['key']}: "
          f"expected {e['expected']!r}, received {e['actual']!r}" for e in failures]
lines += ["", "## Limits", ""] + ["- " + s for s in report["limitations"]]
write(".md", "\n".join(lines) + "\n")
print(json.dumps(dict(completed=report["completed_runs"], attempted=len(runs),
                      retrieval=report["retrieval_by_view"])))
