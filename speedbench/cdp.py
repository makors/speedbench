"""Common fresh Chrome launcher and independent, read-only final-page collector."""
import base64
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

import websocket

OBSERVE = """JSON.stringify({url:location.href,title:document.title,
ready:document.readyState,headings:[...document.querySelectorAll('h1,h2,h3')]
.filter(e=>e.checkVisibility({checkVisibilityCSS:true,checkOpacity:true}))
.map(e=>e.innerText),text:document.body.innerText.slice(0,250000)})"""


def chrome_binary():
    configured = os.environ.get("SPEEDBENCH_CHROME")
    candidates = [configured] if configured else [
        shutil.which("google-chrome"), shutil.which("chromium"),
        shutil.which("chromium-browser"),
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    ]
    return next((str(p) for p in candidates if p and Path(p).is_file()), None)


class CDP:
    def __init__(self, endpoint):
        self.ws = websocket.create_connection(endpoint, timeout=20, suppress_origin=True)
        self.counter = 0

    def call(self, method, session_id=None, **params):
        self.counter += 1
        packet = {"id": self.counter, "method": method, "params": params}
        if session_id:
            packet["sessionId"] = session_id
        self.ws.send(json.dumps(packet))
        while True:
            response = json.loads(self.ws.recv())
            if response.get("id") == self.counter:
                if "error" in response:
                    raise RuntimeError(f"CDP {method}: {response['error']}")
                return response.get("result", {})

    def capture(self, target, directory):
        session = self.call("Target.attachToTarget", targetId=target, flatten=True)["sessionId"]
        self.call("Page.enable", session_id=session)
        observed = self.call("Runtime.evaluate", session_id=session,
                             expression=OBSERVE, returnByValue=True)
        if observed.get("exceptionDetails"):
            raise RuntimeError("Independent observation failed")
        evidence = json.loads(observed["result"]["value"])
        directory.joinpath("page.json").write_text(json.dumps(evidence, indent=2))
        png = self.call("Page.captureScreenshot", session_id=session, format="png")["data"]
        directory.joinpath("final.png").write_bytes(base64.b64decode(png))
        self.call("Target.detachFromTarget", sessionId=session)
        return evidence

    def close(self):
        self.ws.close()


class Chrome:
    def __enter__(self):
        self.profile = tempfile.TemporaryDirectory(prefix="speedbench-")
        binary = chrome_binary()
        if not binary:
            raise RuntimeError("No Chrome binary; set SPEEDBENCH_CHROME")
        self.process = subprocess.Popen([
            binary, "--headless=new", "--remote-debugging-port=0",
            f"--user-data-dir={self.profile.name}", "--no-first-run",
            "--no-default-browser-check", "--disable-background-networking",
            "--window-size=1120,780", "about:blank",
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        port_file = Path(self.profile.name) / "DevToolsActivePort"
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if port_file.exists():
                lines = port_file.read_text().splitlines()
                if len(lines) >= 2:
                    self.endpoint = f"ws://127.0.0.1:{lines[0]}{lines[1]}"
                    self.cdp = CDP(self.endpoint)
                    self.version = self.cdp.call("Browser.getVersion")
                    return self
            if self.process.poll() is not None:
                break
            time.sleep(.05)
        self.__exit__(None, None, None)
        raise RuntimeError("Chrome startup failed")

    def __exit__(self, *_):
        if hasattr(self, "cdp"):
            self.cdp.close()
        if hasattr(self, "process") and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        self.profile.cleanup()
