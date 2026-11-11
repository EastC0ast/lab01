"""Publish a code-free notebook while preserving a byte-identical calculation copy.

Run after build_report.py. No analysis is rerun or changed here: the reader is
constructed solely from saved Markdown and saved cell outputs. PNG bytes and
all numeric/text/table results are checked before publication.
"""
from __future__ import annotations

import base64
import argparse
import copy
import hashlib
import html
import json
import re
from pathlib import Path

import nbformat
from bs4 import BeautifulSoup
from nbconvert import HTMLExporter

ROOT = Path(__file__).resolve().parents[1]
REPO = 'https://github.com/EastC0ast/lab01'
BRANCH = 'design-layout'
CALCULATIONS = REPO + '/blob/' + BRANCH + '/lab01_calculations.ipynb'
RAW = 'https://raw.githubusercontent.com/EastC0ast/lab01/' + BRANCH + '/'
REPORT = REPO + '/blob/' + BRANCH + '/REPORT.md'


def string(value):
    return ''.join(value) if isinstance(value, list) else str(value)


def md_cell(source, cell_id):
    return nbformat.v4.new_markdown_cell(source=source, id=cell_id,
                                        metadata={'id': cell_id})


def visible_text(markup):
    return BeautifulSoup(markup, 'html.parser').get_text()


def reader_title():
    """Plain reader title with the authors supplied by the team."""
    team = json.loads((ROOT / 'design/team.json').read_text(encoding='utf-8'))
    researchers = '\n'.join(
        f'Случайная величина {item["variable"]} (`{item["column"]}`) — {item["author"]}.  '
        for item in team['research'])
    designers = '; '.join(team['design'])
    return (
        '<a id="top" name="top" class="lab-anchor"></a>\n\n'
        '# Лабораторная работа № 1\n\n'
        'Прикладная статистика. Первый спринт.\n\n'
        'Исследование трёх случайных величин\n\n'
        '**Авторы исследования**\n\n'
        + researchers + '\n\n'
        '**КТвД: оформление и дополнительное дизайнерское задание**\n\n'
        + designers + '.\n\n'
        'Данные: `ASE10.csv`.')


def reader_contents(source):
    return source.replace(
        'Код свёрнут; результаты расчётов оставлены видимыми.',
        'В читательской версии код отсутствует; результаты расчётов оставлены видимыми.').replace(
        '[Указатель рисунков и таблиц](#figure-index)',
        '**[7. Дополнительное задание КТвД](#additional-assignment)**  \n'
        '[Рукописные знаки](#additional-assignment) · [Генератор marimo](#additional-assignment)\n\n'
        '[Указатель рисунков и таблиц](#figure-index)')


def notebook_navigation(source):
    """GitHub's notebook iframe rewrites fragment-only URLs to a broken path.

    Send notebook navigation to the native Markdown reader. Keep local fragments
    in REPORT.md and the downloadable HTML so those viewers scroll in place.
    """
    source = re.sub(r'\]\(#([^\s)]+)\)',
                    lambda m: '](' + REPORT + '#' + m.group(1) + ')', source)
    return re.sub(r'href="#([^"]+)"',
                  lambda m: 'href="' + REPORT + '#' + m.group(1) + '"', source)


