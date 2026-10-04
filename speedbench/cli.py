"""Serial randomized runs with bounded wall time, isolated profiles, and audit logs."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import random
import signal
import subprocess
import sys
import time

from dotenv import load_dotenv
from speedbench.cdp import chrome_binary
from speedbench.grading import grade

ROOT = Path(__file__).resolve().parents[1]
AGENTS = ["browser-use", "jev-ultrafast", "fastbrowse"]
REQUIRED = {"browser-use": ["OPENAI_API_KEY"],
            "jev-ultrafast": ["TYPESAFE_API_KEY", "TEXT_MODEL_API_KEY"],
            "fastbrowse": ["OPENROUTER_API_KEY"]}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, data):
    path.write_text(json.dumps(data, indent=2, default=str) + "\n")


def secrets():
    return sorted({v for k, v in os.environ.items()
                   if any(word in k.upper() for word in ("KEY", "TOKEN", "SECRET", "PASSWORD"))
                   and len(v) > 5}, key=len, reverse=True)


def redact(value):
    for secret in secrets():
        value = value.replace(secret, "[REDACTED]")
    return value


def sanitize(directory):
    for path in directory.rglob("*"):
        if path.is_file() and path.suffix in {".json", ".jsonl", ".txt", ".log"}:
            path.write_text(redact(path.read_text()))


def runtime_python(agent):
    return ROOT / ".runtimes" / agent / ".venv" / "bin" / "python"


def blockers(agent):
    issues = [f"missing {key}" for key in REQUIRED[agent] if not os.environ.get(key)]
    if not runtime_python(agent).is_file():
        issues.append("runtime not installed; run scripts/bootstrap.py")
    if not chrome_binary():
        issues.append("Chrome not found; set SPEEDBENCH_CHROME")
    return issues


def manifest(args, suite):
    paths = [ROOT / "tasks.json", ROOT / "upstream.json", ROOT / "uv.lock"]
    paths += sorted((ROOT / "speedbench").glob("*.py"))
    paths += sorted((ROOT / "locks").glob("*.lock"))
    return {"schema_version": 1, "created_at": datetime.now(timezone.utc).isoformat(),
            "suite": suite["suite"], "task_count": len(suite["tasks"]),
            "repeats": args.repeats, "seed": args.seed, "timeout_seconds": args.timeout,
            "max_steps": args.max_steps, "agents": args.agents,
            "task_selection": args.task, "host": {"system": platform.system(),
            "release": platform.release(), "machine": platform.machine(),
            "python": platform.python_version(), "cpu_count": os.cpu_count()},
            "source_hashes": {str(p.relative_to(ROOT)): digest(p) for p in paths if p.exists()},
            "upstream": json.loads((ROOT / "upstream.json").read_text()),
            "credential_presence": {k: bool(os.environ.get(k)) for k in
                                    ("OPENAI_API_KEY", "OPENROUTER_API_KEY", "TYPESAFE_API_KEY",
                                     "TEXT_MODEL_API_KEY", "AI_GATEWAY_API_KEY")},
            "models": {k: os.environ.get(k, default) for k, default in {
                "SPEEDBENCH_BU_MODEL": "gpt-4.1-mini", "TYPESAFE_MODEL": "jev-latest",
                "TEXT_MODEL": "inception/mercury-2.5", "FASTBROWSE_LLM_MODEL": "google/gemini-3.8-flash",
                "FASTBROWSE_JEV_MODEL": "upstream default", "FASTBROWSE_JEV_SOURCE": "automatic"}.items()},
            "timing": "Supervisor monotonic clock: worker launch through Chrome startup, agent execution, independent DOM/screenshot evidence, browser shutdown, and objective grading. Installs and report rendering excluded.",
            "isolation": "Sequential; fresh Chrome process and profile for each attempt. Headless 1120x780. No benchmark-level retries."}


def attempt(agent, task, repetition, position, run, timeout, max_steps):
    directory = run / "attempts" / f"{position:04d}-{agent}-{task['id']}-r{repetition}"
    directory.mkdir(parents=True)
    row = {"agent": agent, "task_id": task["id"], "category": task["category"],
           "repeat": repetition, "position": position,
           "artifact_dir": str(directory.relative_to(ROOT)),
           "started_at": datetime.now(timezone.utc).isoformat(), "passed": False}
    problems = blockers(agent)
    if problems:
        row.update(status="unavailable", attempted=False, seconds=None, reasons=problems)
        save(directory / "preflight.json", row)
        return row
    # No expectations or target_url are made available to the agent subprocess.
    public_task = {k: task[k] for k in ("id", "category", "start_url", "goal")}
    input_file = directory / "input.json"
    save(input_file, public_task)
    env = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONUNBUFFERED="1",
               ANONYMIZED_TELEMETRY="false", BROWSER_USE_TELEMETRY="false")
    command = [str(runtime_python(agent)), "-m", "speedbench.worker", agent,
               str(input_file), str(directory), str(max_steps)]
    started = time.perf_counter()
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               env=env, cwd=ROOT, start_new_session=True)
    row["attempted"] = True
    try:
        stdout, stderr = process.communicate(timeout=timeout)
        row["exit_code"] = process.returncode
        worker_path = directory / "worker.json"
        worker = json.loads(worker_path.read_text()) if worker_path.exists() else {}
        row["worker"] = worker
        if process.returncode == 0 and worker.get("status") == "completed":
            page = json.loads((directory / "page.json").read_text())
            outcome = grade(task, page)
            row.update(outcome)
            row["status"] = "passed" if outcome["passed"] else "failed"
        else:
            row["status"] = "error"
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        stdout, stderr = process.communicate()
        row["status"] = "timeout"
    except Exception as exc:
        row.update(status="error", error=f"{type(exc).__name__}: {exc}")
        stdout, stderr = b"", b""
    row["seconds"] = time.perf_counter() - started
    directory.joinpath("stdout.log").write_text(redact(stdout.decode(errors="replace")))
    directory.joinpath("stderr.log").write_text(redact(stderr.decode(errors="replace")))
    save(directory / "result.json", row)
    sanitize(directory)
    return json.loads(redact(json.dumps(row)))


def run(args):
    suite = json.loads((ROOT / "tasks.json").read_text())
    tasks = suite["tasks"]
    if args.task:
        tasks = [t for t in tasks if t["id"] in args.task]
        if len(tasks) != len(set(args.task)):
            raise SystemExit("Unknown or duplicate --task selection")
    run_id = args.run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    if not run_id.replace("-", "").replace(".", "").replace("_", "").isalnum():
        raise SystemExit("run-id must be a simple identifier")
    output = ROOT / "results" / run_id
    output.mkdir(parents=True, exist_ok=False)
    metadata = manifest(args, suite)
    metadata["selected_tasks"] = [t["id"] for t in tasks]
    save(output / "manifest.json", metadata)
    # A report can always use this exact suite, even if a later revision changes tasks.
    save(output / "tasks.json", suite)
    rng = random.Random(args.seed)
    rng.shuffle(tasks)
    jobs = []
    for repetition in range(1, args.repeats + 1):
        for task in tasks:
            order = list(args.agents)
            rng.shuffle(order)
            jobs.extend((agent, task, repetition) for agent in order)
    save(output / "schedule.json", [{"agent": a, "task_id": t["id"], "repeat": r}
                                    for a, t, r in jobs])
    for i, (agent, task, repetition) in enumerate(jobs, 1):
        row = attempt(agent, task, repetition, i, output, args.timeout, args.max_steps)
        with (output / "results.jsonl").open("a") as log:
            log.write(json.dumps(row, default=str) + "\n")
        print(f"[{i}/{len(jobs)}] {agent} {task['id']}: {row['status']}"
              + (f" ({row['seconds']:.2f}s)" if row["seconds"] is not None else ""), flush=True)
    print(f"Run saved: {output}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, help="Local credentials; never copied into output")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="Read-only credential/runtime availability check")
    cmd = sub.add_parser("run")
    cmd.add_argument("--agents", nargs="+", choices=AGENTS, default=AGENTS)
    cmd.add_argument("--repeats", type=int, default=1)
    cmd.add_argument("--timeout", type=float, default=180)
    cmd.add_argument("--max-steps", type=int, default=60)
    cmd.add_argument("--seed", type=int, default=1729)
    cmd.add_argument("--run-id")
    cmd.add_argument("--task", action="append", help="Exact task id; repeat for a subset")
    report = sub.add_parser("report")
    report.add_argument("run", type=Path)
    args = parser.parse_args()
    load_dotenv(args.env_file or ROOT / ".env", override=False)
    if args.command == "doctor":
        report = {a: {"ready": not blockers(a), "blockers": blockers(a)} for a in AGENTS}
        print(json.dumps(report, indent=2))
        return
    if args.command == "report":
        from speedbench.report import build
        build(args.run.resolve())
        return
    if args.repeats < 1 or args.timeout <= 0 or args.max_steps < 1 or len(set(args.agents)) != len(args.agents):
        parser.error("positive limits and distinct agents required")
    run(args)


if __name__ == "__main__":
    main()
