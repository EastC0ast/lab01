"""Independent geometry, calibration and writer-grouping regression checks.

Run from the repository root:
    python -m unittest discover -s design/handwriting -p test_handwriting.py -v

Synthetic examples have hand-calculated expected values. The archive checks
then connect the published source strokes with the 120-glyph / 60-writer sample.
"""

from copy import deepcopy
from collections import Counter
import csv
import hashlib
from pathlib import Path
import unittest
from unittest.mock import patch

from design.handwriting import prepare_data

ROOT = Path(__file__).resolve().parents[2]
ARCHIVE = ROOT / "design/handwriting/data/uji_pen_characters_version2.zip"
ARCHIVE_SHA256 = "0881b522911b99d9922820289441b50fd3d307f71cd7f9cc70e86872424a5f90"


def sample_record(writer_id, writer_number, site, repetition, width, height, scale,
                  split="trn", n_points=2):
    """Deliberately unequal point counts must not reweight written repetitions."""
    return {"sample_id": f"{writer_id}-{repetition:02d}", "character": "a",
            "writer_id": writer_id, "writer_number": writer_number, "split": split,
            "site": site, "repetition": repetition, "ink_units_per_mm": scale,
            "x_min_ink": 0, "x_max_ink": width, "y_min_ink": 0, "y_max_ink": height,
            "width_ink": width, "height_ink": height, "n_strokes": 1, "n_points": n_points,
            "width_mm": width / scale, "height_mm": height / scale}


def paired_records():
    # Both writers have mean width 2 mm and height 3 mm, at different raw scales.
    # Input is interleaved and repetition order is reversed for the first writer.
    return [sample_record("trn_UJI_W01", 1, "UJI", 2, 300, 400, 100, n_points=1000),
            sample_record("tst_UPV_W02", 2, "UPV", 1, 152, 304, 152, split="tst"),
            sample_record("trn_UJI_W01", 1, "UJI", 1, 100, 200, 100),
            sample_record("tst_UPV_W02", 2, "UPV", 2, 456, 608, 152, split="tst", n_points=500)]


class BoundingBoxTests(unittest.TestCase):
    def test_all_strokes_and_negative_coordinates_are_included(self):
        strokes = [[(2, 5), (8, 7), (2, 5)], [(-3, 9), (7, -2)]]
        original = deepcopy(strokes)
        self.assertEqual(prepare_data.bounding_box(strokes),
                         {"x_min_ink": -3, "x_max_ink": 8, "y_min_ink": -2, "y_max_ink": 9,
                          "width_ink": 11, "height_ink": 11, "n_strokes": 2, "n_points": 5})
        self.assertEqual(strokes, original)

    def test_single_point_has_zero_extent_without_pixel_inclusive_plus_one(self):
        box = prepare_data.bounding_box([[(17, -4)]])
        self.assertEqual((box["width_ink"], box["height_ink"]), (0, 0))
        self.assertEqual((box["n_strokes"], box["n_points"]), (1, 1))

    def test_closed_trace_keeps_duplicate_points_but_not_extra_extent(self):
        box = prepare_data.bounding_box([[(1, 2), (4, 6), (1, 2), (1, 2)]])
        self.assertEqual((box["width_ink"], box["height_ink"]), (3, 4))
        self.assertEqual(box["n_points"], 4)

    def test_translation_and_axis_reflection_do_not_change_dimensions(self):
        original = [[(-7, 3), (2, 11)], [(4, -5), (0, 0)]]
        transformed = [[(-2 * x + 999, 3 * y - 123) for x, y in stroke] for stroke in original]
        before, after = prepare_data.bounding_box(original), prepare_data.bounding_box(transformed)
        self.assertEqual(after["width_ink"], 2 * before["width_ink"])
        self.assertEqual(after["height_ink"], 3 * before["height_ink"])
        self.assertEqual(after["n_points"], before["n_points"])

    def test_missing_ink_is_rejected(self):
        for strokes in ([], [[]], [[], []]):
            with self.subTest(strokes=strokes), self.assertRaises(ValueError):
                prepare_data.bounding_box(strokes)


