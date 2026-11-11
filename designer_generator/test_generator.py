"""Regression checks for presentation wrappers, not approval of the source model."""

import hashlib
import json
from pathlib import Path
import unittest

import numpy as np

from designer_generator import original_generators
from designer_generator.core import generate


class GeneratorPresentationTests(unittest.TestCase):
    def test_source_cell_is_unchanged(self):
        root = Path(__file__).resolve().parent
        provenance = json.loads((root / "provenance.json").read_text(encoding="utf-8"))
        raw = (root / "original_generators.py").read_text(encoding="utf-8")
        source = raw.split("import numpy as np\n\n", 1)[1]
        self.assertEqual(hashlib.sha256(source.encode()).hexdigest(), provenance["source_sha256"])
        self.assertEqual(provenance["commit"], "01a1c6ce89d076e969bf0a8300fcd9abc2c96e36")

    def test_exact_arrays_and_attempt_counts_match_original(self):
        initial = np.random.get_state()
        try:
            for method, source in [("A", original_generators.generate_knuth), ("GD", original_generators.generate_gd)]:
                for a in (1.1, 3., 20.):
                    for seed in (0, 40, 4294967295):
                        with self.subTest(method=method, a=a, seed=seed):
                            np.random.seed(seed)
                            values, attempts = source(250, a, -7., 2.5)
                            actual = generate(method, 250, a, -7., 2.5, seed)
                            np.testing.assert_array_equal(actual["values"], values)
                            self.assertEqual(actual["attempts"], attempts)
                            self.assertGreaterEqual(attempts, 250)
                            self.assertTrue(np.isfinite(actual["values"]).all())
        finally:
            np.random.set_state(initial)

    def test_reproducibility_and_global_rng_isolation(self):
        initial = np.random.get_state()
        first = generate("GD", 100, 4., 0., 1., 40)
        second = generate("GD", 100, 4., 0., 1., 40)
        np.testing.assert_array_equal(first["values"], second["values"])
        after = np.random.get_state()
        self.assertEqual(initial[0], after[0])
        np.testing.assert_array_equal(initial[1], after[1])
        self.assertEqual(initial[2:], after[2:])

    def test_invalid_parameters_are_rejected_before_generation(self):
        for kwargs in [("A", 0, 2., 0., 1., 40), ("A", 100, 1., 0., 1., 40),
                       ("GD", 100, 2., 0., 0., 40), ("A", 100, 2., 0., 1., -1),
                       ("other", 100, 2., 0., 1., 40), ("A", 100, np.nan, 0., 1., 40),
                       ("A", 100, 1001., 0., 1., 40), ("A", 100, 2., 1e10, 1., 40),
                       ("A", 100, 2., 0., 1e7, 40), ("GD", 100, 2., 0., 1e-8, 40)]:
            with self.subTest(parameters=kwargs), self.assertRaises(ValueError):
                generate(*kwargs)


if __name__ == "__main__":
    unittest.main()
