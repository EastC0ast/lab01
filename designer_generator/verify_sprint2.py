"""Read-only audit of stored Sprint 2, with optional non-writing re-execution."""
import argparse,base64,copy,hashlib,json,math,os,re,sys
from pathlib import Path
import nbformat
import numpy as np
import pandas as pd
from bs4 import BeautifulSoup
from nbclient import NotebookClient
from jupyter_client import KernelManager
from jupyter_client.kernelspec import KernelSpec

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
TIMING_COLUMNS={'Медиана времени, с','Q25 времени, с','Q75 времени, с'}
FIGURES=['gen01-models.png','gen02-generators.png','gen03-intervals.png']


def sha(path): return hashlib.sha256(path.read_bytes().replace(b'\r\n',b'\n')).hexdigest()


def text_table(html,ignore_timing=False):
    soup=BeautifulSoup(html,'html.parser')
    for table in soup.find_all('table'):
        rows=table.find_all('tr')
        headers=[cell.get_text(' ',strip=True) for cell in rows[0].find_all(['th','td'])]
        ignored={i for i,name in enumerate(headers) if ignore_timing and name in TIMING_COLUMNS}
        yield [[cell.get_text(' ',strip=True) for i,cell in enumerate(row.find_all(['th','td'])) if i not in ignored] for row in rows]


def verify():
    manifest=json.loads((HERE/'sprint2_verification.json').read_text(encoding='utf8'))
    result=json.loads((HERE/'results.json').read_text(encoding='utf8'))
    assert manifest['status']=='passed' and result['data']['N']==manifest['N']==3686
    for name,expected in manifest['sha256_lf'].items(): assert sha(HERE/name)==expected,name
    full=nbformat.read(HERE/'sprint2_calculations.ipynb',as_version=4)
    reader=nbformat.read(HERE/'sprint2.ipynb',as_version=4)
    nbformat.validate(full);nbformat.validate(reader)
    assert all(cell.cell_type=='markdown' for cell in reader.cells)
    assert all(cell.id.startswith('gen-') for cell in full.cells)
    assert len(set(c.id for c in full.cells))==len(full.cells)
    codes=[c for c in full.cells if c.cell_type=='code']
    assert len(codes)==manifest['executed_code_cells']==13
    assert [c.execution_count for c in codes]==list(range(1,len(codes)+1))
    outputs=[o for cell in codes for o in cell.outputs]
    assert not any(o.output_type=='error' or (o.output_type=='stream' and o.get('name')=='stderr') for o in outputs)
    images=[base64.b64decode(o.data['image/png']) for o in outputs if 'image/png' in o.get('data',{})]
    assert images==[(HERE/'figures'/name).read_bytes() for name in FIGURES]
    tables=[o.data['text/html'] for o in outputs if 'text/html' in o.get('data',{})]
    assert len(tables)==6
    html=BeautifulSoup((HERE/'sprint2_reading.html').read_text(encoding='utf8'),'html.parser')
    assert not html.select('.jp-CodeCell') and len(html.find_all('img'))==3
    assert [base64.b64decode(i['src'].split(',',1)[1]) for i in html.find_all('img')]==images
    assert len(html.select('table.dataframe'))==6
    generated=pd.read_csv(HERE/'generated.csv',float_precision='round_trip')
    assert generated.shape==(3686,3) and set(generated.columns)=={'data','A','GD'}
    a,b,theta=[result['parameters'][key] for key in ('a','b','theta')]
    for method in ['A','GD']:
        values=generated[method].to_numpy()
        assert np.isfinite(values).all() and np.all(values<=b)
        assert np.isclose(values.mean(),result['metrics'][method]['mean'],rtol=1e-12)
        assert np.isclose(values.var(ddof=1),result['metrics'][method]['variance'],rtol=1e-12)
        assert result['metrics'][method]['modes']==[]
    assert np.isclose(result['metrics']['model']['mean'],b-a*theta,rtol=1e-12)
    assert np.isclose(result['metrics']['model']['variance'],a*theta**2,rtol=1e-12)
    assert result['metrics']['model']['skew']<0
    model={r['key']:r for r in result['models']}
    assert model['skew_normal']['AIC']<model['reflected_gamma']['AIC']
    assert model['reflected_gamma']['D_data']<model['right_gamma']['D_data']
    assert len(result['distribution_checks'])==8
    for row in result['distribution_checks']:
        assert row['Вне поддержки']==0
        assert row['D к Γ(a,1)']<row['Граница DKW']
        assert row['|ошибка среднего|']<row['Допуск среднего, 6SE']
        assert row['|ошибка дисперсии|']<row['Допуск дисперсии, 6SE']
    readme=(HERE/'README.md').read_text(encoding='utf8')
    assert not re.search(r'__[A-Z_]+__',readme)
    for number in range(11,17): assert f'gen-table-{number}' in readme and f'Таблица {number}' in readme
    for number in range(17,20): assert f'gen-figure-{number}' in readme and f'Рисунок {number}' in readme
    assert '| cat_id | notebook_link | coeff | comment |' in readme
    assert 'lab.ic.02.' not in readme
    return full,{'status':'passed','N':3686,'code_cells':13,'PNG':3,'tables':6,'law_checks':8,'reader_code_cells':0}


def execute_without_writes(full):
    paths=[p for p in HERE.rglob('*') if p.is_file() and '__pycache__' not in p.parts]
    before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    executed=copy.deepcopy(full)
    manager=KernelManager(kernel_name='python3')
    manager._kernel_spec=KernelSpec(argv=[sys.executable,'-m','ipykernel_launcher','-f','{connection_file}'],display_name='Sprint 2 verification',language='python')
    environment={k:v for k,v in os.environ.items() if k!='LAB01_SPRINT2_EXPORT'}
    environment['PYTHONDONTWRITEBYTECODE']='1'
    try: NotebookClient(executed,km=manager,timeout=240,resources={'metadata':{'path':str(ROOT)}}).execute(env=environment)
    finally:
        if manager.has_kernel:manager.shutdown_kernel(now=True)
    after={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    assert before==after,'Ordinary notebook execution changed a Sprint 2 artifact'
    for old,new in zip(full.cells,executed.cells):
        if old.cell_type!='code':continue
        assert len(old.outputs)==len(new.outputs),old.id
        for x,y in zip(old.outputs,new.outputs):
            assert y.output_type!='error',old.id
            if 'image/png' in x.get('data',{}):
                assert 'image/png' in y.get('data',{})
                continue
            if 'text/html' in x.get('data',{}):
                ignore=old.id=='gen-benchmark-and-results'
                assert list(text_table(x.data['text/html'],ignore))==list(text_table(y.data['text/html'],ignore)),old.id
            else: assert x==y,old.id
    return {'reexecuted':True,'artifact_writes':0,'numeric_tables_identical_except_three_timing_columns':True}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--execute',action='store_true');args=parser.parse_args()
    full,result=verify()
    if args.execute:result.update(execute_without_writes(full))
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
