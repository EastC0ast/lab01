"""Browser bundle retains exactly the current algorithms, model and source data."""
import ast,base64,gzip,hashlib,math,unittest
from pathlib import Path
from time import perf_counter
from types import SimpleNamespace
import numpy as np,pandas as pd
from scipy import stats
from designer_generator import core
ROOT=Path(__file__).resolve().parents[1]

def capsule():
    values={}
    for node in ast.walk(ast.parse((ROOT/'designer_generator/browser_app.py').read_text(encoding='utf8'))):
        if isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name) and node.targets[0].id in ['_algorithm_source','_wrapper_source','_csv_gzip_b64','_expected_algorithm_sha','_expected_csv_sha']:
            values[node.targets[0].id]=ast.literal_eval(node.value)
    return values

def browser_helpers():
    c=capsule(); algorithms={}; exec(compile(c['_algorithm_source'],'<gamma-algorithms>','exec'),algorithms)
    namespace={'np':np,'pd':pd,'stats':stats,'math':math,'perf_counter':perf_counter,'algorithms':SimpleNamespace(gamma_a=algorithms['gamma_a'],gamma_gd=algorithms['gamma_gd'])}
    exec(compile(c['_wrapper_source'],'<model-and-validation>','exec'),namespace)
    return namespace

class BrowserNotebookTests(unittest.TestCase):
    def test_current_algorithms_are_embedded_exactly(self):
        c=capsule(); source=(ROOT/'designer_generator/algorithms.py').read_text(encoding='utf8')
        self.assertEqual(c['_algorithm_source'],source)
        self.assertEqual(hashlib.sha256(source.encode()).hexdigest(),c['_expected_algorithm_sha'])

    def test_model_helpers_are_embedded_exactly(self):
        source=(ROOT/'designer_generator/core.py').read_text(encoding='utf8')
        selected='\n\n'.join(ast.get_source_segment(source,n) for n in ast.parse(source).body if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and n.name!='load_no2')
        self.assertEqual(capsule()['_wrapper_source'],selected)

    def test_csv_is_exact_after_lf_normalization(self):
        c=capsule(); raw=gzip.decompress(base64.b64decode(c['_csv_gzip_b64']))
        self.assertEqual(raw,(ROOT/'ASE10.csv').read_bytes().replace(b'\r\n',b'\n'))
        self.assertEqual(hashlib.sha256(raw).hexdigest(),c['_expected_csv_sha'])

    def test_browser_values_match_native_current_scientific_samplers(self):
        generate=browser_helpers()['generate']
        for method in ['A','GD']:
            for a in [1.01,3.,5.4525349587]:
                for seed in [0,40,4294967295]:
                    actual=generate(method,250,a,29322.,38.,seed); expected=core.generate(method,250,a,29322.,38.,seed)
                    np.testing.assert_array_equal(actual['values'],expected['values']); self.assertEqual(actual['proposals'],expected['proposals'])

    def test_ui_and_no_local_imports(self):
        source=(ROOT/'designer_generator/browser_app.py').read_text(encoding='utf8')
        original=(ROOT/'designer_generator/app.py').read_text(encoding='utf8')
        original_cells=[n for n in ast.parse(original).body if isinstance(n,ast.FunctionDef)]
        browser_cells=[n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef)]
        for cell in original_cells[1:]: self.assertTrue(any(ast.dump(cell)==ast.dump(other) for other in browser_cells))
        self.assertNotIn('sys.path',source); self.assertNotIn('__file__',source)
        self.assertFalse(any((n.module or '').startswith('designer_generator') for n in ast.walk(ast.parse(source)) if isinstance(n,ast.ImportFrom)))

if __name__=='__main__': unittest.main()
