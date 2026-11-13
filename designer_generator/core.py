"""Reflected-gamma model, independent samplers and descriptive validation."""
from pathlib import Path
from time import perf_counter
import math
import numpy as np
import pandas as pd
from scipy import stats
from designer_generator import algorithms

ROOT = Path(__file__).resolve().parents[1]
SOURCE_COMMIT = "01a1c6ce89d076e969bf0a8300fcd9abc2c96e36"


def load_no2(path=None):
    return pd.read_csv(path or ROOT / 'ASE10.csv', sep=';')['ASE_NO2'].dropna()


def _values(data):
    x = np.asarray(data, dtype=float)
    if x.ndim != 1 or len(x) < 3 or not np.isfinite(x).all() or np.ptp(x) == 0:
        raise ValueError('At least three finite, nonconstant observations are required.')
    return x


def fit_parameters(data):
    """MLE for X=b-theta*G, by fitting Gamma to -X."""
    a, location, theta = stats.gamma.fit(-_values(data), method='MLE')
    return float(a), float(-location), float(theta)


def moment_parameters(data):
    x = _values(data)
    skew = float(stats.skew(x, bias=True))
    if skew >= 0:
        raise ValueError('Reflected-gamma moment estimates require negative skewness.')
    a = 4 / skew**2
    theta = math.sqrt(float(x.var(ddof=0)) / a)
    return a, float(x.mean()) + a*theta, theta


def model_cdf(x, a, b, theta):
    return stats.gamma.sf((b-np.asarray(x))/theta, a)


def model_pdf(x, a, b, theta):
    return stats.gamma.pdf((b-np.asarray(x))/theta, a) / theta


def model_quantile(p, a, b, theta):
    return b-theta*stats.gamma.isf(p, a)


def theoretical(a, b, theta, n=None):
    return {'n': n, 'sum': None if n is None else n*(b-a*theta),
            'mean': b-a*theta, 'median': float(model_quantile(.5,a,b,theta)),
            'std': math.sqrt(a)*theta, 'variance': a*theta**2,
            'skew': -2/math.sqrt(a), 'q05': float(model_quantile(.05,a,b,theta)),
            'q95': float(model_quantile(.95,a,b,theta)),
            'min': None, 'max': b, 'modes': [], 'mode_frequency': None,
            'density_mode': b-theta*(a-1) if a>1 else b}


def summary(data):
    x = _values(data)
    unique, counts = np.unique(x, return_counts=True)
    frequency = int(counts.max())
    return {'n': len(x), 'sum': float(x.sum()), 'mean': float(x.mean()),
            'median': float(np.median(x)), 'std': float(x.std(ddof=1)),
            'variance': float(x.var(ddof=1)), 'skew': float(stats.skew(x,bias=False)),
            'min': float(x.min()), 'max': float(x.max()),
            'q05': float(np.quantile(x,.05)), 'q95': float(np.quantile(x,.95)),
            'modes': unique[counts==frequency].tolist() if frequency>1 else [],
            'mode_frequency': frequency}


def compare_models(data):
    x = _values(data)
    a,b,theta = fit_parameters(x)
    ma,mb,mt = moment_parameters(x)
    alpha,loc,scale = stats.skewnorm.fit(x)
    ga,gl,gt = stats.gamma.fit(x)
    mu,sd = stats.norm.fit(x)
    specifications = [
        ('Отражённая гамма, MLE','reflected_gamma','MLE',(a,b,theta),3,
         lambda z:model_cdf(z,a,b,theta), lambda z:stats.gamma.logpdf(-z,a,-b,theta),
         theoretical(a,b,theta)),
        ('Отражённая гамма, моменты','reflected_gamma_moments','moments',(ma,mb,mt),None,
         lambda z:model_cdf(z,ma,mb,mt),lambda z:stats.gamma.logpdf(-z,ma,-mb,mt),theoretical(ma,mb,mt)),
        ('Скошенная нормальная, MLE','skew_normal','MLE',(alpha,loc,scale),3,
         lambda z:stats.skewnorm.cdf(z,alpha,loc,scale),lambda z:stats.skewnorm.logpdf(z,alpha,loc,scale),
         {'mean':float(stats.skewnorm.mean(alpha,loc,scale)), 'std':float(stats.skewnorm.std(alpha,loc,scale)),
          'variance':float(stats.skewnorm.var(alpha,loc,scale)), 'skew':float(stats.skewnorm.stats(alpha,loc,scale,moments='s'))}),
        ('Обычная гамма, MLE','right_gamma','MLE',(ga,gl,gt),3,
         lambda z:stats.gamma.cdf(z,ga,gl,gt),lambda z:stats.gamma.logpdf(z,ga,gl,gt),
         {'mean':gl+ga*gt,'std':math.sqrt(ga)*gt,'variance':ga*gt**2,'skew':2/math.sqrt(ga)}),
        ('Нормальная, MLE','normal','MLE',(mu,sd),2,
         lambda z:stats.norm.cdf(z,mu,sd),lambda z:stats.norm.logpdf(z,mu,sd),
         {'mean':mu,'std':sd,'variance':sd**2,'skew':0.})]
    records=[]
    for name,key,estimation,parameters,k,cdf,logpdf,moments in specifications:
        likelihood=float(np.sum(logpdf(x)))
        records.append({'name':name,'key':key,'estimation':estimation,
                        'parameters':[float(p) for p in parameters],
                        'D_data':float(stats.ks_1samp(x,cdf).statistic),
                        'log_likelihood':likelihood,'AIC':None if k is None else 2*k-2*likelihood,
                        **{key:float(value) for key,value in moments.items() if key in ['mean','std','variance','skew']}})
    return records


