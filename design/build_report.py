"""Rebuild the prepared design edition; preserve every original calculation cell."""
from __future__ import annotations

import ast
import base64
import copy
import gzip
import hashlib
import importlib.metadata
import json
import re
import subprocess
from pathlib import Path

import nbformat
from bs4 import BeautifulSoup
from nbclient import NotebookClient
from nbconvert import HTMLExporter

ROOT = Path(__file__).resolve().parents[1]
BASE = 'f857ccb2bc1ba39f29be79677d018fc7e0d2d28c'
BLOB = '61c0e5adda0abfd1edafd5e220d624b2b816dc69'
PACKET_SHA = '77cfea26416862e15852103b31a2fa2e13441cda7ec06702217b1a375953c602'


def source_hash(notebook):
    values = [(c.id, c.cell_type, c.source) for c in notebook.cells]
    return hashlib.sha256(json.dumps(values, ensure_ascii=False).encode()).hexdigest()


def text_results(cell):
    """Compare printed results, not transport-dependent stdout chunk boundaries."""
    streams = {}
    displays = []
    for output in cell.get('outputs', []):
        if output.output_type == 'stream':
            name = output.get('name', 'stdout')
            streams[name] = streams.get(name, '') + output.text
        elif output.output_type in ('execute_result', 'display_data'):
            data = output.get('data', {})
            if 'image/png' in data or 'image/svg+xml' in data:
                continue
            if 'text/plain' in data:
                value = data['text/plain']
                if value.startswith('<IPython.core.display.HTML object>'):
                    continue
                displays.append(('text', value))
    return [('stream:' + name, streams[name]) for name in sorted(streams) if streams[name]] + displays


def execute(notebook):
    for cell in notebook.cells:
        if cell.cell_type == 'code':
            cell.outputs = []
            cell.execution_count = None
    # Configure the rendering environment, without modifying stored author code.
    bootstrap = nbformat.v4.new_code_cell(
        "get_ipython().run_line_magic('matplotlib', 'inline')\n"
        "import logging\n"
        "logging.getLogger('matplotlib.font_manager').setLevel(logging.ERROR)",
        id='build-environment')
    notebook.cells.insert(0, bootstrap)
    try:
        NotebookClient(notebook, timeout=150, kernel_name='python3',
                       resources={'metadata': {'path': str(ROOT)}}).execute()
    finally:
        notebook.cells.pop(0)
    nbformat.validate(notebook)
    return notebook


