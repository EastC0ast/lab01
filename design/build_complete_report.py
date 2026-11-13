"""Compose the executed sprint notebooks without changing their calculations."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import re

import nbformat
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
SOURCES = [ROOT / 'design/sprint1_calculations.ipynb',
           ROOT / 'designer_generator/sprint2_calculations.ipynb']


def figure_index(cells):
    figures, tables = [], []
    for cell in cells:
        sources = [cell.source] if cell.cell_type == 'markdown' else [
            o.get('data', {}).get('text/markdown', '') for o in cell.get('outputs', [])]
        for source in sources:
            soup = BeautifulSoup(source, 'html.parser')
            targets = [tag.get('id') or tag.get('name') for tag in soup.find_all('a')
                       if tag.get('id') or tag.get('name')]
            caption = soup.select_one('.lab-caption')
            text = caption.get_text(' ', strip=True) if caption else soup.get_text(' ', strip=True)
            strong = re.search(r'\*\*((?:Рисунок|Рисунки|Таблица).*?)\*\*', source)
            if caption is None and strong:
                text = strong.group(1)
            text = re.sub(r'\*|^#+\s*', '', text).strip()
            target = next((x for x in targets if x.startswith((
                'fig', 'table', 'gen-figure', 'gen-table', 'research-table'))), None)
            if not target:
                continue
            line = f'- [{text[:180]}](#{target})'
            (tables if ('table' in target) else figures).append(line)
    return nbformat.v4.new_markdown_cell(
        '<a id="figure-index" name="figure-index" class="lab-anchor"></a>\n\n'
        '## Указатель рисунков и таблиц\n\nРисунки\n\n' + '\n'.join(figures)
        + '\n\nТаблицы\n\n' + '\n'.join(tables)
        + '\n\n[К оглавлению](#contents)', id='design-figure-index')


def main():
    from make_reader import reader_title, reader_contents
    cells, sources, execution = [], [], 0
    for path in SOURCES:
        notebook = nbformat.read(path, as_version=4)
        nbformat.validate(notebook)
        for cell in notebook.cells:
            if cell.id == 'design-figure-index':
                continue
            item = copy.deepcopy(cell)
            if item.cell_type == 'markdown' and path.parent.name == 'designer_generator':
                item.source = re.sub(r'\]\((?!https?://|#)([^)]+)\)',
                    lambda m: '](' + 'https://github.com/EastC0ast/lab01/blob/design-layout/designer_generator/' + m.group(1) + ')', item.source)
            if item.id == 'design-title':
                item.source = reader_title()
            elif item.id == 'design-contents':
                item.source = reader_contents(item.source)
            if item.cell_type == 'code':
                assert isinstance(item.execution_count, int), ('Unexecuted cell', path, item.id)
                assert not any(o.output_type == 'error' for o in item.get('outputs', []))
                execution += 1
                item.execution_count = execution
                for output in item.get('outputs', []):
                    if output.output_type == 'execute_result':
                        output.execution_count = execution
            cells.append(item)
        sources.append({'path': path.relative_to(ROOT).as_posix(),
                        'sha256_lf': hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest(),
                        'cells': len(notebook.cells)})
    additional = (ROOT / 'design/additional_assignment.md').read_text(encoding='utf-8')
    summary = (ROOT / 'design/handwriting/summary.md').read_text(encoding='utf-8')
    assert additional.count('<!-- HANDWRITING_SUMMARY -->') == 1
    cells.append(nbformat.v4.new_markdown_cell(
        additional.replace('<!-- HANDWRITING_SUMMARY -->', summary.strip()),
        id='design-additional-assignment'))
    cells.append(figure_index(cells))
    assert len({c.id for c in cells}) == len(cells), 'Notebook cell IDs must be unique'
    full = nbformat.v4.new_notebook(cells=cells, metadata={
        'kernelspec': {'name': 'python3', 'display_name': 'Python 3', 'language': 'python'},
        'language_info': {'name': 'python'},
    })
    nbformat.validate(full)
    nbformat.write(full, ROOT / 'lab01_calculations.ipynb')
    record = {'sources': sources, 'executed_code_cells': execution,
              'presentation_overrides': ['design-title', 'design-contents',
                                         'design-additional-assignment', 'design-figure-index'],
              'source_code_and_outputs_preserved': True,
              'calculation_sha256_lf': hashlib.sha256(
                  (ROOT / 'lab01_calculations.ipynb').read_bytes().replace(b'\r\n', b'\n')).hexdigest()}
    (ROOT / 'checks/complete_report.json').write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(record, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
