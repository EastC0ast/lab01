"""Reproducible EDA of two handwriting measurements; no sensor analysis is changed."""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

HERE = Path(__file__).resolve().parent
SEED = 20261111
PERMUTATIONS = 19999
BOOTSTRAPS = 10000
COLORS = {'UJI': '#245B78', 'UPV': '#B87532'}


def summary(values):
    x = np.asarray(values, dtype=float)
    if x.ndim != 1 or len(x) < 2 or not np.isfinite(x).all():
        raise ValueError('At least two finite observations are required.')
    unique, counts = np.unique(x, return_counts=True)
    frequency = int(counts.max())
    q05, q25, q50, q75, q95 = np.quantile(x, [.05, .25, .50, .75, .95], method='linear')
    return {'n': len(x), 'sum': float(x.sum()), 'mean': float(x.mean()),
            'median': float(q50), 'min': float(x.min()), 'max': float(x.max()),
            'std': float(x.std(ddof=1)), 'variance': float(x.var(ddof=1)),
            'q05': float(q05), 'q25': float(q25), 'q75': float(q75), 'q95': float(q95),
            'iqr': float(q75-q25), 'mode_frequency': frequency,
            'modes': unique[counts == frequency].tolist() if frequency > 1 else []}


def centered_ranks(x, groups):
    ranks = stats.rankdata(np.asarray(x, dtype=float), method='average')
    labels = np.asarray(groups)
    for group in np.unique(labels):
        positions = labels == group
        ranks[positions] -= ranks[positions].mean()
    return ranks


def adjusted_rank_correlation(x, y, groups):
    """Spearman rank residual correlation after controlling the site indicator."""
    rx, ry = centered_ranks(x, groups), centered_ranks(y, groups)
    denominator = np.linalg.norm(rx) * np.linalg.norm(ry)
    if denominator == 0:
        return float('nan')
    return float(np.dot(rx, ry) / denominator)


def dependence(x, y, groups, permutations=PERMUTATIONS, bootstraps=BOOTSTRAPS, seed=SEED):
    x, y, groups = np.asarray(x), np.asarray(y), np.asarray(groups)
    if len(x) != len(y) or len(y) != len(groups) or not np.isfinite(x).all() or not np.isfinite(y).all():
        raise ValueError('Measurements and groups must be aligned and finite.')
    blocks = [np.flatnonzero(groups == group) for group in np.unique(groups)]
    if any(len(block) < 3 for block in blocks):
        raise ValueError('Each site must contain at least three writers.')
    observed = adjusted_rank_correlation(x, y, groups)
    if not np.isfinite(observed):
        raise ValueError('Association is undefined when residual ranks have zero variance.')
    rng_perm, rng_boot = [np.random.default_rng(s) for s in np.random.SeedSequence(seed).spawn(2)]
    rx, ry = centered_ranks(x, groups), centered_ranks(y, groups)
    denominator = np.linalg.norm(rx) * np.linalg.norm(ry)
    null = np.empty(permutations)
    for b in range(permutations):
        shuffled = ry.copy()
        for block in blocks:
            shuffled[block] = rng_perm.permutation(ry[block])
        null[b] = np.dot(rx, shuffled) / denominator
    # Include exact ties; the tolerance only covers floating point rank arithmetic.
    extreme = int(np.count_nonzero(np.abs(null) >= abs(observed) - 1e-12))
    p_mc = (extreme + 1) / (permutations + 1)
    boot = np.empty(bootstraps)
    for b in range(bootstraps):
        selected = np.concatenate([rng_boot.choice(block, len(block), replace=True) for block in blocks])
        boot[b] = adjusted_rank_correlation(x[selected], y[selected], groups[selected])
    valid = boot[np.isfinite(boot)]
    if len(valid) < .99 * bootstraps:
        raise ValueError('Too many undefined bootstrap correlations; review the data.')
    interval = np.quantile(valid, [.025, .975], method='linear')
    info = {'adjusted_rank_correlation': observed, 'permutation_p_two_sided': float(p_mc),
            'permutation_extreme_count': extreme, 'permutations': permutations,
            'permutation_mc_se': float(np.sqrt(p_mc * (1-p_mc)/(permutations+1))),
            'bootstrap_ci95': interval.tolist(), 'bootstraps': bootstraps,
            'valid_bootstraps': len(valid), 'seed': seed, 'alpha': .05,
            'reject_conditional_pairing_null': bool(p_mc < .05)}
    return info, null, valid


def _save(fig, name):
    target = HERE / 'figures' / name
    target.parent.mkdir(exist_ok=True)
    fig.savefig(target, dpi=150, bbox_inches='tight', facecolor='white', metadata={'Software': 'Matplotlib'})
    plt.close(fig)


