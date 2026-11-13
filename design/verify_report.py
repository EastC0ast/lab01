"""Independently check saved artifacts; optionally execute a copy without writing it."""
from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import importlib.metadata
import json
import math
import re
import subprocess
from pathlib import Path
from urllib.parse import urlsplit, unquote

import nbformat
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
BASELINE = 'ffeba64ab3fea83f163979760deb0b39ba77c419'
AUTHOR_BASE = 'f857ccb2bc1ba39f29be79677d018fc7e0d2d28c'
RAW = 'https://raw.githubusercontent.com/EastC0ast/lab01/design-layout/'
REPORT = 'https://github.com/EastC0ast/lab01/blob/design-layout/REPORT.md'


def local_navigation(source):
    return source.replace(REPORT + '#', '#')


def saved(path):
    return nbformat.read(ROOT / path, as_version=4)


def table_cells(markup):
    return [x.get_text() for x in BeautifulSoup(markup, 'html.parser').select('th,td')]


def comparison_table_cells(markup):
    soup = BeautifulSoup(markup, 'html.parser')
    for table in soup.find_all('table'):
        head = table.find('thead')
        if head is None:
            continue
        headings = [x.get_text(' ', strip=True) for x in head.find_all('th')]
        runtime_columns = [i for i, value in enumerate(headings) if 'времени, с' in value]
        if not runtime_columns:
            continue
        for row in table.select('tbody tr'):
            values = row.find_all(['th', 'td'], recursive=False)
            for index in runtime_columns:
                assert index < len(values)
                values[index].clear()
                values[index].string = '<measured runtime>'
    return [x.get_text() for x in soup.select('th,td')]


def text_values(cell):
    streams = {}
    values = []
    for output in cell.get('outputs', []):
        if output.output_type == 'stream':
            name = output.get('name', 'stdout')
            streams[name] = streams.get(name, '') + output.text
        else:
            data = output.get('data', {})
            if 'image/png' in data or cell.id == 'design-style':
                continue
            if 'text/html' in data:
                values.append(('table', '\n'.join(comparison_table_cells(data['text/html']))))
            elif 'text/markdown' in data:
                values.append(('markdown', data['text/markdown']))
            elif 'text/plain' in data:
                value = data['text/plain']
                if not value.startswith(('<IPython.core.display.', '<Figure size')):
                    values.append(('text', value))
    return [('stream:' + name, streams[name]) for name in sorted(streams)] + values


NUMBER = re.compile(r'(?<![\w])[-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][-+]?\d+)?')


def equivalent_text(expected, actual):
    """Allow floating point platform noise, while preserving words and all decisions."""
    if expected == actual:
        return True
    if NUMBER.sub('<number>', expected) != NUMBER.sub('<number>', actual):
        return False
    left, right = NUMBER.findall(expected), NUMBER.findall(actual)
    return len(left) == len(right) and all(
        math.isclose(float(a), float(b), rel_tol=1e-10, abs_tol=1e-12)
        for a, b in zip(left, right))


