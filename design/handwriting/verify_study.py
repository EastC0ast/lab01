"""Read-only audit of saved handwriting artifacts, before or after a rebuild.

Default: verify files currently on disk. Run this before the builder in CI to
audit committed outputs, then run it again after the builder. --git-ref HEAD
instead audits the immutable Git snapshot. No analysis or builder is imported,
no notebook is executed, and no artifact is written.
"""
from __future__ import annotations

import sys
sys.dont_write_bytecode = True

import argparse
import base64
from collections import Counter, defaultdict
import copy
import csv
import hashlib
import html
import io
import json
import math
from pathlib import Path
import posixpath
import re
from statistics import fmean
import subprocess
import unicodedata
from urllib.parse import unquote, urlsplit
import zipfile

import nbformat
from bs4 import BeautifulSoup

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PREFIX = "design/handwriting/"
ARCHIVE_SHA256 = "0881b522911b99d9922820289441b50fd3d307f71cd7f9cc70e86872424a5f90"
FIGURES = ["hw01-examples.png", "hw02-distributions.png", "hw03-pairs.png",
           "hw04-calibration.png", "hw05-uncertainty.png"]
SITE_SCALES = {"UJI": 100, "UPV": 152}


class VerificationError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise VerificationError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def lf(raw):
    return raw.replace(b"\r\n", b"\n")


class Source:
    def __init__(self, git_ref=None, overrides=None):
        self.overrides = overrides or {}
        self.commit = None
        self.files = None
        if git_ref:
            self.commit = subprocess.check_output(
                ["git", "rev-parse", "--verify", git_ref + "^{commit}"], cwd=ROOT).decode().strip()
            raw = subprocess.check_output(["git", "ls-tree", "-rz", "--name-only", self.commit], cwd=ROOT)
            self.files = {p.decode("utf-8") for p in raw.split(b"\0") if p}

    @staticmethod
    def path(path):
        clean = posixpath.normpath(str(path).replace("\\", "/"))
        require(not clean.startswith(("../", "/")) and clean != "..", f"Path escapes repository: {path}")
        return clean

    def read(self, path):
        path = self.path(path)
        if path in self.overrides:
            return self.overrides[path]
        require(self.is_file(path), f"Required file is missing: {path}")
        if self.commit:
            return subprocess.check_output(["git", "show", f"{self.commit}:{path}"], cwd=ROOT)
        return (ROOT / path).read_bytes()

    def is_file(self, path):
        path = self.path(path)
        return path in self.overrides or (path in self.files if self.files is not None else (ROOT / path).is_file())

    def is_dir(self, path):
        path = self.path(path)
        if self.files is not None:
            return any(p.startswith(path.rstrip("/") + "/") for p in self.files)
        return (ROOT / path).is_dir()

    def replaced(self, path, raw):
        replacement = copy.copy(self)
        replacement.overrides = {**self.overrides, self.path(path): raw}
        return replacement


def read_json(source, path):
    def invalid_number(value):
        raise VerificationError(f"Non-finite JSON number {value} in {path}")
    return json.loads(source.read(path).decode("utf-8-sig"), parse_constant=invalid_number)


def read_csv(source, name):
    return list(csv.DictReader(io.StringIO(source.read(PREFIX + "data/" + name).decode("utf-8-sig"), newline="")))


def close(actual, expected, context):
    actual = float(actual)
    require(math.isfinite(actual) and math.isclose(actual, float(expected), rel_tol=1e-12, abs_tol=1e-12),
            f"Numeric mismatch at {context}: {actual} != {expected}")


