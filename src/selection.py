"""Post-double-selection local projections with dependent-score penalties.

All estimators use the original full-model observation set. Six monetary/debt
interactions remain unpenalized; nuisance selection includes the outcome and
every exposure equation. Full-model projections are independently checked by two OLS formulations.
"""
from pathlib import Path
import os,json,hashlib,gc,sys
os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
import numpy as np
import pandas as pd
from scipy.linalg import qr,lstsq
from scipy.stats import norm,t
from lasso import coordinate_descent
from local_projection import fit,nuisance
from specification import setup,EM
from macro_data import EA_ENTRY

P=Path(__file__).resolve().parents[1];D=P/'data/processed';R=P/'results'
FOCAL=['domestic_noncb','domestic_noncb_x_refinancing']
CONFIG=dict(method='post-double-selection with quarterly HAC penalty loadings',
    mandatory='source and calendar-quarter intercepts, country seasons, source-specific own MP/information slopes, current focal-state levels and information interactions, four GDP/inflation lags, macro state levels and available baseline fiscal controls',
    optional='Remaining columns in the original full-model nuisance dictionary',
    target='All six monetary-by-debt and monetary-by-debt-by-refinancing regressors are retained unpenalized',
    penalty_c=1.1,penalty_gamma='0.1/log(max(T,3))',penalty_iterations=3,
    penalty_initial_residual='OLS on the five highest absolute-correlation residualized predictors',
    penalty_loadings='Centered Bartlett(12) covariance of scores aggregated within calendar quarter; mandatory-rank finite-sample scaling',
    lag_bandwidth=12,primary_horizons=[4,8,12],curves=list(range(13)),groups=['ea','advanced','emerging'],
    inference='Quarter-score HAC(12), post-selection design rank; main simultaneous family has 48 contrasts',
    no_outcome_based_country_deletion=True,seed=20261018)

def independent(x):
    if x.shape[1]==0:return x,np.zeros((len(x),0)),0,np.array([],int)
    q,r,piv=qr(x,mode='economic',pivoting=True,check_finite=False)
    tol=max(x.shape)*np.finfo(float).eps*abs(r[0,0])*20
    rank=int((np.abs(np.diag(r))>tol).sum())
    return x[:,piv[:rank]],q[:,:rank],rank,piv[:rank]

def mandatory(label):
    return (label=='intercept' or label.startswith(('est_group_','time_index_','country_season_','MP_group_','CBI_group_','level_','information_','growth_l','inflation_l'))
        or label in ['primary_balance_lag','net_interest_lag','unemployment_lag','macro_reer_state','macro_ca_state','macro_wti_state','macro_spy_state'])

def designs(v,names,extra):
    g=v['g'];x,labels=nuisance(g,names,'Q')
    x=np.column_stack([x,g[extra].to_numpy(float)]);labels+=list(extra)
    force=[j for j,k in enumerate(labels) if mandatory(k)]
    choose=[j for j,k in enumerate(labels) if not mandatory(k)]
    c,q,rank,piv=independent(x[:,force])
    w=x[:,choose];wr=w-q@(q.T@w)
    original_norm=np.linalg.norm(w,axis=0);norms=np.linalg.norm(wr,axis=0)
    keep=norms>1e-9*np.maximum(1,original_norm)
    return c,q,rank,w[:,keep],wr[:,keep],[labels[choose[j]] for j in np.flatnonzero(keep)], [labels[force[j]] for j in piv]

def hac_loadings(z,e,time,rank):
    n=len(e);times=time-time.min();T=int(times.max())+1
    s=np.zeros((T,z.shape[1]));np.add.at(s,times,z*e[:,None])
    s-=s.mean(axis=0,keepdims=True)
    var=(s*s).sum(axis=0)
    for lag in range(1,min(12,T-1)+1):var+=2*(1-lag/13)*(s[lag:]*s[:-lag]).sum(axis=0)
    unique=len(np.unique(time));var*=unique/(unique-1)*(n-1)/max(1,n-rank)
    return np.sqrt(np.maximum(var,1e-16))

def selector(w,y,time,rank):
    n,p=w.shape
    if not p:return np.zeros(0,bool),dict(selected=0,converged=True)
    scale=np.sqrt(np.mean(w*w,axis=0));z=w/scale
    sy=float(np.sqrt(np.mean(y*y)))
    if sy<1e-12:return np.zeros(p,bool),dict(selected=0,converged=True)
    target=y/sy;b=np.zeros(p);ok=True
    first=np.argsort(-np.abs(z.T@target),kind='stable')[:min(5,p)]
    initial=lstsq(z[:,first],target,lapack_driver='gelsd',check_finite=False)[0]
    e=target-z[:,first]@initial
    gamma=.1/np.log(max(len(np.unique(time)),3));q=norm.ppf(1-gamma/(2*p));alpha=CONFIG['penalty_c']*q/n
    for iteration in range(CONFIG['penalty_iterations']):
        loading=hac_loadings(z,e,time,rank)
        loading=np.maximum(loading,1e-6)
        zz=np.asfortranarray(z/loading)
        coefficient, diagnostic=coordinate_descent(zz,target,alpha)
        ok &= diagnostic['converged']
        if not diagnostic['converged']:
            raise ArithmeticError('LASSO coordinate descent did not converge: '+str(diagnostic))
        b=coefficient/loading
        active=np.abs(b)>1e-8
        if active.any():
            bp=lstsq(z[:,active],target,lapack_driver='gelsd',check_finite=False)[0]
            e=target-z[:,active]@bp
        else:e=target.copy()
    return active,dict(selected=int(active.sum()),converged=bool(ok),iterations=iteration+1,penalty_quantile=float(q),alpha=float(alpha))

