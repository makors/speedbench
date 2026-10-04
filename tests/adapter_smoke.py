"""Offline transport smoke: real pinned libraries and Chrome, stubbed model/agent decisions.

Not performance data. Run with each competitor's isolated interpreter.
"""
import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from speedbench.cdp import Chrome
from speedbench.worker import browser_use, fastbrowse, jev


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(b'<h1>Finish</h1>' if self.path == '/finish' else
                        b'<h1>Start</h1><a href="/finish">Open finish</a>')
    def log_message(self, *_):
        pass


name = sys.argv[1]
server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
start = f"http://127.0.0.1:{server.server_port}/"
task = {"id": "offline-fixture", "start_url": start, "goal": "Open finish"}
os.environ.update(OPENAI_API_KEY="offline-test-key", OPENROUTER_API_KEY="offline-test-key",
                  ANONYMIZED_TELEMETRY="false", BROWSER_USE_TELEMETRY="false")
try:
    with tempfile.TemporaryDirectory() as folder, Chrome() as chrome:
        directory = Path(folder)
        if name == "jev-ultrafast":
            def choose(page, goal, history):
                action = next((a for a in page["actions"] if a["kind"] == "click" and "Open finish" in a["label"]), None)
                selected = action["id"] if action else "DONE"
                return {"choice": selected, "probabilities": {selected: 1.0}, "confidence": 1.0,
                        "latency_ms": 0, "operation": "CLICK" if action else "DONE",
                        "target": None, "usage": {}}
            with patch("jev_ultrafast.agent.choose", side_effect=choose):
                info = jev(chrome, task, directory, 10)
        elif name == "browser-use":
            class History:
                def save_to_file(self, path):
                    Path(path).write_text('{"kind":"offline_stub"}')
                def is_done(self):
                    return True
                def final_result(self):
                    return "offline smoke only"
            async def fake_run(self, **kwargs):
                await self.browser_session.start()
                page = await self.browser_session.must_get_current_page()
                await page.goto(start + "finish")
                return History()
            with patch("browser_use.Agent.run", new=fake_run):
                info = asyncio.run(browser_use(chrome, task, directory, 10))
        elif name == "fastbrowse":
            from fastbrowse.clients.environment import Settings
            from fastbrowse.models import CostBreakdown, RunResult, Status
            from pydantic import SecretStr
            settings = Settings(openrouter_api_key=SecretStr("offline-test-key"))
            async def fake_run(self, *args, **kwargs):
                await self._page.navigate(start + "finish")
                return RunResult(status=Status.COMPLETE, answer=None, data=None,
                                 evidence=(), steps=(), cost=CostBreakdown(lines=()), artifacts=())
            with patch("fastbrowse.agent.Agent.run", new=fake_run), \
                 patch("fastbrowse.clients.environment.load_settings", return_value=settings):
                info = asyncio.run(fastbrowse(chrome, task, directory, 10))
        else:
            raise ValueError(name)
        page = json.loads((directory / "page.json").read_text())
        assert page["url"] == start + "finish", page
        assert "Finish" in page["headings"], page
        assert (directory / "trace.json").exists()
        assert (directory / "final.png").read_bytes().startswith(b'\x89PNG')
        print(name, "offline adapter transport smoke passed")
finally:
    server.shutdown()
    server.server_close()