def source_measurements(archive_bytes):
    """Read raw Version 2 tokens independently of prepare_data.py."""
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
        text = archive.read("ujipenchars2.txt").decode("utf-8")
    lines = [line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith("//")]
    selected, labels, writers = [], set(), Counter()
    index = 0
    while index < len(lines):
        header = lines[index].split()
        require(len(header) == 3 and header[0] == "WORD", "Unexpected raw WORD format")
        _, character, session = header
        match = re.fullmatch(r"(trn|tst)_(UJI|UPV)_W(\d{2})-(\d{2})", session)
        require(match is not None, f"Invalid raw session ID: {session}")
        split, site, number, repetition = match.groups()
        index += 1
        count = lines[index].split()
        require(len(count) == 2 and count[0] == "NUMSTROKES", f"Missing NUMSTROKES: {session}")
        n_strokes = int(count[1])
        require(n_strokes > 0, f"Empty raw trace: {session}")
        index += 1
        strokes = []
        for _ in range(n_strokes):
            left, marker, right = lines[index].partition("#")
            count = left.split()
            require(marker and len(count) == 2 and count[0] == "POINTS", f"Invalid raw POINTS: {session}")
            coordinates = [int(value) for value in right.split()]
            require(len(coordinates) == 2 * int(count[1]) and coordinates, f"Raw point count mismatch: {session}")
            strokes.append([list(point) for point in zip(coordinates[::2], coordinates[1::2])])
            index += 1
        writer_id = session.rsplit("-", 1)[0]
        writers[writer_id] += 1
        labels.add(character)
        if character != "a":
            continue
        points = [point for stroke in strokes for point in stroke]
        xs, ys = [p[0] for p in points], [p[1] for p in points]
        width, height = max(xs) - min(xs), max(ys) - min(ys)
        selected.append({"sample_id": session + "-U+0061", "character": character,
                         "writer_id": writer_id, "writer_number": int(number), "split": split,
                         "site": site, "repetition": int(repetition), "strokes": strokes,
                         "ink_units_per_mm": SITE_SCALES[site], "n_strokes": n_strokes, "n_points": len(points),
                         "x_min_ink": min(xs), "x_max_ink": max(xs), "y_min_ink": min(ys), "y_max_ink": max(ys),
                         "width_ink": width, "height_ink": height,
                         "width_mm": width / SITE_SCALES[site], "height_mm": height / SITE_SCALES[site]})
    require(sum(writers.values()) == 11640 and len(labels) == 97 and len(writers) == 60,
            "Raw archive must contain 11640 glyphs / 97 characters / 60 writers")
    require(set(writers.values()) == {194}, "Each source writer must have 194 glyphs")
    return selected


