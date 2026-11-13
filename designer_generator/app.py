import marimo

__generated_with = '0.25.2'
app = marimo.App(width='medium', app_title='Генератор сигнала NO₂')


@app.cell
def _():
    import marimo as mo
    import numpy as np
    import pandas as pd
    import matplotlib.pyplot as plt
    from scipy import stats
    from designer_generator.core import load_no2, fit_parameters, generate, comparison_table
    return mo, np, pd, plt, stats, load_no2, fit_parameters, generate, comparison_table


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # Генератор сигнала NO₂

    [Отчёт команды](https://github.com/EastC0ast/lab01/blob/design-layout/REPORT.md#sprint2)

    Задайте параметры и нажмите «Сгенерировать».
    """)
    return


@app.cell
def _(load_no2, fit_parameters):
    no2 = load_no2()
    fitted = fit_parameters(no2)
    return no2, fitted


@app.cell(hide_code=True)
def _(mo, fitted):
    parameter_form = mo.ui.batch(mo.md('''### Параметры

    {n}

    {seed}

    {a}

    {loc}

    {scale}
    '''), {
        'n': mo.ui.number(start=100, stop=20000, step=1, value=1000, label='Число значений N'),
        'seed': mo.ui.number(start=0, stop=4294967295, step=1, value=40, label='Начальное число (seed)'),
        'a': mo.ui.number(start=1.000001, stop=1000, value=fitted[0], label='Параметр формы a'),
        'loc': mo.ui.number(start=-1e9, stop=1e9, value=fitted[1], label='Сдвиг loc, мкВ'),
        'scale': mo.ui.number(start=1e-6, stop=1e6, value=fitted[2], label='Масштаб scale, мкВ'),
    }).form(submit_button_label='Сгенерировать', show_clear_button=False)
    parameter_form
    return (parameter_form,)


@app.cell
def _(parameter_form, fitted, mo, np, generate):
    settings = parameter_form.value or dict(n=1000, seed=40, a=fitted[0], loc=fitted[1], scale=fitted[2])
    mo.stop(any(v is None or not np.isfinite(v) for v in settings.values()), mo.md('Заполните все параметры.'))
    _valid = (100 <= settings['n'] <= 20000 and int(settings['n']) == settings['n'] and
              0 <= settings['seed'] < 2**32 and int(settings['seed']) == settings['seed'] and
              1 < settings['a'] <= 1000 and abs(settings['loc']) <= 1e9 and 1e-6 <= settings['scale'] <= 1e6)
    mo.stop(not _valid, mo.md('Проверьте значения параметров.'))
    runs = {method: generate(method, int(settings['n']), settings['a'], settings['loc'], settings['scale'], int(settings['seed']))
            for method in ('A', 'GD')}
    return settings, runs


@app.cell(hide_code=True)
def _(no2, runs, plt, np, stats, mo):
    with plt.rc_context({'font.family': 'DejaVu Sans', 'font.size': 10,
                         'axes.spines.top': False, 'axes.spines.right': False,
                         'axes.grid': True, 'grid.alpha': .18}):
        figure, axes = plt.subplots(figsize=(10, 4.5), constrained_layout=True)
        _all = np.r_[no2.to_numpy(), runs['A']['values'], runs['GD']['values']]
        _grid = np.linspace(_all.min(), _all.max(), 600)
        for _values, _label, _color in [(no2.to_numpy(), 'Реальные данные', '#64748b'),
                                         (runs['A']['values'], 'Алгоритм А', '#245c7a'),
                                         (runs['GD']['values'], 'Алгоритм GD', '#a57240')]:
            axes.plot(_grid, stats.gaussian_kde(_values)(_grid), label=_label, color=_color)
        axes.set(title='Сравнение сгенерированных данных', xlabel='Напряжение сенсора NO2 (мкВ)', ylabel='Плотность вероятности')
        axes.legend()
    mo.vstack([mo.md('### Результаты'), figure])
    return


@app.cell(hide_code=True)
def _(no2, runs, settings, comparison_table, pd, mo):
    metric_table = comparison_table(no2, runs)
    performance = pd.DataFrame([{
        'Метод': method, 'N': len(run['values']), 'Попыток': run['attempts'],
        'Эффективность, %': 100 * len(run['values']) / run['attempts'], 'Время, с': run['seconds'],
    } for method, run in runs.items()])
    mo.vstack([
        mo.ui.table(metric_table.reset_index(names='Показатель'), selection=None, show_data_types=False),
        mo.ui.table(performance, selection=None, show_data_types=False),
        mo.md(f"Применено: N={int(settings['n'])}, seed={int(settings['seed'])}, a={settings['a']:.6g}, loc={settings['loc']:.6g}, scale={settings['scale']:.6g}."),
    ])
    return


if __name__ == '__main__':
    app.run()