class RawStrokeParserTests(unittest.TestCase):
    def test_raw_multistroke_record_and_repetition_calibration(self):
        text = """// UJI: 100 units per millimetre
WORD a trn_UJI_W01-01
  NUMSTROKES 2
  POINTS 3 # 0 0 10 5 20 15
  POINTS 2 # -5 8 7 -2
WORD a trn_UJI_W01-02
  NUMSTROKES 1
  POINTS 2 # 0 0 30 20
"""
        records = prepare_data.parse_ujipenchars(text)
        self.assertEqual(len(records), 2)
        first, second = records
        self.assertEqual(first["strokes"], [[(0, 0), (10, 5), (20, 15)], [(-5, 8), (7, -2)]])
        self.assertEqual((first["width_ink"], first["height_ink"]), (25, 17))
        self.assertEqual((first["n_strokes"], first["n_points"]), (2, 5))
        self.assertEqual((first["repetition"], second["repetition"]), (1, 2))
        self.assertEqual(first["writer_id"], second["writer_id"])
        self.assertEqual(first["writer_number"], 1)
        self.assertEqual(first["character"], "a")
        self.assertEqual(first["ink_units_per_mm"], 100)
        self.assertAlmostEqual(first["width_mm"], .25)
        self.assertAlmostEqual(first["height_mm"], .17)
        self.assertAlmostEqual(second["width_mm"], .3)
        self.assertAlmostEqual(second["height_mm"], .2)

    def test_truncated_trace_or_wrong_point_count_cannot_be_silently_accepted(self):
        for text in ("WORD a trn_UJI_W01-01\nNUMSTROKES 2\nPOINTS 1 # 0 0\n",
                     "WORD a trn_UJI_W01-01\nNUMSTROKES 1\nPOINTS 3 # 0 0 10 15\n"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                prepare_data.parse_ujipenchars(text)


class WriterAggregationTests(unittest.TestCase):
    def test_pairing_calibration_metadata_and_equal_weight_of_repetitions(self):
        records = paired_records()
        original = deepcopy(records)
        result = {r["writer_id"]: r for r in prepare_data.aggregate_writer_means(records)}
        self.assertEqual(set(result), {"trn_UJI_W01", "tst_UPV_W02"})
        expected = {"trn_UJI_W01": (200, 300, 100, "UJI", "trn", 1),
                    "tst_UPV_W02": (304, 456, 152, "UPV", "tst", 2)}
        for writer, (width, height, scale, site, split, number) in expected.items():
            row = result[writer]
            with self.subTest(writer=writer):
                self.assertEqual(row["n_samples"], 2)
                self.assertEqual(row["width_mean_ink"], width)
                self.assertEqual(row["height_mean_ink"], height)
                self.assertEqual(row["ink_units_per_mm"], scale)
                self.assertEqual((row["site"], row["split"], row["writer_number"]), (site, split, number))
                self.assertAlmostEqual(row["width_mean_mm"], 2)
                self.assertAlmostEqual(row["height_mean_mm"], 3)
        self.assertEqual(records, original)

    def test_missing_mm_columns_are_derived_from_each_writers_scale(self):
        records = paired_records()
        for record in records:
            record.pop("width_mm")
            record.pop("height_mm")
        result = prepare_data.aggregate_writer_means(records)
        self.assertTrue(all(r["width_mean_mm"] == 2 and r["height_mean_mm"] == 3 for r in result))

    def test_order_does_not_change_writer_pairs_or_means(self):
        records = paired_records()
        key = lambda row: row["writer_id"]
        self.assertEqual(sorted(prepare_data.aggregate_writer_means(records), key=key),
                         sorted(prepare_data.aggregate_writer_means(list(reversed(records))), key=key))

    def test_duplicate_repetition_is_rejected(self):
        records = paired_records()
        duplicate = deepcopy(records[0])
        duplicate["sample_id"] += "-duplicate"
        with self.assertRaises(ValueError):
            prepare_data.aggregate_writer_means(records + [duplicate])

    def test_inconsistent_writer_metadata_is_rejected(self):
        for field, different in (("site", "UPV"), ("split", "tst"),
                                 ("writer_number", 99), ("ink_units_per_mm", 152)):
            records = paired_records()
            records[0][field] = different
            with self.subTest(field=field), self.assertRaises(ValueError):
                prepare_data.aggregate_writer_means(records)

    def test_inconsistent_conversion_to_mm_is_rejected(self):
        for field in ("width_mm", "height_mm"):
            records = paired_records()
            records[0][field] += 1
            with self.subTest(field=field), self.assertRaises(ValueError):
                prepare_data.aggregate_writer_means(records)

    def test_balanced_selection_counts_writers_instead_of_treating_repetitions_as_people(self):
        checks = prepare_data.validate_selection(paired_records(), expected_writers=2, repetitions=(1, 2))
        self.assertEqual((checks["n_glyphs"], checks["n_writers"]), (4, 2))
        self.assertEqual(checks["character"], "a")
        self.assertEqual(tuple(checks["repetitions"]), (1, 2))
        self.assertEqual(checks["dropped_glyphs"], 0)

    def test_incomplete_or_duplicated_repetitions_fail_selection_validation(self):
        complete = paired_records()
        for records in (complete[:-1], complete + [deepcopy(complete[0])]):
            with self.subTest(n_records=len(records)), self.assertRaises(ValueError):
                prepare_data.validate_selection(records, expected_writers=2, repetitions=(1, 2))

    def test_wrong_character_or_nonpositive_extent_fails_the_prespecified_selection(self):
        for field, invalid in (("character", "A"), ("width_ink", 0), ("height_ink", -1)):
            records = paired_records()
            records[0][field] = invalid
            with self.subTest(field=field), self.assertRaises(ValueError):
                prepare_data.validate_selection(records, expected_writers=2, repetitions=(1, 2))


class PublishedArchiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # This is a required input for this study: absence is a failure, not a pass.
        cls.archive_bytes = ARCHIVE.read_bytes()
        cls.all_records = prepare_data.parse_archive(ARCHIVE)
        cls.records = [r for r in cls.all_records if r["character"] == "a"]

    def test_official_archive_identity_and_selection(self):
        self.assertEqual(hashlib.sha256(self.archive_bytes).hexdigest(), ARCHIVE_SHA256)
        self.assertEqual(len(self.all_records), 11640)
        checks = prepare_data.validate_selection(self.records)
        self.assertEqual((checks["n_glyphs"], checks["n_writers"]), (120, 60))
        self.assertEqual(checks["character"], "a")
        self.assertEqual(tuple(checks["repetitions"]), (1, 2))

    def test_every_selected_trace_matches_its_geometry_and_site_calibration(self):
        for row in self.records:
            with self.subTest(sample_id=row["sample_id"]):
                points = [point for stroke in row["strokes"] for point in stroke]
                self.assertEqual(len(points), row["n_points"])
                self.assertEqual(len(row["strokes"]), row["n_strokes"])
                self.assertEqual(row["width_ink"], max(x for x, _ in points) - min(x for x, _ in points))
                self.assertEqual(row["height_ink"], max(y for _, y in points) - min(y for _, y in points))
                self.assertGreater(row["width_ink"], 0)
                self.assertGreater(row["height_ink"], 0)
                expected_scale = {"UJI": 100, "UPV": 152}[row["site"]]
                self.assertEqual(row["ink_units_per_mm"], expected_scale)
                self.assertAlmostEqual(row["width_mm"], row["width_ink"] / expected_scale)
                self.assertAlmostEqual(row["height_mm"], row["height_ink"] / expected_scale)

    def test_sixty_writer_means_preserve_both_coordinate_pairs(self):
        means = prepare_data.aggregate_writer_means(self.records)
        self.assertEqual(len(means), 60)
        for mean in means:
            pair = [r for r in self.records if r["writer_id"] == mean["writer_id"]]
            with self.subTest(writer_id=mean["writer_id"]):
                self.assertEqual(len(pair), 2)
                self.assertEqual(mean["n_samples"], 2)
                self.assertEqual({r["repetition"] for r in pair}, {1, 2})
                self.assertAlmostEqual(mean["width_mean_mm"], (pair[0]["width_mm"] + pair[1]["width_mm"]) / 2)
                self.assertAlmostEqual(mean["height_mean_mm"], (pair[0]["height_mm"] + pair[1]["height_mm"]) / 2)

    def test_published_glyph_csv_matches_the_selected_raw_records(self):
        with (ARCHIVE.parent / "glyphs.csv").open(encoding="utf-8", newline="") as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual(len(rows), 120)
        stored = {row["sample_id"]: row for row in rows}
        self.assertEqual(set(stored), {row["sample_id"] for row in self.records})
        for expected in self.records:
            actual = stored[expected["sample_id"]]
            with self.subTest(sample_id=expected["sample_id"]):
                self.assertEqual(actual["writer_id"], expected["writer_id"])
                self.assertEqual(actual["character"], "a")
                for field in ("repetition", "ink_units_per_mm", "n_points", "n_strokes", "width_ink", "height_ink"):
                    self.assertEqual(int(actual[field]), expected[field])
                for field in ("width_mm", "height_mm"):
                    self.assertAlmostEqual(float(actual[field]), expected[field])

    def test_published_writer_csv_matches_the_paired_repetition_means(self):
        with (ARCHIVE.parent / "writer_means.csv").open(encoding="utf-8", newline="") as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual(len(rows), 60)
        stored = {row["writer_id"]: row for row in rows}
        expected_means = prepare_data.aggregate_writer_means(self.records)
        self.assertEqual(set(stored), {row["writer_id"] for row in expected_means})
        for expected in expected_means:
            actual = stored[expected["writer_id"]]
            with self.subTest(writer_id=expected["writer_id"]):
                self.assertEqual(int(actual["n_samples"]), 2)
                self.assertEqual(actual["site"], expected["site"])
                self.assertEqual(int(actual["ink_units_per_mm"]), expected["ink_units_per_mm"])
                for field in ("width_mean_ink", "height_mean_ink", "width_mean_mm", "height_mean_mm"):
                    self.assertAlmostEqual(float(actual[field]), expected[field])


class StatisticalDependenceTests(unittest.TestCase):
    """Scientific invariants using small, reproducible resampling experiments."""

    @classmethod
    def setUpClass(cls):
        import numpy as np
        from scipy import stats
        from design.handwriting import analyze
        cls.np, cls.stats, cls.analysis = np, stats, analyze

    def test_zero_within_site_variance_is_undefined_and_not_reported_as_zero(self):
        np, analyze = self.np, self.analysis
        groups = np.array(["A"] * 8 + ["B"] * 8)
        varying = np.arange(16, dtype=float)
        site_only = np.array([1.] * 8 + [100.] * 8)
        for x, y in ((site_only, varying), (varying, site_only)):
            with self.subTest(constant_axis="x" if x is site_only else "y"):
                effect = analyze.adjusted_rank_correlation(x, y, groups)
                self.assertTrue(np.isnan(effect))
                with self.assertRaises(ValueError):
                    analyze.dependence(x, y, groups, permutations=199, bootstraps=199, seed=17)

    def test_perfect_positive_and_negative_rank_relations_are_detected(self):
        np, analyze = self.np, self.analysis
        x = np.arange(20, dtype=float)
        groups = np.array(["A"] * 10 + ["B"] * 10)
        for sign, y in ((1, 7 * x + 4), (-1, 200 - 7 * x)):
            with self.subTest(sign=sign):
                self.assertAlmostEqual(analyze.adjusted_rank_correlation(x, y, groups), sign, places=12)
                info, null, bootstrap = analyze.dependence(x, y, groups, permutations=199, bootstraps=199, seed=29)
                self.assertAlmostEqual(info["adjusted_rank_correlation"], sign, places=12)
                self.assertLessEqual(info["permutation_p_two_sided"], .05)
                self.assertGreaterEqual(info["permutation_p_two_sided"], 1 / 200)
                self.assertTrue(info["reject_conditional_pairing_null"])
                self.assertEqual(len(null), 199)
                np.testing.assert_allclose(bootstrap, sign, atol=1e-12)
                np.testing.assert_allclose(info["bootstrap_ci95"], [sign, sign], atol=1e-12)

    def test_seed_repeats_results_and_bootstrap_preserves_site_counts_and_pairs(self):
        np, analyze = self.np, self.analysis
        x = np.arange(16, dtype=float)
        y = np.array([2, 7, 1, 5, 8, 4, 6, 3, 12, 17, 11, 15, 18, 14, 16, 13], dtype=float)
        groups = np.array(["A"] * 8 + ["B"] * 8)
        originals = [value.copy() for value in (x, y, groups)]
        allowed_pairs = set(zip(x, y, groups))
        expected_counts = Counter(groups)
        original_effect = analyze.adjusted_rank_correlation
        bootstrap_calls = []

        def observe_resampling(sample_x, sample_y, sample_groups):
            # The first evaluation is the observed sample; subsequent calls are
            # bootstrap samples. Permutation calculations do not call this hook.
            if bootstrap_calls:
                self.assertEqual(Counter(sample_groups), expected_counts)
                self.assertTrue(all(pair in allowed_pairs for pair in zip(sample_x, sample_y, sample_groups)))
            bootstrap_calls.append(len(sample_x))
            return original_effect(sample_x, sample_y, sample_groups)

        with patch.object(analyze, "adjusted_rank_correlation", side_effect=observe_resampling):
            first = analyze.dependence(x, y, groups, permutations=199, bootstraps=199, seed=43)
        second = analyze.dependence(x, y, groups, permutations=199, bootstraps=199, seed=43)
        self.assertEqual(len(bootstrap_calls), 200)
        self.assertEqual(first[0], second[0])
        np.testing.assert_array_equal(first[1], second[1])
        np.testing.assert_array_equal(first[2], second[2])
        for current, original in zip((x, y, groups), originals):
            np.testing.assert_array_equal(current, original)

    def test_site_only_pooled_artifact_is_removed_without_a_random_p_value_threshold(self):
        np, analyze = self.np, self.analysis
        # Each site contains a complete 4x4 Cartesian grid: its two coordinates
        # have exactly zero rank covariance. A shared shift creates the pooled
        # relationship while preserving this within-site absence of association.
        within_x = np.repeat(np.arange(1, 5, dtype=float), 4)
        within_y = np.tile(np.arange(1, 5, dtype=float), 4)
        x = np.r_[within_x, within_x + 100]
        y = np.r_[within_y, within_y + 100]
        groups = np.array(["A"] * 16 + ["B"] * 16)
        self.assertGreater(self.stats.spearmanr(x, y).statistic, .7)
        self.assertAlmostEqual(analyze.adjusted_rank_correlation(x, y, groups), 0, places=12)
        info, _, _ = analyze.dependence(x, y, groups, permutations=199, bootstraps=199, seed=61)
        # Observed |effect| is zero: every permutation is at least as extreme.
        # This is an exact construction, not a lucky Monte Carlo p-value.
        self.assertEqual(info["permutation_extreme_count"], 199)
        self.assertEqual(info["permutation_p_two_sided"], 1.)
        self.assertFalse(info["reject_conditional_pairing_null"])


if __name__ == "__main__":
    unittest.main()
