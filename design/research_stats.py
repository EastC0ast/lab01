"""Statistical definitions used by the first-sprint notebook."""
from __future__ import annotations

from collections import Counter
import numpy as np
import pandas as pd
from scipy import stats

CHANNELS = ('ASE_NO2', 'ASE_T', 'ASE_CO')
LABELS = {'ASE_NO2': 'Сигнал NO₂', 'ASE_T': 'Температура внутри узла', 'ASE_CO': 'Сигнал CO'}
UNITS = {'ASE_NO2': 'мкВ', 'ASE_T': '°C', 'ASE_CO': 'мкВ'}


def display_table(frame, number, label):
    from IPython.display import Markdown, display
    display(Markdown(f'<a id="research-table{number:02d}" name="research-table{number:02d}"></a>\n\n**Таблица {number:02d} · {label}**'))
    display(frame)


def observations(values):
    x = np.asarray(values, dtype=float)
    if x.ndim != 1 or not len(x) or not np.isfinite(x).all():
        raise ValueError('A nonempty, finite, one-dimensional series is required.')
    return x


def modal_values(values):
    """Return all empirical modes only if some value is repeated."""
    counts = Counter(observations(values).tolist())
    frequency = max(counts.values())
    return (sorted(x for x, count in counts.items() if count == frequency)
            if frequency > 1 else []), frequency


def mode_text(values):
    modes, frequency = modal_values(values)
    if not modes:
        return 'Нет выделенной моды: все значения уникальны'
    return '; '.join(format(x, '.12g') for x in modes) + f' (частота каждого: {frequency})'


def empirical_cdf(values):
    """Knots and right-continuous CDF values, without rounding observations."""
    x = observations(values)
    knots, counts = np.unique(x, return_counts=True)
    return knots, np.cumsum(counts) / len(x)


def cdf_at(values, query):
    x = np.sort(observations(values))
    return np.searchsorted(x, query, side='right') / len(x)


def plot_ecdf(axis, values, label=None):
    knots, probability = empirical_cdf(values)
    margin = .03 * np.ptp(knots) if len(knots) > 1 else max(abs(knots[0]) * .01, .5)
    return axis.step(np.r_[knots[0] - margin, knots, knots[-1] + margin],
                     np.r_[0., probability, 1.], where='post', label=label)


def minmax(values):
    x = observations(values)
    span = np.ptp(x)
    if span == 0:
        raise ValueError('Min–max scaling is undefined for a constant series.')
    return (x - x.min()) / span


def metrics(values):
    x = observations(values)
    if len(x) < 2:
        raise ValueError('At least two observations are required for sample variance.')
    return {'Объём, наблюдений': len(x), 'Сумма': float(x.sum()),
            'Среднее': float(x.mean()), 'Медиана': float(np.median(x)),
            'Минимум': float(x.min()), 'Максимум': float(x.max()),
            'Стандартное отклонение (ddof=1)': float(x.std(ddof=1)),
            '95-й перцентиль': float(np.quantile(x, .95)),
            'Выборочная дисперсия (ddof=1)': float(x.var(ddof=1)),
            'Мода / все равноправные моды': mode_text(x)}


def print_metrics(values):
    for name, value in metrics(values).items():
        print(f'{name}: {value}')


def compare_samples(values, n=600, seed=40):
    x = pd.Series(observations(values))
    if not 1 < n <= len(x):
        raise ValueError('Sample size must be between 2 and the population size.')
    without = x.sample(n=n, replace=False, random_state=seed)
    with_replacement = x.sample(n=n, replace=True, random_state=seed)
    return pd.DataFrame({'Все доступные значения': metrics(x),
                         '600 без возвращения' if n == 600 else f'{n} без возвращения': metrics(without),
                         '600 с возвращением' if n == 600 else f'{n} с возвращением': metrics(with_replacement)})


def sampling_diagnostics(values, n=600, seed=40):
    x = pd.Series(observations(values))
    shuffled = x.sample(frac=1, random_state=seed).to_numpy()
    sizes = np.r_[np.arange(10, len(x), 10), len(x)]
    means = np.asarray([shuffled[:k].mean() for k in sizes])
    subsets = [x.sample(n=n, replace=replace, random_state=seed) for replace in (False, True)]
    return {'sizes': sizes, 'means': means,
            'max_deviation_after_n': float(np.max(np.abs(means[sizes >= n] - x.mean()))),
            'mean_relative_errors_pct': [float(100 * (s.mean() / x.mean() - 1)) for s in subsets],
            'variance_relative_errors_pct': [float(100 * (s.var() / x.var() - 1)) for s in subsets]}