def verify_data(source):
    provenance = read_json(source, PREFIX + "data/provenance.json")
    archive = source.read(PREFIX + "data/uji_pen_characters_version2.zip")
    require(digest(archive) == ARCHIVE_SHA256, "Official source ZIP SHA256 mismatch")
    require(provenance["source_zip"]["sha256"] == ARCHIVE_SHA256 and provenance["source_zip"]["bytes"] == len(archive),
            "Source ZIP provenance does not match the archive")
    with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
        require(set(zipped.namelist()) == set(provenance["source_members"]), "Source member inventory mismatch")
        for name, record in provenance["source_members"].items():
            raw = zipped.read(name)
            require(len(raw) == record["bytes"] and digest(raw) == record["sha256"], f"Archive member mismatch: {name}")
        require(lf(source.read(PREFIX + "data/uji2.names")) == lf(zipped.read("uji2.names")), "Saved source documentation changed")
    for name, record in provenance["generated_files"].items():
        raw = lf(source.read(PREFIX + "data/" + name))
        require(digest(raw) == record["sha256"] and len(raw) == record["bytes"], f"Derived data provenance mismatch: {name}")
    api = provenance["official_api_metadata"]
    api_bytes = source.read(PREFIX + "data/" + api["path"])
    require(api["sha256"] in {digest(api_bytes), digest(lf(api_bytes))}, "Saved official API metadata hash mismatch")
    require(provenance["derived_quantities"]["ink_units_per_mm"] == SITE_SCALES, "Incorrect site calibration in provenance")
    plan = read_json(source, PREFIX + "data/selection_plan.json")
    require(plan == provenance["selection_plan"], "Selection plan and provenance disagree")
    require(plan["character"] == "a" and plan["selected_before_outcome_analysis"] is True,
            "Selection must be the prespecified lowercase Latin a")

    expected = source_measurements(archive)
    samples = read_json(source, PREFIX + "data/samples.json")
    csv_rows = read_csv(source, "glyphs.csv")
    require(len(expected) == len(samples) == len(csv_rows) == 120, "Expected 120 selected glyphs")
    by_sample = {row["sample_id"]: row for row in samples}
    by_csv = {row["sample_id"]: row for row in csv_rows}
    require(len(by_sample) == len(by_csv) == 120, "Duplicate saved sample IDs")
    require(set(by_sample) == set(by_csv) == {r["sample_id"] for r in expected}, "Selected source/sample/CSV IDs differ")
    groups = defaultdict(list)
    string_fields = ["character", "writer_id", "split", "site"]
    integer_fields = ["writer_number", "repetition", "ink_units_per_mm", "n_strokes", "n_points",
                      "x_min_ink", "x_max_ink", "y_min_ink", "y_max_ink", "width_ink", "height_ink"]
    for row in expected:
        sample_id = row["sample_id"]
        require(by_sample[sample_id]["strokes"] == row["strokes"], f"Source strokes were modified: {sample_id}")
        require(row["width_ink"] > 0 and row["height_ink"] > 0, f"Non-positive selected extent: {sample_id}")
        for actual in (by_sample[sample_id], by_csv[sample_id]):
            for field in string_fields:
                require(actual[field] == row[field], f"Metadata mismatch: {sample_id}/{field}")
            for field in integer_fields:
                require(int(actual[field]) == row[field], f"Raw measurement mismatch: {sample_id}/{field}")
            for field in ("width_mm", "height_mm"):
                close(actual[field], row[field], sample_id + "/" + field)
        groups[row["writer_id"]].append(row)
    require(len(groups) == 60 and all(sorted(r["repetition"] for r in pair) == [1, 2] for pair in groups.values()),
            "Every one of 60 writers must have both repetitions")
    means = read_csv(source, "writer_means.csv")
    mean_map = {row["writer_id"]: row for row in means}
    require(len(means) == len(mean_map) == 60 and set(mean_map) == set(groups), "Writer mean inventory mismatch")
    for writer_id, pair in groups.items():
        actual = mean_map[writer_id]
        require(int(actual["n_samples"]) == 2, f"Wrong repetition count: {writer_id}")
        for field in ("site", "split"):
            require(actual[field] == pair[0][field], f"Writer metadata mismatch: {writer_id}/{field}")
        for field in ("writer_number", "ink_units_per_mm"):
            require(int(actual[field]) == pair[0][field], f"Writer metadata mismatch: {writer_id}/{field}")
        for dimension in ("width", "height"):
            for unit in ("ink", "mm"):
                close(actual[f"{dimension}_mean_{unit}"], fmean(r[f"{dimension}_{unit}"] for r in pair), writer_id + "/" + dimension + "/" + unit)
    selection = provenance["selected_dataset"]
    require((selection["n_glyphs"], selection["n_writers"], selection["repetitions"], selection["dropped_glyphs"]) == (120, 60, [1, 2], 0),
            "Selection provenance counts mismatch")
    require(selection["writers_by_site"] == dict(Counter(pair[0]["site"] for pair in groups.values())), "Writer site counts mismatch")
    require(selection["glyphs_by_site"] == dict(Counter(r["site"] for r in expected)), "Glyph site counts mismatch")
    return {"glyphs": 120, "writers": 60, "source_archive_sha256": ARCHIVE_SHA256}


def notebook(source, filename):
    raw = read_json(source, PREFIX + filename)
    ids = [cell.get("id") for cell in raw["cells"]]
    require(all(ids) and len(set(ids)) == len(ids), f"Missing/duplicate notebook cell IDs: {filename}")
    result = nbformat.from_dict(raw)
    nbformat.validate(result)
    return result


def png_bytes(value):
    if isinstance(value, list):
        value = "".join(value)
    raw = base64.b64decode("".join(value.split()), validate=True)
    require(raw.startswith(b"\x89PNG\r\n\x1a\n"), "Invalid embedded PNG signature")
    return raw


