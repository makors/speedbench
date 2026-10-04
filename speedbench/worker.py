"""One real agent per subprocess; private grader expectations never enter its prompt."""
import asyncio
import importlib.metadata
import json
import os
from pathlib import Path
import sys
import time
import traceback

from speedbench.cdp import Chrome


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2, default=str) + "\n")


async def browser_use(chrome, task, directory, max_steps):
    from browser_use import Agent, Browser, ChatOpenAI
    browser = Browser(cdp_url=chrome.endpoint, keep_alive=True,
                      viewport={"width": 1120, "height": 780})
    model = os.environ.get("SPEEDBENCH_BU_MODEL", "gpt-4.1-mini")
    agent = Agent(task=f"Start at {task['start_url']}. {task['goal']}",
                  llm=ChatOpenAI(model=model), browser=browser,
                  generate_gif=False)
    try:
        history = await agent.run(max_steps=max_steps)
        history.save_to_file(str(directory / "trace.json"))
        agent_end = time.perf_counter()
        page = await browser.must_get_current_page()
        chrome.cdp.capture(page._target_id, directory)
        return {"agent_status": "done" if history.is_done() else "step_limit",
                "model": model, "answer": history.final_result(), "agent_end": agent_end}
    finally:
        # Explicitly release CDP/event-bus tasks before asyncio.run cancels them;
        # reconnect handlers otherwise keep the worker alive after a finished run.
        await browser.kill()


def jev(chrome, task, directory, max_steps):
    # Upstream uses Browser Harness for transport. Swap only its two transport
    # entry points so all competitors get the same fresh isolated Chrome.
    import jev_ultrafast.browser as transport
    from jev_ultrafast import Agent
    transport.ensure_daemon = lambda: None
    transport.cdp = chrome.cdp.call
    with Agent(task["start_url"], task["goal"], screenshots=False) as agent:
        for state in agent.run():
            with (directory / "steps.jsonl").open("a") as log:
                log.write(json.dumps(state, default=str) + "\n")
            if len(state["history"]) >= max_steps or len(state["decisions"]) >= max_steps * 2:
                break
        agent_end = time.perf_counter()
        write_json(directory / "trace.json", agent.snapshot())
        chrome.cdp.capture(agent.browser.target, directory)
        return {"agent_status": agent.state["status"], "agent_end": agent_end,
                "model": os.environ.get("TYPESAFE_MODEL", "jev-latest"),
                "text_model": os.environ.get("TEXT_MODEL", "inception/mercury-2.5")}


async def fastbrowse(chrome, task, directory, max_steps):
    import httpx
    from fastbrowse.agent import Agent
    from fastbrowse.artifacts import DirectorySink
    from fastbrowse.browser import BrowserSession, CdpPage
    from fastbrowse.clients.environment import load_settings
    from fastbrowse.config import Config
    from fastbrowse.models import BrowserConnection, Limits
    config = Config()
    settings = load_settings()
    async def event(value):
        with (directory / "steps.jsonl").open("a") as log:
            log.write(value.model_dump_json() + "\n")
    async with httpx.AsyncClient(timeout=60) as http:
        async with BrowserSession(BrowserConnection(cdp_url=chrome.endpoint, remote=False),
                                  DirectorySink(directory / "artifacts")) as session:
            agent = Agent(CdpPage(session, config), settings.jev(http), settings.llm(http),
                          config=config, on_event=event)
            result = await agent.run(task["goal"], start=task["start_url"],
                                     limits=Limits(max_steps=max_steps))
            agent_end = time.perf_counter()
            write_json(directory / "trace.json", result.model_dump(mode="json"))
            chrome.cdp.capture(session.active_target_id, directory)
            return {"agent_status": str(result.status), "agent_end": agent_end,
                    "model": settings.models(), "cost": result.cost.model_dump(mode="json")}


def main():
    agent_name, task_file, output, steps = sys.argv[1:]
    task = json.loads(Path(task_file).read_text())
    directory = Path(output)
    began = time.perf_counter()
    result = {"agent": agent_name, "task_id": task["id"], "status": "error"}
    try:
        with Chrome() as chrome:
            result["chrome"] = chrome.version
            result["package_version"] = importlib.metadata.version(agent_name)
            if agent_name == "jev-ultrafast":
                info = jev(chrome, task, directory, int(steps))
            else:
                fn = browser_use if agent_name == "browser-use" else fastbrowse
                info = asyncio.run(fn(chrome, task, directory, int(steps)))
            result.update(info)
            result["agent_seconds"] = result.pop("agent_end") - began
            result["status"] = "completed"
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        traceback.print_exc()
    finally:
        result["worker_seconds"] = time.perf_counter() - began
        write_json(directory / "worker.json", result)


if __name__ == "__main__":
    main()
