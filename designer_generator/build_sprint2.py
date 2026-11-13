"""Execute standalone Sprint 2; create reader artifacts without changing root reports."""
import ast,base64,copy,hashlib,json,os,re,sys,textwrap
from pathlib import Path
import nbformat
from nbclient import NotebookClient
from nbconvert import HTMLExporter
from bs4 import BeautifulSoup
from jupyter_client import KernelManager
from jupyter_client.kernelspec import KernelSpec

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
RAW='https://raw.githubusercontent.com/EastC0ast/lab01/design-layout/designer_generator/'
URL='https://github.com/EastC0ast/lab01/blob/design-layout/designer_generator/'
FIGURES=['gen01-models.png','gen02-generators.png','gen03-intervals.png']


def functions_source(filename):
    source=(HERE/filename).read_text(encoding='utf8')
    return '\n\n'.join(ast.get_source_segment(source,node) for node in ast.parse(source).body
                       if isinstance(node,(ast.FunctionDef,ast.ClassDef)) and node.name!='load_no2')


def notebook_math(text):
    return re.sub(r'```math\s*\n(.*?)\n```',lambda m:'\n\n$$\n'+m[1]+'\n$$\n\n',text,flags=re.S)


def github_math(text):
    return re.sub(r'(?m)^\$\$\s*\n(.*?)\n\$\$\s*$',lambda m:'```math\n'+m[1]+'\n```',text,flags=re.S)


def fill(text,result):
    a,b,theta=[result['parameters'][k] for k in ('a','b','theta')]
    observed=result['metrics']['data']; model=result['metrics']['model']
    models={r['key']:r for r in result['models']}
    format_number=lambda v,d=6:f'{v:.{d}f}'.replace('.',',')
    fit=(f"Оценки MLE: a={format_number(a)}, b={format_number(b)} мкВ, θ={format_number(theta)} мкВ. "
         f"Модель даёт среднее {format_number(model['mean'])} мкВ, SD {format_number(model['std'])} мкВ "
         f"и асимметрию {format_number(model['skew'])}. В данных: {format_number(observed['mean'])} мкВ, "
         f"{format_number(observed['std'])} мкВ и {format_number(observed['skew'])}. "
         f"Разность дисперсий модели и данных составляет {format_number(100*(model['variance']/observed['variance']-1),3)}%. "
         f"Для отражённой гаммы D={format_number(models['reflected_gamma']['D_data'])}, "
         f"для скошенной нормальной D={format_number(models['skew_normal']['D_data'])}; "
         f"AIC соответственно {format_number(models['reflected_gamma']['AIC'],3)} и {format_number(models['skew_normal']['AIC'],3)}.")
    resume=(f"Обычная гамма не передавала отрицательную асимметрию. Отражение позволило получить модель "
            f"с близкими средним и разбросом, однако скошенная нормальная описывает эту выборку лучше по AIC. "
            f"Для N={result['data']['N']} и seed={result['seed']} алгоритм А дал среднее "
            f"{format_number(result['metrics']['A']['mean'])} мкВ и дисперсию {format_number(result['metrics']['A']['variance'])} мкВ²; "
            f"GD — {format_number(result['metrics']['GD']['mean'])} мкВ и {format_number(result['metrics']['GD']['variance'])} мкВ². "
            f"Значений выше b нет у обоих методов. В восьми контрольных выборках поддержка, моменты и CDF "
            f"удовлетворили указанным допускам; это численная проверка реализации, а не доказательство истинности "
            f"модели реальных данных. Сравнение эффективности приведено для семи запусков на одном компьютере.")
    return text.replace('__FIT_CONCLUSION__',fit).replace('__RESUME__',resume).replace('__MISSING__',str(result['data']['missing'])).replace('__N__',str(result['data']['N']))