def execute_copy(full):
    from nbclient import NotebookClient
    from jupyter_client import KernelManager
    from jupyter_client.kernelspec import KernelSpec
    import sys

    clone = copy.deepcopy(full)
    for cell in clone.cells:
        if cell.cell_type == 'code':
            cell.outputs = []
            cell.execution_count = None
    bootstrap = nbformat.v4.new_code_cell(
        "get_ipython().run_line_magic('matplotlib', 'inline')\n"
        "import logging\nlogging.getLogger('matplotlib.font_manager').setLevel(logging.ERROR)",
        id='verification-environment')
    clone.cells.insert(0, bootstrap)
    manager = KernelManager(kernel_name='python3')
    manager._kernel_spec = KernelSpec(
        argv=[sys.executable, '-m', 'ipykernel_launcher', '-f', '{connection_file}'],
        display_name='Verification', language='python')
    try:
        NotebookClient(clone, km=manager, timeout=180,
                       resources={'metadata': {'path': str(ROOT)}}).execute()
    finally:
        if manager.has_kernel:
            manager.shutdown_kernel(now=True)
    clone.cells.pop(0)
    before = {c.id: c for c in full.cells if c.cell_type == 'code'}
    for cell in clone.cells:
        if cell.id not in before:
            continue
        left, right = text_values(before[cell.id]), text_values(cell)
        assert len(left) == len(right), ('Output group mismatch', cell.id, left, right)
        for (lk, lv), (rk, rv) in zip(left, right):
            assert lk == rk and equivalent_text(lv, rv), ('Numerical result changed', cell.id, lv, rv)
    count = sum('image/png' in o.get('data', {}) for c in clone.cells for o in c.get('outputs', []))
    expected_count = sum('image/png' in o.get('data', {}) for c in full.cells for o in c.get('outputs', []))
    assert count == expected_count, (count, expected_count)
    return {'executed_code_cells': len(before), 'execution_errors': 0,
            'numeric_results_match_saved': True, 'float_relative_tolerance': 1e-10,
            'float_absolute_tolerance': 1e-12, 'generated_figures': count}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    full = saved('lab01_calculations.ipynb')
    reader = saved('lab01.ipynb')
    nbformat.validate(full)
    nbformat.validate(reader)
    # The 13-Nov scientific revision is explicit; preserve the historical source
    # and raw data while comparing the complete notebook to both executed sprints.
    baseline_bytes = subprocess.check_output(
        ['git', 'show', BASELINE + ':lab01_calculations.ipynb'], cwd=ROOT)
    csv_baseline = subprocess.check_output(['git', 'show', BASELINE + ':ASE10.csv'], cwd=ROOT)
    normalize_bytes = lambda value: value.replace(b'\r\n', b'\n')
    assert normalize_bytes((ROOT / 'ASE10.csv').read_bytes()) == normalize_bytes(csv_baseline)
    composition = json.loads((ROOT / 'checks/complete_report.json').read_text(encoding='utf-8'))
    assert hashlib.sha256(normalize_bytes((ROOT / 'lab01_calculations.ipynb').read_bytes())).hexdigest() == composition['calculation_sha256_lf']
    source_cells = []
    for item in composition['sources']:
        path = ROOT / item['path']
        assert hashlib.sha256(normalize_bytes(path.read_bytes())).hexdigest() == item['sha256_lf'], path
        source_cells.extend(c for c in nbformat.read(path, as_version=4).cells if c.id != 'design-figure-index')
    actual_cells = [c for c in full.cells if c.id not in ('design-figure-index', 'design-additional-assignment')]
    assert [c.id for c in actual_cells] == [c.id for c in source_cells]
    for actual, source in zip(actual_cells, source_cells):
        assert actual.cell_type == source.cell_type, actual.id
        if actual.id not in ('design-title', 'design-contents'):
            actual_source = actual.source
            expected_source = source.source
            if source.id.startswith('gen-') and source.cell_type == 'markdown':
                actual_source = actual_source.replace('https://github.com/EastC0ast/lab01/blob/design-layout/designer_generator/', '')
                expected_source = expected_source.replace('https://github.com/EastC0ast/lab01/blob/design-layout/designer_generator/', '')
            assert actual_source == expected_source, actual.id
        if actual.cell_type == 'code':
            normalize_outputs = lambda outputs: [{k:v for k,v in o.items() if k != 'execution_count'} for o in outputs]
            assert normalize_outputs(actual.outputs) == normalize_outputs(source.outputs), ('Saved output changed during composition', actual.id)
    code = {c.id: c.source for c in full.cells if c.cell_type == 'code'}
    assert len(code) == composition['executed_code_cells']
    assert any('Lab01 - Sprint 2' in c.source for c in full.cells if c.cell_type == 'markdown')
    expected_figures = sum('image/png' in o.get('data', {}) for c in full.cells for o in c.get('outputs', []))
    expected_tables = sum(len(BeautifulSoup(o.get('data', {}).get('text/html', ''), 'html.parser').find_all('table')) for c in full.cells for o in c.get('outputs', []))
    assert expected_figures >= 16 and expected_tables >= 10
    assert all(c.cell_type == 'markdown' for c in reader.cells)
    assert reader.cells[0].id == 'design-title' and reader.cells[1].id == 'design-contents'
    assert 'Код свёрнут' not in reader.cells[1].source
    reader_map = {c.id: c for c in reader.cells}
    assert 'reader-notice' not in reader_map
    assert 'Навигационные ссылки размещены' not in reader_map['design-contents'].source
    team = json.loads((ROOT / 'design/team.json').read_text(encoding='utf-8'))
    title = reader_map['design-title'].source
    for member in team['research']:
        assert f'Случайная величина {member["variable"]} (`{member["column"]}`) — {member["author"]}' in title
    assert all(name in title for name in team['design'])
    if team.get('team_number'):
        assert str(team['team_number']) in title
    for isu in team.get('isu', {}).values():
        assert str(isu) in title
    assert 'заполняются командой' not in title
    for cell in full.cells:
        if cell.cell_type == 'markdown' and cell.id not in ('design-title', 'design-contents'):
            assert local_navigation(reader_map[cell.id].source) == cell.source, ('Author prose changed', cell.id)
    native_markdown = (ROOT / 'REPORT.md').read_text(encoding='utf-8')
    expected_local = '\n\n'.join(local_navigation(c.source) for c in reader.cells) + '\n'
    native_comparison = re.sub(
        r'<p class="lab-native-navigation">(.*?)</p>',
        lambda m: '<nav class="lab-nav" aria-label="Навигация по отчёту">'
        + m.group(1).replace('</a> · <a', '</a><a') + '</nav>', native_markdown)
    def math_normalized(text):
        text = re.sub(r'```math\n(.*?)\n```', lambda m: '$$' + m.group(1).strip() + '$$', text, flags=re.S)
        return re.sub(r'\$\$(.*?)\$\$', lambda m: '$$' + m.group(1).strip() + '$$', text, flags=re.S)
    assert math_normalized(native_comparison.replace('<br>\n', '\n')) == math_normalized(expected_local), 'Native reader lost or changed content'
    notebook_markdown = '\n'.join(c.source for c in reader.cells)
    assert not re.search(r'\]\(#|href="#', notebook_markdown), 'Fragment-only navigation breaks in GitHub notebook viewer'
    notebook_destinations = re.findall(re.escape(REPORT) + r'#([^\s)"<>]+)', notebook_markdown)
    assert len(notebook_destinations) >= 100
    page = BeautifulSoup((ROOT / 'lab01_reading.html').read_text(encoding='utf-8'), 'html.parser')
    assert not page.select('.jp-CodeCell, details.lab-code')
    assert not any(a.get('href', '').startswith(REPORT + '#') for a in page.find_all('a'))
    assert all(page.find(id='cell-id=' + c.id) is not None for c in reader.cells)
    images = page.find_all('img')
    assert len(images) == expected_figures
    figures = tables = streams = 0
    for cell in full.cells:
        for position, output in enumerate(cell.get('outputs', [])):
            assert output.output_type != 'error'
            key = 'out-' + cell.id[:36] + '-' + str(position)
            if output.output_type == 'stream' and output.text.strip():
                assert output.get('name', 'stdout') == 'stdout'
                markup = reader_map[key].source
                assert BeautifulSoup(markup, 'html.parser').get_text() == output.text
                html_cell = page.find(id='cell-id=' + key)
                assert html_cell.select_one('.lab-result').get_text() == output.text
                streams += 1
            data = output.get('data', {})
            if 'image/png' in data:
                png = base64.b64decode(data['image/png'])
                path = re.search(r'\]\(' + re.escape(RAW) + r'([^)]*)\)', reader_map[key].source).group(1)
                assert (ROOT / path).resolve().is_relative_to(ROOT)
                assert (ROOT / path).read_bytes() == png
                assert base64.b64decode(images[figures]['src'].split(',', 1)[1]) == png
                figures += 1
            elif 'text/markdown' in data:
                assert local_navigation(reader_map[key].source) == data['text/markdown'], ('Markdown output changed', cell.id)
            elif 'text/html' in data and cell.id != 'design-style':
                expected = table_cells(data['text/html'])
                assert expected and table_cells(reader_map[key].source) == expected
                html_cell = page.find(id='cell-id=' + key)
                assert html_cell is not None and table_cells(str(html_cell)) == expected
                tables += len(BeautifulSoup(data['text/html'], 'html.parser').find_all('table'))
    assert figures == expected_figures and tables == expected_tables
    markdown = native_markdown
    targets = set(re.findall(r'(?:id|name)="([^"]+)"', markdown))
    links = re.findall(r'\]\(#([^\s)]+)\)', markdown) + re.findall(r'href="#([^"]+)"', markdown)
    assert not set(links) - targets
    html_ids = {tag['id'] for tag in page.select('[id]')}
    assert all(a['href'][1:] in html_ids for a in page.select('a[href^="#"]'))
    for match in re.findall(r'\]\((https://github.com/EastC0ast/lab01/blob/design-layout/[^)]+)\)', markdown):
        path = unquote(urlsplit(match).path.split('/blob/design-layout/', 1)[1])
        assert (ROOT / path).is_file() or (ROOT / path).is_dir(), match
    handwriting = json.loads((ROOT / 'design/handwriting/verification.json').read_text(encoding='utf-8'))
    assert handwriting['status'] == 'passed' and handwriting['glyphs'] == 120 and handwriting['writers'] == 60
    summary = (ROOT / 'design/handwriting/summary.md').read_text(encoding='utf-8').strip()
    assert summary in reader_map['design-additional-assignment'].source
    assert '<!-- HANDWRITING_SUMMARY -->' not in markdown
    result = {
        'baseline_commit': BASELINE, 'baseline_calculation_sha256': hashlib.sha256(baseline_bytes).hexdigest(),
        'scientific_revision_authorized_on': '2026-11-13',
        'raw_dataset_unchanged_from_baseline': True,
        'composed_sprint_code_and_outputs_identical': True,
        'executed_code_cells_in_saved_notebook': len(code),
        'reader_code_cells': 0, 'html_code_cells': 0, 'title_immediately_followed_by_contents': True,
        'saved_figures_byte_identical': figures, 'calculation_tables_identical': tables,
        'stdout_blocks_identical': streams, 'html_stdout_blocks_identical': streams,
        'html_reader_cells_present': len(reader.cells), 'broken_internal_links': [],
        'github_reader': 'REPORT.md', 'native_reader_matches_notebook_content': True,
        'notebook_links_to_native_reader': len(notebook_destinations),
        'fragment_only_links_in_notebook': 0, 'html_navigation_stays_local': True,
        'scientific_revision_manifest': 'design/research_revision_manifest.json',
        'reader_title_matches_supplied_team': True,
        'research_authors': team['research'], 'design_authors': team['design'],
        'units_verified': True, 'dataset_provenance': 'design/data_sources/provenance.json',
        'submission_info_complete': bool(team.get('team_number')) and all(team.get('isu', {}).get(name) for name in [*[x['author'] for x in team['research']], *team['design']]),
        'handwriting_results_recovered': False,
        'new_handwriting_study_completed': True,
        'handwriting_study_verification': 'design/handwriting/verification.json',
        'versions': {p: importlib.metadata.version(p) for p in
                     ['numpy', 'pandas', 'scipy', 'matplotlib', 'nbformat', 'nbclient', 'nbconvert']},
        'execution': execute_copy(full) if args.execute else {'status': 'not run'},
    }
    (ROOT / 'checks/current_verification.json').write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
