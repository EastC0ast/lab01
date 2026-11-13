"""Check source equivalence and native execution of the browser bundle."""
from datetime import datetime, timezone
import json
from designer_generator.verify import HERE, hashes, inspect_export, run_commands


def main():
    commands = [
        ['-m', 'unittest', 'designer_generator.browser_test', '-v'],
        ['-m', 'marimo', 'check', '--strict', 'designer_generator/browser_app.py'],
        ['-m', 'marimo', 'export', 'html', 'designer_generator/browser_app.py', '-o', 'designer_generator/browser_preview.html', '--no-include-code', '--no-sandbox', '--force'],
    ]
    results = run_commands(commands)
    inspection = inspect_export(HERE / 'browser_preview.html')
    record = {'native_execution': 'passed', 'checked_at_utc': datetime.now(timezone.utc).isoformat(),
              'scope': 'Bundled author source equivalence and native presentation execution',
              'commands': results, 'export': inspection, 'browser_runtime_checked': False,
              'sha256_lf': hashes(['browser_app.py', 'browser_preview.html', 'browser_test.py'])}
    (HERE / 'browser_verification.json').write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps(record, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
