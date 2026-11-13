"""Numerical experiment and restrained figures for Sprint 2."""
import math
from time import perf_counter
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy import stats


def scientific_checks(algorithms,n=40000,seed=20261113):
    epsilon=math.sqrt(math.log(2/1e-6)/(2*n))
    rows=[]
    for name,fn in [('A',algorithms.gamma_a),('GD',algorithms.gamma_gd)]:
        for a in [1.01,3.,5.4525349587,200.]:
            x,counts=fn(n,a,np.random.default_rng(seed))
            distance=float(stats.ks_1samp(x,lambda z:stats.gamma.cdf(z,a)).statistic)
            mean_error=abs(float(x.mean())-a)
            variance_error=abs(float(x.var(ddof=1))-a)
            mean_bound=6*math.sqrt(a/n)
            variance_bound=6*math.sqrt((2*a*a+6*a)/n)
            assert np.all(x>0) and np.isfinite(x).all()
            assert distance<epsilon and mean_error<mean_bound and variance_error<variance_bound
            rows.append({'Метод':name,'a':a,'N':n,'D к Γ(a,1)':distance,'Граница DKW':epsilon,
                         '|ошибка среднего|':mean_error,'Допуск среднего, 6SE':mean_bound,
                         '|ошибка дисперсии|':variance_error,'Допуск дисперсии, 6SE':variance_bound,
                         'Вне поддержки':int(np.sum(x<0)),'Кандидатов оболочки':counts['hat_proposals']})
    return rows


def benchmark(generate,n,a,b,theta,repeats=7,seed=40):
    rows=[]
    for method in ['A','GD']:
        elapsed=[]; proposals=[]
        for repeat in range(repeats):
            run=generate(method,n,a,b,theta,seed+repeat)
            elapsed.append(run['seconds']); proposals.append(run['proposals'])
        rows.append({'Метод':method,'N':n,'Повторений':repeats,'Медиана времени, с':float(np.median(elapsed)),
                     'Q25 времени, с':float(np.quantile(elapsed,.25)),'Q75 времени, с':float(np.quantile(elapsed,.75)),
                     'Медиана кандидатов':float(np.median(proposals))})
    return rows


def interval_table(data,runs,parameters,bands,summary,theoretical):
    a,b,theta=parameters
    moments=theoretical(a,b,theta,len(data)); observed=summary(data)
    labels={'mean':'Среднее, мкВ','std':'SD, мкВ','variance':'Дисперсия, мкВ²','skew':'Асимметрия','q05':'5-й процентиль, мкВ','q95':'95-й процентиль, мкВ'}
    records=[]
    for key,label in labels.items():
        row={'Показатель':label,'Данные':observed[key],'Модель':moments[key],
             'Данные − модель':observed[key]-moments[key],
             '95% нижняя':bands[key]['low'],'95% верхняя':bands[key]['high']}
        row.update({name:summary(run['values'])[key] for name,run in runs.items()})
        records.append(row)
    return records


def _style():
    return plt.rc_context({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False,
                           'axes.grid':True,'grid.alpha':.2,'figure.facecolor':'white','axes.facecolor':'white'})


def figure_models(data,models,model_pdf,model_cdf):
    with _style():
        fig,axes=plt.subplots(1,2,figsize=(11,4.3))
        grid=np.linspace(min(data)-50,max(data)+65,700)
        axes[0].plot(grid,stats.gaussian_kde(data)(grid),color='#64748b',label='Данные, KDE')
        ordered=np.sort(data)
        axes[1].step(ordered,np.arange(1,len(ordered)+1)/len(ordered),where='post',color='#64748b',label='Данные, ECDF')
        for key,color,label in [('reflected_gamma','#245c7a','Отражённая гамма'),('skew_normal','#a57240','Скошенная нормальная'),('right_gamma','#85978b','Обычная гамма')]:
            row=next(r for r in models if r['key']==key); p=row['parameters']
            if key=='reflected_gamma': pdf,cdf=model_pdf(grid,*p),model_cdf(grid,*p)
            elif key=='skew_normal': pdf,cdf=stats.skewnorm.pdf(grid,*p),stats.skewnorm.cdf(grid,*p)
            else: pdf,cdf=stats.gamma.pdf(grid,*p),stats.gamma.cdf(grid,*p)
            axes[0].plot(grid,pdf,color=color,label=label); axes[1].plot(grid,cdf,color=color,label=label)
        axes[0].set(title='Плотности',ylabel='Плотность, 1/мкВ',xlabel='ASE_NO2, мкВ')
        axes[1].set(title='Функции распределения',ylabel='F(x)',xlabel='ASE_NO2, мкВ',ylim=(0,1.02))
        for axis in axes: axis.legend(fontsize=8)
        fig.tight_layout(pad=1.6)
        return fig


def figure_generators(data,runs,parameters,model_pdf,model_cdf):
    with _style():
        fig,axes=plt.subplots(1,2,figsize=(11,4.3))
        values=np.r_[data,*[r['values'] for r in runs.values()]]
        grid=np.linspace(values.min()-10,max(values.max()+10,parameters[1]+5),700)
        for x,label,color in [(data,'Данные','#64748b'),(runs['A']['values'],'Алгоритм А','#245c7a'),(runs['GD']['values'],'Алгоритм GD','#a57240')]:
            axes[0].plot(grid,stats.gaussian_kde(x)(grid),color=color,label=label)
            ordered=np.sort(x); axes[1].step(ordered,np.arange(1,len(x)+1)/len(x),where='post',color=color,label=label)
        axes[0].plot(grid,model_pdf(grid,*parameters),'--',color='#334155',label='Модель')
        axes[1].plot(grid,model_cdf(grid,*parameters),'--',color='#334155',label='Модель')
        axes[0].set(title='Плотности',ylabel='Плотность, 1/мкВ',xlabel='ASE_NO2, мкВ')
        axes[1].set(title='Функции распределения',ylabel='F(x)',xlabel='ASE_NO2, мкВ',ylim=(0,1.02))
        for axis in axes: axis.legend(fontsize=8)
        fig.tight_layout(pad=1.6)
        return fig


def figure_intervals(rows):
    with _style():
        fig,axes=plt.subplots(1,2,figsize=(10,4))
        for axis,index,title in zip(axes,[0,2],['Среднее, мкВ','Дисперсия, мкВ²']):
            row=rows[index]
            axis.axvspan(row['95% нижняя'],row['95% верхняя'],color='#dbe5ec',label='95% выборочный диапазон')
            for i,(label,color) in enumerate([('Данные','#64748b'),('Модель','#334155'),('A','#245c7a'),('GD','#a57240')]):
                axis.scatter(row[label],i,color=color,s=48,label=label)
            axis.set(yticks=range(4),yticklabels=['Данные','Модель','А','GD'],xlabel=title,title=title)
        fig.tight_layout(pad=1.6)
        return fig