def main():
    raw = subprocess.check_output(['git', 'show', BASE + ':lab01.ipynb'], cwd=ROOT)
    actual_blob = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
    if actual_blob != BLOB:
        raise RuntimeError('Unexpected source notebook. Refusing to replace it.')
    original = nbformat.reads(raw.decode('utf-8'), as_version=4)
    original_cells = {c.id: c for c in original.cells}
    encoded = (ROOT / 'design/notebook_source.json.gz.b64').read_text().strip()
    decoded = gzip.decompress(base64.b64decode(encoded, validate=True))
    if hashlib.sha256(decoded).hexdigest() != PACKET_SHA:
        raise RuntimeError('Uploaded presentation source failed its checksum.')
    packet = json.loads(decoded)
    cells = []
    for specification in packet['cells']:
        if 'base' in specification:
            cell = copy.deepcopy(original_cells[specification['base']])
            cell.metadata = copy.deepcopy(packet['code_metadata'])
            cell.metadata['id'] = cell.id
            cell.outputs = []
            cell.execution_count = None
        else:
            constructor = nbformat.v4.new_code_cell if specification['type'] == 'code' else nbformat.v4.new_markdown_cell
            cell = constructor(source=specification['source'], id=specification['id'],
                               metadata=specification.get('metadata', {}))
        cell.metadata.pop('execution', None)
        cells.append(cell)
    notebook = nbformat.v4.new_notebook(cells=cells, metadata=packet['metadata'])
    if source_hash(notebook) != packet['expected_source_sha256']:
        raise RuntimeError('Reconstructed notebook differs from the prepared edition.')
    original_code = {c.id: c.source for c in original.cells if c.cell_type == 'code' and c.source.strip()}
    rebuilt_code = {c.id: c.source for c in notebook.cells if c.cell_type == 'code'}
    if not all(rebuilt_code.get(k) == v for k, v in original_code.items()):
        raise RuntimeError('An author calculation cell has changed.')
    design_source = next(c.source for c in notebook.cells if c.id == 'design-style')
    css = None
    for statement in ast.parse(design_source).body:
        if isinstance(statement, ast.Assign) and any(isinstance(t, ast.Name) and t.id == '_DESIGN_CSS' for t in statement.targets):
            css = ast.literal_eval(statement.value)
    if css is None:
        raise RuntimeError('Presentation stylesheet is missing.')
    (ROOT / 'design/style_layer.py').write_text(design_source + '\n', encoding='utf-8')
    (ROOT / 'design/report.css').write_text(css, encoding='utf-8')

    print('Executing the prepared notebook...', flush=True)
    execute(notebook)
    print('Executing the control notebook for numerical comparison...', flush=True)
    control = copy.deepcopy(original)
    compatibility = nbformat.v4.new_code_cell("import seaborn as _sns\n_hist = _sns.histplot\ndef _hist_compatible(*a, **kw):\n    if kw.get('hue') is None:\n        kw.setdefault('color', '#245B78')\n    return _hist(*a, **kw)\n_sns.histplot = _hist_compatible")
    control.cells.insert(0, compatibility)
    execute(control)
    control_cells = {c.id: c for c in control.cells}
    comparisons = []
    for cell in notebook.cells:
        if cell.id in original_code:
            expected = text_results(control_cells[cell.id])
            observed = text_results(cell)
            same = expected == observed
            comparisons.append({'id': cell.id, 'groups': len(expected), 'unchanged': same})
            if not same:
                raise RuntimeError('Numerical output changed in cell ' + cell.id + ': ' + repr((expected, observed))[:1500])
    for cell in notebook.cells:
        if cell.cell_type == 'code':
            cell.metadata.update(copy.deepcopy(packet['code_metadata']))
            cell.metadata['id'] = cell.id
    markdown = '\n'.join(c.source for c in notebook.cells if c.cell_type == 'markdown')
    targets = set(re.findall(r'(?:id|name)="([^"]+)"', markdown))
    links = re.findall(r'\]\(#([^\s)]+)\)', markdown) + re.findall(r'href="#([^"]+)"', markdown)
    missing = sorted(set(links) - targets)
    if missing:
        raise RuntimeError('Broken internal links: ' + repr(missing))
    figures = sum('image/png' in output.get('data', {}) for cell in notebook.cells for output in cell.get('outputs', []))
    if figures != 15:
        raise RuntimeError('Expected 15 saved plots; got ' + str(figures))
    if source_hash(notebook) != packet['expected_source_sha256']:
        raise RuntimeError('Execution altered notebook source.')
    nbformat.write(notebook, str(ROOT / 'lab01.ipynb'))

    exported = copy.deepcopy(notebook)
    for cell in exported.cells:
        if cell.cell_type == 'code':
            cell.metadata = {}
    html, _ = HTMLExporter(template_name='lab').from_notebook_node(exported)
    soup = BeautifulSoup(html, 'html.parser')
    style = soup.new_tag('style')
    style.string = css + '''
body{background:white;color:#243447}
main{max-width:1060px;margin:0 auto;padding:16px 24px}
.jp-InputPrompt,.jp-OutputPrompt{display:none!important}
.jp-Cell-inputWrapper,.jp-Cell-outputWrapper{margin-left:0!important}
details.lab-code{border:1px solid #d9e2ea;border-radius:5px;margin:6px 0 14px;padding:6px 12px}
details.lab-code summary{cursor:pointer;color:#245b78;font-size:13px;padding:5px 0}
.lab-toolbar{position:sticky;top:0;z-index:99;background:white;border-bottom:1px solid #d9e2ea;padding:10px;display:flex;gap:10px;flex-wrap:wrap}
.lab-toolbar button,.lab-toolbar a{border:1px solid #c7d3dd;border-radius:4px;background:#f4f7fa;padding:6px 10px;color:#245b78;font:inherit;text-decoration:none}
.jp-RenderedHTMLCommon{overflow-wrap:anywhere}
.jp-OutputArea-output{overflow-x:auto}
@media(max-width:640px){main{padding:8px}.lab-toolbar{font-size:12px}}
'''
    soup.head.append(style)
    for index, input_area in enumerate(list(soup.select('.jp-CodeCell .jp-InputArea')), 1):
        details = soup.new_tag('details', attrs={'class': 'lab-code'})
        summary = soup.new_tag('summary')
        summary.string = 'Показать код · ячейка ' + str(index)
        details.append(summary)
        input_area.wrap(details)
    toolbar = soup.new_tag('nav', attrs={'class': 'lab-toolbar', 'aria-label': 'Управление отчётом'})
    for label, target in [('Оглавление', '#contents'), ('Рисунки и таблицы', '#figure-index'), ('К началу', '#top')]:
        a = soup.new_tag('a', href=target)
        a.string = label
        toolbar.append(a)
    for label, value in [('Показать весь код', 'true'), ('Скрыть весь код', 'false')]:
        button = soup.new_tag('button', attrs={'type': 'button', 'onclick': "document.querySelectorAll('details.lab-code').forEach(x=>x.open=" + value + ')'})
        button.string = label
        toolbar.append(button)
    soup.body.insert(0, toolbar)
    (ROOT / 'lab01_reading.html').write_text(str(soup), encoding='utf-8')
    verification = {
        'source_commit': BASE, 'source_blob': BLOB, 'source_code_cells_preserved': len(original_code),
        'source_code_identical': True, 'source_matches_prepared_edition': True,
        'numeric_text_outputs_identical': True, 'comparisons': comparisons,
        'execution_errors': 0, 'figures': figures, 'internal_links': len(links),
        'broken_internal_links': missing, 'code_cells_hidden': len(rebuilt_code),
        'html_code_panels': len(soup.select('details.lab-code')), 'html_code_panels_open_by_default': 0,
        'scope': 'presentation only; author conclusions not edited; generator not merged',
        'versions': {name: importlib.metadata.version(name) for name in ['numpy', 'pandas', 'scipy', 'matplotlib', 'seaborn', 'nbformat', 'nbclient', 'nbconvert']}
    }
    (ROOT / 'checks').mkdir(exist_ok=True)
    (ROOT / 'checks/render_verification.json').write_text(json.dumps(verification, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    readme = '''# Lab01: оформленный ноутбук

Рабочая ветка: `design-layout` в `EastC0ast/lab01`. Основа — commit `f857ccb2bc1ba39f29be79677d018fc7e0d2d28c` из ветки `design`. Основная ветка и репозиторий команды не изменяются.

## Просмотр

- [Открыть ноутбук](lab01.ipynb).
- [Открыть в Colab](https://colab.research.google.com/github/EastC0ast/lab01/blob/design-layout/lab01.ipynb).
- [Версия для чтения](lab01_reading.html): скачать и открыть в браузере. Код скрыт при открытии; все ячейки можно раскрыть.
- [Результаты проверок](checks/render_verification.json).

Добавлены титульник, оглавление, нумерация, перекрёстные ссылки, переходы между разделами и указатель рисунков/таблиц. Все графики оформлены одинаково. 21 исходная расчётная ячейка сохранена посимвольно. Исходные статистические выводы не исправлялись. Это не подтверждение их корректности: замечания по содержанию необходимо согласовать с командой.

Все кодовые ячейки в `.ipynb` имеют метаданные скрытого источника. Поддержка зависит от среды: просмотрщик GitHub может показывать код. Для чтения без кода используйте HTML, в котором доступны отдельные переключатели и кнопки показа/скрытия всех ячеек.

## Пересчёт

Держать `ASE10.csv` рядом с ноутбуком. Установить зависимости из `requirements-design.txt` и выполнить ячейки сверху вниз. Для Colab загрузить CSV в рабочую среду. Сохранённые результаты видны без запуска. Формулы в HTML используют стандартный MathJax и могут требовать интернет.

## Воспроизводимость

`design/build_report.py` восстанавливает подготовленную редакцию из `design/notebook_source.json.gz.b64` и расчётных ячеек исходного commit. Проверяются контрольные суммы и тождественность исходного кода, затем оформленный и контрольный ноутбуки выполняются отдельно. При отличиях в численных результатах сборка останавливается. Успешный результат сохраняется только в ветке `design-layout`.

Авторы и группы пока не заполнены. Ветка `generator` не объединялась. Автоматического merge в основную ветку нет.
'''
    (ROOT / 'DESIGN_README.md').write_text(readme, encoding='utf-8')
    print(json.dumps(verification, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    main()
