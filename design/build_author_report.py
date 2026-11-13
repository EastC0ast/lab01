"""Add presentation cells around the unchanged final notebook of the authors.

This builder never executes, edits or rewrites an author's cell. Its input is
the immutable notebook snapshot recorded by SOURCE_COMMIT and SOURCE_GIT_BLOB.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import nbformat


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'design/author_source.ipynb'
SOURCE_REPOSITORY = 'ffriewrya/lab01'
SOURCE_COMMIT = '4567e0cb35967e50b6ade9f963d2171fa4d97b31'
SOURCE_GIT_BLOB = 'b9b3ec7a2d44aeb6238b75d06ae851afbfea423d'
SOURCE_SHA256_LF = '18a2bf558f8dcb961a919bf4a2bbfa6c6a7f1b1c709a59daa53a3a593ab7ce96'

# All labels below are navigation and figure/table captions. Author headings,
# paragraphs, formulae, source code and saved outputs remain in their own cells.
SECTIONS = {
    1: ('data', '1. Исходные данные'),
    2: ('rv-no2', '2. Сигнал сенсора NO2'),
    14: ('rv-temp', '3. Сигнал сенсора температуры (ASE_T)'),
    26: ('dependence', '4. Зависимость NO2 от температуры'),
    31: ('rv-co', '5. Сигнал сенсора CO'),
    45: ('resume', '6. Lab resume — спринт 1'),
    47: ('sprint2', '7. Генератор — спринт 2'),
}

ANCHORS = {
    0: ['sprint1'],
    3: ['no2-description'], 4: ['no2-eda'], 6: ['no2-model'],
    7: ['no2-test'], 8: ['no2-normalization'], 9: ['no2-estimates'],
    12: ['no2-samples'],
    15: ['temp-description'], 16: ['temp-eda'], 18: ['temp-model'],
    19: ['temp-test'], 20: ['temp-normalization'], 21: ['temp-estimates'],
    24: ['temp-samples'],
    27: ['dependence-test'], 28: ['dependence-plots'],
    30: ['dependence-conclusion'],
    32: ['co-description'], 33: ['co-eda'], 35: ['co-model'],
    36: ['co-test'], 39: ['co-normalization'], 40: ['co-estimates'],
    43: ['co-samples'], 46: ['criteria'],
    49: ['generator-description'], 50: ['generator-math'],
    53: ['generator-code'], 55: ['generator-tests'],
    57: ['generator-resume'], 58: ['generator-lab-resume'],
    59: ['generator-criteria'],
}

FIGURE_TITLES = [
    'Распределение напряжения сенсора NO2',
    'График функции распределения NO2',
    'Нормализованное распределение напряжения сенсора NO2',
    'Состоятельность оценки для NO2',
    'Распределение напряжения сенсора температуры',
    'График функции распределения температуры',
    'Нормализованное распределение напряжения сенсора температуры',
    'Состоятельность оценки для температуры',
    'Зависимость напряжения сенсора NO2 от температуры',
    'Матрица корреляции',
    'Распределение напряжения сенсора CO',
    'График функции распределения CO',
    'Подгонка теоретических распределений',
    'Нормализованное распределение напряжения сенсора CO',
    'Состоятельность оценки для CO',
    'Сравнение сгенерированных данных',
]
TABLE_TITLES = [
    'Первые строки исходных данных',
    'Статистики NO2 и выборок',
    'Статистики температуры и выборок',
    'Статистики CO и выборок',
    'Статистики исходных и сгенерированных данных NO2',
]


def canonical_hash(value):
    data = json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(data).hexdigest()


def file_hash(path):
    return hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest()


def md(source, cell_id):
    return nbformat.v4.new_markdown_cell(source, id=cell_id)


def anchor(target):
    return f'<a id="{target}" name="{target}" class="lab-anchor"></a>'


def contents():
    lines = [anchor('contents'), '', '## Оглавление', '']
    for _, (target, title) in SECTIONS.items():
        lines += [f'**[{title}](#{target})**', '']
        prefix = {'rv-no2': 'no2', 'rv-temp': 'temp', 'rv-co': 'co'}.get(target)
        if prefix:
            entries = [('Описание', 'description'), ('EDA', 'eda'),
                       ('Распределение', 'model'), ('Гипотеза', 'test'),
                       ('Нормализация', 'normalization'),
                       ('Оценки', 'estimates'), ('Выборки', 'samples')]
            lines += [' · '.join(f'[{label}](#{prefix}-{suffix})'
                                  for label, suffix in entries), '']
        elif target == 'dependence':
            lines += ['[Корреляция](#dependence-test) · '
                      '[Графики](#dependence-plots) · '
                      '[Вывод](#dependence-conclusion)', '']
        elif target == 'resume':
            lines += ['[Таблица критериев](#criteria)', '']
        elif target == 'sprint2':
            lines += ['[Description](#generator-description) · '
                      '[Math Desc](#generator-math) · '
                      '[Code](#generator-code) · '
                      '[Tests](#generator-tests) · '
                      '[Resume](#generator-resume) · '
                      '[Lab resume](#generator-lab-resume) · '
                      '[Таблица критериев](#generator-criteria)', '']
    lines += ['[Указатель рисунков и таблиц](#figure-index)']
    return md('\n'.join(lines), 'design-contents')


def section_navigation(position):
    sections = list(SECTIONS.values())
    previous = sections[position - 1] if position else None
    following = sections[position + 1] if position + 1 < len(sections) else None
    links = [f'[← {previous[1]}](#{previous[0]})'] if previous else []
    links.append('[Оглавление](#contents)')
    if following:
        links.append(f'[{following[1]} →](#{following[0]})')
    return ' · '.join(links)


def build():
    assert file_hash(SOURCE) == SOURCE_SHA256_LF, 'Author snapshot changed'
    source = nbformat.read(SOURCE, as_version=4)
    nbformat.validate(source)
    assert len(source.cells) == 60
    assert sum(c.cell_type == 'code' for c in source.cells) == 24

    # Only the front matter is supplied by the design layer.
    from make_reader import reader_title
    cells = [md(reader_title(), 'design-title'), contents()]
    figures, tables, captions = [], [], []
    section_positions = {index: pos for pos, index in enumerate(SECTIONS)}
    author_records = []

    for index, original in enumerate(source.cells):
        if index in SECTIONS:
            target, title = SECTIONS[index]
            if index == 1:
                text = anchor(target) + '\n\n## ' + title.replace('1. ', '1 · ', 1)
            else:
                number = title.split('.', 1)[0]
                text = anchor(target) + f'\n\n<p class="lab-section-label">Раздел {number}</p>'
            text += '\n\n' + section_navigation(section_positions[index])
            cells.append(md(text, 'design-section-' + target))
        if index in ANCHORS:
            cells.append(md('\n'.join(anchor(a) for a in ANCHORS[index]),
                            'design-anchor-' + ANCHORS[index][0]))

        caption_lines = []
        for output_index, output in enumerate(original.get('outputs', [])):
            data = output.get('data', {})
            kind = None
            if 'image/png' in data:
                number = len(figures) + 1
                title = FIGURE_TITLES[number - 1]
                target = f'fig{number:02d}'
                label = f'Рисунок {number:02d} · {title}'
                figures.append((target, label))
                kind = 'image/png'
            elif 'text/html' in data:
                number = len(tables) + 1
                title = TABLE_TITLES[number - 1]
                target = f'table{number:02d}'
                label = f'Таблица {number:02d} · {title}'
                tables.append((target, label))
                kind = 'text/html'
            if kind:
                caption_lines += [anchor(target), f'<p class="lab-caption">{label}</p>']
                captions.append({'cell_id': original.id, 'output_index': output_index,
                                 'mime_type': kind, 'target': target, 'label': label})
        if caption_lines:
            cells.append(md('\n\n'.join(caption_lines),
                            'design-caption-' + original.id))

        cells.append(copy.deepcopy(original))
        author_records.append({
            'id': original.id, 'cell_type': original.cell_type,
            'source_sha256_utf8': hashlib.sha256(original.source.encode('utf-8')).hexdigest(),
            'outputs_sha256_canonical': canonical_hash(original.get('outputs', [])),
            'cell_sha256_canonical': canonical_hash(original),
        })

    index_lines = [anchor('figure-index'), '', '## Указатель рисунков и таблиц',
                   '', 'Рисунки', '']
    index_lines += [f'- [{label}](#{target})' for target, label in figures]
    index_lines += ['', 'Таблицы', '']
    index_lines += [f'- [{label}](#{target})' for target, label in tables]
    index_lines += ['', '[К оглавлению](#contents)']
    cells.append(md('\n'.join(index_lines), 'design-figure-index'))

    author_ids = [c.id for c in source.cells]
    copied = [c for c in cells if c.id in set(author_ids)]
    assert copied == list(source.cells), 'An author cell was changed or reordered'
    assert len(figures) == 16 and len(tables) == 5
    assert len({c.id for c in cells}) == len(cells)
    added = [c for c in cells if c.id not in set(author_ids)]
    assert all(c.cell_type == 'markdown' for c in added)
    full = nbformat.v4.new_notebook(cells=cells, metadata=copy.deepcopy(source.metadata))
    nbformat.validate(full)
    target = ROOT / 'lab01_calculations.ipynb'
    nbformat.write(full, target)

    manifest = {
        'status': 'passed',
        'source_repository': SOURCE_REPOSITORY,
        'source_commit': SOURCE_COMMIT,
        'source_git_blob': SOURCE_GIT_BLOB,
        'source_path': SOURCE.relative_to(ROOT).as_posix(),
        'source_sha256_lf': SOURCE_SHA256_LF,
        'author_cells_preserved': len(author_records),
        'author_markdown_cells_preserved': sum(c.cell_type == 'markdown' for c in source.cells),
        'author_code_cells_preserved': sum(c.cell_type == 'code' for c in source.cells),
        'author_cell_order_preserved': True,
        'author_execution_counts_preserved': True,
        'author_cells': author_records,
        'added_presentation_cell_ids': [c.id for c in added],
        'added_code_cells': 0,
        'saved_png_outputs': len(figures),
        'saved_html_tables': len(tables),
        'output_captions': captions,
        'calculation_notebook': target.relative_to(ROOT).as_posix(),
        'calculation_sha256_lf': file_hash(target),
        'calculations_reexecuted': False,
    }
    (ROOT / 'checks/author_preservation.json').write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return manifest


def main():
    record = build()
    print(json.dumps({key: value for key, value in record.items()
                      if key not in ('author_cells', 'output_captions',
                                     'added_presentation_cell_ids')},
                     ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
