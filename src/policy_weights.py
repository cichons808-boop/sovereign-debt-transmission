"""Equal policy-issuer weight: the euro-area block totals one row per quarter.

Country-residence stocks retain their national definition. Weighting avoids
constructing a spurious consolidated foreign stock by adding intra-area claims.
"""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from scipy.linalg import qr,lstsq
from scipy.stats import t
from local_projection import fit
from specification import setup
from international_data import shocks
from macro_data import EA_ENTRY

P=Path(__file__).resolve().parents[1];D=P/'data/processed';R=P/'results'

def main():
    ea=pd.read_csv(D/'fiscal_panel_ea.csv.gz',float_precision='round_trip');ea=ea[ea.country.isin(EA_ENTRY)].copy()
    own=pd.read_csv(D/'fiscal_panel_external.csv.gz',float_precision='round_trip')
    own.loc[own.country.eq('US'),['Fed_MP','Fed_CBI']]=0.
    s=shocks();s['period']=s.period.astype(str);ecb=s[s.issuer.eq('DEU')].set_index('period');fed=s[s.issuer.eq('USA')].set_index('period')
    for col in ['MP_median','CBI_median','MP_pm','CBI_pm','pc1_hf']:ea[col]=ea.period.map(ecb[col])
    ea['ECB_MP']=0.;ea['ECB_CBI']=0.;ea['Fed_MP']=ea.period.map(fed.MP_median);ea['Fed_CBI']=ea.period.map(fed.CBI_median)
    ea=ea.drop(columns=['primary_balance_lag','net_interest_lag'],errors='ignore')
    data=pd.concat([ea,own],ignore_index=True).sort_values(['country','time_index']).reset_index(drop=True)
    data['ea_member']=data.ea_member.astype(bool);d,extra,names=setup(data,'rollover',True)
    fits=[];checks=[]
    for out in ['log_gdp','log_prices']:
        for h in [4,8,12]:
            base,v=fit(d,names,'rollover',out,h,additional_nuisance=extra,return_validation=True)
            g=v['g'];in_ea=g.country.isin(EA_ENTRY)
            count=in_ea.groupby(g.time_index).transform('sum');w=np.where(in_ea,1/count.clip(lower=1),1.)
            root=np.sqrt(w);x=v['X0']*root[:,None];F=v['F']*root[:,None];y=v['Y']*root
            Q,_=qr(x,mode='economic',check_finite=False);Z=F-Q@(Q.T@F);yr=y-Q@(Q.T@y)
            bread=np.linalg.inv(Z.T@Z);beta=bread@(Z.T@yr);res=yr-Z@beta
            inf=np.zeros((base['time_end']-base['time_start']+1,len(names)));np.add.at(inf,v['time'],Z*res[:,None]);inf=inf@bread
            cov=inf.T@inf
            for lag in range(1,13):
                a=inf[lag:].T@inf[:-lag];cov+=(1-lag/13)*(a+a.T)
            cov*=base['finite_sample_factor'];crit=t.ppf(.975,base['df']);est=[]
            for j,name in enumerate(names):
                se=np.sqrt(cov[j,j]);est.append(dict(term=name,estimate=float(beta[j]),se=float(se),ci_low=float(beta[j]-crit*se),ci_high=float(beta[j]+crit*se),p_value=float(2*t.sf(abs(beta[j]/se),base['df']))))
            result={k:base[k] for k in ['outcome','horizon','n','p','countries','time_periods','df','country_names','time_start','time_end']}
            result['influence_by_time']=(inf*np.sqrt(base['finite_sample_factor'])).tolist()
            result.update(model='rollover',sample='equal_policy_weight',estimates=est,coefficient_names=names,beta=beta.tolist(),covariance_HAC=cov.tolist(),weight_sum=float(w.sum()),rule='Each own-policy country has weight 1; all eligible euro-area countries together have weight 1 within a quarter')
            fits.append(result)
            if out=='log_gdp' and h==4:
                direct=lstsq(np.column_stack([x,F]),y,lapack_driver='gelsd')[0][-len(names):]
                err=float(np.max(np.abs(direct-beta)));assert err<1e-7
                checks.append(dict(weighted_OLS_error=err,weight_sum=float(w.sum()),country_quarters=base['n']))
    (R/'fiscal_policy_block_weights.json').write_text(json.dumps(fits,indent=2)+'\n')
    rows=[{**{k:f[k] for k in ['outcome','horizon','n','countries','sample','weight_sum']},**e} for f in fits for e in f['estimates']]
    pd.DataFrame(rows).to_csv(R/'fiscal_policy_block_weights.csv',index=False)
    (R/'fiscal_policy_block_weight_validation.json').write_text(json.dumps(checks,indent=2)+'\n')
    print(pd.DataFrame(rows).query('term=="domestic_noncb"')[['outcome','horizon','estimate','se','p_value','weight_sum']].to_string(index=False))

if __name__=='__main__':main()
