import contextlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from speedbench.cdp import Chrome, chrome_binary
from speedbench.cli import attempt, redact
from speedbench.grading import grade
from speedbench.report import summarize

ROOT = Path(__file__).resolve().parents[1]
TASK = {"id": "test", "category": "fixture", "start_url": "http://example.test/",
        "goal": "Open the target page", "expected": {
            "url_regex": r"^http://example\.test/target/?$", "heading_regex": "Target page"}}


class GraderTests(unittest.TestCase):
    def test_original_suite_is_50_distinct_tasks_on_ten_sites(self):
        tasks = json.loads((ROOT / "tasks.json").read_text())["tasks"]
        self.assertEqual(len(tasks), 50)
        self.assertEqual(len({t["id"] for t in tasks}), 50)
        self.assertEqual(len({t["goal"] for t in tasks}), 50)
        self.assertEqual(len({t["category"] for t in tasks}), 10)
        for task in tasks:
            self.assertTrue(re.search(task["expected"]["url_regex"], task["target_url"]))

    def test_done_does_not_prove_success(self):
        self.assertFalse(grade(TASK, {"url": "http://example.test/target", "ready": "complete",
                                    "headings": ["Agent said done"]})["passed"])

    def test_url_and_heading_and_loaded_document_required(self):
        page = {"url": "http://example.test/target", "headings": ["Target page"], "ready": "complete"}
        self.assertTrue(grade(TASK, page)["passed"])
        for key, value in [("url", "http://evil.test/target"), ("ready", "loading"), ("headings", [])]:
            self.assertFalse(grade(TASK, {**page, key: value})["passed"])

    def test_lookalike_host_and_descendant_do_not_match(self):
        for url in ["http://example.test.evil/target", "http://example.test/target/other"]:
            self.assertFalse(grade(TASK, {"url": url, "ready": "complete", "headings": ["Target page"]})["passed"])


class ReportTests(unittest.TestCase):
    def row(self, agent, task="test", passed=True, seconds=4, attempted=True):
        return {"agent": agent, "task_id": task, "repeat": 1, "passed": passed,
                "seconds": seconds if attempted else None, "attempted": attempted,
                "status": "passed" if passed else "failed" if attempted else "unavailable"}

    def test_missing_credentials_never_become_zero_second_scores(self):
        row = self.row("fastbrowse", passed=False, attempted=False)
        report = summarize([row], {"timeout_seconds": 180, "repeats": 1}, ["test"])
        self.assertFalse(report["ranked"])
        fast = report["summaries"][2]
        self.assertIsNone(fast["success_rate"])
        self.assertIsNone(fast["penalized_mean_seconds"])

    def test_failures_count_and_receive_full_cap(self):
        rows = [self.row("fastbrowse"), self.row("fastbrowse", task="other", passed=False, seconds=1)]
        report = summarize(rows, {"timeout_seconds": 180, "repeats": 1}, ["test", "other"])
        fast = report["summaries"][2]
        self.assertEqual(fast["success_rate"], .5)
        self.assertEqual(fast["penalized_mean_seconds"], 92)
        self.assertEqual(fast["median_success_seconds"], 4)

    def test_complete_cohort_ranks_by_success_then_penalized_time(self):
        rows = [self.row("browser-use", seconds=10), self.row("jev-ultrafast", seconds=1, passed=False),
                self.row("fastbrowse", seconds=4)]
        report = summarize(rows, {"timeout_seconds": 180, "repeats": 1}, ["test"])
        self.assertTrue(report["ranked"])
        self.assertEqual([r["agent"] for r in report["summaries"]], ["fastbrowse", "browser-use", "jev-ultrafast"])

    def test_missing_pair_and_duplicate_pair_refuse_ranking(self):
        row = self.row("browser-use")
        self.assertFalse(summarize([row], {"timeout_seconds": 180, "repeats": 1}, ["test"])["ranked"])
        with self.assertRaises(ValueError):
            summarize([row, row], {"timeout_seconds": 180, "repeats": 1}, ["test"])


class SupervisorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / "work")
        self.run = Path(self.temp.name)
        self.real_popen = subprocess.Popen

    def tearDown(self):
        self.temp.cleanup()

    def launch_fixture(self, command, **kwargs):
        directory = command[-2]
        code = '''import json,sys,pathlib
p=pathlib.Path(sys.argv[1])
task=json.loads((p/'input.json').read_text())
assert 'expected' not in task and 'target_url' not in task
(p/'page.json').write_text(json.dumps({'url':'http://example.test/target','headings':['Target page'],'ready':'complete'}))
(p/'worker.json').write_text(json.dumps({'status':'completed'}))
print('test-private-value')
'''
        return self.real_popen([sys.executable, "-c", code, directory], **kwargs)

    def test_actual_subprocess_output_is_graded_and_redacted(self):
        with patch("speedbench.cli.blockers", return_value=[]), \
             patch("speedbench.cli.subprocess.Popen", side_effect=self.launch_fixture), \
             patch.dict(os.environ, {"TEST_API_KEY": "test-private-value"}):
            row = attempt("browser-use", TASK, 1, 1, self.run, 5, 60)
        self.assertTrue(row["passed"])
        self.assertGreater(row["seconds"], 0)
        self.assertNotIn("test-private-value", next(self.run.rglob("stdout.log")).read_text())

    def test_wall_deadline_terminates_a_real_process(self):
        def sleeper(command, **kwargs):
            return self.real_popen([sys.executable, "-c", "import time;time.sleep(60)"], **kwargs)
        with patch("speedbench.cli.blockers", return_value=[]), \
             patch("speedbench.cli.subprocess.Popen", side_effect=sleeper):
            row = attempt("browser-use", TASK, 1, 1, self.run, .15, 60)
        self.assertEqual(row["status"], "timeout")
        self.assertFalse(row["passed"])
        self.assertLess(row["seconds"], 2)

    def test_preflight_creates_evidence_without_launching_worker(self):
        with patch("speedbench.cli.blockers", return_value=["missing OPENAI_API_KEY"]), \
             patch("speedbench.cli.subprocess.Popen") as spawn:
            row = attempt("browser-use", TASK, 1, 1, self.run, 5, 60)
        spawn.assert_not_called()
        self.assertFalse(row["attempted"])
        self.assertIsNone(row["seconds"])


@unittest.skipUnless(chrome_binary(), "Chrome not installed")
class ChromeIntegrationTests(unittest.TestCase):
    def test_real_browser_observation_screenshot_and_hidden_heading(self):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(b'<title>Fixture</title><h1>Real page</h1><h2 style="display:none">Hidden</h2>')
            def log_message(self, *_):
                pass
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as output, Chrome() as chrome:
                target = chrome.cdp.call("Target.createTarget", url=f"http://127.0.0.1:{server.server_port}/")["targetId"]
                import time
                time.sleep(.2)
                page = chrome.cdp.capture(target, Path(output))
                self.assertIn("Real page", page["headings"])
                self.assertNotIn("Hidden", page["headings"])
                self.assertTrue((Path(output) / "final.png").read_bytes().startswith(b'\x89PNG'))
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    (ROOT / "work").mkdir(exist_ok=True)
    unittest.main()
