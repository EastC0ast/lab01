import marimo

__generated_with = "0.25.2"
app = marimo.App(width="medium", app_title="Лабораторная № 1 · Генерация сигнала NO₂")


@app.cell
def _():
    import sys
    from pathlib import Path
    _root=Path(__file__).resolve().parents[1]
    if str(_root) not in sys.path: sys.path.insert(0,str(_root))
    import marimo as mo
    import numpy as np
    import pandas as pd
    import matplotlib.pyplot as plt
    from scipy import stats
    from designer_generator.core import load_no2,fit_parameters,compare_models,generate,comparison_table,diagnostics,model_pdf,model_cdf
    return mo,np,pd,plt,stats,load_no2,fit_parameters,compare_models,generate,comparison_table,diagnostics,model_pdf,model_cdf


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # Лабораторная работа № 1 · Sprint 2
    ## Генерация сигнала датчика NO₂

    [1. Модель](#method) · [2. Параметры](#parameters) · [3. Результаты](#results)

    <a id="method"></a>

    ### 1. Модель и методы

    ASE_NO2 — усреднённый за час электрический сигнал датчика, мкВ.
    Наблюдения имеют левую асимметрию. Используется отражённая гамма-модель:

    $$
    X=b-\theta G,\qquad G\sim\Gamma(a,1),\quad a>1,\quad\theta>0,\quad X\leq b.
    $$

    Здесь a — форма, b — верхняя граница модели в мкВ, θ — масштаб в мкВ.
    Граница b оценивается по данным и не является паспортным пределом датчика.

    $$
    f_X(x)=\frac{1}{\theta\Gamma(a)}\left(\frac{b-x}{\theta}\right)^{a-1}
    e^{-(b-x)/\theta},\quad x<b;\qquad f_X(x)=0,\quad x\geq b.
    $$

    $$
    \mathrm E[X]=b-a\theta,\qquad\mathrm{Var}(X)=a\theta^2,\qquad\gamma_1=-2/\sqrt a.
    $$

    Сравниваются алгоритм А с предложением Коши и полный алгоритм GD с
    нормальным предложением и экспоненциальной оболочкой. Оба сначала
    генерируют G, затем применяют одно и то же отражение.

    В таблице 1 приведены альтернативные модели. Скошенная нормальная имеет
    меньший AIC; отражённая гамма выбрана как учебная аппроксимация для
    исследования двух гамма-генераторов. Она не объявляется истинным или
    лучшим законом сигнала. Независимые реализации воспроизводят одномерное
    распределение, а временную зависимость наблюдений не моделируют.
    """)
    return


@app.cell
def _(load_no2,fit_parameters,compare_models):
    no2=load_no2()
    fitted=fit_parameters(no2)
    models=compare_models(no2)
    return no2,fitted,models


@app.cell(hide_code=True)
def _(fitted,no2,mo):
    parameter_form=mo.ui.dictionary({
        'n':mo.ui.number(start=100,stop=20000,step=1,value=len(no2),label='Число значений N'),
        'seed':mo.ui.number(start=0,stop=4294967295,step=1,value=40,label='Начальное число (seed)'),
        'a':mo.ui.number(start=1.000001,stop=1000,value=fitted[0],label='Форма a > 1'),
        'b':mo.ui.number(start=-1e9,stop=1e9,value=fitted[1],label='Верхняя граница b, мкВ'),
        'theta':mo.ui.number(start=1e-6,stop=1e6,value=fitted[2],label='Масштаб θ > 0, мкВ')
    }).form(submit_button_label='Сгенерировать',show_clear_button=False)
    mo.vstack([mo.md("<a id='parameters'></a>\n\n### 2. Параметры\nНачальные значения оценены методом максимального правдоподобия. Измените параметры и нажмите «Сгенерировать»."),parameter_form])
    return (parameter_form,)


@app.cell
def _(parameter_form,fitted,no2,generate,mo,np):
    settings=parameter_form.value or dict(n=len(no2),seed=40,a=fitted[0],b=fitted[1],theta=fitted[2])
    mo.stop(any(v is None or not np.isfinite(v) for v in settings.values()),mo.md('Заполните все параметры конечными числами.'))
    _valid=(100<=settings['n']<=20000 and int(settings['n'])==settings['n'] and
            0<=settings['seed']<2**32 and int(settings['seed'])==settings['seed'] and
            1<settings['a']<=1000 and abs(settings['b'])<=1e9 and 1e-6<=settings['theta']<=1e6)
    mo.stop(not _valid,mo.md('Допустимы целые N от 100 до 20 000 и seed от 0 до 4 294 967 295; 1<a≤1000, |b|≤10⁹, 10⁻⁶≤θ≤10⁶.'))
    runs={method:generate(method,int(settings['n']),settings['a'],settings['b'],settings['theta'],int(settings['seed'])) for method in ['A','GD']}
    return settings,runs


@app.cell(hide_code=True)
def _(no2,runs,settings,model_pdf,model_cdf,np,plt,stats,mo):
    with plt.rc_context({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False,'axes.grid':True,'grid.alpha':.18}):
        figure,axes=plt.subplots(1,2,figsize=(11,4.1),constrained_layout=True)
        _all=np.r_[no2.to_numpy(),runs['A']['values'],runs['GD']['values']]
        _grid=np.linspace(_all.min()-10,max(_all.max()+10,settings['b']+5),600)
        for _values,_label,_color in [(no2.to_numpy(),'Данные','#64748b'),(runs['A']['values'],'Алгоритм А','#245c7a'),(runs['GD']['values'],'Алгоритм GD','#a57240')]:
            axes[0].plot(_grid,stats.gaussian_kde(_values)(_grid),label=_label,color=_color)
            _sorted=np.sort(_values)
            axes[1].step(_sorted,np.arange(1,len(_sorted)+1)/len(_sorted),where='post',label=_label,color=_color)
        _parameters=(settings['a'],settings['b'],settings['theta'])
        axes[0].plot(_grid,model_pdf(_grid,*_parameters),'--',color='#334155',label='Модель')
        axes[1].plot(_grid,model_cdf(_grid,*_parameters),'--',color='#334155',label='Модель')
        axes[0].set(title='1. Оценки плотности',xlabel='Сигнал ASE_NO2, мкВ',ylabel='Плотность, 1/мкВ')
        axes[1].set(title='2. Функции распределения',xlabel='Сигнал ASE_NO2, мкВ',ylabel='F(x)',ylim=(0,1.02))
        for _axis in axes: _axis.legend(fontsize=8)
    mo.vstack([mo.md("<a id='results'></a>\n\n### 3. Результаты\nРисунок 1 — данные, модель и две синтетические выборки. Кривые плотности сглажены; ступени ECDF построены по всем значениям."),figure])
    return


@app.cell(hide_code=True)
def _(models,runs,no2,settings,comparison_table,diagnostics,pd,mo):
    fit_table=pd.DataFrame([{'Модель':row['name'],'D к данным':row['D_data'],'AIC':row['AIC'],
                             'Среднее, мкВ':row['mean'],'SD, мкВ':row['std'],'Асимметрия':row['skew']} for row in models])
    metric_table=comparison_table(no2,runs,settings['a'],settings['b'],settings['theta'])
    performance=pd.DataFrame([{'Метод':name,'N':len(run['values']),'Кандидатов':run['proposals'],'Доля принятых, %':100*run['acceptance'],
                               'Кандидатов оболочки GD':run['hat_proposals'],'Время, с':run['seconds'],
                               **diagnostics(run['values'],settings['a'],settings['b'],settings['theta'],no2)} for name,run in runs.items()])
    mo.vstack([mo.md('**Таблица 1 — модели данных.** Меньшие D и AIC означают лучшее описательное согласие. D рассчитано после оценивания параметров и не является p-value. AIC указан для MLE; оценки методом моментов показаны отдельно.'),
               mo.ui.table(fit_table,selection=None,show_data_types=False),
               mo.md('**Таблица 2 — характеристики.** Дисперсия и SD выборок используют делитель n−1. В модели приведены теоретические моменты. Все моды повторяющихся значений перечислены; при уникальных значениях единственная эмпирическая мода отсутствует. Суммы приведены только при одинаковом N.'),
               mo.ui.table(metric_table,selection=None,page_size=15,show_data_types=False),
               mo.md('**Таблица 3 — работа алгоритмов.** D к модели характеризует генерацию заданного закона, D к данным — близость синтетической и наблюдаемой выборок. Время одного запуска зависит от компьютера; эффективность не доказывает качество модели.'),
               mo.ui.table(performance,selection=None,show_data_types=False),
               mo.md(f"Применено: N={int(settings['n'])}, seed={int(settings['seed'])}, a={settings['a']:.6g}, b={settings['b']:.6g} мкВ, θ={settings['theta']:.6g} мкВ. Одинаковые параметры и seed повторяют выборку.")])
    return


if __name__=='__main__':
    app.run()