def generate(method,n,a,b,theta,seed):
    if method not in ('A','GD') or not isinstance(n,int) or not 1<=n<=20000:
        raise ValueError('Choose A or GD and integer N from 1 to 20000.')
    if not all(np.isfinite(v) for v in (a,b,theta)) or not 1<a<=1000 or abs(b)>1e9 or not 1e-6<=theta<=1e6:
        raise ValueError('Require 1<a<=1000, |b|<=1e9 and 1e-6<=theta<=1e6.')
    if not isinstance(seed,int) or not 0<=seed<2**32:
        raise ValueError('Seed must be an integer from 0 through 2**32-1.')
    rng=np.random.default_rng(seed)
    start=perf_counter()
    gamma,counts=(algorithms.gamma_a if method=='A' else algorithms.gamma_gd)(n,a,rng)
    elapsed=perf_counter()-start
    values=b-theta*gamma
    return {'values':values,'gamma_values':gamma,'attempts':counts['proposals'],
            'acceptance':n/counts['proposals'],'seconds':elapsed,**counts,
            'support_violations':int(np.count_nonzero(values>b))}


def diagnostics(values,a,b,theta,data=None):
    x=np.asarray(values)
    result={'D к модели':float(stats.ks_1samp(x,lambda z:model_cdf(z,a,b,theta)).statistic),
            'Асимметрия':float(stats.skew(x,bias=False)),
            'Значений выше b':int(np.count_nonzero(x>b))}
    if data is not None:
        result['D к данным']=float(stats.ks_2samp(x,np.asarray(data)).statistic)
    return result


def comparison_table(data,runs,a,b,theta):
    observed=summary(data)
    rows={'Данные':observed,'Модель':theoretical(a,b,theta,len(data))}
    rows.update({method:summary(run['values']) for method,run in runs.items()})
    keys=[('n','N'),('sum','Сумма, мкВ'),('mean','Среднее, мкВ'),('median','Медиана, мкВ'),
          ('std','Стандартное отклонение, мкВ'),('variance','Дисперсия, мкВ²'),('skew','Асимметрия'),
          ('q05','5-й процентиль, мкВ'),('q95','95-й процентиль, мкВ'),('min','Минимум, мкВ'),('max','Максимум, мкВ'),('modes','Эмпирические моды, мкВ')]
    if any(len(run['values'])!=len(data) for run in runs.values()):
        keys=[item for item in keys if item[0]!='sum']
    records=[]
    for key,label in keys:
        record={'Показатель':label}
        for name,row in rows.items():
            value=row.get(key)
            if key=='modes':
                value='Нет повторов' if not value else '; '.join(f'{v:.6g}' for v in value)
                if name=='Модель': value='—'
            elif key=='max' and name=='Модель': value=f'Граница b = {b:.9g}'
            elif value is None: value='—'
            elif key=='n': value=str(value)
            else: value=f'{value:.9g}'
            record[name]=value
        records.append(record)
    return pd.DataFrame(records)


def sampling_intervals(n,a,b,theta,repetitions=600,seed=20261113):
    """95% Monte Carlo prediction bands for sample statistics at fixed parameters.

    Reference Gamma sampling is used only for calibration, not as A or GD.
    These are not parameter CIs and not fitted-distribution goodness-of-fit tests.
    """
    rng=np.random.default_rng(seed)
    samples=b-theta*rng.gamma(a,size=(repetitions,n))
    statistics={'mean':samples.mean(axis=1),'std':samples.std(axis=1,ddof=1),
                'variance':samples.var(axis=1,ddof=1),'skew':stats.skew(samples,axis=1,bias=False),
                'q05':np.quantile(samples,.05,axis=1),'q95':np.quantile(samples,.95,axis=1)}
    return {key:{'low':float(np.quantile(value,.025)), 'high':float(np.quantile(value,.975))}
            for key,value in statistics.items()}
