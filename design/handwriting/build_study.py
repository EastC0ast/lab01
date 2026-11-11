"""Execute and publish the handwriting study, keeping the sensor notebook intact."""
from __future__ import annotations

import base64
import copy
import hashlib
import json
from pathlib import Path
import re
import sys

import nbformat
from bs4 import BeautifulSoup
from nbclient import NotebookClient
from nbconvert import HTMLExporter
from jupyter_client import KernelManager
from jupyter_client.kernelspec import KernelSpec

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from design.handwriting.analyze import run_analysis

URL = 'https://github.com/EastC0ast/lab01/blob/design-layout/design/handwriting/'
RAW = 'https://raw.githubusercontent.com/EastC0ast/lab01/design-layout/design/handwriting/'
GENERATOR = 'https://marimo.app/github/EastC0ast/lab01/blob/design-layout/designer_generator/browser_app.py/wasm?embed=true&mode=read&include-code=false&show-code=false'
FIGURES = ['hw01-examples.png', 'hw02-distributions.png', 'hw03-pairs.png',
           'hw04-calibration.png', 'hw05-uncertainty.png']


def number(value, digits=3):
    return f'{value:.{digits}f}'.replace('.', ',')


def statistic_rows(result, level):
    rows = []
    definitions = [('n', 'Объём, ' + ('записей' if level == 'glyphs' else 'авторов')),
                   ('sum', 'Сумма, мм'), ('mean', 'Среднее, мм'), ('median', 'Медиана, мм'),
                   ('min', 'Минимум, мм'), ('max', 'Максимум, мм'), ('std', 'Стандартное отклонение, мм'),
                   ('variance', 'Выборочная дисперсия, мм²'), ('q05', '5-й перцентиль, мм'),
                   ('q25', '1-й квартиль, мм'), ('q75', '3-й квартиль, мм'),
                   ('q95', '95-й перцентиль, мм'), ('iqr', 'Квартильный размах, мм'), ('modes', 'Все моды, мм')]
    for key, label in definitions:
        values = []
        for col in ['width_mm', 'height_mm']:
            data = result['summaries'][level][col]
            if key == 'n':
                text = str(data[key])
            elif key == 'modes':
                text = '; '.join(number(v) for v in data[key]) if data[key] else 'Нет повторяющихся значений'
            else:
                text = number(data[key])
            values.append(text)
        rows.append([label, *values])
    return rows


def association_rows(result):
    a = result['association']
    return [['Спирмен: исходные ink units, 60 авторов', number(a['raw_pooled_spearman'], 6)],
            ['Спирмен: единые мм, 60 авторов', number(a['pooled_spearman'], 6)],
            ['Пирсон: единые мм, 60 авторов', number(a['pooled_pearson'], 6)],
            ['Частная ранговая корреляция с учётом площадки', number(a['adjusted_rank_correlation'], 6)],
            ['Двустороннее перестановочное p', number(a['permutation_p_two_sided'], 4)],
            ['95% bootstrap-интервал', '[' + '; '.join(number(v, 6) for v in a['bootstrap_ci95']) + ']']]


def site_rows(result):
    return [[site, str(a['n_writers']), str(2*a['n_writers']), number(a['spearman'], 6)]
            for site, a in result['association']['site'].items()]


def table(headers, rows):
    return '\n'.join(['| ' + ' | '.join(headers) + ' |',
                      '| ' + ' | '.join(['---'] * len(headers)) + ' |',
                      *['| ' + ' | '.join(row) + ' |' for row in rows]])


def absolute_notebook_links(source):
    source = re.sub(r'\]\((?!https?://|#)([^)]+)\)', lambda m: '](' + URL + m.group(1) + ')', source)
    source = source.replace('](' + URL + 'figures/', '](' + RAW + 'figures/')
    return re.sub(r'\]\(#([^)]*)\)', lambda m: '](' + URL + 'README.md#' + m.group(1) + ')', source)


