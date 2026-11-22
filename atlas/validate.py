"""Numerical validation on actual atlas observations, not simulated outputs."""
import json

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import linalg

from .data import AUDIT,PROCESSED
from .estimation import fit,fit_record,response_frame
from .moderators import annual_characteristic,attach


def run():
    tests=[]
    d=pd.read_csv(PROCESSED/'H_BDY_daily.csv.gz',low_memory=False)
    local=d[d.country.eq('POL')].copy()
    frame=response_frame(local,'gdp',4).dropna(subset=['response','shock','lag_d'])
    record=fit_record(d,'gdp',4,scope='country',country='POL')
    assert record['status']=='ok'
    assert np.all(np.diff(frame.time)==1),'Choose a contiguous actual sample for the statsmodels row-HAC comparison'
    dummy=pd.get_dummies(frame.season,drop_first=True,dtype=float).to_numpy()
    design=np.column_stack([np.ones(len(frame)),frame[['shock','lag_d']].to_numpy(),dummy])
    gold=sm.OLS(frame.response.to_numpy(),design).fit(cov_type='HAC',
        cov_kwds=dict(maxlags=record['bandwidth'],use_correction=True),use_t=True)
    coef_error=float(np.max(np.abs(np.array(record['beta'])-gold.params[1:3])))
    cov_error=float(np.max(np.abs(np.array(record['covariance'])-gold.cov_params()[1:3,1:3])))
    assert coef_error<1e-8 and cov_error<1e-8,(coef_error,cov_error)
    tests.append(dict(test='country_OLS_and_HAC_vs_statsmodels_on_actual_POL',n=len(frame),
        max_coefficient_error=coef_error,max_covariance_error=cov_error,status='passed'))
    z=annual_characteristic('F01');panel=attach(d,z,'F01')
    sample=panel[panel.country.isin(['DEU','FRA','POL','USA','JPN'])].copy()
    sample=response_frame(sample,'gdp',4)
    sample['interaction']=sample.shock*sample.z
    sample=sample.dropna(subset=['response','shock','interaction','z','lag_d'])
    sample.attrs['horizon']=4
    result=fit(sample,panel=True,moderator=True,min_n=100,frequency='Q')
    assert result['status']=='ok',result
    ec=sample[['shock','interaction','z','lag_d']].to_numpy()
    countryseason=pd.get_dummies(sample.country+'_'+sample.season.astype(str),dtype=float).to_numpy()
    date=pd.get_dummies(sample.time,dtype=float).to_numpy()
    nuisance=np.column_stack([countryseason,date])
    _,r,piv=linalg.qr(nuisance,mode='economic',pivoting=True)
    rank=int((np.abs(np.diag(r))>1e-9).sum())
    design=np.column_stack([nuisance[:,piv[:rank]],ec])
    beta=np.linalg.lstsq(design,sample.response.to_numpy(),rcond=None)[0]
    residual=sample.response.to_numpy()-design@beta
    bread=np.linalg.inv(design.T@design)
    times=sample.time.to_numpy(int);calendar=np.arange(times.min(),times.max()+1)
    # Independent dense calendar-score calculation, including the FE columns.
    fullscores=np.zeros((len(calendar),design.shape[1]))
    for k,t in enumerate(calendar):fullscores[k]=(design[times==t]*residual[times==t,None]).sum(axis=0)
    meat=fullscores.T@fullscores
    bandwidth=result['bandwidth']
    for lag in range(1,min(bandwidth,len(calendar)-1)+1):
        cross=fullscores[lag:].T@fullscores[:-lag]
        meat+=(1-lag/(bandwidth+1))*(cross+cross.T)
    covariance=bread@meat@bread*len(sample)/(len(sample)-design.shape[1])
    coefficient_error=float(np.max(np.abs(np.array(result['beta'])-beta[-4:])))
    covariance_error=float(np.max(np.abs(np.array(result['covariance'])-covariance[-4:,-4:])))
    assert coefficient_error<1e-6 and covariance_error<1e-6,(coefficient_error,covariance_error)
    assert rank==result['fe_rank'],(rank,result['fe_rank'])
    tests.append(dict(test='absorbed_panel_vs_full_dummy_design_and_dense_calendar_HAC',n=len(sample),
        fe_rank=rank,max_coefficient_error=coefficient_error,max_covariance_error=covariance_error,status='passed'))
    jk=json.loads((AUDIT/'ecb_reconstruction_validation.json').read_text())
    us=json.loads((AUDIT/'usa_reconstruction_validation.json').read_text())
    assert jk['legacy_monthly_max_absolute_error']<1e-6
    assert us['official_factor_max_abs_error']<1e-8
    tests.append(dict(test='source_methodology_replication_US_and_ECB',status='passed',
        ECB_max_error=jk['legacy_monthly_max_absolute_error'],USA_max_error=us['official_factor_max_abs_error']))
    complete=pd.read_csv(PROCESSED/'global_native_quarterly_macro.csv.gz',low_memory=False)
    assert complete.loc[complete.log_cpi.notna(),'observed_months'].eq(3).all()
    assert not complete.duplicated(['country','period']).any()
    for _,g in complete.groupby('country'):assert g.time.diff().dropna().eq(1).all()
    tests.append(dict(test='native_quarterly_calendar_and_three_observed_CPI_months',status='passed'))
    for path in (PROCESSED).glob('H_*csv.gz'):
        x=pd.read_csv(path,low_memory=False)
        for outcome in ['gdp','cpi']:
            r=response_frame(x,outcome,4)
            reference=x[['country','time','log_'+outcome]].rename(columns={'log_'+outcome:'lead_value'})
            reference['time']=reference.time-4
            aligned=x[['country','time','before_'+outcome]].merge(reference,on=['country','time'],how='left')
            a=r.response.to_numpy();b=(aligned.lead_value-aligned['before_'+outcome]).to_numpy()
            mask=np.isfinite(a)
            assert np.max(np.abs(a[mask]-b[mask]),initial=0)<1e-9
    tests.append(dict(test='calendar_leads_vs_exact_time_key_join_on_all_H_panels',status='passed'))
    payload=dict(status='passed',actual_observations_only=True,tests=tests)
    (AUDIT/'numerical_validation.json').write_text(json.dumps(payload,indent=2))
    print(json.dumps(payload,indent=2),flush=True)
    return payload


if __name__=='__main__':run()
