# Validation

Verified locally on macOS arm64 with Python 3.13.5 and Google Chrome 154.0.8037.98.

| Check | Result | What it establishes |
| --- | --- | --- |
| Offline harness tests | 12 passed | Objective grading, cohort accounting, redaction, real subprocess timing/deadline handling, real Chrome DOM/PNG capture |
| Pinned environment installs/imports | All three passed | Dependency compatibility in isolated locked environments |
| Offline adapter transport smoke | All three passed | Actual adapter constructors, dedicated Chrome connection, final tab observation, trace writing, and cleanup work with stubbed agent/model decisions |
| Live destination audit | 50/50 passed | Current targets and heading checks are reachable by the independent collector |
| Leaderboard UI | Search and combined agent filters passed | Generated data renders and can be inspected by task |
| JavaScript syntax | Passed | Static client parses |

The Browser Use smoke stubs `Agent.run`; the fastbrowse smoke stubs `Agent.run`; the Jev smoke stubs its decision function while exercising the upstream observation/action loop. They make no provider calls and are **not benchmark measurements**. Their artifacts are temporary and excluded from the leaderboard.

The initial target audit caught bot challenges on npm/PyPI and two unsuitable entity/heading definitions. The final v1 task list replaced those before any timed agent execution. Earlier target audits are retained as QA history. The latest [task-audit.json](task-audit.json) corresponds to the final task list; all 50 direct-target checks pass. This does not prove that agents can navigate from their start pages.

No credential-backed agent performance run has been executed. The published availability records prove only that the required provider keys were absent. Full runs remain necessary to verify provider behavior, agent completion rates, and performance.

To repeat the adapter smoke after bootstrap:

```sh
.runtimes/browser-use/.venv/bin/python tests/adapter_smoke.py browser-use
.runtimes/jev-ultrafast/.venv/bin/python tests/adapter_smoke.py jev-ultrafast
.runtimes/fastbrowse/.venv/bin/python tests/adapter_smoke.py fastbrowse
```
