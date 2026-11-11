"""Exact-source and data checks for the self-contained browser notebook."""

import ast
import base64
import gzip
import hashlib
import io
from pathlib import Path
from time import perf_counter
from types import FunctionType, SimpleNamespace
import unittest

import numpy as np
import pandas as pd
from scipy import stats

from designer_generator import original_generators
from designer_generator import core

ROOT = Path(__file__).resolve().parents[1]


def read_capsule():
    source = (ROOT / "designer_generator/browser_app.py").read_text(encoding="utf-8")
    values = {}
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if name in ("_algorithm_source", "_wrapper_source", "_csv_gzip_b64", "_expected_algorithm_sha", "_expected_csv_sha"):
                values[name] = ast.literal_eval(node.value)
    return values


def browser_helpers():
    capsule = read_capsule()
    algorithms = {"np": np}
    exec(compile(capsule["_algorithm_source"], "<team-generator-cell>", "exec"), algorithms)
    helpers = {"np": np, "pd": pd, "stats": stats, "perf_counter": perf_counter, "FunctionType": FunctionType,
               "original_generators": SimpleNamespace(generate_knuth=algorithms["generate_knuth"], generate_gd=algorithms["generate_gd"])}
    exec(compile(capsule["_wrapper_source"], "<presentation-helpers>", "exec"), helpers)
    return helpers


class BrowserNotebookTests(unittest.TestCase):
    def test_original_algorithm_cell_preserved_exactly(self):
        capsule = read_capsule()
        actual = capsule["_algorithm_source"]
        expected = (ROOT / "designer_generator/original_generators.py").read_text(encoding="utf-8").split("import numpy as np\n\n", 1)[1]
        self.assertEqual(actual, expected)
        self.assertEqual(hashlib.sha256(actual.encode()).hexdigest(), capsule["_expected_algorithm_sha"])
        self.assertEqual(capsule["_expected_algorithm_sha"], "a05865e011e7e6aba00e64a901a8927c814d4d936c62f58a156488c1525eb7d7")

    def test_presentation_helpers_preserved_exactly(self):
        source = (ROOT / "designer_generator/core.py").read_text(encoding="utf-8")
        expected = "\n\n".join(ast.get_source_segment(source, node) for node in ast.parse(source).body
                               if isinstance(node, (ast.FunctionDef, ast.ClassDef))
                               and node.name in {"_LocalNumpy", "fit_parameters", "generate", "summary", "diagnostics"})
        self.assertEqual(read_capsule()["_wrapper_source"], expected)

    def test_embedded_csv_is_byte_identical_after_lf_normalization(self):
        capsule = read_capsule()
        actual = gzip.decompress(base64.b64decode(capsule["_csv_gzip_b64"]))
        expected = (ROOT / "ASE10.csv").read_bytes().replace(b"\r\n", b"\n")
        self.assertEqual(actual, expected)
        self.assertEqual(hashlib.sha256(actual).hexdigest(), capsule["_expected_csv_sha"])
        embedded = pd.read_csv(io.BytesIO(actual), sep=";")["ASE_NO2"].dropna()
        np.testing.assert_array_equal(embedded.to_numpy(), core.load_no2().to_numpy())
        self.assertEqual(len(embedded), 3686)

    def test_same_values_and_attempts_for_both_methods(self):
        helper = browser_helpers()["generate"]
        for method in ("A", "GD"):
            for a in (1.1, 3., 202.40228003336605):
                for seed in (0, 40, 4294967295):
                    with self.subTest(method=method, a=a, seed=seed):
                        actual = helper(method, 250, a, 27756., 6.7, seed)
                        expected = core.generate(method, 250, a, 27756., 6.7, seed)
                        np.testing.assert_array_equal(actual["values"], expected["values"])
                        self.assertEqual(actual["attempts"], expected["attempts"])

    def test_ui_cells_and_metadata(self):
        source = (ROOT / "designer_generator/browser_app.py").read_text(encoding="utf-8")
        original = (ROOT / "designer_generator/app.py").read_text(encoding="utf-8")
        original_cells = [n for n in ast.parse(original).body if isinstance(n, ast.FunctionDef)]
        browser_cells = [n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef)]
        for cell in original_cells[1:]:
            expected = ast.dump(cell)
            self.assertTrue(any(ast.dump(n) == expected for n in browser_cells))
        for package in ("marimo==0.25.2", "numpy", "pandas", "scipy", "matplotlib"):
            self.assertIn('"' + package + '"', source.split("# ///", 2)[1])
        imports = [n.module or "" for n in ast.walk(ast.parse(source)) if isinstance(n, ast.ImportFrom)]
        self.assertFalse(any(name.startswith("designer_generator") for name in imports))
        self.assertNotIn("sys.path", source)
        self.assertNotIn("__file__", source)


if __name__ == "__main__":
    unittest.main()
