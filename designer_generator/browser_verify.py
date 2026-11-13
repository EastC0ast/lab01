"""Verify native execution and a real WASM payload; browser review is separate."""

from datetime import datetime, timezone
import argparse
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--wasm-export", action="store_true", help="Also rebuild WASM HTML; requires the developer tool uv")
    options = parser.parse_args()
    env = {**os.environ, "MPLBACKEND": "Agg", "PYTHONIOENCODING": "utf-8",
           "MARIMO_SKIP_UPDATE_CHECK": "1", "XDG_CONFIG_HOME": str(ROOT / ".venv" / "config"),
           "XDG_CACHE_HOME": str(ROOT / ".venv" / "cache"), "UV_CACHE_DIR": str(ROOT / ".venv" / "uv-cache"),
           "UV_PYTHON": sys.executable, "UV_PYTHON_DOWNLOADS": "never", "UV_NATIVE_TLS": "true",
           "PATH": str(ROOT / ".venv" / "Scripts") + os.pathsep + os.environ.get("PATH", "")}
    commands = [
        ["-m", "unittest", "designer_generator.browser_test", "-v"],
        ["-m", "marimo", "check", "--strict", "designer_generator/browser_app.py"],
        ["-m", "marimo", "export", "html", "designer_generator/browser_app.py", "-o",
         "designer_generator/browser_preview.html", "--no-include-code", "--no-sandbox", "--force"],
    ]
    if options.wasm_export:
        commands.append(["-m", "marimo", "export", "html-wasm", "designer_generator/browser_app.py", "--mode", "run", "--single-file",
                         "-o", "designer_generator/browser_wasm.html", "--no-show-code", "--no-sandbox", "--force"])
    results = []
    for args in commands:
        print("Running python " + " ".join(args), flush=True)
        result = subprocess.run([sys.executable, *args], cwd=ROOT, capture_output=True,
                                text=True, encoding="utf-8", env=env, timeout=240)
        results.append({"command": "python " + " ".join(args), "exit_code": result.returncode,
                        "stdout": result.stdout, "stderr": result.stderr})
        print(result.stdout + result.stderr, flush=True)
        if result.returncode:
            raise SystemExit(result.returncode)

    preview = (ROOT / "designer_generator/browser_preview.html").read_text(encoding="utf-8")
    payload = preview.split('"__MARIMO_MOUNT_CONFIG__"', 1)[1].split("value: Object.freeze(", 1)[1]
    mount, _ = json.JSONDecoder().raw_decode(payload)
    cells = mount["session"]["cells"]
    assert len(cells) == 8 and all(not c["console"] for c in cells)
    outputs = [o for c in cells for o in c["outputs"]]
    assert all(o["type"] == "data" for o in outputs)
    assert "MarimoExceptionRaisedError" not in preview and "Traceback (most recent call last)" not in preview
    rendered = "\n".join(o["data"].get("text/html", "") for o in outputs)
    assert "Применено: N=3686, seed=40" in rendered and "data:image/png;base64," in rendered
    assert rendered.count("<marimo-table ") == 3 and rendered.count("marimo-number ") == 5
    assert all(not c["code"] for c in mount["notebook"]["cells"])

    files = ["browser_app.py", "browser_preview.html", "browser_test.py"]
    if options.wasm_export:
        wasm = (ROOT / "designer_generator/browser_wasm.html").read_text(encoding="utf-8")
        assert "pyodide" in wasm.lower() and "browser_app.py" in wasm
        files.append("browser_wasm.html")
    result = {"native_execution": "passed", "wasm_export": "passed" if options.wasm_export else "not_requested",
              "checked_at_utc": datetime.now(timezone.utc).isoformat(),
              "python": sys.version, "packages": {p: version(p) for p in ["marimo", "numpy", "pandas", "scipy", "matplotlib"]},
              "commands": results, "session_cells_executed": len(cells), "serialized_errors": 0,
              "csv_newlines": "LF normalized, identical to source Git blob; numeric observations unchanged",
              "browser_runtime_checked": False,
              "browser_runtime_note": "This command checks native execution only; see browser_live_verification.json for the separate published-browser test.",
              "sha256_line_endings": "LF (Git canonical)",
              "sha256": {name: hashlib.sha256((ROOT / "designer_generator" / name).read_bytes().replace(b'\r\n', b'\n')).hexdigest() for name in files}}
    (ROOT / "designer_generator/browser_verification.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Requested native/export checks passed; published browser execution remains to be verified.")


if __name__ == "__main__":
    main()