def main():
    chunks=re.split(r'<!-- cell:([^ ]+) -->\s*',(HERE/'report_source.md').read_text(encoding='utf8'))
    sections=list(zip(chunks[1::2],chunks[2::2]))
    cells=[]
    def code(source,key,figure=None):
        metadata={} if figure is None else {'figure_filename':figure}
        cells.append(nbformat.v4.new_code_cell(source,id=key,metadata=metadata))
    for key,text in sections:
        cells.append(nbformat.v4.new_markdown_cell(notebook_math(text.strip()),id=key))
        if key=='gen-description':
            code("""from pathlib import Path
import sys,math,json,hashlib,io
from time import perf_counter
from types import SimpleNamespace
import numpy as np
import pandas as pd
from scipy import stats
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from IPython.display import display,Image
ROOT=next(p for p in [Path.cwd(),*Path.cwd().parents] if (p/'ASE10.csv').is_file())
GEN_HERE=ROOT/'designer_generator'
(GEN_HERE/'figures').mkdir(parents=True,exist_ok=True)
pd.set_option('display.max_columns',None)
pd.set_option('display.max_colwidth',None)
pd.set_option('display.max_rows',40)
pd.set_option('display.precision',9)
pd.set_option('display.float_format',None)
gen_raw=pd.read_csv(ROOT/'ASE10.csv',sep=';')
gen_data=gen_raw['ASE_NO2'].dropna().to_numpy()
assert len(gen_data)==3686 and len(gen_raw)==len(gen_data)+int(gen_raw.ASE_NO2.isna().sum())""",'gen-data')
        elif key=='gen-code':
            code((HERE/'algorithms.py').read_text(encoding='utf8')+"\nalgorithms=SimpleNamespace(gamma_a=gamma_a,gamma_gd=gamma_gd)",'gen-algorithms')
            code(functions_source('core.py'),'gen-model-functions')
            code(functions_source('study.py'),'gen-experiment-functions')
        elif key=='gen-fit-caption':
            code("""gen_parameters=fit_parameters(gen_data)
gen_models=compare_models(gen_data)
gen_model_table=pd.DataFrame([{'Модель':r['name'],'Параметры':', '.join(f'{p:.9g}' for p in r['parameters']),
    'Среднее, мкВ':r['mean'],'SD, мкВ':r['std'],'Асимметрия':r['skew'],'D':r['D_data'],
    'AIC':'—' if r['AIC'] is None else f"{r['AIC']:.6f}"} for r in gen_models])
display(gen_model_table)""",'gen-fit')
        elif key=='gen-model-figure':
            code("""gen_fig=figure_models(gen_data,gen_models,model_pdf,model_cdf)
gen_buffer=io.BytesIO(); gen_fig.savefig(gen_buffer,format='png',dpi=150,bbox_inches='tight',facecolor='white')
(GEN_HERE/'figures/gen01-models.png').write_bytes(gen_buffer.getvalue())
plt.close(gen_fig); display(Image(data=gen_buffer.getvalue()))""",'gen-plot-models',FIGURES[0])
        elif key=='gen-tests':
            code("""gen_seed=40
gen_runs={method:generate(method,len(gen_data),*gen_parameters,gen_seed) for method in ['A','GD']}
gen_metrics={'data':summary(gen_data),'model':theoretical(*gen_parameters,len(gen_data)),
             **{method:summary(run['values']) for method,run in gen_runs.items()}}
display(comparison_table(gen_data,gen_runs,*gen_parameters))
""",'gen-metrics')
        elif key=='gen-diagnostics':
            code("""
gen_diagnostics={method:diagnostics(run['values'],*gen_parameters,gen_data) for method,run in gen_runs.items()}
display(pd.DataFrame(gen_diagnostics).T)
""",'gen-diagnostics-table')
        elif key=='gen-sampling-table':
            code("""
gen_bands=sampling_intervals(len(gen_data),*gen_parameters,repetitions=600,seed=20261113)
gen_interval_rows=interval_table(gen_data,gen_runs,gen_parameters,gen_bands,summary,theoretical)
display(pd.DataFrame(gen_interval_rows))
""",'gen-sampling-table-output')
        elif key=='gen-law-tests':
            code("""
gen_checks=scientific_checks(algorithms,n=40000,seed=20261113)
gen_check_table=pd.DataFrame([{'Метод':r['Метод'],'a':r['a'],'N':r['N'],'D':r['D к Γ(a,1)'],'Граница DKW':r['Граница DKW'],
    'Ошибка среднего / допуск':r['|ошибка среднего|']/r['Допуск среднего, 6SE'],
    'Ошибка дисперсии / допуск':r['|ошибка дисперсии|']/r['Допуск дисперсии, 6SE'],'Вне поддержки':r['Вне поддержки']} for r in gen_checks])
display(gen_check_table)
for method,run in gen_runs.items():
    assert run['support_violations']==0
    repeated=generate(method,len(gen_data),*gen_parameters,gen_seed)
    np.testing.assert_array_equal(run['values'],repeated['values'])""",'gen-law-checks')
        elif key=='gen-generated-figure':
            code("""gen_fig=figure_generators(gen_data,gen_runs,gen_parameters,model_pdf,model_cdf)
gen_buffer=io.BytesIO(); gen_fig.savefig(gen_buffer,format='png',dpi=150,bbox_inches='tight',facecolor='white')
(GEN_HERE/'figures/gen02-generators.png').write_bytes(gen_buffer.getvalue())
plt.close(gen_fig); display(Image(data=gen_buffer.getvalue()))""",'gen-plot-generators',FIGURES[1])
        elif key=='gen-interval-figure':
            code("""gen_fig=figure_intervals(gen_interval_rows)
gen_buffer=io.BytesIO(); gen_fig.savefig(gen_buffer,format='png',dpi=150,bbox_inches='tight',facecolor='white')
(GEN_HERE/'figures/gen03-intervals.png').write_bytes(gen_buffer.getvalue())
plt.close(gen_fig); display(Image(data=gen_buffer.getvalue()))""",'gen-plot-intervals',FIGURES[2])
        elif key=='gen-benchmark':
            code("""gen_benchmark=benchmark(generate,len(gen_data),*gen_parameters,repeats=7,seed=gen_seed)
display(pd.DataFrame(gen_benchmark))
gen_result={'study':'Sprint 2: reflected gamma for ASE_NO2','selected_model':'reflected_gamma',
 'data':{'N':len(gen_data),'raw_rows':len(gen_raw),'missing':int(gen_raw.ASE_NO2.isna().sum()),'units':'µV',
         'source':'https://data.mendeley.com/datasets/82dnstrd93/2',
         'csv_sha256_lf':hashlib.sha256((ROOT/'ASE10.csv').read_bytes().replace(b'\\r\\n',b'\\n')).hexdigest()},
 'parameters':dict(zip(['a','b','theta'],gen_parameters)),'models':gen_models,'metrics':gen_metrics,
 'diagnostics':gen_diagnostics,'sampling_intervals':gen_bands,'sampling_repetitions':600,'sampling_seed':20261113,
 'sampling_rows':gen_interval_rows,'distribution_checks':gen_checks,'benchmark':gen_benchmark,'seed':gen_seed}
(GEN_HERE/'results.json').write_text(json.dumps(gen_result,ensure_ascii=False,indent=2,allow_nan=False)+'\\n',encoding='utf8')
pd.DataFrame({'data':gen_data,'A':gen_runs['A']['values'],'GD':gen_runs['GD']['values']}).to_csv(GEN_HERE/'generated.csv',index=False)
gen_model_table.to_csv(GEN_HERE/'model_comparison.csv',index=False)
comparison_table(gen_data,gen_runs,*gen_parameters).to_csv(GEN_HERE/'metrics.csv',index=False)
pd.DataFrame(gen_interval_rows).to_csv(GEN_HERE/'sampling_intervals.csv',index=False)
pd.DataFrame(gen_benchmark).to_csv(GEN_HERE/'benchmark.csv',index=False)""",'gen-benchmark-and-results')

    for cell in cells:
        if cell.cell_type!='code': continue
        if cell.id=='gen-data':
            cell.source=cell.source.replace('import sys,math,json,hashlib,io','import sys,math,json,hashlib,io,os')
            cell.source=cell.source.replace("(GEN_HERE/'figures').mkdir(parents=True,exist_ok=True)",
                "GEN_EXPORT=os.environ.get('LAB01_SPRINT2_EXPORT')=='1'\nif GEN_EXPORT: (GEN_HERE/'figures').mkdir(parents=True,exist_ok=True)")
        if 'figure_filename' in cell.metadata:
            cell.source=re.sub(r"(?m)^(\(GEN_HERE/'figures/[^\n]+)$",r'if GEN_EXPORT: \1',cell.source)
        if cell.id=='gen-benchmark-and-results':
            marker="(GEN_HERE/'results.json').write_text"
            head,tail=cell.source.split(marker,1)
            cell.source=head+'if GEN_EXPORT:\n'+textwrap.indent(marker+tail,'    ')
    full=nbformat.v4.new_notebook(cells=cells,metadata={'kernelspec':{'name':'python3','display_name':'Python 3','language':'python'}})
    manager=KernelManager(kernel_name='python3')
    manager._kernel_spec=KernelSpec(argv=[sys.executable,'-m','ipykernel_launcher','-f','{connection_file}'],display_name='Sprint 2',language='python')
    try:
        NotebookClient(full,km=manager,timeout=240,resources={'metadata':{'path':str(ROOT)}}).execute(env={**os.environ,'LAB01_SPRINT2_EXPORT':'1'})
    finally:
        if manager.has_kernel: manager.shutdown_kernel(now=True)
    result=json.loads((HERE/'results.json').read_text(encoding='utf8'))
    for cell in full.cells:
        if cell.cell_type=='markdown': cell.source=fill(cell.source,result)
    nbformat.validate(full)
    nbformat.write(full,HERE/'sprint2_calculations.ipynb')
    reader=nbformat.v4.new_notebook(cells=[])
    local=nbformat.v4.new_notebook(cells=[])
    readme=[]; images=[]
    for cell in full.cells:
        if cell.cell_type=='markdown':
            for target in (reader,local): target.cells.append(copy.deepcopy(cell))
            readme.append(github_math(cell.source))
            continue
        for index,output in enumerate(cell.get('outputs',[])):
            bundle=output.get('data',{})
            if 'image/png' in bundle:
                image=base64.b64decode(bundle['image/png']); filename=cell.metadata['figure_filename']
                assert image==(HERE/'figures'/filename).read_bytes()
                images.append(filename)
                public=f'![Рисунок — {filename}]({RAW}figures/{filename})'
                readme.append(f'![Рисунок — {filename}](figures/{filename})')
                reader.cells.append(nbformat.v4.new_markdown_cell(public,id=cell.id+'-output-'+str(index)))
                local.cells.append(nbformat.v4.new_markdown_cell('<img alt="Рисунок Sprint 2" src="data:image/png;base64,'+bundle['image/png']+'">',id=cell.id+'-output-'+str(index)))
            elif 'text/html' in bundle:
                for target in (reader,local): target.cells.append(nbformat.v4.new_markdown_cell(bundle['text/html'],id=cell.id+'-output-'+str(index)))
                readme.append(bundle['text/html'])
    assert images==FIGURES
    for cell in reader.cells:
        cell.source=re.sub(r'\]\((?!https?://|#)([^)]+)\)',lambda m:']('+URL+m[1]+')',cell.source)
        cell.source=re.sub(r'\]\(#([^)]*)\)',lambda m:']('+URL+'README.md#'+m[1]+')',cell.source)
    nbformat.write(reader,HERE/'sprint2.ipynb')
    body,_=HTMLExporter(template_name='lab').from_notebook_node(local)
    soup=BeautifulSoup(body,'html.parser')
    style=soup.new_tag('style'); style.string='main{max-width:1100px;margin:auto;padding:24px}body{color:#243447}img{max-width:100%;height:auto}table{border-collapse:collapse}th,td{padding:6px;border-bottom:1px solid #d9e2ea}p{line-height:1.6}pre{white-space:pre-wrap}'
    soup.head.append(style)
    assert len(soup.find_all('img'))==3 and not soup.select('.jp-CodeCell')
    (HERE/'sprint2_reading.html').write_text(str(soup),encoding='utf8')
    (HERE/'README.md').write_text('\n\n'.join(readme)+'\n',encoding='utf8',newline='\n')
    fragment=re.sub(r'\]\((?!https?://|#)([^)]+)\)',lambda m:']('+URL+m[1]+')','\n\n'.join(readme))
    fragment=fragment.replace(']('+URL+'figures/',']('+RAW+'figures/')
    (HERE/'reader_fragment.md').write_text(fragment+'\n',encoding='utf8',newline='\n')
    a,b,theta=[result['parameters'][k] for k in ('a','b','theta')]
    (HERE/'summary.md').write_text(f"Для ASE_NO2 (мкВ) выбрана отражённая гамма-модель X=b−θG с a={a:.6f}, b={b:.6f}, θ={theta:.6f}. Она передаёт отрицательную асимметрию; скошенная нормальная имеет меньший AIC и остаётся лучшей описательной альтернативой. Алгоритмы А и полный GD проверены отдельно от качества модели. [Полный Sprint 2]({URL}README.md) · [Расчёты]({URL}sprint2_calculations.ipynb)\n",encoding='utf8')
    filenames=['README.md','sprint2.ipynb','sprint2_calculations.ipynb','sprint2_reading.html','results.json','algorithms.py','core.py','generated.csv']
    verification={'status':'passed','N':result['data']['N'],
                  'executed_code_cells':sum(c.cell_type=='code' for c in full.cells),'reader_code_cells':0,
                  'errors':0,'png_outputs':3,'html_embedded_pngs':3,'scientific_law_checks':len(result['distribution_checks']),
                  'sha256_lf':{name:hashlib.sha256((HERE/name).read_bytes().replace(b'\r\n',b'\n')).hexdigest() for name in filenames},
                  'historical_source_sha256':hashlib.sha256((HERE/'original_generators.py').read_text(encoding='utf8').split('import numpy as np\n\n',1)[1].encode()).hexdigest()}
    (HERE/'sprint2_verification.json').write_text(json.dumps(verification,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(verification,ensure_ascii=False,indent=2))


if __name__=='__main__': main()