def make_figures(glyphs, writers, result, null, bootstrap):
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10,
                         'axes.spines.top': False, 'axes.spines.right': False,
                         'axes.titleweight': 'bold', 'axes.titlelocation': 'left',
                         'axes.labelcolor': '#243447', 'text.color': '#243447',
                         'axes.edgecolor': '#C7D3DD', 'grid.color': '#DEE6ED',
                         'axes.grid': True, 'grid.alpha': .6, 'legend.frameon': False,
                         'figure.facecolor': 'white', 'axes.facecolor': 'white'})
    samples = json.loads((HERE / 'data/samples.json').read_text(encoding='utf-8'))
    by_writer = {w: [s for s in samples if s['writer_id'] == w] for w in sorted(writers.writer_id)}
    chosen = [sorted(by_writer)[i] for i in np.linspace(0, len(by_writer)-1, 6, dtype=int)]
    selected = [s for w in chosen for s in sorted(by_writer[w], key=lambda v: v['repetition'])]
    extent = float(np.ceil(max(max(s['width_mm'], s['height_mm']) for s in selected))) + .5
    fig, axes = plt.subplots(3, 4, figsize=(11, 8), constrained_layout=True)
    for ax, sample in zip(axes.flat, selected):
        c = sample['ink_units_per_mm']
        for stroke in sample['strokes']:
            points = np.asarray(stroke, dtype=float)
            ax.plot((points[:, 0]-sample['x_min_ink'])/c,
                    (points[:, 1]-sample['y_min_ink'])/c, color=COLORS[sample['site']], linewidth=1.5)
        ax.set(xlim=(-.4, extent), ylim=(extent, -.4), aspect='equal')
        ax.set_title(f"{sample['writer_id']} · {sample['repetition']}", fontsize=8)
        ax.tick_params(labelsize=7)
        ax.set_xlabel('X, мм', fontsize=8); ax.set_ylabel('Y экрана, мм', fontsize=8)
    fig.suptitle('КТвД · Рисунок 1. Два повторения буквы a у шести авторов', fontsize=13)
    _save(fig, 'hw01-examples.png')

    fig, axes = plt.subplots(2, 2, figsize=(10, 7), constrained_layout=True)
    for col, (column, label) in enumerate([('width_mm', 'Ширина'), ('height_mm', 'Высота')]):
        values = glyphs[column].to_numpy()
        axes[0, col].hist(values, bins=np.histogram_bin_edges(values, bins='fd'),
                          color=COLORS['UJI'], edgecolor='white', linewidth=.6)
        axes[0, col].set(title=f'{label}: 120 записей', xlabel=f'{label}, мм', ylabel='Записи, шт.')
        xs, counts = np.unique(values, return_counts=True)
        pad = .03 * np.ptp(xs)
        axes[1, col].step(np.r_[xs[0]-pad, xs, xs[-1]+pad],
                          np.r_[0, np.cumsum(counts)/len(values), 1], where='post', color=COLORS['UJI'])
        axes[1, col].set(xlabel=f'{label}, мм', ylabel='Накопленная доля', ylim=(-.02, 1.02))
    fig.suptitle('КТвД · Рисунок 2. Распределения размеров и точные ECDF', fontsize=13)
    _save(fig, 'hw02-distributions.png')

    fig, axes = plt.subplots(1, 2, figsize=(10, 4.8), constrained_layout=True)
    limit = float(np.ceil(max(glyphs.width_mm.max(), glyphs.height_mm.max()))) + .5
    for _, pair in glyphs.groupby('writer_id', sort=True):
        axes[0].plot(pair.width_mm, pair.height_mm, color='#C7D3DD', linewidth=.7, zorder=1)
    for site, color in COLORS.items():
        g, w = glyphs[glyphs.site == site], writers[writers.site == site]
        axes[0].scatter(g.width_mm, g.height_mm, color=color, s=24, alpha=.8, label=f'{site}: {len(g)} записей', zorder=2)
        axes[1].scatter(w.width_mean_mm, w.height_mean_mm, color=color, s=30, alpha=.85, label=f'{site}: {len(w)} авторов')
    for ax, title in zip(axes, ['Все записи; линии соединяют повторы', 'Средние двух повторений каждого автора']):
        ax.set(title=title, xlabel='Ширина, мм', ylabel='Высота, мм', xlim=(0, limit), ylim=(0, limit), aspect='equal')
        ax.legend(fontsize=8)
    fig.suptitle('КТвД · Рисунок 3. Парные размеры и единица анализа', fontsize=13)
    _save(fig, 'hw03-pairs.png')

    fig, axes = plt.subplots(1, 2, figsize=(10, 4.8), constrained_layout=True)
    for site, color in COLORS.items():
        w = writers[writers.site == site]
        axes[0].scatter(w.width_mean_ink, w.height_mean_ink, color=color, s=30, alpha=.85, label=site)
        axes[1].scatter(w.width_mean_mm, w.height_mean_mm, color=color, s=30, alpha=.85, label=site)
    axes[0].set(title=f"Исходные шкалы: ρ = {result['association']['raw_pooled_spearman']:.3f}",
                xlabel='Ширина, ink units', ylabel='Высота, ink units')
    axes[1].set(title=f"Единые мм: ρ = {result['association']['pooled_spearman']:.3f}",
                xlabel='Ширина, мм', ylabel='Высота, мм', xlim=(0, limit), ylim=(0, limit))
    for ax in axes:
        ax.set_aspect('equal', adjustable='box'); ax.legend(fontsize=8)
    fig.suptitle('КТвД · Рисунок 4. Почему нельзя смешивать разные масштабы', fontsize=13)
    _save(fig, 'hw04-calibration.png')

    assoc = result['association']
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.8), constrained_layout=True)
    axes[0].hist(null, bins=40, color=COLORS['UJI'], edgecolor='white', linewidth=.3)
    axes[0].set(title=f"Перестановки внутри площадок; p = {assoc['permutation_p_two_sided']:.4f}",
                xlabel='Частная ранговая корреляция', ylabel='Перестановки, шт.')
    axes[1].hist(bootstrap, bins=40, color='#8DA8B8', edgecolor='white', linewidth=.3)
    axes[1].axvspan(*assoc['bootstrap_ci95'], color=COLORS['UJI'], alpha=.12, label='95% percentile-интервал')
    axes[1].set(title='Bootstrap авторов внутри площадок',
                xlabel='Частная ранговая корреляция', ylabel='Повторные выборки, шт.')
    for ax in axes:
        ax.axvline(0, color='#697A8C', linewidth=1, linestyle=':')
        ax.axvline(assoc['adjusted_rank_correlation'], color=COLORS['UPV'], linewidth=1.6, label='Наблюдаемая оценка')
        ax.set_xlim(-1, 1); ax.legend(fontsize=8)
    fig.suptitle('КТвД · Рисунок 5. Проверка связи и неопределённость оценки', fontsize=13)
    _save(fig, 'hw05-uncertainty.png')


