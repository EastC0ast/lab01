import marimo

__generated_with = "0.25.2"
app = marimo.App(width="medium", app_title="Лабораторная № 1 · Генератор команды")


@app.cell
def _():
    import sys
    from pathlib import Path

    # The app also works when marimo is launched outside the repository directory.
    _root = Path(__file__).resolve().parents[1]
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))
    import marimo as mo
    import numpy as np
    import pandas as pd
    import matplotlib.pyplot as plt
    from scipy import stats
    from designer_generator.core import load_no2, fit_parameters, generate, summary, diagnostics, SOURCE_COMMIT
    return SOURCE_COMMIT, diagnostics, fit_parameters, generate, load_no2, mo, np, pd, plt, stats, summary


@app.cell(hide_code=True)
def _(SOURCE_COMMIT, mo):
    mo.md(rf"""
    # Лабораторная работа № 1
    ## Интерактивное представление генератора команды

    **Прикладная статистика · КТвД**

    [1. Метод](#method) · [2. Параметры](#parameters) · [3. Результаты](#results)

    <a id="method"></a>
    ### 1. Метод и границы представления

    Исследуется одна величина — сигнал **ASE_NO2**. Параметры гамма-модели
    оцениваются по `ASE10.csv` тем же вызовом `scipy.stats.gamma.fit`, что у команды.
    Воспроизведены **алгоритм А** и **исходная реализация GD** из
    [ветки generator](https://github.com/EastC0ast/lab01/blob/{SOURCE_COMMIT}/lab01.ipynb).
    Обе функции перенесены посимвольно. Ветку generator не объединяли.

    Для параметров $a>1$, $\theta>0$ и $x>\ell$ заданная модель имеет плотность
    $$f(x)=\frac{{1}}{{\Gamma(a)\theta}}
    \left(\frac{{x-\ell}}{{\theta}}\right)^{{a-1}}
    \exp\!\left(-\frac{{x-\ell}}{{\theta}}\right).$$
    Здесь $a$ — форма, $\ell$ — сдвиг, $\theta$ — масштаб.
    Исходное обоснование выбора гамма-модели требует доработки командой:
    асимметрия сама по себе не доказывает этот закон распределения.

    **Замечание для согласования.** В коде GD возвращается
    $\ell+\theta(2a-x^2)$, а в описании метода — $\ell+\theta x^2$.
    Расхождение сохранено. Поэтому сходство кривых и скорость не служат
    подтверждением корректности GD. Ниже показаны диагностические показатели.
    Числовой сигнал не пересчитывается: единицы ASE_NO2 требуют подтверждения
    по описанию датчика (в исходной ветке указаны мкВ).
    """)
    return


@app.cell
def _(fit_parameters, load_no2):
    no2 = load_no2()
    fitted = fit_parameters(no2)
    return fitted, no2


@app.cell(hide_code=True)
def _(fitted, mo):
    n_control = mo.ui.number(start=100, stop=20000, step=100, value=1000, label="Число значений N")
    seed_control = mo.ui.number(start=0, stop=4294967295, step=1, value=40, label="Seed")
    shape_control = mo.ui.number(start=1.000001, stop=1000, value=fitted[0], label="Форма a (> 1, до 1000)")
    loc_control = mo.ui.number(start=-1e9, stop=1e9, value=fitted[1], label="Сдвиг loc")
    scale_control = mo.ui.number(start=.000001, stop=1e6, value=fitted[2], label="Масштаб scale (> 0)")
    parameter_form = mo.ui.dictionary({"n": n_control, "seed": seed_control, "a": shape_control,
                                       "loc": loc_control, "scale": scale_control}).form(
                                           submit_button_label="Сгенерировать", show_clear_button=False)
    mo.vstack([mo.md("<a id='parameters'></a>\n\n### 2. Параметры\nНачальные значения — оценка команды по исходным данным. Изменения применяются кнопкой."),
               parameter_form])
    return (parameter_form,)


@app.cell
def _(fitted, generate, mo, np, parameter_form):
    settings = parameter_form.value or {"n": 1000, "seed": 40, "a": fitted[0], "loc": fitted[1], "scale": fitted[2]}
    mo.stop(any(_value is None or not np.isfinite(_value) for _value in settings.values()),
            mo.md("Заполните все параметры конечными числовыми значениями и нажмите «Сгенерировать»."))
    _valid = (100 <= settings["n"] <= 20000 and int(settings["n"]) == settings["n"]
              and 0 <= settings["seed"] < 2**32 and int(settings["seed"]) == settings["seed"]
              and 1 < settings["a"] <= 1000 and abs(settings["loc"]) <= 1e9
              and 1e-6 <= settings["scale"] <= 1e6)
    mo.stop(not _valid, mo.md("Допустимы целые N от 100 до 20 000 и seed от 0 до 4 294 967 295; 1 < a ≤ 1000, |loc| ≤ 10⁹, 10⁻⁶ ≤ scale ≤ 10⁶."))
    generated_a = generate("A", int(settings["n"]), settings["a"], settings["loc"], settings["scale"], int(settings["seed"]))
    generated_gd = generate("GD", int(settings["n"]), settings["a"], settings["loc"], settings["scale"], int(settings["seed"]))
    return generated_a, generated_gd, settings


