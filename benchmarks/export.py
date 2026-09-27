"""Export shareable evidence only; never copy runtime databases or credentials."""
import argparse
import csv
import hashlib
import json
import platform
import shutil
import sqlite3
import subprocess
from collections import Counter
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def export(source, target, revision):
    target.mkdir(parents=True, exist_ok=True)
    records = []
    for result in sorted((source / "cases").glob("*/round-*/result.json")):
        folder = result.parent
        relative = folder.relative_to(source)
        destination = target / relative
        destination.mkdir(parents=True, exist_ok=True)
        raw = json.loads(result.read_text(encoding="utf-8"))
        evidence = []
        for name in ("result.json", "events.json", "tool-calls.json", "sources.json", "hashes.json", "answer.md", "hidden-result.txt", "evidence.json"):
            original = folder / name
            if original.exists():
                shutil.copy2(original, destination / name)
                evidence.append({"path": name, "sha256": digest(original)})
        if (folder / "artifacts").exists():
            shutil.copytree(folder / "artifacts", destination / "artifacts", dirs_exist_ok=True)
            evidence.extend({"path": p.relative_to(destination).as_posix(), "sha256": digest(p)} for p in (destination / "artifacts").rglob("*") if p.is_file())
        inputs, active, approvals, clarifications, known_input, known_output, complete = [], 0, 0, 0, 0, 0, True
        databases = list(folder.glob("**/state.sqlite3"))
        for database in databases:
            with sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True) as connection:
                connection.row_factory = sqlite3.Row
                tasks = connection.execute("SELECT id,prompt,scenario,checkpoint FROM tasks").fetchall()
                approvals += connection.execute("SELECT COUNT(*) FROM approvals").fetchone()[0]
                clarifications += connection.execute("SELECT COUNT(*) FROM events WHERE type='input_required'").fetchone()[0]
                for task in tasks:
                    checkpoint = json.loads(task["checkpoint"])
                    inputs.append({"task_id": task["id"], "prompt": task["prompt"], "scenario": task["scenario"]})
                    active += checkpoint.get("active_seconds", 0)
                    usage = checkpoint.get("usage", {})
                    complete = complete and usage.get("complete", False) and not checkpoint.get("usage_pending", False)
                    known_input += usage.get("input_tokens", 0)
                    known_output += usage.get("output_tokens", 0)
        dump(destination / "input.json", inputs)
        dump(destination / "evidence-index.json", evidence)
        if raw["result"] == "BLOCKED":
            complete = False
        record = {
            "run_id": source.name, "attempt_id": f"{source.name}-{raw['case']}-{raw['round']}",
            "case_id": raw["case"], "round": raw["round"], "status": raw["result"],
            "track": raw.get("track"), "model_id": raw.get("model"), "code_revision": revision,
            "assertions": raw.get("checks", {}), "evidence_path": relative.as_posix(),
            "wall_seconds": raw.get("duration_seconds"), "active_seconds": active if inputs else None,
            "wait_seconds": None, "timing_note": "Controller overhead/waits are not independently measured.",
            "input_tokens": known_input if complete else None, "output_tokens": known_output if complete else None,
            "known_input_tokens": known_input if inputs else None, "known_output_tokens": known_output if inputs else None,
            "usage_complete": bool(complete), "estimated_cost": None, "currency": None, "price_table_version": None,
            "tool_calls": raw.get("tool_calls"), "model_requests": raw.get("model_requests"), "automatic_retries": 0,
            "approval_count": approvals if inputs else None, "clarification_count": clarifications if inputs else None,
            "rescue_count": 0, "replacement_for": None,
            "failure_category": "ENVIRONMENT" if raw["result"] == "BLOCKED" else None,
            "error": raw.get("error") or raw.get("error_type"),
            "review": "Automatic checks only; see manual-review.jsonl for semantic review."
        }
        records.append(record)
    (target / "attempts.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")
    fields = ["attempt_id", "case_id", "round", "status", "wall_seconds", "active_seconds", "input_tokens", "output_tokens", "usage_complete", "tool_calls", "model_requests", "approval_count"]
    with (target / "matrix.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader(); writer.writerows(records)
    dump(target / "summary.json", {"release_gate": "INCOMPLETE", "planned_attempts": 60, "recorded_attempts": len(records), "counts": dict(Counter(r["status"] for r in records)), "rounds": {str(n): dict(Counter(r["status"] for r in records if r["round"] == n)) for n in (1, 2, 3)}})
    fixtures = [Path("benchmarks/fixtures.py"), Path("benchmarks/run.py"), Path("benchmarks/controls.py"), Path("benchmarks/crash_worker.py")]
    dump(target / "run-manifest.json", {"run_id": source.name, "code_revision": revision, "python": platform.python_version(), "os": platform.platform(), "fixture_hashes": {str(p): digest(p) for p in fixtures}, "model": "gpt-5.4-mini", "protocol": "openai-responses", "credentials": "Not exported; original explicit StarCode configuration reused.", "source_database_exported": False, "semantic_reviewer": "development assistant, not an independent human panel", "git_worktree_diff": "See reports/review-fixes.patch for final run based on d6911a6."})
    return records


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("target", type=Path)
    parser.add_argument("--revision", default="d6911a6+review-fixes")
    args = parser.parse_args()
    results = export(args.source, args.target, args.revision)
    print(json.dumps({"exported": len(results), "destination": str(args.target)}))
