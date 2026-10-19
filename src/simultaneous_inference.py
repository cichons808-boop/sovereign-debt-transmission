"""Calendar-aligned simultaneous inference, computed in memory-bounded batches."""
import json
import numpy as np
import pandas as pd
from selection import R
from reporting_families import record,difference
SEED=20261018;B=99999;GROUPS=['ea','advanced','emerging'];TERMS=['domestic_noncb','domestic_noncb_x_refinancing'];HS=[4,8,12]

def correct(name,records):
    lo=min(r['start'] for r in records);hi=max(r['end'] for r in records)
    psi=np.zeros((hi-lo+1,len(records)))
    for j,r in enumerate(records):psi[r['start']-lo:r['end']-lo+1,j]=r['psi']
    se=np.array([r['se'] for r in records]);cov=psi.T@psi
    for lag in range(1,min(12,len(psi)-1)+1):
        c=psi[lag:].T@psi[:-lag];cov+=(1-lag/13)*(c+c.T)
    assert np.max(np.abs(np.diag(cov)-se**2))<1e-7
    rng=np.random.default_rng(SEED);maximum=[];remaining=B
    while remaining:
        m=min(2000,remaining);z=rng.standard_normal((m,len(psi)+12));c=np.column_stack([np.zeros(m),np.cumsum(z,axis=1)])
        xi=(c[:,13:]-c[:,:-13])/np.sqrt(13);maximum.append(np.max(np.abs(xi@psi/se),axis=1));remaining-=m
    maximum=np.concatenate(maximum);critical=float(np.quantile(maximum,.95,method='higher'));rows=[]
    for r in records:
        pm=(1+np.count_nonzero(maximum>=abs(r['estimate']/r['se'])))/(B+1)
        rows.append({k:v for k,v in r.items() if k not in ['psi','start','end']}|dict(family=name,family_size=len(records),p_maxT=max(float(r['p_value']),float(pm)),simultaneous_low=r['estimate']-critical*r['se'],simultaneous_high=r['estimate']+critical*r['se'],critical_95=critical,draws=B,seed=SEED))
    return rows

def main():
    fits=[f for f in json.loads((R/'ml_lp.json').read_text()) if f['estimator']=='pds'];acc=[f for f in json.loads((R/'ml_accumulation.json').read_text()) if f['estimator']=='pds']
    def pick(s,o,h):return next(f for f in fits if f['sample']==s and f['outcome']==o and f['horizon']==h)
    core=[];curves=[];channels=[];spill=[]
    for f in fits:
        if f['sample'] in GROUPS and f['outcome'] in ['log_gdp','log_prices']:
            curves.extend(record(f,k) for k in TERMS)
            if f['horizon'] in HS:core.extend(record(f,k) for k in TERMS)
        if f['sample']!='ea_bolhuis' and f['outcome'] in ['log_reer','debt_ratio_observed']:
            channels.extend(record(f,k) for k in TERMS)
    for out in ['log_gdp','log_prices']:
        for h in HS:
            for term in TERMS:
                r=difference(pick('advanced',out,h),pick('emerging',out,h),term);core.append(r);curves.append(r)
    channels.extend(record(f,'debt_accumulation') for f in acc)
    assert len(core)==48 and len(curves)==168 and len(channels)==90
    forced=json.loads((R/'ml_forced_spillover_sensitivity.json').read_text())
    for f in forced:spill.extend(record(f,k) for k in TERMS)
    families=dict(main=core,full_curves=curves,channels=channels,forced_spillovers=spill);rows=[]
    for name,rr in families.items():
        rows.extend(correct(name,rr));print('inference',name,len(rr),flush=True)
    pd.DataFrame(rows).to_csv(R/'ml_simultaneous.csv',index=False)
    (R/'ml_simultaneous.json').write_text(json.dumps(dict(method='Post-double-selection; max-|t| with Bartlett(12) Gaussian calendar-quarter multipliers',conditional_on_selected_support=True,draws=B,seed=SEED,families={k:len(v) for k,v in families.items()},rows=rows),indent=2)+'\n')
    d=pd.DataFrame(rows);print(d[d.p_maxT.lt(.10)][['family','sample','outcome','horizon','term','estimate','p_value','p_maxT']].to_string(index=False))
if __name__=='__main__':main()