@app.cell(hide_code=True)
def _(generated_a, generated_gd, mo, no2, np, plt, settings, stats):
    with plt.rc_context({"font.family": "DejaVu Sans", "font.size": 10, "axes.spines.top": False,
                         "axes.spines.right": False, "axes.grid": True, "grid.alpha": .18,
                         "axes.labelcolor": "#263238", "text.color": "#263238"}):
        figure, axes = plt.subplots(1, 2, figsize=(11, 4.1), constrained_layout=True)
        _series = [(no2.to_numpy(), "Исходные данные", "#64748b"),
                   (generated_a["values"], "Алгоритм А", "#245c7a"),
                   (generated_gd["values"], "GD: исходный код", "#a57240")]
        _all = np.concatenate([_entry[0] for _entry in _series])
        _grid = np.linspace(_all.min(), _all.max(), 500)
        for _values, _label, _color in _series:
            axes[0].plot(_grid, stats.gaussian_kde(_values)(_grid), color=_color, label=_label, linewidth=1.6)
            _ordered = np.sort(_values)
            axes[1].step(_ordered, np.arange(1, len(_ordered) + 1) / len(_ordered), where="post", color=_color, label=_label)
        axes[0].plot(_grid, stats.gamma.pdf(_grid, settings["a"], settings["loc"], settings["scale"]),
                     color="#334155", linestyle="--", linewidth=1.3, label="Заданная гамма-модель")
        axes[0].set(title="1. Оценки плотности", xlabel="Сигнал ASE_NO2 (ед. исходных данных)", ylabel="Плотность (1 / ед. сигнала)")
        axes[1].set(title="2. Эмпирические функции распределения", xlabel="Сигнал ASE_NO2 (ед. исходных данных)", ylabel="Fₙ(x)", ylim=(0, 1.02))
        axes[0].legend(fontsize=8)
        axes[1].legend(fontsize=8)
    mo.vstack([mo.md("<a id='results'></a>\n\n### 3. Результаты\nРисунок 1 — сопоставление данных и генераторов. Плотности сглажены, функция распределения построена по всем наблюдениям."), figure])
    return


@app.cell(hide_code=True)
def _(diagnostics, generated_a, generated_gd, mo, no2, pd, settings, summary):
    summary_table = pd.DataFrame({"Исходные данные": summary(no2), "Алгоритм А": summary(generated_a["values"]),
                                 "GD: исходный код": summary(generated_gd["values"])}).rename_axis("Показатель").reset_index()
    performance_table = pd.DataFrame([
        {"Метод": _name, "N": len(_result["values"]), "Попыток": _result["attempts"],
         "Доля принятых, %": 100 * _result["acceptance"], "Время одного запуска, с": _result["seconds"],
         **diagnostics(_result["values"], settings["a"], settings["loc"], settings["scale"])}
        for _name, _result in [("А", generated_a), ("GD: исходный код", generated_gd)]
    ])
    mo.vstack([mo.md("**Таблица 1 — описательные характеристики.** Дисперсия и стандартное отклонение используют ddof=1, как у команды. Для суммы единицы совпадают с сигналом, для дисперсии — квадрат единиц сигнала; остальные характеристики имеют единицы сигнала."),
               mo.ui.table(summary_table, selection=None, page_size=12),
               mo.md("**Таблица 2 — работа генераторов и диагностика.** D — максимальное расстояние до заданной гамма-функции распределения. Показатель описательный; проверка гипотезы и p-value здесь не заявляются. Асимметрия и доля принятых безразмерны. Время одного запуска зависит от компьютера и не подтверждает превосходство метода."),
               mo.ui.table(performance_table, selection=None),
               mo.md(f"Применено: N={int(settings['n'])}, seed={int(settings['seed'])}, a={settings['a']:.6g}, loc={settings['loc']:.6g}, scale={settings['scale']:.6g}. Одинаковый seed повторяет выборки. У каждого алгоритма собственное состояние генератора случайных чисел.")])
    return


if __name__ == "__main__":
    app.run()
