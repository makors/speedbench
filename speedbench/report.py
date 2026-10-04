"""Derive a static leaderboard from one immutable run, never example numbers."""
import csv
import hashlib
import json
from pathlib import Path
import shutil
import statistics

ROOT = Path(__file__).resolve().parents[1]
AGENTS = ["browser-use", "jev-ultrafast", "fastbrowse"]


def percentile(values, p):
    values = sorted(values)
    if not values:
        return None
    i = (len(values) - 1) * p
    low = int(i)
    high = min(low + 1, len(values) - 1)
    return values[low] + (values[high] - values[low]) * (i - low)


def summarize(rows, metadata, task_ids):
    keys = [(r["agent"], r["task_id"], r["repeat"]) for r in rows]
    if len(keys) != len(set(keys)):
        raise ValueError("Duplicate attempt identity; refusing a biased report")
    expected = {(a, t, r) for a in AGENTS for t in task_ids
                for r in range(1, metadata["repeats"] + 1)}
    full = set(keys) == expected and all(r.get("attempted") for r in rows)
    cap = metadata["timeout_seconds"]
    summaries = []
    for agent in AGENTS:
        selected = [r for r in rows if r["agent"] == agent]
        attempted = [r for r in selected if r.get("attempted")]
        passed = [r for r in attempted if r["passed"]]
        durations = [r["seconds"] for r in passed]
        if any(r["seconds"] is None or r["seconds"] < 0 for r in attempted):
            raise ValueError("An attempted run needs a nonnegative duration")
        scores = [min(r["seconds"], cap) if r["passed"] else cap for r in attempted]
        summaries.append({"agent": agent, "rank": None, "scheduled": len(selected),
            "attempted": len(attempted), "unavailable": len(selected) - len(attempted),
            "passed": len(passed), "success_rate": len(passed) / len(attempted) if attempted else None,
            "median_success_seconds": statistics.median(durations) if durations else None,
            "p95_success_seconds": percentile(durations, .95),
            "penalized_mean_seconds": statistics.mean(scores) if scores else None,
            "statuses": {s: sum(r["status"] == s for r in selected)
                         for s in ("passed", "failed", "timeout", "error", "unavailable")}})
    if full:
        summaries.sort(key=lambda r: (-r["passed"], r["penalized_mean_seconds"]))
        for i, row in enumerate(summaries):
            row["rank"] = i + 1
    return {"ranked": full, "summaries": summaries}


def build(run):
    metadata = json.loads((run / "manifest.json").read_text())
    task_file = run / "tasks.json" if (run / "tasks.json").exists() else ROOT / "tasks.json"
    tasks_doc = json.loads(task_file.read_text())
    if metadata["source_hashes"]["tasks.json"] != hashlib.sha256(task_file.read_bytes()).hexdigest():
        raise ValueError("Tasks do not match run manifest")
    rows = [json.loads(line) for line in (run / "results.jsonl").read_text().splitlines() if line]
    summary = summarize(rows, metadata, [t["id"] for t in tasks_doc["tasks"]])
    site = ROOT / "site"
    raw = site / "raw"
    if raw.exists():
        shutil.rmtree(raw)
    shutil.copytree(run, raw)
    for row in rows:
        row["artifact_url"] = "raw/attempts/" + Path(row["artifact_dir"]).name + "/"
    checksums = {str(p.relative_to(raw)): hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in sorted(raw.rglob("*")) if p.is_file()}
    (raw / "sha256.json").write_text(json.dumps(checksums, indent=2) + "\n")
    data = {"run_id": run.name, "manifest": metadata, "rows": rows, **summary,
            "notice": "Measured results" if summary["ranked"] else
            "Not ranked: the complete 50-task × 3-agent cohort has not been measured. Availability records are not timing results."}
    (site / "data.json").write_text(json.dumps(data, indent=2, default=str) + "\n")
    shutil.copyfile(task_file, site / "tasks.json")
    with (site / "results.csv").open("w", newline="") as file:
        columns = ["agent", "task_id", "category", "repeat", "status", "attempted", "passed", "seconds", "artifact_url"]
        writer = csv.DictWriter(file, columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(f"Report built: {site}; ranked={summary['ranked']}; {len(rows)} records")