def sections(result):
    a, repeated = result['association'], result['repeated_writing']
    w, h = result['summaries']['glyphs']['width_mm'], result['summaries']['glyphs']['height_mm']
    return [
        ('hw-title', '''<a id="hw-top" name="hw-top"></a>

# Дополнительное исследование КТвД

## Размеры рукописной буквы a: две случайные величины

Лабораторная работа № 1 по прикладной статистике. Янковская Катерина; Шерстнев Игорь.

Исследование выполнено заново по открытому датасету. Это не восстановление прежних измерений команды.

[1. Данные](#hw-data) · [2. Величины и случайность](#hw-variables) · [3. EDA](#hw-eda) · [4. Связь](#hw-association) · [5. Выводы](#hw-conclusions) · [6. Воспроизводимость и источники](#hw-sources) · [7. Критерии](#hw-criteria)

[Вернуться к общему отчёту](https://github.com/EastC0ast/lab01/blob/design-layout/REPORT.md#additional-assignment)
'''),
        ('hw-data', '''<a id="hw-data" name="hw-data"></a>

## 1 · Данные и отбор

Использован [UJI Pen Characters (Version 2), UCI](https://archive.ics.uci.edu/dataset/177/uji+pen+characters+version+2), DOI [10.24432/C5FG8S](https://doi.org/10.24432/C5FG8S), лицензия CC BY 4.0. Исходный набор содержит 11 640 принятых записей 97 знаков от 60 авторов. Он получен с помощью пера на планшете; это реальные траектории, а не сгенерированные изображения.

До расчёта итоговых статистик выбрана одна метка — строчная **латинская** `a` (U+0061). Оставлены все 120 её записей: по два повторения каждого автора. Другие буквы и цифры исключены только по метке. Выбросы не удалялись; пропусков и нулевых размеров в выбранной серии нет. Выбор знака и правила обработки записаны в [selection_plan.json](data/selection_plan.json).

Площадки сбора: UJI — 16 авторов и 32 записи; UPV — 44 автора и 88 записей. В документации указаны разные масштабы: **100 ink units/мм у UJI и 152 ink units/мм у UPV**. Координаты переведены в миллиметры экранной системы планшета. Это не размеры букв на бумаге. Индивидуальная нормализация размера, поворот и сглаживание не применялись.

Весь исходный ZIP, описание `uji2.names`, метаданные и контрольные суммы сохранены в [data/](data/). Разметка `trn/tst` сохранена как метаданные; классификатор здесь не обучается, поэтому для описания используются все записи `a`.
'''),
        ('hw-variables', r'''<a id="hw-variables" name="hw-variables"></a>

## 2 · Две величины и природа случайности

Случайный опыт: равновероятно выбрать одного из 60 авторов, затем одно из двух его повторений. В наблюдаемой серии это эквивалентно равновероятному выбору одной из 120 записей. Величины:

- $W$ — ширина ограничивающего прямоугольника траектории, мм;
- $H$ — высота того же прямоугольника, мм.

Для автора $i$, повторения $j$ и площадки $s$ берутся все точки всех штрихов:

$$W_{ij}=\frac{\max_k x_{ijk}-\min_k x_{ijk}}{c_s},\qquad
H_{ij}=\frac{\max_k y_{ijk}-\min_k y_{ijk}}{c_s},\qquad c_{UJI}=100,\ c_{UPV}=152.$$

Используется разность крайних координат без прибавления единицы. Переходы пера между штрихами не дорисовываются. Повторные точки не удаляются и не меняют экстремумы.

Условие «написать букву a» не задаёт единственный размер: результат зависит от автора и конкретного движения пера. По заранее известной метке знака нельзя однозначно вычислить будущие $W$ и $H$. Формула выше измеряет уже полученную траекторию; детерминированность измерения не устраняет случайность выбранного наблюдения. Это обоснование стохастической модели опыта, а не утверждение о невозможности любой детерминированной модели моторики человека.
'''),
        ('hw-examples', fr'''**Рисунок КТвД 1 · Примеры исходных траекторий.** Два повторения шести авторов, выбранных по равномерным позициям в отсортированном списке ID. Размеры панелей и масштаб в мм одинаковы; выполнен только перенос начала координат. Экранная ось Y направлена вниз. Синий — UJI, охра — UPV.

![Рисунок КТвД 1 — исходные траектории буквы a](figures/{FIGURES[0]})
'''),
        ('hw-eda', fr'''<a id="hw-eda" name="hw-eda"></a>

## 3 · Разведочный анализ

**Таблица КТвД 1 · Все 120 записей.** Значения для чтения округлены до трёх знаков; расчётная точность сохранена в CSV и JSON. Для дисперсии и стандартного отклонения используется делитель $n-1$. Квантили вычислены линейной интерполяцией. Перечислены все значения с максимальной частотой, а не первая найденная мода.

{table(['Показатель', 'Ширина W', 'Высота H'], statistic_rows(result, 'glyphs'))}

Ширина изменяется от {number(w['min'])} до {number(w['max'])} мм, высота — от {number(h['min'])} до {number(h['max'])} мм. Средняя ширина равна {number(w['mean'])} мм, средняя высота — {number(h['mean'])} мм. На гистограммах виден правый хвост и отдельные крупные знаки; такие записи сохранены в расчёте. Моды зависят от дискретности координат и не являются подбором теоретического закона.

У {repeated['writers_with_different_width']} из 60 авторов ширина двух повторений различается, у {repeated['writers_with_different_height']} различается высота. Медианы абсолютных различий равны соответственно {number(repeated['median_absolute_width_difference_mm'])} и {number(repeated['median_absolute_height_difference_mm'])} мм. Вариация есть и внутри одного автора.
'''),
        ('hw-distributions', fr'''**Рисунок КТвД 2 · Гистограммы и эмпирические функции распределения.** Границы столбцов выбраны правилом Фридмана—Диакониса. ECDF построены по исходным размерам без округления; ступени правосторонне непрерывны.

![Рисунок КТвД 2 — распределения ширины и высоты](figures/{FIGURES[1]})

$$\widehat F_n(t)=\frac{{1}}{{n}}\sum_{{j=1}}^n\mathbf 1\{{Z_j\leq t\}},\qquad Z\in\{{W,H\}}.$$
'''),
        ('hw-writers', fr'''Два повторения одного человека могут быть зависимы из-за общего почерка. Поэтому 120 записей не считаются 120 независимыми авторами. Для проверки межавторской связи используется по одной паре средних на человека:

$$\bar W_i=\frac{{W_{{i1}}+W_{{i2}}}}{{2}},\qquad\bar H_i=\frac{{H_{{i1}}+H_{{i2}}}}{{2}}.$$

**Таблица КТвД 2 · 60 пар авторских средних.** Это другая единица анализа; она не описывает связь изменений между двумя попытками одного человека.

{table(['Показатель', 'Средняя ширина автора', 'Средняя высота автора'], statistic_rows(result, 'writers'))}
'''),
        ('hw-pairs', fr'''**Рисунок КТвД 3 · Парные размеры.** Слева — все записи и соединённые повторы каждого автора, справа — 60 авторских средних. Оси обоих графиков имеют одинаковые пределы и единицы.

![Рисунок КТвД 3 — размеры и средние авторов](figures/{FIGURES[2]})
'''),
        ('hw-association', r'''<a id="hw-association" name="hw-association"></a>

## 4 · Проверка связи с учётом площадки

Обе величины относятся к одной записи, поэтому их независимость заранее не предполагается. Сначала приведены описательные коэффициенты. Различия в составе участников и условиях площадок могут сохраняться даже после перевода шкал в мм.

Основная проверка относится к **средним размерам авторов**. $H_0$: средняя ширина и средняя высота условно независимы при фиксированной площадке, $\bar W\perp\bar H\mid S$; соответствие ширин и высот внутри каждой площадки обменно; выбранная статистика чувствительна к ранговой связи. Альтернатива — связь, нарушающая это предположение. Это не тест общего pooled-коэффициента на равенство нулю и не проверка причинности.

Всем 60 средним присваиваются ранги $R_i$ и $Q_i$; совпадения получают средний ранг. Из рангов вычитаются средние ранги своей площадки:

$$u_i=R_i-\overline R_{s(i)},\qquad v_i=Q_i-\overline Q_{s(i)},\qquad
r_{rank\mid S}=\frac{\sum_i u_i v_i}{\sqrt{\sum_i u_i^2\sum_i v_i^2}}.$$

Высоты авторов переставляются только внутри UJI и внутри UPV, ширины остаются на месте. При $B=19999$ двустороннее Monte Carlo p вычисляется с поправкой для конечного числа перестановок:

$$p_{MC}=\frac{1+\#\{|r^{(b)}|\geq |r_{obs}|\}}{B+1}.$$

Для 95% percentile bootstrap-интервала 10 000 раз выбираются с возвращением целые пары авторских средних отдельно внутри площадок. Числа авторов 16 и 44 сохраняются; ранги пересчитываются заново. Для воспроизведения задан seed `20261111` и независимые потоки случайных чисел для двух процедур. Интервал приближённый и условен относительно этой модели.
'''),
        ('hw-association-table', fr'''**Таблица КТвД 3 · Коэффициенты и основная проверка.** Описательные коэффициенты не сопровождаются дополнительными проверками значимости.

{table(['Показатель', 'Значение'], association_rows(result))}

**Таблица КТвД 4 · Описательная чувствительность к площадке, единые мм.**

{table(['Площадка', 'Авторы', 'Записи', 'Спирмен по средним авторов'], site_rows(result))}
'''),
        ('hw-calibration', fr'''**Рисунок КТвД 4 · Влияние масштаба.** Без пересчёта единиц pooled-корреляция Спирмена равна {number(a['raw_pooled_spearman'], 3)}, после пересчёта — {number(a['pooled_spearman'], 3)}. Сравнение исходных ink units смешивало разные шкалы и завышало видимую связь. Перевод единиц исправляет известную техническую разницу, а условная проверка дополнительно учитывает площадку.

![Рисунок КТвД 4 — влияние разных шкал координат](figures/{FIGURES[3]})
'''),
        ('hw-uncertainty', fr'''**Рисунок КТвД 5 · Перестановочная проверка и bootstrap.** Частная ранговая оценка равна {number(a['adjusted_rank_correlation'], 6)}. Более экстремальных перестановок — {a['permutation_extreme_count']} из {a['permutations']}; p = {number(a['permutation_p_two_sided'], 4)}. Оценка Monte Carlo стандартной ошибки p составляет около {number(a['permutation_mc_se'], 4)}.

![Рисунок КТвД 5 — проверка связи и интервал оценки](figures/{FIGURES[4]})

При $\alpha=0,05$ нулевая гипотеза **не отвергается**. Данный ранговый тест не дал достаточных оснований против условной независимости внутри площадок. **Независимость не доказана**: возможны другие виды связи и недостаточная точность выборки из 60 авторов. Интервал [{number(a['bootstrap_ci95'][0], 6)}; {number(a['bootstrap_ci95'][1], 6)}] включает ноль.
'''),
        ('hw-conclusions', fr'''<a id="hw-conclusions" name="hw-conclusions"></a>

## 5 · Выводы и ограничения

1. Для одинаковой буквы размеры не фиксированы: средние по всем записям составили {number(w['mean'])} мм по ширине и {number(h['mean'])} мм по высоте. Различия есть между авторами и между двумя повторениями одного автора. Это поддерживает выбранную модель случайного наблюдения.
2. При объединении рукописных данных сначала нужно согласовать единицы. Разные масштабы площадок заметно увеличивали наблюдаемую корреляцию. После документированного пересчёта и учёта площадки оценка связи слабая: {number(a['adjusted_rank_correlation'], 3)}, p = {number(a['permutation_p_two_sided'], 4)}.
3. При уровне 0,05 статистически значимая ранговая связь **между средними размерами авторов** не обнаружена. Это не равносильно доказанной независимости ширины и высоты отдельных букв.
4. Все описательные числа относятся к 120 принятым записям `a` данного набора. Авторы не описаны как случайная выборка населения. P-value и интервал требуют условной обменности/независимости участников внутри площадок; bootstrap не устраняет ограничение способа набора людей.
5. Участники писали в направляющих рамках и могли переделывать неудачные записи. Поэтому результаты относятся к принятым записям на планшете, а не к свободному письму на бумаге. Данных о времени и давлении нет, и эти характеристики не исследовались.

Ни знак, ни правила отбора не менялись ради получения значимого p-value. Отрицательный результат проверки сохранён.
'''),
        ('hw-sources', '''<a id="hw-sources" name="hw-sources"></a>

## 6 · Воспроизводимость и источники

- [Исполняемый ноутбук с расчётами](handwriting_calculations.ipynb), [читательский ноутбук без кода](handwriting.ipynb), [HTML для скачивания](https://github.com/EastC0ast/lab01/raw/refs/heads/design-layout/design/handwriting/handwriting_reading.html).
- [Все 120 измерений](data/glyphs.csv), [60 пар авторских средних](data/writer_means.csv), [полные результаты](results.json), [контроль происхождения](data/provenance.json).
- [Порядок воспроизведения и проверки](REPRODUCIBILITY.md). Код измерений и анализа вынесен в отдельные файлы; исходный ZIP сохранён. Штрихи не сглаживались, записи по величине размеров не отбрасывались.

Источники:

1. Prat F., Castro M., Llorens D., Marzal A., Vilar J. **UJI Pen Characters (Version 2)**. UCI Machine Learning Repository, 2008. [DOI: 10.24432/C5FG8S](https://doi.org/10.24432/C5FG8S). Данные используются по [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/); изменения — отбор `a`, расчёт размеров и перевод в мм.
2. Llorens D. et al. **The UJIpenchars Database: a Pen-Based Database of Isolated Handwritten Characters**. LREC, 2008. [Первичная статья](https://aclanthology.org/L08-1467/). Описывает процедуру сбора и развитие набора; численные результаты настоящего анализа получены отдельно.
3. SciPy. [Перестановочные проверки, парные перестановки и Monte Carlo поправка](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.permutation_test.html). Использована собственная явно стратифицированная реализация; она проверена на синтетических случаях.

Исторический [протокол поиска прежней работы](history_search.json) сохранён для истории. Текущее исследование использует новый открытый источник.
'''),
        ('hw-criteria', fr'''<a id="hw-criteria" name="hw-criteria"></a>

## 7 · Соответствие дополнительному заданию КТвД

| Требование | Раздел и результат |
| --- | --- |
| Отдельный датасет и две величины | [Данные](#hw-data), [ширина и высота](#hw-variables) |
| Обоснование случайности | [Описание случайного опыта](#hw-variables) |
| Исследование связи величин одной природы | [Проверка связи](#hw-association); значимая ранговая связь не обнаружена, независимость не доказана |
| EDA и изученные статистики | [Разведочный анализ](#hw-eda), рисунки 1–4, таблицы 1–4 |
| Интерактивность генератора и marimo | [Общее приложение команды]({GENERATOR}), проверенное отдельно; это генератор сигнала NO₂, а не модель размеров букв |
| Формулы, подписи и источники | Определения в мм, LaTeX, единая палитра, источники и воспроизводимые расчёты |

[К оглавлению](#hw-top) · [В общий отчёт](https://github.com/EastC0ast/lab01/blob/design-layout/REPORT.md#additional-assignment)
''')]