def run_analysis(write_outputs=True):
    glyphs = pd.read_csv(HERE / 'data/glyphs.csv', float_precision='round_trip')
    writers = pd.read_csv(HERE / 'data/writer_means.csv', float_precision='round_trip')
    assert len(glyphs) == 120 and len(writers) == 60
    assert set(glyphs.character) == {'a'} and glyphs.groupby('writer_id').size().eq(2).all()
    assert glyphs[['width_mm', 'height_mm']].gt(0).all().all()
    x, y, sites = writers.width_mean_mm.to_numpy(), writers.height_mean_mm.to_numpy(), writers.site.to_numpy()
    assoc, null, bootstrap = dependence(x, y, sites)
    assoc.update({'raw_pooled_spearman': float(stats.spearmanr(writers.width_mean_ink, writers.height_mean_ink).statistic),
                  'pooled_spearman': float(stats.spearmanr(x, y).statistic),
                  'pooled_pearson': float(stats.pearsonr(x, y).statistic),
                  'site': {site: {'n_writers': int(np.sum(sites == site)),
                                  'spearman': float(stats.spearmanr(x[sites == site], y[sites == site]).statistic),
                                  'pearson': float(stats.pearsonr(x[sites == site], y[sites == site]).statistic)}
                           for site in sorted(set(sites))}})
    result = {
        'study': 'UJI Pen Characters 2: lowercase Latin a, width and height',
        'glyph_count': len(glyphs), 'writer_count': len(writers), 'repetitions_per_writer': 2,
        'units': 'screen millimetres, calibrated using site metadata',
        'summaries': {
            'glyphs': {'width_mm': summary(glyphs.width_mm), 'height_mm': summary(glyphs.height_mm)},
            'writers': {'width_mm': summary(x), 'height_mm': summary(y)}},
        'association': assoc,
        'source_zip_sha256': hashlib.sha256((HERE / 'data/uji_pen_characters_version2.zip').read_bytes()).hexdigest(),
        'versions': {p: importlib.metadata.version(p) for p in ['numpy', 'pandas', 'scipy', 'matplotlib']},
    }
    differences = glyphs.sort_values(['writer_id', 'repetition']).groupby('writer_id')[['width_ink', 'height_ink', 'width_mm', 'height_mm']].diff().dropna().abs()
    result['repeated_writing'] = {
        'writers_with_different_width': int(differences.width_ink.gt(0).sum()),
        'writers_with_different_height': int(differences.height_ink.gt(0).sum()),
        'median_absolute_width_difference_mm': float(differences.width_mm.median()),
        'median_absolute_height_difference_mm': float(differences.height_mm.median())}
    if write_outputs:
        (HERE / 'results.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        pd.DataFrame(result['summaries']['glyphs']).rename_axis('statistic').to_csv(HERE / 'statistics_glyphs.csv')
        pd.DataFrame(result['summaries']['writers']).rename_axis('statistic').to_csv(HERE / 'statistics_writers.csv')
        make_figures(glyphs, writers, result, null, bootstrap)
    return result


if __name__ == '__main__':
    result = run_analysis()
    print(json.dumps({'glyphs': result['glyph_count'], 'writers': result['writer_count'],
                      'association': result['association']}, ensure_ascii=False, indent=2))
