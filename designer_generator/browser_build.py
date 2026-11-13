"""Bundle the unmodified author functions and the UI into a one-file marimo app."""
import ast
import base64
import gzip
import hashlib
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / 'designer_generator'


def embedded_sources():
    originals = (HERE / 'original_generators.py').read_text(encoding='utf8')
    statistics = (HERE / 'original_statistics.py').read_text(encoding='utf8')
    core = (HERE / 'core.py').read_text(encoding='utf8')
    helpers = '\n\n'.join(ast.get_source_segment(core, node) for node in ast.parse(core).body
                           if isinstance(node, ast.FunctionDef) and node.name != 'load_no2')
    return originals, statistics, helpers


def build():
    app = (HERE / 'app.py').read_text(encoding='utf8')
    lines = app.splitlines(keepends=True)
    nodes = [node for node in ast.parse(app).body if isinstance(node, ast.FunctionDef)]
    cells = [''.join(lines[min([n.lineno] + [d.lineno for d in n.decorator_list])-1:n.end_lineno]) + '\n\n' for n in nodes]
    originals, statistics, helpers = embedded_sources()
    csv = (ROOT / 'ASE10.csv').read_bytes().replace(b'\r\n', b'\n')
    encoded = '\n'.join('        ' + repr(line) for line in textwrap.wrap(base64.b64encode(gzip.compress(csv, mtime=0)).decode(), 100))
    header = '''# /// script
# requires-python = ">=3.11"
# dependencies = ["marimo==0.25.2", "numpy", "pandas", "scipy", "matplotlib"]
# ///
import marimo
__generated_with = '0.25.2'
app = marimo.App(width='medium', app_title='Генератор сигнала NO₂')

'''
    imports = f'''@app.cell
def _():
    import marimo as mo
    import base64, gzip, hashlib, io
    from time import perf_counter
    import numpy as np
    import pandas as pd
    import matplotlib.pyplot as plt
    from scipy import stats
    _original_source = {originals!r}
    _statistics_source = {statistics!r}
    _helper_source = {helpers!r}
    _csv_b64 = (
{encoded}
    )
    _csv = gzip.decompress(base64.b64decode(_csv_b64))
    assert hashlib.sha256(_csv).hexdigest() == {hashlib.sha256(csv).hexdigest()!r}
    _namespace = {{'np': np, 'pd': pd, 'stats': stats, 'perf_counter': perf_counter}}
    exec(compile(_original_source, '<author-generators>', 'exec'), _namespace)
    exec(compile(_statistics_source, '<author-statistics>', 'exec'), _namespace)
    exec(compile(_helper_source, '<presentation-adapters>', 'exec'), _namespace)
    fit_parameters = _namespace['fit_parameters']
    generate = _namespace['generate']
    comparison_table = _namespace['comparison_table']
    def load_no2():
        return pd.read_csv(io.BytesIO(_csv), sep=';')['ASE_NO2'].dropna()
    return mo, np, pd, plt, stats, load_no2, fit_parameters, generate, comparison_table

'''
    (HERE / 'browser_app.py').write_text(header + imports + ''.join(cells[1:]) + "\nif __name__ == '__main__':\n    app.run()\n", encoding='utf8', newline='\n')


if __name__ == '__main__':
    build()
