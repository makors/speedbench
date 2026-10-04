# Methodology — live-navigation-50-v1

## Scope and originality

Fifty prompts were authored for SpeedBench. No upstream eval prompts or published timing records were imported. Each of ten sites contributes five navigation goals: Wikipedia, Python documentation, MDN, NumPy documentation, GitHub, Books to Scrape, Quotes to Scrape, arXiv, Django documentation, and Rust documentation. Goal wording identifies an entity rather than disclosing its grading URL. The navigation can involve search, category navigation, pagination, or reference links; direct address navigation is also allowed. This suite measures arrival at the requested page, not the navigation strategy.

This is a navigation benchmark. It does not measure purchase completion, form submission, answer quality, structured extraction, authenticated sessions, general web workflows, or safety gates. Repeated tasks on the same site are correlated. A large variety of sites would be needed for broad browser-agent claims.

## Execution protocol

The pinned open-source Python implementation is used for each competitor. Browser Use is the local Python agent rather than its hosted-agent product. Code and transitive dependencies are pinned independently. Default model stacks differ intentionally; results compare configured systems, not a common policy under a common model. Jev aliases and other provider model names can change remotely despite code pins. Provider routing/retries and helper defaults remain those of the pinned upstream code and are not standardized by this harness.

Each job starts a new worker and a new Chrome process/profile. Chrome is headless with an 1120×780 window. Browser Use and Jev explicitly receive that viewport; fastbrowse retains upstream handling. The OS, machine architecture, Python version, and actual Chrome product version are recorded. Browser Use can configure screenshots differently from the two Jev systems; the public manifest makes the implementation identities and settings inspectable.

The same natural-language goal and start page are supplied to each agent. The worker input excludes target URLs and expected headings. The agents are ordinary Python libraries in the benchmark checkout, not sandboxed adversaries; this is not a security claim that they cannot inspect local files.

The supervisor shuffles task order and agent order within each task/repetition using a recorded seed. It runs jobs sequentially to avoid resource contention. There is no benchmark retry. Upstream provider retries remain part of elapsed time. One full repetition schedules 150 jobs. Three or more full repetitions are recommended. All jobs and their exact positions are recorded before execution.

## Adapter boundaries

Browser Use uses `Agent`, `Browser(cdp_url=...)`, and `ChatOpenAI`. History is saved before independent collection, using the focused page’s target ID. fastbrowse assembles the same public `Agent`, `BrowserSession`, `CdpPage`, and environment clients used by its own eval runner, permitting observation before the owned tab closes. Events and the returned result are saved.

jev-ultrafast exposes no CDP endpoint argument. Its imported Browser transport’s `ensure_daemon` and `cdp` functions are replaced with a no-op daemon initializer and a direct synchronous CDP connection to the dedicated Chrome. Its DOM snapshot, action policy, TypeSafe requests, text helper, freshness checks, and action execution remain upstream. This removes Browser Harness daemon startup and profile reuse from Jev’s path; that transport adaptation is a material comparison limitation. There is no site-specific policy patch.

## Timing and deadlines

The primary measurement uses the supervisor’s `perf_counter`, beginning immediately before worker `Popen` and ending after the worker returns and the independent grade has been computed. The worker runs imports, starts Chrome, runs the agent, saves trace data, independently collects DOM/headings/PNG, closes Chrome, and writes its final result. Process startup, cold Python imports, browser startup, initial navigation, waits, provider retries, evidence I/O, and teardown count. Log redaction and report generation follow the clock and are excluded. This boundary deliberately differs from upstream demo timings that begin after initial observation.

Secondary worker and agent durations are retained for diagnosis. The worker’s `agent_seconds` starts before Chrome startup and ends at the agent’s final state before final independent evidence capture. It is not the leaderboard metric.

The common external wall deadline defaults to 180 seconds. On timeout, the supervisor kills the worker process group, including its Chrome subprocess, and retains captured output. The measured timeout includes small process-kill/collection overhead and can exceed 180 seconds. All attempted failures receive exactly the cap in the penalized score, regardless of how quickly they fail. Browser Use and fastbrowse receive a 60-step limit; Jev is capped at 60 history actions or 120 decisions, preserving upstream stale-decision handling. A wall limit bounds all cases; step definitions differ across projects.

## Independent success checks

After agent execution, a separate CDP connection reads the active final tab. The collector reads the current URL, document title/readiness, visible `h1`/`h2`/`h3` headings, and rendered body text, then captures a PNG. A heading can be outside the viewport but must pass the browser’s CSS visibility check. CSS-visible here does not mean physically unobscured. Frames and closed shadow roots are not searched.

A task passes only if its final URL matches its anchored pattern, a visible semantic heading matches its case-insensitive pattern, and `document.readyState` is `complete`. URL matching allows trailing slash, fragments, and query strings, and arXiv version suffixes. Targets are fixed entities rather than mutable values such as package versions or GitHub stars. Agent output or a DONE operation has no weight in the grade. A final correct page passes even when the agent stops at its action limit. Collection failures are errors. Bot challenges cannot pass unless they somehow reproduce both the expected URL and heading.

Target audits visit known grading URLs directly. They help detect invalid routes and unexpected headings and are never benchmark attempts. External site outages and blocking may affect both the audit and actual agent runs. A blocked target is disclosed, not replaced after seeing agent scores.

## Reporting and missingness

Success rate is passed/attempted. Timeouts, agent errors, and grading failures count in attempted. Preflight missing-key/runtime/browser records have `attempted=false`, `seconds=null`, and status `unavailable`; they are displayed separately and excluded from attempted counts.

Successful-run median and linear-interpolated P95 describe passes only. Penalized mean assigns each attempted failure the wall cap, and each success its measured duration clipped to that cap. This clipping can slightly reduce the score of a successful run whose supervisor collection runs past the cap. Actual recorded durations remain available. Ranking orders success count descending, then penalized mean ascending, and appears only for every expected task/agent/repetition with no unavailable jobs. A missing or duplicate pair prevents ranking. Equal scores currently receive deterministic sequential ranks; do not interpret such a tie as a measured advantage.

No confidence intervals or statistical-significance claims are produced. Site clustering, temporal drift, provider conditions, unequal helper models, and single-machine results limit generalization. Model cost is not ranked: fastbrowse exposes a breakdown, while complete comparable billing telemetry for all systems is not available. Missing cost remains unknown.

## Reproducibility and evidence

Each run has a UTC timestamp, immutable upstream commits, file hashes for task definitions/harness/locks, a seeded schedule, host metadata, model configuration, and agent versions. Each attempted job retains result/worker records, stdout/stderr, upstream trace, and any available DOM/PNG evidence. Completed tasks have final evidence; timeout/error jobs may have only partial logs. The static report copies the selected run and produces SHA-256 checksums and CSV. Older runs remain under `results/`; the leaderboard uses exactly one selected run.

Text artifacts are redacted against key-like values present in the environment. Credential files and agent runtime directories are ignored. This is best-effort redaction; review provider traces before adding new authenticated tasks or publishing logs. The current suite supplies no secrets to pages.

## Current publication

The initial publication is an availability report, not a measured cohort. Required provider credentials were absent. There are 150 `unavailable` preflight records, zero timed agent attempts, and no ranking. Local Chrome evidence tests and direct-target audits are separately labeled QA. Complete credential-backed agent execution remains necessary before publishing performance conclusions.
