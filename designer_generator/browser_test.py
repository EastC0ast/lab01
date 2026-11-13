"""Verify that browser bundling preserves the author source and UI adapters."""
import ast
import base64
import gzip
from pathlib import Path
from time import perf_counter
import unittest
import numpy as np
import pandas as pd
from scipy import stats
from designer_generator import core
from designer_generator.browser_build import embedded_sources

ROOT = Path(__file__).resolve().parents[1]


def browser_payload():
    source = (ROOT / 'designer_generator/browser_app.py').read_text(encoding='utf8')
    wanted = {'_original_source', '_statistics_source', '_helper_source', '_csv_b64'}
    return {n.targets[0].id: ast.literal_eval(n.value) for n in ast.walk(ast.parse(source))
            if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name)
            and n.targets[0].id in wanted}


class BrowserPreservationTests(unittest.TestCase):
    def test_embedded_sources_match_current_author_files_and_adapters(self):
        payload = browser_payload()
        self.assertEqual(tuple(payload[name] for name in ('_original_source', '_statistics_source', '_helper_source')), embedded_sources())

    def test_embedded_csv_matches_unchanged_repository_data(self):
        csv = gzip.decompress(base64.b64decode(browser_payload()['_csv_b64']))
        self.assertEqual(csv, (ROOT / 'ASE10.csv').read_bytes().replace(b'\r\n', b'\n'))

    def test_browser_and_native_outputs_equal_for_same_parameters(self):
        payload = browser_payload()
        namespace = {'np': np, 'pd': pd, 'stats': stats, 'perf_counter': perf_counter}
        for name in ('_original_source', '_statistics_source', '_helper_source'):
            exec(compile(payload[name], '<bundled-author-source>', 'exec'), namespace)
        for method in ('A', 'GD'):
            native = core.generate(method, 100, 202, 27750, 7, 41)
            browser = namespace['generate'](method, 100, 202, 27750, 7, 41)
            np.testing.assert_array_equal(native['values'], browser['values'])
            self.assertEqual(native['attempts'], browser['attempts'])


if __name__ == '__main__':
    unittest.main()
