"""Joint, time-aligned inference for economically defined reporting families.

These are retrospective reporting families, not a preregistration. Gaussian
moving-average multipliers reproduce the Bartlett HAC(12) covariance, including
cross-country, cross-group and cross-horizon dependence. No model is selected.
"""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from scipy.stats import t

P=Path(__file__).resolve().parents[1]; R=P/'results'
SEED=20261018; B=99999; TERMS=['domestic_noncb','domestic_noncb_x_refinancing']
GROUPS=['ea','advanced','emerging']; HS=[4,8,12]

def read(n):return json.loads((R/(n+'.json')).read_text())

def record(f,term):
    e=next(e for e in f['estimates'] if e['term']==term)
    return dict(sample=f['sample'],model=f['model'],outcome=f['outcome'],horizon=f['horizon'],term=term,
        n=f['n'],countries=f['countries'],p=f.get('p'),df=f['df'],**{k:v for k,v in e.items() if k!='term'},
        start=f['time_start'],end=f['time_end'],psi=np.asarray(f['influence_by_time'])[:,f['coefficient_names'].index(term)])

def difference(f,g,term):
    a,b=record(f,term),record(g,term);start=min(a['start'],b['start']);end=max(a['end'],b['end'])
    psi=np.zeros(end-start+1)
    for sign,r in [(1,a),(-1,b)]:psi[r['start']-start:r['end']-start+1]+=sign*r['psi']
    var=psi@psi
    for lag in range(1,min(12,len(psi)-1)+1):var+=2*(1-lag/13)*(psi[lag:]@psi[:-lag])
    se=np.sqrt(var);coef=a['estimate']-b['estimate'];df=min(a['df'],b['df']);c=t.ppf(.975,df)
    return dict(a,sample=a['sample']+' minus '+b['sample'],model='group_difference',start=start,end=end,psi=psi,
        estimate=coef,se=se,df=df,ci_low=coef-c*se,ci_high=coef+c*se,p_value=2*t.sf(abs(coef/se),df))

def correct(name,records):
    lo=min(r['start'] for r in records);hi=max(r['end'] for r in records);psi=np.zeros((hi-lo+1,len(records)))
    for j,r in enumerate(records):psi[r['start']-lo:r['end']-lo+1,j]=r['psi']
    rng=np.random.default_rng(SEED);L=13
    z=rng.standard_normal((B,len(psi)+L-1));c=np.column_stack([np.zeros(B),np.cumsum(z,axis=1)])
    xi=(c[:,L:]-c[:,:-L])/np.sqrt(L);se=np.array([r['se'] for r in records])
    maximum=np.max(np.abs((xi@psi)/se),axis=1);critical=float(np.quantile(maximum,.95,method='higher'))
    # Numerically verify each score covariance against the fitted HAC variance.
    cov=psi.T@psi
    for lag in range(1,13):
        v=psi[lag:].T@psi[:-lag];cov+=(1-lag/13)*(v+v.T)
    assert np.max(np.abs(np.diag(cov)-se**2))<1e-7
    out=[]
    for r in records:
        pm=(1+np.count_nonzero(maximum>=abs(r['estimate']/r['se'])))/(B+1)
        row={k:v for k,v in r.items() if k not in ['psi','start','end']}
        row.update(family=name,family_size=len(records),p_maxT=max(float(r['p_value']),float(pm)),
            simultaneous_low=r['estimate']-critical*r['se'],simultaneous_high=r['estimate']+critical*r['se'],
            critical_95=critical,draws=B,seed=SEED)
        out.append(row)
    return out

def main():
    main=read('fiscal_main');acc=read('fiscal_accumulation');sec=read('fiscal_sectors');weighted=read('fiscal_policy_block_weights')
    def pick(sample,out,h):return next(f for f in main if f['sample']==sample and f['model']=='rollover' and f['outcome']==out and f['horizon']==h)
    families={};core=[];curves=[];channels=[];pool=[];sectors=[];benchmark=[]
    for f in main:
        if f.get('status')!='ok':continue
        if f['sample'] in GROUPS and f['outcome'] in ['log_gdp','log_prices']:
            if f['model']=='rollover':
                curves.extend(record(f,k) for k in TERMS)
                if f['horizon'] in HS:core.extend(record(f,k) for k in TERMS)
            elif f['horizon'] in HS:benchmark.append(record(f,'domestic_noncb'))
        if f['model']=='rollover' and f['horizon'] in HS:
            if f['outcome'] in ['debt_ratio_observed','log_reer']:channels.extend(record(f,k) for k in TERMS)
            elif f['sample'] in ['own','pooled']:pool.extend(record(f,k) for k in TERMS)
    for out in ['log_gdp','log_prices']:
        for h in HS:
            for term in TERMS:
                r=difference(pick('advanced',out,h),pick('emerging',out,h),term);core.append(r);curves.append(r)
    for f in acc:
        if f.get('status')=='ok' and f['variant']=='debt accumulation':channels.append(record(f,'debt_accumulation'))
    for f in weighted:pool.extend(record(f,k) for k in TERMS)
    for f in sec:
        if f.get('status')=='ok' and f['model'].endswith('_rollover'):
            terms=TERMS if f['model'].startswith('foreign_official') else ['domestic_bank','domestic_nonbank','domestic_bank_x_refinancing','domestic_nonbank_x_refinancing']
            sectors.extend(record(f,k) for k in terms)
    families=dict(main=core,full_curves=curves,channels=channels,policy_aggregation=pool,creditor_sectors=sectors,ownership_benchmark=benchmark)
    rows=[]
    for name,records in families.items():rows.extend(correct(name,records))
    d=pd.DataFrame(rows);d.to_csv(R/'fiscal_simultaneous.csv',index=False)
    (R/'fiscal_simultaneous.json').write_text(json.dumps(dict(method='Single-step max-|t|, Gaussian Bartlett(12) dependent time multipliers',
        retrospective_families=True,draws=B,seed=SEED,families={k:len(v) for k,v in families.items()},rows=rows),indent=2)+'\n')
    print(d[d.family.eq('main')&d.p_value.lt(.05)][['sample','outcome','horizon','term','estimate','p_value','p_maxT']].to_string(index=False))
    print('Other families, adjusted p < .05:')
    print(d[~d.family.isin(['main','full_curves'])&d.p_maxT.lt(.05)][['family','sample','outcome','horizon','term','estimate','p_value','p_maxT']].to_string(index=False))

if __name__=='__main__':main()
