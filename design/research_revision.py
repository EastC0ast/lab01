"""Build and execute the scientific revision from an immutable historical notebook."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import nbformat

ROOT = Path(__file__).resolve().parents[1]
BASELINE = 'ffeba64ab3fea83f163979760deb0b39ba77c419'
BASELINE_BLOB = 'ea1112e8a9bd0b39de4de3d73788fc2ab503d27f'
SOURCE_URL = 'https://data.mendeley.com/datasets/82dnstrd93/2'

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from design.research_stats import load_data, association_summary, sampling_diagnostics


def number(x, digits=3):
    return f'{x:.{digits}f}'.replace('.', ',')


def section(anchor, heading, body):
    return f'<a id="{anchor}" name="{anchor}" class="lab-anchor"></a>\n\n{heading}\n\n{body.strip()}\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    raw = subprocess.check_output(['git', 'show', BASELINE + ':lab01_calculations.ipynb'], cwd=ROOT)
    blob = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
    assert blob == BASELINE_BLOB
    csv_hash = hashlib.sha256((ROOT / 'ASE10.csv').read_bytes()).hexdigest()
    notebook = nbformat.reads(raw.decode('utf-8'), as_version=4)
    by_id = {c.id: c for c in notebook.cells}
    metadata = copy.deepcopy(by_id['design-style'].metadata)
    metadata.pop('execution', None)
    changed, inserted = [], []

    def replace(cell_id, source):
        by_id[cell_id].source = source.strip() + '\n'
        changed.append(cell_id)

    def add_after(cell_id, additions):
        at = next(i for i, c in enumerate(notebook.cells) if c.id == cell_id) + 1
        cells = []
        for new_id, kind, source in additions:
            constructor = nbformat.v4.new_code_cell if kind == 'code' else nbformat.v4.new_markdown_cell
            cell = constructor(source=source.strip() + '\n', id=new_id,
                               metadata=copy.deepcopy(metadata) if kind == 'code' else {})
            cell.metadata['id'] = new_id
            cells.append(cell)
            by_id[new_id] = cell
            inserted.append(new_id)
        notebook.cells[at:at] = cells

    frame = load_data(ROOT / 'ASE10.csv')
    diagnostics = {column: sampling_diagnostics(frame[column].dropna()) for column in ('ASE_NO2', 'ASE_T', 'ASE_CO')}
    association = association_summary(frame)
    common = frame[['ASE_NO2', 'ASE_T', 'ASE_CO']].dropna()

    replace('design-style', by_id['design-style'].source.replace(
        '# Оформление отчёта. Расчётные ячейки ниже оставлены без изменений.', '# Единый стиль рисунков и таблиц.').replace(
        '"semibold"', '"bold"'))
    replace('design-data', section('data', '## 1 · Исходные данные', f'''
Используется файл `ASE10.csv` из набора [Air quality low-cost sensors and monitoring stations NO2 raw dataset in Rouen (France)]({SOURCE_URL}), Mendeley Data, версия 2, DOI [10.17632/82dnstrd93.2](https://doi.org/10.17632/82dnstrd93.2), CC BY 4.0. Описание эксперимента: [Thulliez et al., Data in Brief, 2023](https://doi.org/10.1016/j.dib.2023.109398).

Это почасовые средние узла AirSensEUR №10 в Руане за 20.10.2021–25.03.2022. `date` задан в UTC. `ASE_NO2` и `ASE_CO` — сырые электрические сигналы каналов, мкВ, а не откалиброванные концентрации газов. `ASE_T` — температура **внутри узла**, °C, а не отдельное измерение температуры наружного воздуха. Узел находился на площадках SUD3 и QDP; `Location` указывает его положение в соответствующий час.

В файле 3739 строк. По каждому каналу исключаются только его пропуски: остаются 3686 значений NO₂, 3736 температур и 3686 значений CO. Для совместной связи трёх каналов используются {len(common)} полных строк. Пропуски не заменяются нулями. Смешение площадок и смена сезона могут менять распределения; поэтому приведены общая сводка и коэффициенты отдельно по `Location`.

Под «всей совокупностью» далее понимается **конечный набор доступных значений данного файла**. Выборки из 600 элементов описывают этот набор; они не являются основанием автоматически переносить выводы на будущие часы или другие города.
'''))
    replace('57204573-447d-49c1-8280-6a9420145ea1', '''
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from scipy import stats
from IPython.display import display
from design.research_stats import (load_data, metrics, print_metrics, mode_text, plot_ecdf,
    minmax, compare_samples, sampling_diagnostics, iid_normality, joint_hours,
    association_summary, location_summary, lag_diagnostics, fitted_models, display_table)
pd.set_option('display.max_colwidth', None)
sensors = load_data(Path('ASE10.csv'))
model_fits = fitted_models(sensors.ASE_NO2.dropna(), sensors.ASE_T.dropna(), sensors.ASE_CO.dropna())
display(sensors.head(5))
''')
    add_after('57204573-447d-49c1-8280-6a9420145ea1', [
        ('research-context-heading', 'markdown', '''Числа доступных значений по каналам отличаются из-за пропусков.

Соседние часы не следует считать независимыми только потому, что это разные строки. В таблице 03 приведена описательная корреляция каждого канала с предыдущим часом: учитываются только соседние UTC-часы на одной площадке без пропусков. Это диагностика временной структуры, а не дополнительная проверка гипотезы.'''),
        ('research-context-summary', 'code', '''display_table(location_summary(sensors), 2, 'Площадки и доступные наблюдения')
display_table(lag_diagnostics(sensors), 3, 'Связь соседних часов; коэффициенты безразмерны')''')])

    definitions = [
        ('no2', 'ASE_NO2', 'no2', 'Сигнал NO₂', 'мкВ',
         '2d94d0e9-bbb0-4f49-99e7-5b43f94eb941', 'e183f3df-185e-4eae-960f-8f9c3ac4a105',
         '4c54c438-02d3-4ff6-9f4a-e14b106e19d0', 'b4407c30-dd23-42c6-94b6-734b42d3296c',
         'c15de02f-d7b5-49e3-a535-918b4ee6c920', 'fb083562-dfb8-4e7f-8fa5-c35273523cad',
         '865b3883-e220-4fa6-8dff-805991565771', 'f9ed8ed9-63a6-475c-8266-0d7b72ec0cbd'),
        ('temp', 'ASE_T', 'temp', 'Температура внутри узла', '°C',
         'b39ae66f-e6ba-45a2-a5f8-d8c2f939e484', '6d003cbd-d697-4bc2-8530-860b4c7f290c',
         'c2480eee-2d9b-405a-aa93-3031c35377f6', '1ff94e9c-4b3c-49d7-a7b7-2b8ffda3070a',
         'a82ebb55-0840-4e70-bff6-c10774592b37', 'f3a7e8a5-947f-4682-a070-1cef8be711a0',
         '0a95a4b5-f5b5-460a-b087-6458ec294fe9', '4e96fd0b-7fd8-44fc-86f6-3607e065fff1'),
        ('co', 'ASE_CO', 'co', 'Сигнал CO', 'мкВ',
         '19c75d09', '773b9537', '22a68f8a', 'a98aa826', '66c7f26a', 'bbc98ecb',
         '1e9e466e', '4eb1624e')]
    for index, (prefix, column, variable, label, unit, desc_id, eda_id, test_id, norm_id,
                means_id, sample_id, sample_intro, conclusion_id) in enumerate(definitions, 2):
        index = 5 if prefix == 'co' else index
        context = ('электрический сигнал электрохимического канала. Он зависит от состава среды, '
                   'температурной чувствительности и шума измерительного тракта; без калибровки это не концентрация газа'
                   if column != 'ASE_T' else 'температура внутри корпуса узла, а не наружного воздуха. На неё могут влиять внешние условия и работа самого устройства')
        replace(desc_id, section(prefix + '-description', f'### {index}.1 · Description', f'''
Случайная величина — {label.lower()} (`{column}`), измеряемая в {unit}. В эмпирическом опыте равновероятно выбирается один из доступных для канала часов наблюдения. Это {context}.

По названию канала и времени нельзя однозначно вычислить ещё не наблюдавшееся показание: конкретное значение зависит от состояния среды и измерительной системы. После измерения число уже известно, но случайным остаётся выбор наблюдения из конечного набора. Такая модель не требует утверждать, что физический процесс принципиально не может иметь детерминированного описания.
'''))
        replace(eda_id, f'''
{variable} = sensors['{column}'].dropna()
print(f"Всего строк: {{len(sensors)}}; доступных значений: {{len({variable})}}; пропусков: {{sensors['{column}'].isna().sum()}}")
fig, ax = plt.subplots()
sns.histplot({variable}, bins=20, kde=True, ax=ax)
ax.set(title='{label}: распределение', xlabel='{label}, {unit}', ylabel='Наблюдения, шт.')
plt.show()
fig, ax = plt.subplots()
plot_ecdf(ax, {variable})
ax.set(title='{label}: эмпирическая функция распределения', xlabel='{label}, {unit}', ylabel='Накопленная доля', ylim=(-.02, 1.02))
plt.show()
print_metrics({variable})
print('Выборочная асимметрия:', {variable}.skew())
''')
        test_source = f'normality_{variable} = iid_normality({variable})'
        if column != 'ASE_CO':
            table_number = 4 if column == 'ASE_NO2' else 6
            test_source += f"\ndisplay_table(model_fits[model_fits['Канал'] == '{column}'].reset_index(drop=True), {table_number}, '{label}: параметры моделей и AIC')"
        replace(test_id, test_source)
        replace('design-' + prefix + '-test', section(prefix + '-test', f'#### {index}.2.2 · Проверка гипотезы нормальности', r'''
$H_0$: одномерное распределение нормально; $H_1$: оно отличается от нормального. Уровень значимости $\alpha=0{,}05$. Применяется критерий Д’Агостино—Пирсона (`normaltest`), объединяющий информацию об асимметрии и эксцессе.

В **iid-модели** предполагаются независимые одинаково распределённые наблюдения. Приведённый p-value рассчитан именно в этой модели. В почасовом временном ряду наблюдения зависимы и объединены разные условия, поэтому это учебная модельная проверка, а не достоверная оценка вероятности для всего физического процесса. Отклонение нормальности не доказывает асимметрию, конкретное семейство распределений или причину отклонения. Параметры подогнанных моделей и AIC ниже описывают приближения к наблюдаемому набору.'''))
        replace(norm_id, f'''
{variable}_normalized = minmax({variable})
fig, ax = plt.subplots()
sns.histplot({variable}_normalized, bins=20, kde=True, ax=ax)
ax.set(title='{label}: min–max-преобразование', xlabel='Нормализованное значение, безразмерное', ylabel='Наблюдения, шт.')
plt.show()
print('Минимум:', {variable}_normalized.min())
print('Максимум:', {variable}_normalized.max())
print('Среднее:', {variable}_normalized.mean())
''')
        replace(means_id, f'''
sampling_{variable} = sampling_diagnostics({variable}, n=600, seed=40)
fig, ax = plt.subplots()
ax.plot(sampling_{variable}['sizes'], sampling_{variable}['means'], label='Среднее префикса')
ax.axhline({variable}.mean(), linestyle='--', label='Среднее всех доступных значений')
ax.set(title='{label}: накопленное среднее', xlabel='Размер префикса, наблюдений', ylabel='Среднее, {unit}')
ax.legend()
plt.show()
''')
        replace(sample_id, f'''display(compare_samples({variable}, n=600, seed=40))''')
        diag = diagnostics[column]
        replace(sample_intro, f'''После одной случайной перестановки строк (`random_state=40`) среднее префикса приближается к среднему конечного набора. При размерах от 600 максимальное отклонение на показанном графике равно {number(diag['max_deviation_after_n'], 6)} {unit}. Это эмпирическая иллюстрация устойчивости среднего в данном наборе, а не доказательство независимости исходных часов или универсальная гарантия точности для любого набора из 600 элементов.

Для сопоставления выбраны по 600 значений с возвращением и без него. В таблице приведены объём и все рассчитанные характеристики. Суммы наборов разной длины непосредственно не сравниваются как оценка качества выборки.''')
        mean_err = diag['mean_relative_errors_pct']
        variance_err = diag['variance_relative_errors_pct']
        if column == 'ASE_T':
            reference_mean = frame[column].mean()
            mean_sentence = (f'Среднее в выборке без возвращения отличается от среднего конечного набора на '
                             f'{number(reference_mean * mean_err[0] / 100, 4)} °C, с возвращением — на '
                             f'{number(reference_mean * mean_err[1] / 100, 4)} °C. '
                             'Для температуры разность указана в °C: процент от среднего по шкале Цельсия зависит от выбора нуля шкалы.')
        else:
            mean_sentence = (f'Среднее в выборке без возвращения отличается от среднего конечного набора на '
                             f'{number(mean_err[0], 4)}%, с возвращением — на {number(mean_err[1], 4)}%.')
        replace(conclusion_id, section(prefix + '-conclusion', '**Вывод по сравнению выборок**', f'''
{mean_sentence} Соответствующие отличия выборочной дисперсии: {number(variance_err[0], 3)}% и {number(variance_err[1], 3)}%. Разные показатели могут быть ближе в разных выборках, поэтому общего превосходства одного подхода этот единственный опыт не устанавливает.

Дублирование строк при выборе с возвращением само по себе не объясняет направление изменения дисперсии. Экстремумы и эмпирические моды чувствительны к составу выборки. Если все значения уникальны, выделенная мода отсутствует; при совпадении максимальных частот перечислены все равноправные моды.

Размер 600 даёт показанное описательное приближение к данным этого файла. Вывод не переносится автоматически на будущие часы, другие площадки или откалиброванные концентрации газов. Использованные $s^2$ и $s$ имеют делитель $n-1$; это выборочные характеристики, а не дисперсия конечной эмпирической совокупности с делителем $N$.'''))

    skew_formula = r'''Для описания асимметричной формы рассматривается семейство skew-normal:

$$f(x)=\frac{2}{\omega}\phi\!\left(\frac{x-\xi}{\omega}\right)\Phi\!\left(\alpha\frac{x-\xi}{\omega}\right),\quad x\in\mathbb R,\quad\omega>0.$$

Здесь $\phi$ и $\Phi$ — плотность и функция стандартного нормального распределения; $\xi$ — сдвиг, $\omega$ — масштаб, $\alpha$ — параметр формы. При $\alpha=0$ получается нормальный закон. Параметр $\xi$ в общем случае не равен математическому ожиданию. Семейство — описательная аппроксимация, а не установленный физический закон. Наличие множества факторов само по себе не доказывает нормальность: центральная предельная теорема требует условий для сумм случайных величин.

Параметры оцениваются максимальным правдоподобием. Сравнение AIC проводится на одних и тех же наблюдениях: $AIC=2k-2\sum_i\log f(x_i;\widehat\theta)$; меньший AIC предпочтителен **среди сравниваемых моделей**, но не доказывает абсолютную правильность модели.'''
    replace('04e608b0-f94b-43c8-b26e-8e4319fd5bde', section('no2-model', '#### 2.2.1 · Математическая база распределения', skew_formula + r'''

В наблюдаемом сигнале NO₂ левый хвост выражен сильнее; это описывается знаком выборочной асимметрии. Направление хвоста электрического сигнала не переносится напрямую на концентрацию газа без модели калибровки. Для сопоставления приведены normal, skew-normal и отражённая гамма-модель $X=b-\theta G$, где $G\sim\Gamma(a,1)$, $a>0$, $\theta>0$, $x<b$:

$$f_X(x)=\frac{(b-x)^{a-1}\exp[-(b-x)/\theta]}{\Gamma(a)\theta^a},\quad x<b.$$

В таблице параметры normal записаны как $(\mu,\sigma)$, skew-normal — $(\alpha,\xi,\omega)$, отражённой gamma — $(a,b,\theta)$. В данном наборе наименьший AIC среди этих кандидатов у skew-normal; отражённая gamma несколько уступает ей по AIC. Сравнение не требует объявлять одну из моделей истинной. В интерактивном генераторе используется отражённая гамма-аппроксимация; её выбор является отдельным допущением генератора.'''))
    replace('d1c6c11e-3770-4c14-800f-089d5e43a092', section('temp-model', '#### 3.2.1 · Математическая база распределения', skew_formula + r'''

Для температуры внутри узла сравниваются normal и skew-normal. Распределение объединяет разные часы, сезоны и места установки. Небольшая асимметрия или несколько особенностей гистограммы не устанавливают ни конкретную причину, ни точный теоретический закон. Таблица параметров и AIC характеризует только выбранные аппроксимации. Порядок параметров normal — $(\mu,\sigma)$, skew-normal — $(\alpha,\xi,\omega)$.'''))
    replace('451919d0', section('co-model', '#### 5.2.1 · Математическая база распределения', r'''
Сигнал CO имеет выраженный правый хвост. Сравниваются skew-normal (плотность определена в §2.2.1) и сдвинутое логнормальное распределение:

$$f(x)=\frac{1}{(x-\ell)s\sqrt{2\pi}}\exp\!\left[-\frac{\{\ln[(x-\ell)/q]\}^2}{2s^2}\right],\qquad x>\ell,\ s>0,\ q>0.$$

$\ell$ — сдвиг в мкВ, $q$ — масштаб в мкВ, $s$ — безразмерный параметр формы. Эквивалентно, $\ln[(X-\ell)/q]\sim N(0,s^2)$. Правый хвост делает эту модель кандидатом, но не доказывает её истинность и не объясняет физическую причину наблюдаемой асимметрии. Подгонка обеих моделей и сравнение AIC выполняются на одном наборе значений.'''))

    replace('4a4d9d4c', '''
co_skew = model_fits.query("Канал == 'ASE_CO' and Модель == 'skew-normal'").iloc[0]
co_lognormal = model_fits.query("Канал == 'ASE_CO' and Модель == 'lognormal'").iloc[0]
alpha_co, xi_co, omega_co = co_skew['Параметры']
shape_co, shift_co, scale_co = co_lognormal['Параметры']
grid_co = np.linspace(co.min(), co.max(), 500)
fig, ax = plt.subplots()
sns.histplot(co, stat='density', bins=20, ax=ax, color='#C8D5DE', label='Данные')
ax.plot(grid_co, stats.skewnorm.pdf(grid_co, alpha_co, xi_co, omega_co), label='skew-normal')
ax.plot(grid_co, stats.lognorm.pdf(grid_co, shape_co, shift_co, scale_co), label='lognormal')
ax.set(title='Сигнал CO: сравнение моделей', xlabel='Сигнал CO, мкВ', ylabel='Плотность, 1/мкВ')
ax.legend()
plt.show()
''')
    replace('design-co-test-repeat', section('co-test-repeat', '#### 5.2.4 · Результат сравнения моделей', r'''В таблице порядок параметров skew-normal — $(\alpha,\xi,\omega)$, lognormal — $(s,\ell,q)$. Обе модели имеют по три оцениваемых параметра.'''))
    replace('8f87c64d', '''
display_table(model_fits[model_fits['Канал'] == 'ASE_CO'].reset_index(drop=True), 9, 'Сигнал CO: параметры моделей и AIC')
print(f"AIC lognormal меньше AIC skew-normal на {co_skew['AIC'] - co_lognormal['AIC']:.6f}.")
print('По AIC среди этих двух кандидатов предпочтительна lognormal. Это не проверка абсолютного согласия модели.')
print(f'Логнормальная модель: s={shape_co:.9g}; сдвиг={shift_co:.9g} мкВ; масштаб={scale_co:.9g} мкВ.')
''')
    replace('02e156e0-ec01-4727-9f0f-490a650301cf', section('rv-temp', '## 3 · Random Variable 02: Температура внутри узла (ASE_T)', ''))
    for prefix, cell_id, index in [('no2', 'a60db57f-72a4-4cd8-8727-c8d1f008b665', 2),
                                    ('temp', '448273ef-b9d0-48f2-9c37-8c4cc841cdc6', 3),
                                    ('co', '95394a95', 5)]:
        replace(cell_id, section(prefix + '-estimates', f'### {index}.3 · Independence & Estimations',
                                'Рассмотрим поведение среднего при росте префикса случайной перестановки конечного набора. Это эмпирическая иллюстрация устойчивости оценки среднего; независимость исходных часов такой перестановкой не проверяется.'))

    replace('49e08406-998e-4891-8b7f-5595163051af', section('dependence', '## 4 · Совместная связь трёх каналов', r'''
Рассматривается конечная совместная совокупность часов, в которых доступны все три канала. Случайный опыт — равновероятный выбор одной из этих строк. Для каждой пары вычисляется ковариация **эмпирического распределения** с делителем $N$:

$$Cov_N(X,Y)=\frac1N\sum_{i=1}^N(x_i-\bar x)(y_i-\bar y).$$

Независимость влечёт нулевую ковариацию при конечных вторых моментах. Следовательно, ненулевая ковариация устанавливает зависимость **в определённом конечном эмпирическом распределении**. Обратное неверно: нулевая корреляция не доказывает независимость. Для этого описания полного набора не требуется считать соседние часы независимой выборкой.

Pearson характеризует линейную связь, Spearman — ранговую. Коэффициенты рассчитаны по всем полным строкам и отдельно по площадкам. Для переноса на будущий процесс понадобятся дополнительные предпосылки о времени, сезонности и способе наблюдения. В этом разделе p-value для такого переноса не заявляется; причинность по корреляциям не устанавливается.'''))
    replace('design-dependence-test', section('dependence-test', '### 4.1 · Ковариации и коэффициенты', '<a id="research-table08" name="research-table08"></a>\n\n**Таблица 08 · Все три пары и обе площадки.** Число N относится к полным строкам совместного набора, а не ко всем доступным значениям каждого канала по отдельности.'))
    replace('454e8ad1-efd9-4441-a484-cbf0b6a3d8fc', '''
df_corr = joint_hours(sensors)
association_results = association_summary(sensors)
display(association_results)
print('Полных совместных часов:', len(df_corr))
print('Ненулевые Cov_N означают зависимость в эмпирическом распределении равновероятно выбранного полного часа.')
''')
    scatter_code = '''
fig, ax = plt.subplots()
for location, marker in [('SUD3', 'o'), ('QDP', 's')]:
    group = df_corr[df_corr.Location == location]
    ax.scatter(group.ASE_T, group.ASE_NO2, marker=marker, s=15, alpha=.4, label=location)
sns.regplot(data=df_corr, x='ASE_T', y='ASE_NO2', scatter=False, ci=None, ax=ax, line_kws={'label': 'Линия тренда'})
ax.set(title='Сигнал NO₂ и температура внутри узла', xlabel='Температура внутри узла, °C', ylabel='Сигнал NO₂, мкВ')
ax.legend()
plt.show()
'''
    replace('ba684c7e-cb7d-4dc7-af7a-7ff144a5fa3d', scatter_code)
    replace('93582a9c-3d91-4a11-a215-c8ba363a56dd', '''
fig, ax = plt.subplots()
corr_matrix = df_corr[['ASE_NO2', 'ASE_T', 'ASE_CO']].corr()
sns.heatmap(corr_matrix, annot=True, cmap='coolwarm', vmin=-1, vmax=1, fmt='.3f', ax=ax)
ax.set(title=f'Описательная матрица Pearson: {len(df_corr)} полных часов')
plt.show()
''')
    full_association = association[association['Набор'] == 'Обе площадки']
    observations_text = '\n'.join(f"- {row['Пара']}: Pearson {number(row['Pearson r'], 4)}, Spearman {number(row['Spearman ρ'], 4)}; $Cov_N={number(row['Cov_N'], 6)}$ {row['Единица Cov_N']}." for _, row in full_association.iterrows())
    replace('a3260c44-c4f1-49d4-b4b0-a9d246e61b77', section('dependence-conclusion', '### 4.3 · Вывод по совместной связи', f'''
{observations_text}

Ковариации всех трёх пар ненулевые, поэтому в выбранном эмпирическом распределении есть зависимость, в том числе между двумя газовыми каналами NO₂ и CO. Знак и величина связи по площадкам могут различаться; объединённый коэффициент смешивает эти условия. Линия тренда описывает данные и не доказывает влияние температуры на концентрацию газа.

Температура измеряется внутри узла, газовые каналы не откалиброваны в концентрации. Поэтому отсюда нельзя вывести, что холод, прогрев автомобилей или направление химического отклика вызвали обнаруженную связь. Почасовая зависимость, смена места установки и сезонность ограничивают обобщение. [Связь CO с остальными каналами показана на рисунке 16](#fig16).
'''))
    add_after('4eb1624e', [
        ('research-co-pairs-heading', 'markdown', section('co-dependence', '### 5.4 · Связь CO с NO₂ и температурой внутри узла', '''Используется тот же совместный набор полных часов, что в разделе 4. Разные маркеры обозначают площадку. Газовые каналы показаны в мкВ, а не в единицах концентрации.

<a id="fig16" name="fig16" class="lab-anchor"></a>

**Рисунок 16 · CO и остальные каналы.**''')),
        ('research-co-pairs', 'code', '''
fig, axes = plt.subplots(1, 2)
for location, marker in [('SUD3', 'o'), ('QDP', 's')]:
    group = df_corr[df_corr.Location == location]
    axes[0].scatter(group.ASE_NO2, group.ASE_CO, marker=marker, s=15, alpha=.4, label=location)
    axes[1].scatter(group.ASE_T, group.ASE_CO, marker=marker, s=15, alpha=.4, label=location)
axes[0].set(title='CO и NO₂', xlabel='Сигнал NO₂, мкВ', ylabel='Сигнал CO, мкВ')
axes[1].set(title='CO и температура внутри узла', xlabel='Температура внутри узла, °C', ylabel='Сигнал CO, мкВ')
for ax in axes: ax.legend()
plt.show()
''')])
    replace('94143416-7b3d-4aac-a84f-ebe5a61726cf', section('resume', '## 6 · Lab resume', '''
Исследованы три величины: сырые сигналы NO₂ и CO в мкВ и температура внутри узла в °C. Для каждого канала определён опыт выбора доступного часа из файла, рассчитаны описательные статистики, построены гистограмма, точная ECDF без округления и min–max-преобразование.

Показано поведение среднего при росте префикса случайной перестановки. Две выборки по 600 элементов сравнивались с конечным набором значений; их различия не дают универсального преимущества выборке с возвращением или без него. Суммы учитывают разный объём, а все равноправные моды перечислены; для уникальных значений выделенной моды нет.

Normaltest даёт отклонение нормальности в учебной iid-модели всех трёх каналов. Это не доказывает асимметрию, точный закон или физическую причину: исходные часы зависимы и условия неоднородны. Skew-normal и отражённая gamma для NO₂, normal/skew-normal для температуры и lognormal/skew-normal для CO рассматриваются как описательные аппроксимации. Для CO меньший AIC у lognormal в сравнении двух заданных кандидатов.

На едином наборе полных часов рассчитаны ковариации и Pearson/Spearman всех трёх пар, в том числе NO₂–CO. Ненулевые Cov_N показывают зависимость в конечном эмпирическом распределении выбора часа. Различия по площадкам и связь соседних часов приведены явно. Из этих результатов не следуют причинные выводы или гарантии для будущих измерений, а электрические сигналы нельзя без калибровки подменять концентрациями газов.
'''))
    # Existing sample-table anchors remain stable, while visible numbering follows
    # the reading order. New tables have disjoint semantic anchors.
    replace('48bdb9e6-fa2b-4e33-a9e8-bf1a72ab8857',
            by_id['48bdb9e6-fa2b-4e33-a9e8-bf1a72ab8857'].source.replace(
                'Сигнал сенсора температуры (ASE_T)', 'Температура внутри узла (ASE_T)').replace(
                'Зависимость NO2 от температуры', 'Совместная связь трёх каналов').replace(
                '| lab.ic.01.05 | Математическая база распределения: [NO2](#no2-model), [ASE_T](#temp-model), [CO](#co-model)',
                '| lab.ic.01.05 | Нормализация: [NO2](#no2-normalization), [ASE_T](#temp-normalization), [CO](#co-normalization)').replace(
                '| lab.ic.01.11 | Математическая база распределения: [NO2](#no2-model), [ASE_T](#temp-model), [CO](#co-model)',
                '| lab.ic.01.11 | Проверка гипотезы нормальности: [NO2](#no2-test), [ASE_T](#temp-test), [CO](#co-test)'))
    for cell_id, anchor, visible_number, label, unit in [
            ('design-table02', 'table02', 5, 'Сравнение выборок NO₂', 'мкВ'),
            ('design-table03', 'table03', 7, 'Сравнение выборок температуры внутри узла', '°C'),
            ('design-table04', 'table04', 10, 'Сравнение выборок CO', 'мкВ')]:
        replace(cell_id, section(anchor, f'**Таблица {visible_number:02d} · {label}**',
                                f'Объём измеряется в наблюдениях, характеристики значений — в {unit}, дисперсия — в ({unit})².'))
    figure_index = by_id['design-figure-index'].source.split('[Таблица 01')[0].rstrip()
    table_links = [
        ('table01', '01 · Первые пять строк исходного датасета'),
        ('research-table02', '02 · Площадки и доступные наблюдения'),
        ('research-table03', '03 · Связь соседних часов'),
        ('research-table04', '04 · Модели сигнала NO₂'),
        ('table02', '05 · Сравнение выборок NO₂'),
        ('research-table06', '06 · Модели температуры внутри узла'),
        ('table03', '07 · Сравнение выборок температуры внутри узла'),
        ('research-table08', '08 · Совместная связь трёх каналов'),
        ('research-table09', '09 · Модели сигнала CO'),
        ('table04', '10 · Сравнение выборок CO')]
    replace('design-figure-index', figure_index + '\n\n[Рисунок 16: CO и остальные каналы](#fig16)  \n\n'
            + '\n'.join(f'[Таблица {label}](#{anchor})  ' for anchor, label in table_links)
            + '\n\n<nav class="lab-nav" aria-label="Навигация по отчёту"><a href="#resume">← Итоги</a><a href="#contents">↑ Оглавление</a></nav>')
    for cell in notebook.cells:
        if cell.cell_type == 'code':
            cell.outputs = []
            cell.execution_count = None
            cell.metadata.pop('execution', None)
    nbformat.validate(notebook)
    path = ROOT / 'design/sprint1_calculations.ipynb'
    nbformat.write(notebook, path)
    if args.execute:
        from nbclient import NotebookClient
        from jupyter_client import KernelManager
        from jupyter_client.kernelspec import KernelSpec
        bootstrap = nbformat.v4.new_code_cell(
            "get_ipython().run_line_magic('matplotlib', 'inline')\n"
            "import logging\nlogging.getLogger('matplotlib.font_manager').setLevel(logging.ERROR)",
            id='research-execution-environment')
        notebook.cells.insert(0, bootstrap)
        manager = KernelManager(kernel_name='python3')
        manager._kernel_spec = KernelSpec(argv=[sys.executable, '-m', 'ipykernel_launcher', '-f', '{connection_file}'], display_name='Research', language='python')
        try:
            NotebookClient(notebook, km=manager, timeout=240,
                           resources={'metadata': {'path': str(ROOT)}}).execute()
        finally:
            if manager.has_kernel:
                manager.shutdown_kernel(now=True)
        notebook.cells.pop(0)
        nbformat.validate(notebook)
        stderr = [(c.id, o.text) for c in notebook.cells for o in c.get('outputs', [])
                  if o.output_type == 'stream' and o.get('name') == 'stderr' and o.text.strip()]
        assert not stderr, ('Review notebook stderr before publication', stderr)
        nbformat.write(notebook, path)
    assert hashlib.sha256((ROOT / 'ASE10.csv').read_bytes()).hexdigest() == csv_hash
    outputs = [o for c in notebook.cells for o in c.get('outputs', [])]
    result = {'historical_commit': BASELINE, 'historical_notebook_blob': BASELINE_BLOB,
              'notebook': 'design/sprint1_calculations.ipynb',
              'csv_sha256': csv_hash,
              'csv_sha256_lf': hashlib.sha256((ROOT / 'ASE10.csv').read_bytes().replace(b'\r\n', b'\n')).hexdigest(),
              'changed_cell_ids': changed, 'inserted_cell_ids': inserted,
              'executed': args.execute, 'code_cells': sum(c.cell_type == 'code' for c in notebook.cells),
              'figures': sum('image/png' in o.get('data', {}) for o in outputs),
              'html_outputs': sum('text/html' in o.get('data', {}) for o in outputs),
              'tables': sum(o.get('data', {}).get('text/html', '').count('<table') for o in outputs),
              'execution_errors': sum(o.output_type == 'error' for o in outputs),
              'stderr_blocks': sum(o.output_type == 'stream' and o.get('name') == 'stderr' and bool(o.text.strip()) for o in outputs),
              'all_code_cells_executed': all(c.execution_count is not None for c in notebook.cells if c.cell_type == 'code'),
              'source_control_characters': sum(ord(ch) < 32 and ch not in '\n\r\t' for c in notebook.cells for ch in c.source),
              'joint_complete_hours': len(common),
              'notebook_sha256_lf': hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest()}
    (ROOT / 'design/research_revision_manifest.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
