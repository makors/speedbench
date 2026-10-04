# SpeedBench

An auditable end-to-end comparison of **Browser Use**, **jev-ultrafast**, and **fastbrowse** on **50 original live-web navigation tasks**. The suite visits ten websites, with five goals per website. It measures the declared agent stacks, including their different models.

**[Published leaderboard](https://makors.github.io/speedbench/)** · [Tasks](tasks.json) · [Methodology](docs/METHODOLOGY.md) · [Pinned upstream builds](upstream.json)

## Current result status

**No agent timings have been measured yet.** Provider credentials were unavailable in the build environment. The first published run contains 150 genuine availability checks, each labeled `unavailable`, with null timings. Those records are not agent runs, successes, failures, or a speed comparison. The page therefore publishes no rank or winner.

All three pinned agent environments have been installed and their imports checked. Offline harness tests include a real Chrome evidence capture and real subprocess success/timeout handling. These tests validate infrastructure; they do not establish that any competitor completed the live suite. The target audit in [docs/task-audit.json](docs/task-audit.json) is also infrastructure QA, not agent results.

## Run it

Requires macOS or Linux, [uv](https://docs.astral.sh/uv/), and Google Chrome or Chromium. Python 3.13 is downloaded by uv when necessary. Windows subprocess-group cleanup is not supported by this version.

```sh
git clone https://github.com/makors/speedbench.git
cd speedbench
uv sync --frozen --python 3.13
uv run python scripts/bootstrap.py
cp .env.example .env
# Configure provider keys locally, then:
uv run speedbench doctor
uv run speedbench run --repeats 1 --run-id first-measured-run
uv run speedbench report results/first-measured-run
python3 -m http.server 8080 --directory site
```

The bootstrap installs each agent from its immutable upstream Git commit in a separate `.runtimes/<agent>` environment, using committed transitive lockfiles. No agent policy code is copied into this repo. Installs occur before timing begins. Model calls incur provider charges when credentials are configured.

Required configuration:

| Agent | Required keys | Declared default stack |
| --- | --- | --- |
| Browser Use open-source Python agent | `OPENAI_API_KEY` | `gpt-4.1-mini` |
| jev-ultrafast | `TYPESAFE_API_KEY`, `TEXT_MODEL_API_KEY` | `jev-latest`, `inception/mercury-2.5` via OpenRouter |
| fastbrowse | `OPENROUTER_API_KEY` | Upstream Jev routing; `google/gemini-3.8-flash` main LLM, upstream helper models |

`TEXT_MODEL_API_KEY` can contain the same locally configured OpenRouter key used for fastbrowse. To use an existing credential file without copying it:

```sh
uv run speedbench --env-file /absolute/path/to/credentials.env doctor
uv run speedbench --env-file /absolute/path/to/credentials.env run --repeats 3
```

Real environment variables take precedence over `.env`. The harness never stores the credential file path in its run manifest. `SPEEDBENCH_CHROME` chooses a custom Chrome binary. `SPEEDBENCH_BU_MODEL`, `TYPESAFE_MODEL`, `TEXT_MODEL`, and `FASTBROWSE_LLM_MODEL` are configurable and recorded; model aliases may drift even when code is pinned.

For a limited pilot, use exact task IDs:

```sh
uv run speedbench run --task 26-travel-books --task 31-einstein --timeout 180
```

Pilot runs remain unranked. Use at least three complete repetitions before making a robust performance claim. Every repetition preserves every failure; there is no retry selection.

## What gets timed and recorded

The supervisor starts a monotonic wall clock before launching the worker and stops after independent grading. This includes Python imports, fresh headless Chrome startup, initial navigation, agent/model work, raw trace writing, final DOM and screenshot capture, and Chrome shutdown. Installs and leaderboard rendering are excluded. The default cap is 180 seconds per attempt, with a common 60-action step cap; an external timeout kills the entire worker/Chrome process group.

Every attempt has stdout/stderr, a result record, and, when execution completes, an agent trace, final page observation, and PNG screenshot. Unavailable attempts have a preflight record only. SHA-256 indexes accompany the published raw artifacts. Key-like environment values are scrubbed from text logs; these tasks never involve sign-in or typing secrets.

Success requires both a matching final URL and a visible matching heading in a fully loaded document, independently observed through CDP. Agent “done” text is not used as the grader. A correct final state can pass even if the agent reaches its step budget rather than saying done.

The report shows success rate, successful-run median/P95, and a penalized mean: successful durations clipped to the cap; every attempted failure assigned the cap. Rank is success count first, penalized mean second. A rank appears only for a complete matched 50-task cohort across all three agents. Unavailable attempts never get synthetic timings or enter an attempt denominator.

## Verification and publication

```sh
uv run python -m unittest discover -s tests -v
node --check site/app.js
uv run python scripts/audit_tasks.py docs/task-audit.json
```

The target audit opens expected destinations directly to check task references and grading. It is explicitly excluded from agent performance data. Some live sites may block headless browsers, alter content, or become unavailable; record these conditions rather than deleting inconvenient runs.

GitHub Actions checks the harness offline and publishes `site/` to GitHub Pages on pushes to `main`. To publish newly measured data, regenerate the report, review logs, commit `results/` and `site/`, then push. The public page links the raw manifest, JSONL, CSV, checksums, and per-attempt evidence. Nothing on the page is backed by sample numbers.

## Layout

| Path | Purpose |
| --- | --- |
| `tasks.json` | Original 50 prompts and deterministic graders |
| `speedbench/cli.py` | Scheduling, preflight, timing, deadlines, redaction |
| `speedbench/worker.py` | Real upstream adapters |
| `speedbench/cdp.py` | Shared isolated Chrome and independent evidence |
| `locks/` | Agent-specific full dependency locks |
| `results/` | Immutable run directories and raw artifacts |
| `site/` | Static, generated leaderboard and copied raw evidence |

MIT licensed. Upstream projects retain their own licenses. This benchmark is independently authored and is not affiliated with the three agent projects.
