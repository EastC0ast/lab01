"""Keep source algorithms unchanged and isolate their random state."""

from pathlib import Path
from time import perf_counter
from types import FunctionType

import numpy as np
import pandas as pd
from scipy import stats

from designer_generator import original_generators

ROOT = Path(__file__).resolve().parents[1]
SOURCE_COMMIT = "01a1c6ce89d076e969bf0a8300fcd9abc2c96e36"


class _LocalNumpy:
    """Same NumPy operations, with the legacy RNG used by the source notebook."""

    def __init__(self, seed):
        self.random = np.random.RandomState(seed)

    def __getattr__(self, name):
        return getattr(np, name)


def load_no2(path=None):
    return pd.read_csv(path or ROOT / "ASE10.csv", sep=";")["ASE_NO2"].dropna()


def fit_parameters(data):
    """Identical fitting call to source cell 51, with free loc and scale."""
    return tuple(float(x) for x in stats.gamma.fit(data))


def generate(method, n, a, loc, scale, seed):
    if method not in ("A", "GD"):
        raise ValueError("method must be A or GD")
    if not isinstance(n, int) or not 1 <= n <= 20000:
        raise ValueError("sample size must be an integer from 1 to 20000")
    if (not all(np.isfinite(x) for x in (a, loc, scale)) or not 1 < a <= 1000
            or abs(loc) > 1e9 or not 1e-6 <= scale <= 1e6):
        raise ValueError("presentation range: 1 < a <= 1000; abs(loc) <= 1e9; 1e-6 <= scale <= 1e6")
    if not isinstance(seed, int) or not 0 <= seed < 2**32:
        raise ValueError("seed must be an integer from 0 to 2**32 - 1")
    source = original_generators.generate_knuth if method == "A" else original_generators.generate_gd
    # Run the exact same code object. Only its np.random provider is private.
    isolated = FunctionType(source.__code__, {"np": _LocalNumpy(seed)}, source.__name__)
    start = perf_counter()
    values, attempts = isolated(n, a, loc, scale)
    elapsed = perf_counter() - start
    return {"values": values, "attempts": attempts, "seconds": elapsed,
            "acceptance": n / attempts, "below_loc": int(np.sum(values < loc))}


def summary(data):
    series = pd.Series(data)
    return {"Сумма": series.sum(), "Среднее": series.mean(), "Медиана": series.median(),
            "Минимум": series.min(), "Максимум": series.max(),
            "Стандартное отклонение": series.std(), "95-й процентиль": series.quantile(.95),
            "Дисперсия": series.var(), "Мода": series.mode().iloc[0]}


def diagnostics(values, a, loc, scale):
    """Descriptive distance, without a significance claim after fitting."""
    return {"D к заданной гамма-модели": float(stats.kstest(values, "gamma", args=(a, loc, scale)).statistic),
            "Асимметрия": float(stats.skew(values)), "Значений ниже loc": int(np.sum(values < loc))}
