"""Independent fully locked uv projects, one per competitor; no model calls."""
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
pins = json.loads((ROOT / "upstream.json").read_text())
for name in sys.argv[1:] or list(pins):
    pin = pins[name]
    runtime = ROOT / ".runtimes" / name
    runtime.mkdir(parents=True, exist_ok=True)
    dependency = f"{name} @ git+{pin['repo']}.git@{pin['commit']}"
    config = f'''[project]
name = "speedbench-runtime-{name}"
version = "0.0.0"
requires-python = ">=3.13,<3.14"
dependencies = [{json.dumps(dependency)}, "websocket-client==1.9.0", "python-dotenv>=1.2.1,<2"]
'''
    (runtime / "pyproject.toml").write_text(config)
    lock = ROOT / "locks" / f"{name}.lock"
    if lock.exists():
        (runtime / "uv.lock").write_bytes(lock.read_bytes())
    subprocess.run(["uv", "sync", "--quiet", "--python", "3.13", "--frozen"] if lock.exists()
                   else ["uv", "sync", "--quiet", "--python", "3.13"], cwd=runtime, check=True)
    lock.parent.mkdir(exist_ok=True)
    lock.write_bytes((runtime / "uv.lock").read_bytes())
    subprocess.run([str(runtime / ".venv/bin/python"), "-c",
                    f"import {name.replace('-', '_')}; print('{name}: import OK')"], check=True)
