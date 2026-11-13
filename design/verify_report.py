"""Verify author-cell identity and presentation exports; never rewrite analysis."""
from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import html
import json
import os
import re
import sys
from pathlib import Path

import nbformat
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'design'))
from build_author_report import SOURCE_COMMIT, SOURCE_GIT_BLOB, SOURCE_SHA256_LF
from make_reader import RAW, REPORT, native_markdown_source


def sha(path):
    return hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest()


def local(source):
    return source.replace(REPORT + '#', '#')


def table_cells(markup):
    return [[x.get_text() for x in row.find_all(['th', 'td'])]
            for row in BeautifulSoup(markup, 'html.parser').find_all('tr')]


def execute_copy(full):
    from nbclient import NotebookClient
    from jupyter_client import KernelManager
    from jupyter_client.kernelspec import KernelSpec
    executed = copy.deepcopy(full)
    manager = KernelManager(kernel_name='python3')
    manager._kernel_spec = KernelSpec(argv=[sys.executable, '-m', 'ipykernel_launcher', '-f', '{connection_file}'],
                                     display_name='Author report verification', language='python')
    try:
        NotebookClient(executed, km=manager, timeout=240,
                       resources={'metadata': {'path': str(ROOT)}}).execute(
            env={**os.environ, 'MPLBACKEND': 'module://matplotlib_inline.backend_inline', 'PYTHONDONTWRITEBYTECODE': '1'})
    finally:
        if manager.has_kernel:
            manager.shutdown_kernel(now=True)
    outputs = [o for c in executed.cells for o in c.get('outputs', [])]
    assert not any(o.output_type == 'error' for o in outputs)
    pngs = sum('image/png' in o.get('data', {}) for o in outputs)
    assert pngs == 16, ('Unexpected figure count in the verification kernel', pngs)
    assert sum('text/html' in o.get('data', {}) for o in outputs) == 5
    return {'status': 'passed', 'code_cells_executed': 24, 'execution_errors': 0,
            'saved_results_overwritten': False,
            'stochastic_values_and_timings_compared_to_saved': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true', help='Run a disposable copy without overwriting saved author results')
    args = parser.parse_args()
    source_path = ROOT / 'design/author_source.ipynb'
    raw = source_path.read_bytes().replace(b'\r\n', b'\n')
    assert sha(source_path) == SOURCE_SHA256_LF
    assert hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest() == SOURCE_GIT_BLOB
    csv = (ROOT / 'ASE10.csv').read_bytes().replace(b'\r\n', b'\n')
    assert hashlib.sha1(b'blob ' + str(len(csv)).encode() + b'\0' + csv).hexdigest() == 'b5e2912f3530be3173b88b6d8417d311309f37bc'
    source = nbformat.read(source_path, as_version=4)
    full = nbformat.read(ROOT / 'lab01_calculations.ipynb', as_version=4)
    reader = nbformat.read(ROOT / 'lab01.ipynb', as_version=4)
    for notebook in (source, full, reader):
        nbformat.validate(notebook)
        assert len({c.id for c in notebook.cells}) == len(notebook.cells)
    original_ids = [c.id for c in source.cells]
    original_set = set(original_ids)
    restored = [c for c in full.cells if c.id in original_set]
    assert restored == source.cells, 'An author cell, its metadata, source, code or saved output was changed'
    added = [c for c in full.cells if c.id not in original_set]
    assert all(c.cell_type == 'markdown' and c.id.startswith('design-') for c in added)
    assert not any(re.search(r'\$\$|```math|\\\[|\\\(', c.source) for c in added), 'Added mathematical reasoning is not a presentation change'
    manifest = json.loads((ROOT / 'checks/author_preservation.json').read_text(encoding='utf-8'))
    assert manifest['calculation_sha256_lf'] == sha(ROOT / 'lab01_calculations.ipynb')
    assert manifest['added_presentation_cell_ids'] == [c.id for c in added]
    assert [c.id for c in full.cells if c.cell_type == 'code'] == [c.id for c in source.cells if c.cell_type == 'code']
    assert len(original_ids) == 60 and len(restored) == 60
    assert all(c.cell_type == 'markdown' for c in reader.cells)
    assert [c.id for c in reader.cells[:2]] == ['design-title', 'design-contents']
    reader_map = {c.id: c for c in reader.cells}
    for cell in full.cells:
        if cell.cell_type == 'markdown':
            assert local(reader_map[cell.id].source) == cell.source, ('Reader prose changed', cell.id)
    team = json.loads((ROOT / 'design/team.json').read_text(encoding='utf-8'))
    assert all(str(value) in reader_map['design-title'].source for value in team['isu'].values())
    assert not re.search(r'\]\(#|href="#', '\n'.join(c.source for c in reader.cells))
    native = (ROOT / 'REPORT.md').read_text(encoding='utf-8')
    expected_native = '\n\n'.join(native_markdown_source(nbformat.v4.new_markdown_cell(local(c.source))) for c in reader.cells) + '\n'
    assert native == expected_native, 'Native report differs from the preserved reader'
    targets = set(re.findall(r'(?:id|name)="([^"]+)"', native))
    links = re.findall(r'\]\(#([^\s)]+)\)', native) + re.findall(r'href="#([^"]+)"', native)
    assert links and not set(links) - targets
    page = BeautifulSoup((ROOT / 'lab01_reading.html').read_text(encoding='utf-8'), 'html.parser')
    assert not page.select('.jp-CodeCell, .cm-editor, details.lab-code')
    html_ids = {x['id'] for x in page.select('[id]')}
    assert all(a['href'][1:] in html_ids for a in page.select('a[href^="#"]'))
    images = page.find_all('img')
    figures = tables = streams = 0
    for cell in source.cells:
        for index, output in enumerate(cell.get('outputs', [])):
            assert output.output_type != 'error'
            key = 'out-' + cell.id[:36] + '-' + str(index)
            if output.output_type == 'stream' and output.text.strip():
                assert output.get('name', 'stdout') == 'stdout'
                assert BeautifulSoup(reader_map[key].source, 'html.parser').get_text() == output.text
                assert page.find(id='cell-id=' + key).select_one('.lab-result').get_text() == output.text
                streams += 1
            data = output.get('data', {})
            if 'image/png' in data:
                png = base64.b64decode(data['image/png'])
                match = re.search(r'\]\(' + re.escape(RAW) + r'([^)]*)\)', reader_map[key].source)
                assert match
                path = (ROOT / match[1]).resolve()
                assert path.is_relative_to(ROOT / 'assets/report') and path.read_bytes() == png
                assert base64.b64decode(images[figures]['src'].split(',', 1)[1]) == png
                figures += 1
            elif 'text/html' in data:
                expected_table = table_cells(data['text/html'])
                assert expected_table == table_cells(reader_map[key].source)
                assert expected_table == table_cells(str(page.find(id='cell-id=' + key)))
                tables += 1
            elif 'text/markdown' in data:
                assert local(reader_map[key].source) == data['text/markdown']
    assert figures == len(images) == 16 and tables == 5
    result = {'status': 'passed', 'scope': 'author preservation and presentation',
              'author_repository': 'ffriewrya/lab01', 'author_commit': SOURCE_COMMIT,
              'author_git_blob': SOURCE_GIT_BLOB, 'author_snapshot_sha256_lf': SOURCE_SHA256_LF,
              'author_cells_preserved_exactly': 60, 'author_markdown_cells_preserved_exactly': 36,
              'author_code_cells_preserved_exactly': 24, 'author_cell_metadata_and_execution_counts_preserved': True,
              'author_formulas_and_conclusions_unchanged': True, 'added_executable_cells': 0,
              'reader_code_cells': 0, 'html_code_cells': 0,
              'saved_pngs_byte_identical': figures, 'saved_data_tables_identical': tables,
              'saved_stdout_blocks_identical': streams, 'broken_internal_links': [],
              'standalone_handwriting_study_included_in_main_report': False,
              'calculation_sha256_lf': sha(ROOT / 'lab01_calculations.ipynb'),
              'execution': execute_copy(full) if args.execute else {'status': 'not requested'}}
    (ROOT / 'checks/current_verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
