"""UI adapters for the unmodified functions from the team's notebook."""
from pathlib import Path
from time import perf_counter
import numpy as np
import pandas as pd
from scipy import stats
from designer_generator.original_generators import generate_knuth, generate_gd
from designer_generator.original_statistics import get_stat

ROOT = Path(__file__).resolve().parents[1]


def load_no2(path=None):
    return pd.read_csv(path or ROOT / 'ASE10.csv', sep=';')['ASE_NO2'].dropna()


def fit_parameters(data):
    return tuple(stats.gamma.fit(data))


def generate(method, n, a, loc, scale, seed):
    if method not in ('A', 'GD') or not isinstance(n, int) or not 1 <= n <= 20000:
        raise ValueError('Require A or GD and integer N from 1 through 20000.')
    if not all(np.isfinite(x) for x in (a, loc, scale)) or not 1 < a <= 1000 or not scale > 0:
        raise ValueError('Require finite parameters, 1<a<=1000 and scale>0.')
    if not isinstance(seed, int) or not 0 <= seed < 2**32:
        raise ValueError('Require an integer seed from 0 through 2**32-1.')
    state = np.random.get_state()
    try:
        np.random.seed(seed)
        started = perf_counter()
        values, attempts = (generate_knuth if method == 'A' else generate_gd)(n, a, loc, scale)
        seconds = perf_counter() - started
    finally:
        np.random.set_state(state)
    return {'values': values, 'attempts': attempts, 'seconds': seconds}


def comparison_table(data, runs):
    return pd.concat([
        get_stat(data, 'Реальные данные NO2'),
        get_stat(pd.Series(runs['A']['values']), 'Алгоритм А'),
        get_stat(pd.Series(runs['GD']['values']), 'Алгоритм GD'),
    ], axis=1)