def native_markdown_source(cell):
    source = cell.source
    if source.startswith('<nav class="lab-nav"'):
        source = re.sub(r'^<nav[^>]*>', '<p class="lab-native-navigation">', source)
        source = source.replace('</nav>', '</p>').replace('</a><a', '</a> · <a')
    if source.startswith('<div class="lab-result"') or source.startswith('<div style="white-space:pre-wrap">'):
        # GitHub strips CSS, including white-space:pre-wrap. Explicit line breaks
        # preserve printed results without presenting them as executable code.
        source = source.replace('\n', '<br>\n')
    return source


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', default='lab01.ipynb',
                        help='Executed notebook; use lab01_calculations.ipynb for repeatable reader-only export')
    args = parser.parse_args()
    source_path = ROOT / 'lab01.ipynb'
    input_path = (ROOT / args.input).resolve()
    source_bytes = input_path.read_bytes()
    original = nbformat.reads(source_bytes.decode('utf-8'), as_version=4)
    code_cells = [c for c in original.cells if c.cell_type == 'code']
    if not code_cells:
        raise RuntimeError('Run build_report.py first; input must be the executed notebook.')
    if any(o.output_type == 'error' for c in code_cells for o in c.get('outputs', [])):
        raise RuntimeError('Refusing to publish a notebook containing execution errors.')
    # This is the unmodified, full, executable notebook, not a reconstruction.
    calculation_path = ROOT / 'lab01_calculations.ipynb'
    if input_path != calculation_path.resolve():
        calculation_path.write_bytes(source_bytes)
    assert calculation_path.read_bytes() == source_bytes

    cells = []
    assets = []
    result_checks = []
    css = []
    figure = 0
    tables = 0
    streams = 0
    for cell in original.cells:
        if cell.cell_type == 'markdown':
            cells.append(copy.deepcopy(cell))
            if cell.id == 'design-title':
                cells[-1].source = reader_title()
            if cell.id == 'design-contents':
                cells[-1].source = reader_contents(cells[-1].source)
                cells.append(md_cell(
                    '> **Режим чтения — без кода.** Текст, формулы, таблицы и графики '
                    'сохранены. Для пересчёта откройте [полный исполняемый ноутбук]('
                    + CALCULATIONS + '). Эта версия содержит только сохранённые результаты.',
                    'reader-notice'))
            if cell.id == 'design-data':
                cells.append(md_cell((ROOT / 'design/reader_notes.md').read_text(encoding='utf-8'),
                                     'reader-notation'))
            if cell.id == 'design-nav-5':
                cells.append(md_cell((ROOT / 'design/additional_assignment.md').read_text(encoding='utf-8'),
                                     'reader-additional-assignment'))
            continue
        if cell.cell_type != 'code':
            raise RuntimeError('Unsupported cell type: ' + cell.cell_type)
        for position, output in enumerate(cell.get('outputs', [])):
            output_id = 'out-' + cell.id[:36] + '-' + str(position)
            if output.output_type == 'stream':
                text = string(output.text)
                if not text.strip():
                    continue
                # Kernel diagnostics are not silently discarded.
                if output.get('name', 'stdout') == 'stderr':
                    raise RuntimeError('Review stderr before publication: ' + text[:300])
                markup = ('<div class="lab-result" style="white-space:pre-wrap;'
                          'font-family:inherit;line-height:1.6">'
                          + html.escape(text) + '</div>')
                assert visible_text(markup) == text
                cells.append(md_cell(markup, output_id))
                streams += 1
                result_checks.append({'cell': cell.id, 'kind': 'stdout',
                                      'text_unchanged': True})
                continue
            data = output.get('data', {})
            if 'image/png' in data:
                figure += 1
                png = base64.b64decode(string(data['image/png']))
                if not png.startswith(b'\x89PNG\r\n\x1a\n'):
                    raise RuntimeError('Unexpected PNG format')
                digest = hashlib.sha256(png).hexdigest()
                relative = 'assets/report/figure-%02d-%s.png' % (figure, digest[:12])
                target = ROOT / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(png)
                assert target.read_bytes() == png
                cells.append(md_cell('![График %02d — сохранённый результат расчёта](%s%s)'
                                     % (figure, RAW, relative), output_id))
                assets.append({'path': relative, 'sha256': digest})
            elif 'text/html' in data:
                markup = string(data['text/html'])
                soup = BeautifulSoup(markup, 'html.parser')
                for element in soup.find_all('style'):
                    css.append(element.get_text())
                if cell.id == 'design-style':
                    # Presentation CSS has no numerical results.
                    if soup.find('table'):
                        raise RuntimeError('Unexpected data in style output')
                    continue
                for element in soup.find_all(['style', 'script']):
                    element.decompose()
                if soup.find('table') is None:
                    raise RuntimeError('Unrecognised HTML output in ' + cell.id)
                tables += len(soup.find_all('table'))
                result = str(soup)
                original_soup = BeautifulSoup(markup, 'html.parser')
                before = [e.get_text() for e in original_soup.select('th,td')]
                after = [e.get_text() for e in soup.select('th,td')]
                assert before == after
                cells.append(md_cell(result, output_id))
                result_checks.append({'cell': cell.id, 'kind': 'table',
                                      'table_cells_unchanged': True, 'cells': len(before)})
            elif 'text/markdown' in data:
                cells.append(md_cell(string(data['text/markdown']), output_id))
            elif 'text/latex' in data:
                cells.append(md_cell(string(data['text/latex']), output_id))
            elif 'text/plain' in data:
                text = string(data['text/plain'])
                if text.startswith(('<IPython.core.display.', '<Figure size')):
                    continue
                markup = '<div style="white-space:pre-wrap">' + html.escape(text) + '</div>'
                assert visible_text(markup) == text
                cells.append(md_cell(markup, output_id))
                result_checks.append({'cell': cell.id, 'kind': 'text', 'text_unchanged': True})
            else:
                raise RuntimeError('Unsupported output in ' + cell.id + ': ' + repr(list(data)))

    metadata = copy.deepcopy(original.metadata)
    metadata['colab'] = {'name': 'lab01.ipynb', 'toc_visible': True}
    metadata['report_mode'] = {'kind': 'saved-results-only',
                               'calculations': 'lab01_calculations.ipynb'}
    report = nbformat.v4.new_notebook(cells=cells, metadata=metadata)
    nbformat.validate(report)
    assert all(c.cell_type == 'markdown' for c in report.cells)
    originals = {c.id: c.source for c in original.cells if c.cell_type == 'markdown'}
    preserved = {c.id: c.source for c in report.cells if c.id in originals}
    expected = dict(originals)
    expected['design-title'] = reader_title()
    expected['design-contents'] = reader_contents(expected['design-contents'])
    assert preserved == expected, 'Existing report text was changed beyond the reader notice'
    markdown = '\n'.join(c.source for c in report.cells)
    targets = set(re.findall(r'(?:id|name)="([^"]+)"', markdown))
    links = re.findall(r'\]\(#([^\s)]+)\)', markdown) + re.findall(r'href="#([^"]+)"', markdown)
    missing = sorted(set(links) - targets)
    assert not missing, missing
    source_figures = sum('image/png' in o.get('data', {}) for c in code_cells
                         for o in c.get('outputs', []))
    assert figure == source_figures
    (ROOT / 'REPORT.md').write_text(
        '\n\n'.join(native_markdown_source(c) for c in report.cells) + '\n', encoding='utf-8')
    notebook_reader = copy.deepcopy(report)
    for cell in notebook_reader.cells:
        cell.source = notebook_navigation(cell.source)
    nbformat.write(notebook_reader, source_path)

    # Offline HTML: the same reader, with PNG data embedded instead of network URLs.
    body, _ = HTMLExporter(template_name='lab').from_notebook_node(report)
    page = BeautifulSoup(body, 'html.parser')
    for image in page.find_all('img'):
        url = image.get('src', '')
        if url.startswith(RAW):
            image['src'] = 'data:image/png;base64,' + base64.b64encode(
                (ROOT / url[len(RAW):]).read_bytes()).decode('ascii')
    style = page.new_tag('style')
    style.string = '\n'.join(css) + '''
body{background:white;color:#243447}
main{max-width:1060px;margin:0 auto;padding:16px 24px}
.jp-InputPrompt,.jp-OutputPrompt{display:none!important}
.lab-toolbar{position:sticky;top:0;z-index:99;background:white;border-bottom:1px solid #d9e2ea;padding:10px;display:flex;gap:20px;flex-wrap:wrap}
.lab-toolbar a{color:#245b78;text-decoration:none}
.jp-RenderedHTMLCommon{overflow-wrap:anywhere}
.jp-RenderedHTMLCommon table{max-width:100%}
.jp-RenderedHTMLCommon img{max-width:100%;height:auto}
@media(max-width:640px){main{padding:8px}.lab-toolbar{font-size:12px}}
'''
    page.head.append(style)
    toolbar = page.new_tag('nav', attrs={'class': 'lab-toolbar'})
    for label, href in [('Оглавление', '#contents'), ('Выводы', '#resume'),
                        ('Рисунки и таблицы', '#figure-index'), ('Полная версия с кодом', CALCULATIONS)]:
        link = page.new_tag('a', href=href)
        link.string = label
        toolbar.append(link)
    page.body.insert(0, toolbar)
    assert not page.select('.jp-CodeCell'), 'Executable source leaked into the reader'
    assert len(page.find_all('img')) == figure
    (ROOT / 'lab01_reading.html').write_text(str(page), encoding='utf-8')

    checks = {
        'reader_notebook': 'lab01.ipynb', 'reader_code_cells': 0,
        'github_reader': 'REPORT.md', 'notebook_navigation_target': REPORT,
        'html_navigation': 'local fragments',
        'calculation_notebook': 'lab01_calculations.ipynb',
        'calculation_notebook_byte_identical_to_executed_input': True,
        'calculation_sha256': hashlib.sha256(source_bytes.replace(b'\r\n', b'\n')).hexdigest(),
        'calculation_hash_line_endings': 'LF (Git canonical)',
        'calculation_code_cells': len(code_cells),
        'markdown_cells_preserved': len(originals) - 2,
        'presentation_only_overrides': ['design-title', 'design-contents'], 'figures_preserved': figure,
        'png_bytes_unchanged': True, 'tables_preserved': tables,
        'stdout_blocks_preserved': streams, 'result_checks': result_checks,
        'internal_links': len(links), 'broken_links': missing,
        'html_code_cells': len(page.select('.jp-CodeCell')),
        'reader_images_require_internet': True, 'html_images_embedded': True,
        'assets': assets,
    }
    (ROOT / 'checks').mkdir(exist_ok=True)
    (ROOT / 'checks/code_visibility.json').write_text(
        json.dumps(checks, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in checks.items() if k not in ('assets', 'result_checks')},
                     ensure_ascii=False, indent=2))
    readme = ROOT / 'DESIGN_README.md'
    notice = '''# Лабораторная № 1 · КТвД

**[Открыть основной отчёт на GitHub → REPORT.md](REPORT.md)**

Это читательская страница с работающим оглавлением и перекрёстными ссылками.
Её можно отправить преподавателю; запускать программы не требуется.
Сохранены исходные формулы, таблицы и все 15 рассчитанных графиков.
Сразу после титульника расположено оглавление. Добавлены справочные обозначения
и ссылки на дополнительное задание; содержательные выводы команды сохранены.
Графики загружаются из этого репозитория; для просмотра на GitHub требуется интернет.

**[lab01.ipynb](lab01.ipynb)** — та же читательская версия без кодовых ячеек.
В просмотрщике ноутбуков GitHub локальные якоря переписываются неверно, поэтому
её оглавление и перекрёстные ссылки открывают разделы основной страницы `REPORT.md`.
В скачанном HTML переходы работают внутри самого документа.

**[lab01_calculations.ipynb](lab01_calculations.ipynb) — полный исполняемый файл.**
Все его расчётные ячейки и сохранённые результаты сохранены. Для пересчёта открывайте
его, а не читательскую версию. Файл ASE10.csv должен находиться рядом.

**[lab01_reading.html](lab01_reading.html)** — скачать и открыть в браузере.
Кода в этой версии тоже нет; изображения встроены в файл. Формулы используют
MathJax и могут требовать соединение с интернетом.

Проверка сохранности: [checks/code_visibility.json](checks/code_visibility.json).
Новая независимая проверка и пересчёт:
[checks/current_verification.json](checks/current_verification.json).
Историческая проверка сборки: [checks/render_verification.json](checks/render_verification.json).

## Дополнительное задание

- [Интерактивный генератор в marimo](designer_generator/README.md): методы команды
  из ветки `generator` перенесены отдельно, без merge. Известное расхождение GD
  показано в интерфейсе; формула команды не исправлялась.
- [Исследование рукописных знаков](design/handwriting/README.md): статус поиска
  исходного материала и форма для измерений. Найденные исходные данные нельзя
  подменять придуманными результатами.
- [Замечания к единицам и выводам](design/REVIEW_NOTES.md): вопросы для согласования
  с инфохимиками; они не исправлены автоматически.

## Проверка и повторный экспорт

Работать из корня репозитория. Установить `requirements-verified.txt` и выполнить:

```sh
python design/make_reader.py --input lab01_calculations.ipynb
python design/verify_report.py --execute
python -m unittest discover -s designer_generator -p 'test_*.py'
python -m marimo check --strict designer_generator/app.py
```

Первый шаг повторно строит читательскую версию из сохранённых результатов,
не записывая исполняемый ноутбук. Проверка исполняет отдельную копию в памяти,
сопоставляет численные результаты и проверяет графики, таблицы и ссылки.
Старый `design/build_report.py` восстанавливает историческую редакцию из
упакованного источника; для обычных правок читательской версии его запуск не нужен.

Изменения публикуются только в `design-layout`. Проверки GitHub работают с правами
чтения и не записывают результаты в ветки. `master`, `design` и исходный репозиторий
`ffriewrya/lab01` не изменяются. Авторы и распределение ролей на титульнике взяты
из `design/team.json` по сведениям команды; номера групп не указаны.

'''
    readme.write_text(notice.rstrip() + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
