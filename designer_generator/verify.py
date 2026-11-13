"""Check source preservation and export the native marimo presentation."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf8')

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / 'designer_generator'


def inspect_export(path):
    text = path.read_text(encoding='utf8')
    payload = text.split('"__MARIMO_MOUNT_CONFIG__"', 1)[1].split('value: Object.freeze(', 1)[1]
    mount, _ = json.JSONDecoder().raw_decode(payload)
    cells = mount['session']['cells']
    assert not any(c['console'] for c in cells), 'Unexpected console output'
    outputs = [o for c in cells for o in c['outputs']]
    assert all(o['type'] == 'data' for o in outputs)
    assert all(not c['code'] for c in mount['notebook']['cells'])
    assert 'MarimoExceptionRaisedError' not in text and 'Traceback (most recent call last)' not in text
    rendered = '\n'.join(o['data'].get('text/html', '') for o in outputs)
    assert 'Применено: N=1000, seed=40' in rendered
    assert 'data:image/png;base64,' in rendered
    assert rendered.count('<marimo-table ') == 2
    assert rendered.count('marimo-number ') == 5
    return {'executed_cells': len(cells), 'tables': 2, 'numeric_inputs': 5,
            'plot_rendered': True, 'code_hidden': True, 'serialized_errors': 0}


def run_commands(commands):
    environment = {**os.environ, 'MPLBACKEND': 'Agg', 'PYTHONIOENCODING': 'utf-8',
                   'MARIMO_SKIP_UPDATE_CHECK': '1', 'XDG_CONFIG_HOME': str(ROOT / '.venv/config'),
                   'XDG_CACHE_HOME': str(ROOT / '.venv/cache')}
    results = []
    for arguments in commands:
        print('Running python ' + ' '.join(arguments), flush=True)
        completed = subprocess.run([sys.executable, *arguments], cwd=ROOT, env=environment,
                                   capture_output=True, text=True, encoding='utf8', timeout=240)
        print(completed.stdout + completed.stderr, flush=True)
        results.append({'command': 'python ' + ' '.join(arguments), 'exit_code': completed.returncode})
        if completed.returncode:
            raise SystemExit(completed.returncode)
    return results


def hashes(names):
    return {name: hashlib.sha256((HERE / name).read_bytes().replace(b'\r\n', b'\n')).hexdigest() for name in names}


def main():
    commands = [
        ['-m', 'unittest', 'designer_generator.test_generator', '-v'],
        ['-m', 'marimo', 'check', '--strict', 'designer_generator/app.py'],
        ['-m', 'marimo', 'export', 'html', 'designer_generator/app.py', '-o', 'designer_generator/preview.html', '--no-include-code', '--no-sandbox', '--force'],
    ]
    results = run_commands(commands)
    inspection = inspect_export(HERE / 'preview.html')
    record = {'status': 'passed', 'checked_at_utc': datetime.now(timezone.utc).isoformat(),
              'scope': 'Author function preservation, native execution and presentation export; no statistical-law correctness claim',
              'author_source_commit': '4567e0cb35967e50b6ade9f963d2171fa4d97b31',
              'commands': results, 'export': inspection,
              'sha256_lf': hashes(['app.py', 'core.py', 'original_generators.py', 'original_statistics.py', 'preview.html'])}
    (HERE / 'verification.json').write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps(record, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