def select_controls(c,q,w,wr,Y,F,time,rank):
    yr=Y-q@(q.T@Y);fr=F-q@(q.T@F)
    if yr.ndim==1:yr=yr[:,None]
    targets=np.column_stack([yr,fr]);union=np.zeros(w.shape[1],bool);logs=[]
    for j in range(targets.shape[1]):
        chosen,log=selector(wr,targets[:,j],time,rank);union|=chosen
        logs.append(dict(log,target=j,indices=np.flatnonzero(chosen).tolist()))
    return union,logs

def ols(c,F,Y,g,names,selected_labels=None):
    x0,q,rank,_=independent(c);z=F-q@(q.T@F);yr=Y-q@(q.T@Y)
    singular=np.linalg.svd(z,compute_uv=False)
    if singular[-1]<1e-8*singular[0]:raise ValueError('Focal block loses rank')
    bread=np.linalg.inv(z.T@z);beta=bread@(z.T@yr);e=yr-z@beta
    n=len(g);p=rank+len(names);T=int(g.time_index.nunique());df=T-1
    if n<=p+5:raise ValueError(f'Insufficient residual dimension: {n}, {p}')
    ti=g.time_index.to_numpy(int);t0,t1=int(ti.min()),int(ti.max())
    score=np.zeros((t1-t0+1,len(names)));np.add.at(score,ti-t0,z*e[:,None]);influence=score@bread
    cov=influence.T@influence
    for lag in range(1,min(12,len(influence)-1)+1):
        a=influence[lag:].T@influence[:-lag];cov+=(1-lag/13)*(a+a.T)
    factor=T/(T-1)*(n-1)/(n-p);cov*=factor;influence*=np.sqrt(factor)
    crit=t.ppf(.975,df);est=[]
    for j,term in enumerate(names):
        se=float(np.sqrt(cov[j,j]));b=float(beta[j])
        est.append(dict(term=term,estimate=b,se=se,ci_low=float(b-crit*se),ci_high=float(b+crit*se),p_value=float(2*t.sf(abs(b/se),df))))
    return dict(status='ok',n=n,p=p,nuisance_rank=rank,residual_df=n-p,countries=int(g.country.nunique()),country_names=sorted(g.country.unique()),time_periods=T,df=df,
        time_start=t0,time_end=t1,beta=beta.tolist(),coefficient_names=names,covariance_HAC=cov.tolist(),influence_by_time=influence.tolist(),estimates=est,
        residual_ss=float(e@e),focal_condition=float(singular[0]/singular[-1]),selected_labels=selected_labels or [])

def estimate(v,names,extra,method):
    c,q,rank,w,wr,labels,mandatory_labels=designs(v,names,extra)
    if method=='minimal':chosen=np.zeros(w.shape[1],bool);logs=[]
    elif method=='pds':chosen,logs=select_controls(c,q,w,wr,v['Y'],v['F'],v['g'].time_index.to_numpy(int),rank)
    elif method=='full':chosen=np.ones(w.shape[1],bool);logs=[]
    else:raise ValueError(method)
    x=np.column_stack([c,w[:,chosen]])
    f=ols(x,v['F'],v['Y'],v['g'],names,[labels[j] for j in np.flatnonzero(chosen)])
    f.update(estimator=method,mandatory_rank=rank,optional_candidates=w.shape[1],selected_count=int(chosen.sum()),selection_equations=logs,
        all_lasso_converged=all(z['converged'] for z in logs),mandatory_labels=mandatory_labels)
    return f

def shocks():
    x=pd.read_excel(P/'data/raw/bolhuis_hf.xlsx',sheet_name='data');x['period']=pd.PeriodIndex(pd.to_datetime(x.market_Date),freq='Q');frames=[]
    for issuer,g in x.groupby('iso3'):
        start=g.period.min()+1;end=g.period.max() if pd.to_datetime(g.market_Date).max().month%3==0 else g.period.max()-1
        idx=pd.period_range(start,end,freq='Q');z=g.groupby('period')[['orth_MP1','orth_CBI1']].sum().reindex(idx,fill_value=0)/10
        z=z.rename(columns={'orth_MP1':'MP_median','orth_CBI1':'CBI_median'});z['period']=idx.astype(str);z['issuer']=issuer;frames.append(z.reset_index(drop=True))
    return pd.concat(frames,ignore_index=True)

