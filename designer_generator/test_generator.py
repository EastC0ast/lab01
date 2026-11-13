"""Verify preservation of author functions, not their statistical correctness."""
import ast
import json
from pathlib import Path
import unittest
import numpy as np
import pandas as pd
from designer_generator import core, original_generators, original_statistics

ROOT = Path(__file__).resolve().parents[1]


def function_source(text, name):
    return ast.get_source_segment(text, next(n for n in ast.parse(text).body
                                            if isinstance(n, ast.FunctionDef) and n.name == name))


class AuthorPreservationTests(unittest.TestCase):
    def test_generator_function_sources_equal_author_notebook(self):
        notebook = json.loads((ROOT / 'design/author_source.ipynb').read_text(encoding='utf8'))
        source = next(''.join(c['source']) for c in notebook['cells']
                      if c['cell_type'] == 'code' and 'def generate_knuth' in ''.join(c['source']))
        copied = (ROOT / 'designer_generator/original_generators.py').read_text(encoding='utf8')
        for name in ('generate_knuth', 'generate_gd'):
            self.assertEqual(function_source(source, name), function_source(copied, name))

    def test_statistics_function_source_equals_author_notebook(self):
        notebook = json.loads((ROOT / 'design/author_source.ipynb').read_text(encoding='utf8'))
        copied = (ROOT / 'designer_generator/original_statistics.py').read_text(encoding='utf8')
        sources = [function_source(''.join(c['source']), 'get_stat') for c in notebook['cells']
                   if c['cell_type'] == 'code' and 'def get_stat' in ''.join(c['source'])]
        self.assertTrue(sources)
        self.assertTrue(all(s == function_source(copied, 'get_stat') for s in sources))

    def test_wrapper_matches_author_functions_for_same_seed(self):
        state = np.random.get_state()
        try:
            for method, function in [('A', original_generators.generate_knuth), ('GD', original_generators.generate_gd)]:
                for seed in (40, 41):
                    np.random.seed(seed)
                    expected, attempts = function(57, 202.40228003336605, 27756.872789469173, 6.6960783780309026)
                    actual = core.generate(method, 57, 202.40228003336605, 27756.872789469173, 6.6960783780309026, seed)
                    np.testing.assert_array_equal(actual['values'], expected)
                    self.assertEqual(actual['attempts'], attempts)
        finally:
            np.random.set_state(state)

    def test_seed_repeats_without_changing_external_random_state(self):
        before = np.random.get_state()
        first = core.generate('GD', 100, 202, 27750, 7, 40)
        after = np.random.get_state()
        self.assertEqual(before[0], after[0]); np.testing.assert_array_equal(before[1], after[1])
        self.assertEqual(before[2:], after[2:])
        repeated = core.generate('GD', 100, 202, 27750, 7, 40)
        np.testing.assert_array_equal(first['values'], repeated['values'])

    def test_table_uses_unmodified_author_statistics(self):
        data = pd.Series([1., 1., 2., 3.])
        runs = {'A': {'values': np.array([4., 5., 6.])}, 'GD': {'values': np.array([7., 8., 9.])}}
        expected = pd.concat([original_statistics.get_stat(data, 'Реальные данные NO2'),
                              original_statistics.get_stat(pd.Series(runs['A']['values']), 'Алгоритм А'),
                              original_statistics.get_stat(pd.Series(runs['GD']['values']), 'Алгоритм GD')], axis=1)
        pd.testing.assert_frame_equal(core.comparison_table(data, runs), expected)


if __name__ == '__main__':
    unittest.main()