def verify_notebooks_html(source):
    reader = notebook(source, "handwriting.ipynb")
    full = notebook(source, "handwriting_calculations.ipynb")
    require(all(c.cell_type == "markdown" for c in reader.cells), "Reader notebook contains code or a non-Markdown cell")
    codes = [c for c in full.cells if c.cell_type == "code"]
    require(codes, "Calculation notebook contains no code")
    counts = [c.execution_count for c in codes]
    require(all(isinstance(c, int) and not isinstance(c, bool) and c > 0 for c in counts), "Unexecuted calculation cells")
    require(counts == sorted(set(counts)), "Calculation execution counts must be unique and ascending")
    outputs = [output for cell in codes for output in cell.get("outputs", [])]
    require(not any(output.output_type == "error" for output in outputs), "Calculation notebook contains saved errors")
    expected = [source.read(PREFIX + "figures/" + name) for name in FIGURES]
    saved = [png_bytes(o.data["image/png"]) for o in outputs if "image/png" in o.get("data", {})]
    require(saved == expected and len(saved) == 5, "Saved notebook PNG outputs differ from the five figure files")
    html_source = source.read(PREFIX + "handwriting_reading.html").decode("utf-8")
    soup = BeautifulSoup(html_source, "html.parser")
    require(not soup.select(".jp-CodeCell, .code_cell, .input_area"), "Reading HTML contains code cells")
    images = soup.find_all("img")
    require(len(images) == 5, "Reading HTML must contain five images")
    embedded = []
    for image in images:
        url = image.get("src", "")
        require(url.startswith("data:image/png;base64,"), "Reading HTML has an external/non-PNG image")
        embedded.append(png_bytes(url.split(",", 1)[1]))
    require(embedded == expected, "HTML embedded PNGs differ from figure files")
    anchors = {unquote(str(tag[attr])) for tag in soup.find_all(True) for attr in ("id", "name") if tag.has_attr(attr)}
    for link in soup.find_all("a", href=True):
        url = link["href"]
        if url.startswith("#") and len(url) > 1:
            require(unquote(url[1:]) in anchors, f"Broken HTML anchor: {url}")
    return {"reader_code_cells": 0, "executed_code_cells": len(codes), "execution_errors": 0,
            "saved_png_outputs_equal_files": len(saved), "html_figures_embedded": len(embedded), "html_code_cells": 0}


def markdown_anchors(text):
    soup = BeautifulSoup(text, "html.parser")
    result = {str(tag[attr]) for tag in soup.find_all(True) for attr in ("id", "name") if tag.has_attr(attr)}
    seen = Counter()
    for heading in re.findall(r"(?m)^#{1,6}\s+(.+?)\s*#*\s*$", text):
        heading = BeautifulSoup(heading, "html.parser").get_text().lower().replace("`", "")
        slug = "".join(c for c in heading if not unicodedata.category(c).startswith("P") or c in "-_")
        slug = re.sub(r"\s", "-", slug.strip())
        duplicate = seen[slug]
        seen[slug] += 1
        result.add(slug if not duplicate else slug + "-" + str(duplicate))
    return result


def verify_readme(source):
    path = PREFIX + "README.md"
    text = source.read(path).decode("utf-8")
    local_links = 0
    for target in re.findall(r"!?\[[^\]]*\]\(([^)]+)\)", text):
        target = html.unescape(target.strip())
        target = target[1:target.index(">")] if target.startswith("<") and ">" in target else target.split()[0]
        parsed = urlsplit(target)
        if parsed.scheme or parsed.netloc:
            continue
        local_links += 1
        destination = Source.path(posixpath.join(PREFIX, unquote(parsed.path))) if parsed.path else path
        require(source.is_file(destination) or source.is_dir(destination), f"Broken README path: {target}")
        if not parsed.fragment:
            continue
        require(source.is_file(destination), f"Directory link cannot resolve this anchor: {target}")
        fragment = unquote(parsed.fragment)
        if destination.endswith((".md", ".markdown")):
            anchors = markdown_anchors(source.read(destination).decode("utf-8"))
        elif destination.endswith(".ipynb"):
            doc = read_json(source, destination)
            anchors = markdown_anchors("\n".join("".join(c["source"]) if isinstance(c["source"], list) else c["source"]
                                                   for c in doc["cells"] if c["cell_type"] == "markdown"))
        elif destination.endswith((".html", ".htm")):
            doc = BeautifulSoup(source.read(destination).decode("utf-8"), "html.parser")
            anchors = {unquote(str(t[a])) for t in doc.find_all(True) for a in ("id", "name") if t.has_attr(a)}
        else:
            line = re.fullmatch(r"L(\d+)(?:-L(\d+))?", fragment)
            require(line is not None, f"Unsupported local README anchor: {target}")
            require(1 <= int(line[1]) <= int(line[2] or line[1]) <= len(source.read(destination).splitlines()), f"Broken line anchor: {target}")
            continue
        require(fragment in anchors, f"Broken README anchor: {target}")
    require(local_links > 0, "README must contain local navigation links")
    return {"readme_local_links_checked": local_links, "broken_readme_links": 0}