def populations():
    ea=pd.read_csv(D/'fiscal_panel_ea.csv.gz',float_precision='round_trip');own=pd.read_csv(D/'fiscal_panel_external.csv.gz',float_precision='round_trip')
    for z in [ea,own]:z['ea_member']=z.ea_member.astype(bool)
    own.loc[own.country.eq('US'),['Fed_MP','Fed_CBI']]=0.
    s=shocks();ecb=s[s.issuer.eq('DEU')].set_index('period');fed=s[s.issuer.eq('USA')].set_index('period')
    common=ea[ea.country.isin(EA_ENTRY)].copy()
    for col in ['MP_median','CBI_median']:common[col]=common.period.map(ecb[col])
    common['MP_pm']=common.MP_median;common['CBI_pm']=common.CBI_median;common['pc1_hf']=common.MP_median+common.CBI_median
    common['ECB_MP']=0.;common['ECB_CBI']=0.;common['Fed_MP']=common.period.map(fed.MP_median);common['Fed_CBI']=common.period.map(fed.CBI_median)
    common=common.drop(columns=['primary_balance_lag','net_interest_lag'],errors='ignore')
    pool=pd.concat([common,own],ignore_index=True).sort_values(['country','time_index']).reset_index(drop=True)
    data={'ea':ea,'own':own,'pooled':pool,'ea_bolhuis':common}
    for sample,mask in [('advanced',~own.country.isin(EM)),('emerging',own.country.isin(EM))]:
        z=own.copy();z['ea_member']&=mask;data[sample]=z
    return data

def dump(fits,name='ml_lp'):
    (R/(name+'.json')).write_text(json.dumps(fits,indent=2,allow_nan=False)+'\n')
    rows=[{k:f.get(k) for k in ['sample','estimator','model','variant','shock_origin','outcome','horizon','n','p','residual_df','countries','time_periods','mandatory_rank','optional_candidates','selected_count','all_lasso_converged','focal_condition','pair_sha256']}|e for f in fits for e in f['estimates']]
    pd.DataFrame(rows).to_csv(R/(name+'.csv'),index=False)

def main(pilot=False):
    cfg=P/'config/selection.json';payload=json.dumps(CONFIG,indent=2)+'\n'
    if cfg.exists():assert cfg.read_text()==payload,'Specification changed'
    else:cfg.write_text(payload)
    data=populations();fits=[];checks=[]
    samples=['advanced','emerging','ea'] if pilot else ['ea','advanced','emerging','own','pooled','ea_bolhuis']
    for sample in samples:
        base=data[sample];d,ex,names=setup(base,'rollover',sample!='ea')
        cases=[('log_gdp',8)] if pilot else [(o,h) for o in ['log_gdp','log_prices'] for h in (range(13) if sample in ['ea','advanced','emerging'] else [4,8,12])]+[(o,h) for o in ['debt_ratio_observed','log_reer'] for h in [4,8,12]]
        for outcome,h in cases:
            f,v=fit(d,names,'rollover',outcome,h,additional_nuisance=ex,return_validation=True)
            keyhash=hashlib.sha256(v['g'][['country','period']].to_csv(index=False).encode()).hexdigest()
            for method in ['minimal','full','pds']:
                ff=estimate(v,names,ex,method)
                ff.update(sample=sample,outcome=outcome,horizon=h,model='rollover',pair_sha256=keyhash)
                if method=='full':
                    err=float(np.max(np.abs(np.array(ff['beta'])-f['beta'])));assert err<1e-7
                    cerr=float(np.max(np.abs(np.array(ff['covariance_HAC'])-f['covariance_HAC'])));assert cerr<1e-6
                    checks.append(dict(sample=sample,outcome=outcome,horizon=h,coefficient_error=err,covariance_error=cerr))
                fits.append(ff)
                if pilot:
                    row=next(z for z in ff['estimates'] if z['term']=='domestic_noncb')
                    print(sample,method,'N',ff['n'],'rank',ff['p'],'selected',ff['selected_count'],row,'converged',ff['all_lasso_converged'],flush=True)
            del v,f;gc.collect()
            if h in [4,8,12]:print('LP',sample,outcome,h,'complete',flush=True)
            dump(fits,'ml_lp_pilot' if pilot else 'ml_lp')
        if not pilot:print('SAMPLE COMPLETE',sample,flush=True)
    (R/('ml_lp_pilot_validation.json' if pilot else 'ml_lp_validation.json')).write_text(json.dumps(dict(specification_sha256=hashlib.sha256(payload.encode()).hexdigest(),same_observations=True,independent_full_design_checks=checks),indent=2)+'\n')

if __name__=='__main__':main('--pilot' in sys.argv)
