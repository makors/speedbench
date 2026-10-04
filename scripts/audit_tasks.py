"""Visit grading targets directly to audit the suite. Never an agent measurement."""
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from speedbench.cdp import Chrome, OBSERVE
from speedbench.grading import grade

root = Path(__file__).resolve().parents[1]
output = Path(sys.argv[1]) if len(sys.argv) > 1 else root / "work/task-audit.json"
output.parent.mkdir(parents=True, exist_ok=True)
tasks = json.loads((root / "tasks.json").read_text())["tasks"]
audit = {"kind": "suite_target_audit_not_agent_results", "records": []}
with Chrome() as chrome:
    audit["chrome"] = chrome.version
    target = chrome.cdp.call("Target.createTarget", url="about:blank")["targetId"]
    session = chrome.cdp.call("Target.attachToTarget", targetId=target, flatten=True)["sessionId"]
    chrome.cdp.call("Page.enable", session_id=session)
    for task in tasks:
        record = {"task_id": task["id"], "target_url": task["target_url"]}
        try:
            chrome.cdp.call("Page.navigate", session_id=session, url=task["target_url"])
            deadline = time.monotonic() + 12
            page = {}
            while time.monotonic() < deadline:
                try:
                    response = chrome.cdp.call("Runtime.evaluate", session_id=session,
                                               expression=OBSERVE, returnByValue=True)
                    page = json.loads(response["result"]["value"])
                    if page.get("ready") == "complete" and page.get("url") != "about:blank":
                        break
                except (KeyError, ValueError):
                    pass
                time.sleep(.15)
            record.update(grade(task, page), url=page.get("url"), title=page.get("title"),
                          headings=page.get("headings", []))
        except Exception as exc:
            record.update(passed=False, error=f"{type(exc).__name__}: {exc}")
        audit["records"].append(record)
        output.write_text(json.dumps(audit, indent=2) + "\n")
        print(task["id"], record["passed"], record.get("url"), flush=True)
print(f"Target checks: {sum(r['passed'] for r in audit['records'])}/{len(tasks)}")