def verify_manifest(source, actual):
    verification = read_json(source, PREFIX + "verification.json")
    results = read_json(source, PREFIX + "results.json")
    require(verification["status"] == "passed", "Saved verification does not report passed")
    for key, value in actual.items():
        require(key in verification and verification[key] == value, f"Verification count/hash mismatch: {key}")
    require(results["glyph_count"] == actual["glyphs"] and results["writer_count"] == actual["writers"] and results["repetitions_per_writer"] == 2,
            "Results counts disagree with stored data")
    require(results["source_zip_sha256"] == actual["source_archive_sha256"], "Results source archive hash mismatch")
    require(verification["association"] == results["association"], "Results and verification association fields differ")
    require(verification["notebook_recalculation_identical"] is True, "Saved notebook recalculation flag is missing")
    required_hashes = {"README.md", "handwriting.ipynb", "handwriting_calculations.ipynb", "results.json"}
    require(required_hashes <= set(verification["sha256_lf"]), "Verification LF hash inventory is incomplete")
    for filename, expected in verification["sha256_lf"].items():
        require(digest(lf(source.read(PREFIX + filename))) == expected, f"Verification LF hash mismatch: {filename}")
    for level, n in (("glyphs", 120), ("writers", 60)):
        for dimension in ("width_mm", "height_mm"):
            require(results["summaries"][level][dimension]["n"] == n, f"Summary count mismatch: {level}/{dimension}")
    association = results["association"]
    p = (1 + association["permutation_extreme_count"]) / (1 + association["permutations"])
    close(association["permutation_p_two_sided"], p, "Monte Carlo p-value correction")
    require(association["reject_conditional_pairing_null"] == (p < association["alpha"]), "Saved test decision is inconsistent with p and alpha")
    require(association["bootstrap_ci95"][0] <= association["bootstrap_ci95"][1], "Bootstrap interval endpoints are reversed")
    return {"results_manifest_consistent": True, "normalized_lf_hashes_checked": len(verification["sha256_lf"])}


def verify(source):
    actual = verify_data(source)
    actual.update(verify_notebooks_html(source))
    actual.update(verify_manifest(source, actual))
    actual.update(verify_readme(source))
    return actual


def self_tests(source):
    """Prove selected failures are caught, using in-memory overrides only."""
    rejected = []
    reader = read_json(source, PREFIX + "handwriting.ipynb")
    reader["cells"].append({"cell_type": "code", "id": "audit-tampered-code", "metadata": {},
                            "source": "print('visible code')", "execution_count": None, "outputs": []})
    cases = [
        ("reader_code", source.replaced(PREFIX + "handwriting.ipynb", json.dumps(reader).encode()), verify_notebooks_html),
        ("figure_bytes", source.replaced(PREFIX + "figures/" + FIGURES[0], source.read(PREFIX + "figures/" + FIGURES[0]) + b"changed"), verify_notebooks_html),
        ("html_code", source.replaced(PREFIX + "handwriting_reading.html", source.read(PREFIX + "handwriting_reading.html") + b'<div class="jp-CodeCell">code</div>'), verify_notebooks_html),
        ("broken_readme_link", source.replaced(PREFIX + "README.md", source.read(PREFIX + "README.md") + b"\n[broken](missing-audit-target.md#none)\n"), verify_readme),
    ]
    for name, changed, check in cases:
        try:
            check(changed)
        except VerificationError:
            rejected.append(name)
        else:
            raise VerificationError("Negative self-test was not rejected: " + name)
    return rejected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--git-ref", help="Read a committed Git snapshot instead of files on disk, e.g. HEAD")
    parser.add_argument("--self-test", action="store_true", help="Also reject four in-memory corrupted snapshots without writing files")
    options = parser.parse_args()
    source = Source(options.git_ref)
    actual = verify(source)
    output = {"status": "passed", "scope": source.commit or "working tree", "read_only": True,
              "calculations_reexecuted": False, **actual}
    if options.self_test:
        output["negative_self_tests_rejected"] = self_tests(source)
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (VerificationError, FileNotFoundError, KeyError, ValueError, IndexError) as error:
        print("Study verification failed: " + str(error), file=sys.stderr)
        raise SystemExit(1)
