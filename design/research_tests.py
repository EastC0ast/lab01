"""Numerical and boundary checks for the scientific first-sprint helpers."""
import unittest

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from design.research_stats import (modal_values, mode_text, empirical_cdf, cdf_at,
                                  plot_ecdf, minmax, metrics, empirical_pair, joint_hours,
                                  compare_samples)


class MeasurementDefinitions(unittest.TestCase):
    def test_no_unique_value_is_selected_as_a_special_mode(self):
        modes, frequency = modal_values([8.5, -2., 7.])
        self.assertEqual(modes, [])
        self.assertEqual(frequency, 1)
        self.assertIn('Нет выделенной моды', mode_text([8.5, -2., 7.]))

    def test_all_tied_modes_are_reported(self):
        self.assertEqual(modal_values([7, 2, 9, 2, 7]), ([2., 7.], 2))
        self.assertEqual(modal_values([3, 3, 3]), ([3.], 3))

    def test_ecdf_is_for_actual_values_and_is_right_continuous(self):
        values = [1.1, 1.1, 1.9, 4.2]
        np.testing.assert_allclose(cdf_at(values, [0., 1.099, 1.1, 1.5, 1.9, 4.2, 20.]),
                                   [0., 0., .5, .5, .75, 1., 1.])
        knots, probability = empirical_cdf(values)
        np.testing.assert_allclose(knots, [1.1, 1.9, 4.2])
        np.testing.assert_allclose(probability, [.5, .75, 1.])
        self.assertTrue(np.all(np.diff(probability) >= 0))
        fig, axis = plt.subplots()
        line, = plot_ecdf(axis, values)
        self.assertEqual(line.get_drawstyle(), 'steps-post')
        self.assertEqual(line.get_ydata()[0], 0.)
        self.assertEqual(line.get_ydata()[-1], 1.)
        plt.close(fig)

    def test_constant_ecdf_and_undefined_constant_scaling(self):
        np.testing.assert_allclose(cdf_at([2, 2, 2], [1.9, 2., 2.1]), [0., 1., 1.])
        np.testing.assert_allclose(cdf_at([5], [4, 5, 6]), [0., 1., 1.])
        with self.assertRaises(ValueError):
            minmax([2, 2, 2])

    def test_definitions_reject_missing_infinite_or_empty_input(self):
        for values in [[], [1, np.nan], [1, np.inf], [[1, 2]]]:
            with self.subTest(values=values):
                with self.assertRaises(ValueError):
                    empirical_cdf(values)

    def test_sample_variance_is_not_population_variance(self):
        result = metrics([1, 2, 3])
        self.assertEqual(result['Среднее'], 2.)
        self.assertEqual(result['Выборочная дисперсия (ddof=1)'], 1.)
        self.assertEqual(result['Стандартное отклонение (ddof=1)'], 1.)
        np.testing.assert_allclose(minmax([2, 4, 10]), [0., .25, 1.])

    def test_empirical_covariance_uses_finite_population_denominator(self):
        result = empirical_pair([1, 2, 3], [2, 4, 6])
        self.assertAlmostEqual(result['Cov_N'], 4/3)
        self.assertAlmostEqual(result['Pearson r'], 1.)
        self.assertAlmostEqual(result['Spearman ρ'], 1.)
        # This deterministic nonlinear relation has zero covariance: the converse
        # "uncorrelated implies independent" must never be inferred.
        uncorrelated = empirical_pair([-1, 0, 1], [1, 0, 1])
        self.assertEqual(uncorrelated['Cov_N'], 0.)

    def test_joint_hours_really_aligns_all_three_channels(self):
        frame = pd.DataFrame({'date': range(4), 'Location': ['SUD3']*4,
                              'ASE_NO2': [1, 2, np.nan, 4],
                              'ASE_T': [3, np.nan, 5, 6], 'ASE_CO': [7, 8, 9, 10]})
        self.assertEqual(joint_hours(frame).index.tolist(), [0, 3])

    def test_sampling_preserves_reference_size_and_fails_impossible_request(self):
        result = compare_samples([1, 2, 3, 4], n=3, seed=40)
        self.assertEqual(result.loc['Объём, наблюдений'].tolist(), [4, 3, 3])
        with self.assertRaises(ValueError):
            compare_samples([1, 2], n=3)


if __name__ == '__main__':
    unittest.main()