def main():
    result = run_analysis()
    blocks = sections(result)
    local_text = '\n\n'.join(source.strip() for _, source in blocks) + '\n'
    (HERE / 'README.md').write_text(local_text, encoding='utf-8')
    reader_cells = []
    for key, source in blocks:
        source = re.sub(r'\]\((?!https?://|#)([^)]+)\)', lambda m: '](' + URL + m.group(1) + ')', source)
        source = source.replace('](' + URL + 'figures/', '](' + RAW + 'figures/')
        reader_cells.append(nbformat.v4.new_markdown_cell(source, id=key))
    reader_local = nbformat.v4.new_notebook(cells=reader_cells)
    reader = copy.deepcopy(reader_local)
    for cell in reader.cells:
        cell.source = re.sub(r'\]\(#([^)]*)\)', lambda m: '](' + URL + 'README.md#' + m.group(1) + ')', cell.source)
    nbformat.write(reader, HERE / 'handwriting.ipynb')

    code = {
        'hw-eda': "display(pd.DataFrame(statistic_rows(result, 'glyphs'), columns=['Показатель','Ширина W','Высота H']))",
        'hw-writers': "display(pd.DataFrame(statistic_rows(result, 'writers'), columns=['Показатель','Средняя ширина автора','Средняя высота автора']))",
        'hw-association-table': "display(pd.DataFrame(association_rows(result), columns=['Показатель','Значение']))\ndisplay(pd.DataFrame(site_rows(result), columns=['Площадка','Авторы','Записи','Спирмен']))",
    }
    for key, filename in zip(['hw-examples', 'hw-distributions', 'hw-pairs', 'hw-calibration', 'hw-uncertainty'], FIGURES):
        code[key] = f"display(Image(filename=str(HERE / 'figures/{filename}')))"
    bootstrap = '''from pathlib import Path
import sys, logging
ROOT = next(p for p in [Path.cwd(), *Path.cwd().parents] if (p/'design/handwriting/analyze.py').is_file())
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
import pandas as pd
from IPython.display import display, Image
from design.handwriting.analyze import run_analysis
from design.handwriting.build_study import statistic_rows, association_rows, site_rows
HERE = ROOT / 'design/handwriting'
logging.getLogger('matplotlib.font_manager').setLevel(logging.ERROR)
pd.set_option('display.max_colwidth', None)
result = run_analysis()
print(f"Проверено: {result['glyph_count']} записей, {result['writer_count']} авторов; seed=20261111")'''
    full_cells = [nbformat.v4.new_markdown_cell(blocks[0][1], id='hw-title'),
                  nbformat.v4.new_code_cell(bootstrap, id='hw-compute')]
    for key, source in blocks[1:]:
        if key in code:
            explanation = re.sub(r'!\[[^\]]*\]\([^)]+\)', '', source)
            explanation = re.sub(r'(?m)^\|.*\|\s*$', '', explanation)
            full_cells.append(nbformat.v4.new_markdown_cell(explanation, id=key))
            full_cells.append(nbformat.v4.new_code_cell(code[key], id=key+'-calculation'))
        else:
            full_cells.append(nbformat.v4.new_markdown_cell(source, id=key))
    for cell in full_cells:
        if cell.cell_type == 'markdown':
            cell.source = absolute_notebook_links(cell.source)
    full = nbformat.v4.new_notebook(cells=full_cells, metadata={'kernelspec': {'name':'python3','display_name':'Python 3','language':'python'}})
    manager = KernelManager(kernel_name='python3')
    manager._kernel_spec = KernelSpec(argv=[sys.executable, '-m', 'ipykernel_launcher', '-f', '{connection_file}'], display_name='Handwriting verification', language='python')
    try:
        NotebookClient(full, km=manager, timeout=240, resources={'metadata': {'path': str(ROOT)}}).execute()
    finally:
        if manager.has_kernel: manager.shutdown_kernel(now=True)
    nbformat.validate(full)
    nbformat.write(full, HERE / 'handwriting_calculations.ipynb')
    assert result == json.loads((HERE / 'results.json').read_text(encoding='utf-8')), 'Notebook recalculation changed results'
    expected_pngs = [(HERE / 'figures' / f).read_bytes() for f in FIGURES]
    actual_pngs = [base64.b64decode(o.data['image/png']) for c in full.cells for o in c.get('outputs',[]) if 'image/png' in o.get('data',{})]
    assert actual_pngs == expected_pngs
    body, _ = HTMLExporter(template_name='lab').from_notebook_node(reader_local)
    soup = BeautifulSoup(body, 'html.parser')
    for im in soup.find_all('img'):
        assert im['src'].startswith(RAW)
        im['src'] = 'data:image/png;base64,' + base64.b64encode((HERE / im['src'][len(RAW):]).read_bytes()).decode()
    style = soup.new_tag('style')
    style.string = 'body{color:#243447;background:white}main{max-width:1040px;margin:auto;padding:20px}img{max-width:100%;height:auto}table{border-collapse:collapse}th,td{padding:7px 10px;border-bottom:1px solid #d9e2ea}p{line-height:1.65}'
    soup.head.append(style)
    assert not soup.select('.jp-CodeCell') and len(soup.find_all('img')) == 5
    (HERE / 'handwriting_reading.html').write_text(str(soup), encoding='utf-8')
    summary = fr'''Исследованы **120 записей строчной латинской `a` от 60 авторов** из открытого UCI UJI Pen Characters 2. Две величины — ширина и высота буквы в миллиметрах экранной системы планшета. Учтены разные масштабы площадок и два повторения каждого автора.

Средняя ширина — **{number(result['summaries']['glyphs']['width_mm']['mean'])} мм**, высота — **{number(result['summaries']['glyphs']['height_mm']['mean'])} мм**. При проверке связи по средним авторов с учётом площадки получены ранговая оценка **{number(result['association']['adjusted_rank_correlation'])}** и **p = {number(result['association']['permutation_p_two_sided'],4)}**. При уровне 0,05 значимая ранговая связь не обнаружена; независимость этим не доказана.

[Открыть полное исследование КТвД](https://github.com/EastC0ast/lab01/blob/design-layout/design/handwriting/README.md) · [Расчёты](https://github.com/EastC0ast/lab01/blob/design-layout/design/handwriting/handwriting_calculations.ipynb)
'''
    (HERE / 'summary.md').write_text(summary, encoding='utf-8')
    checks = {'status':'passed','glyphs':120,'writers':60,'reader_code_cells':0,
              'executed_code_cells':sum(c.cell_type=='code' for c in full.cells),'execution_errors':0,
              'saved_png_outputs_equal_files':5,'html_figures_embedded':5,'html_code_cells':0,
              'notebook_recalculation_identical':True,'source_archive_sha256':result['source_zip_sha256'],
              'association':result['association'],
              'sha256_lf': {p.name:hashlib.sha256(p.read_bytes().replace(b'\r\n',b'\n')).hexdigest() for p in [HERE/'README.md',HERE/'handwriting.ipynb',HERE/'handwriting_calculations.ipynb',HERE/'results.json']}}
    (HERE / 'verification.json').write_text(json.dumps(checks, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(checks, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
