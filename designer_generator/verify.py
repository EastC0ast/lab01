"""Run presentation checks and record only results that actually passed."""

from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
from importlib.metadata import version
import json
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def inspect_export(path):
    text = path.read_text(encoding="utf-8")
    payload = text.split('"__MARIMO_MOUNT_CONFIG__"', 1)[1].split("value: Object.freeze(", 1)[1]
    mount, _ = json.JSONDecoder().raw_decode(payload)
    cells = mount["session"]["cells"]
    outputs = [output for cell in cells for output in cell["outputs"]]
    assert len(cells) == 7 and all(output["type"] == "data" for output in outputs)
    assert not any(cell["console"] for cell in cells), "Unexpected console output in exported session"
    assert "MarimoExceptionRaisedError" not in text and "Traceback (most recent call last)" not in text
    assert all(not cell["code"] for cell in mount["notebook"]["cells"]), "Source code leaked into static export"
    rendered = "\n".join(output["data"].get("text/html", "") for output in outputs)

    class Tags(HTMLParser):
        def __init__(self):
            super().__init__()
            self.counts = {"marimo-number": 0, "marimo-table": 0, "png_figures": 0, "h3": 0}

        def handle_starttag(self, tag, attrs):
            if tag in self.counts:
                self.counts[tag] += 1
            attributes = dict(attrs)
            if tag == "marimo-json-output":
                data = json.loads(attributes["data-json-data"])
                for value in data.values():
                    if isinstance(value, str) and value.startswith("text/html:"):
                        child = Tags()
                        child.feed(value[len("text/html:"):])
                        for key, count in child.counts.items():
                            self.counts[key] += count
            if tag == "marimo-mime-renderer":
                data = json.loads(json.loads(attributes["data-data"]))
                if "image/png" in data:
                    assert data["image/png"].startswith("data:image/png;base64,")
                    self.counts["png_figures"] += 1

    tags = Tags()
    tags.feed(rendered)
    assert tags.counts == {"marimo-number": 5, "marimo-table": 3, "png_figures": 1, "h3": 2}, tags.counts
    assert "Применено: N=3686, seed=40" in rendered
    assert "data:image/png;base64," in rendered
    return {"session_cells_executed": len(cells), "output_types": sorted({o["type"] for o in outputs}),
            "rendered_elements": tags.counts, "source_code_in_export": False,
            "serialized_errors": 0, "default_parameters_rendered": True}


def main():
    commands = [
        ["-m", "unittest", "designer_generator.test_generator", "-v"],
        ["-m", "marimo", "check", "--strict", "designer_generator/app.py"],
        ["-m", "marimo", "export", "html", "designer_generator/app.py", "-o",
         "designer_generator/preview.html", "--no-include-code", "--force"],
    ]
    results = []
    env = {**os.environ, "MPLBACKEND": "Agg", "PYTHONIOENCODING": "utf-8",
           "MARIMO_SKIP_UPDATE_CHECK": "1", "XDG_CONFIG_HOME": str(ROOT / ".venv" / "config"),
           "XDG_CACHE_HOME": str(ROOT / ".venv" / "cache")}
    for args in commands:
        print("Running python " + " ".join(args), flush=True)
        result = subprocess.run([sys.executable, *args], cwd=ROOT, capture_output=True,
                                text=True, encoding="utf-8", env=env, timeout=180)
        results.append({"command": "python " + " ".join(args), "exit_code": result.returncode,
                        "stdout": result.stdout, "stderr": result.stderr})
        print(result.stdout + result.stderr, flush=True)
        if result.returncode:
            raise SystemExit(result.returncode)

    from designer_generator.core import diagnostics, fit_parameters, generate, load_no2

    data = load_no2()
    fitted = fit_parameters(data)
    html_checks = inspect_export(ROOT / "designer_generator/preview.html")
    paths = ["designer_generator/app.py", "designer_generator/core.py",
             "designer_generator/original_generators.py", "designer_generator/algorithms.py", "ASE10.csv", "designer_generator/preview.html"]
    check = {"status": "passed", "checked_at_utc": datetime.now(timezone.utc).isoformat(),
             "python": sys.version, "packages": {name: version(name) for name in ["marimo", "numpy", "pandas", "scipy", "matplotlib"]},
             "commands": results, "source_commit": "01a1c6ce89d076e969bf0a8300fcd9abc2c96e36",
             "sha256": {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in paths},
             "data_observations": len(data), "fitted_parameters": dict(zip(("a", "b", "theta"), fitted)),
             "law_validation": "support, 6SE moment checks, DKW CDF bounds, reflection and reproducibility",
             "html_checks": html_checks,
             "html_export": "static initial state; live controls require marimo run",
             "visual_review": "separate from automated checks"}
    (ROOT / "designer_generator/verification.json").write_text(json.dumps(check, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Generator presentation checks passed.")


if __name__ == "__main__":
    # Allow direct execution as well as python -m designer_generator.verify.
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    main()