def iid_normality(values, alpha=.05):
    x = observations(values)
    test = stats.normaltest(x)
    print(f'Размер набора: {len(x)}; уровень значимости: {alpha}')
    print(f'Статистика Д’Агостино—Пирсона: {test.statistic}')
    print(f'p-value в iid-модели: {test.pvalue}')
    print('В iid-модели H₀ нормальности отвергается.' if test.pvalue < alpha
          else 'В iid-модели нет оснований отвергнуть H₀ нормальности.')
    print('Почасовая зависимость не учтена этим p-value; это не доказательство асимметрии или причин отклонения.')
    return test


def load_data(path):
    frame = pd.read_csv(path, sep=';')
    frame['date'] = pd.to_datetime(frame['date'], utc=True)
    return frame


def joint_hours(frame):
    return frame[['date', 'Location', *CHANNELS]].dropna(subset=[*CHANNELS, 'Location'])


def empirical_pair(values_x, values_y):
    x, y = observations(values_x), observations(values_y)
    if len(x) != len(y) or len(x) < 2:
        raise ValueError('Aligned observations are required.')
    covariance = float(np.mean((x - x.mean()) * (y - y.mean())))
    pearson = float(np.corrcoef(x, y)[0, 1]) if np.ptp(x) and np.ptp(y) else float('nan')
    spearman = float(stats.spearmanr(x, y).statistic) if np.ptp(x) and np.ptp(y) else float('nan')
    return {'N': len(x), 'Cov_N': covariance, 'Pearson r': pearson, 'Spearman ρ': spearman}


def association_summary(frame):
    common = joint_hours(frame)
    rows = []
    pairs = [('ASE_T', 'ASE_NO2'), ('ASE_NO2', 'ASE_CO'), ('ASE_T', 'ASE_CO')]
    for location, group in [('Обе площадки', common), *list(common.groupby('Location', sort=True))]:
        for left, right in pairs:
            rows.append({'Набор': location, 'Пара': f'{left} — {right}',
                         'Единица Cov_N': f'{UNITS[left]} × {UNITS[right]}',
                         **empirical_pair(group[left], group[right])})
    return pd.DataFrame(rows)


def location_summary(frame):
    return frame.groupby('Location', dropna=False).agg(
        Строк=('date', 'size'), Начало_UTC=('date', 'min'), Конец_UTC=('date', 'max'),
        NO2_валидных=('ASE_NO2', 'count'), T_валидных=('ASE_T', 'count'), CO_валидных=('ASE_CO', 'count'))


def lag_diagnostics(frame):
    previous_time = frame['date'].shift()
    adjacent = (frame['date'] - previous_time).eq(pd.Timedelta(hours=1))
    same_location = frame['Location'].eq(frame['Location'].shift()) & frame['Location'].notna()
    rows = []
    for column in CHANNELS:
        mask = adjacent & same_location & frame[column].notna() & frame[column].shift().notna()
        rows.append({'Канал': column, 'Пар соседних часов': int(mask.sum()),
                     'r с предыдущим часом (описательно)': float(frame.loc[mask, column].corr(frame[column].shift()[mask]))})
    return pd.DataFrame(rows)


def fitted_models(no2, temperature, co):
    data = {'ASE_NO2': observations(no2), 'ASE_T': observations(temperature), 'ASE_CO': observations(co)}
    rows = []
    for column, x in data.items():
        distributions = [('skew-normal', stats.skewnorm), ('normal', stats.norm)] if column != 'ASE_CO' else [('skew-normal', stats.skewnorm), ('lognormal', stats.lognorm)]
        for name, distribution in distributions:
            params = tuple(float(v) for v in distribution.fit(x))
            rows.append({'Канал': column, 'Модель': name, 'Параметры': params,
                         'AIC': float(2 * len(params) - 2 * distribution.logpdf(x, *params).sum())})
        if column == 'ASE_NO2':
            params = tuple(float(v) for v in stats.gamma.fit(-x))
            rows.append({'Канал': column, 'Модель': 'отражённая gamma',
                         'Параметры': (params[0], -params[1], params[2]),
                         'AIC': float(6 - 2 * stats.gamma.logpdf(-x, *params).sum())})
    return pd.DataFrame(rows)
