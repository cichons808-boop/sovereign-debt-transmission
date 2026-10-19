"""Direct shock x debt x refinancing local projections with robust inference.

The dependent observations are macroeconomic outcomes at country-period level,
not published IRFs. Nuisance fixed effects are projected out before testing
identification of focal shock interactions. Cross-country correlated errors
and serially overlapping LP residuals enter time-aggregated score HAC.
"""
from pathlib import Path
import json,hashlib
import numpy as np
import pandas as pd
from scipy.linalg import qr
from scipy.stats import t

P=Path(__file__).resolve().parents[1]; DATA=P/'data/processed'; RES=P/'results';RES.mkdir(exist_ok=True)


def load_panel(frequency='Q'):
    name='quarterly' if frequency=='Q' else 'monthly'
    d=pd.read_csv(DATA/f'panel_{name}.csv.gz',float_precision='round_trip')
    d=d.sort_values(['country','time_index']).copy()
    d['ea_member']=d.ea_member.astype(bool)
    outcomes=['log_gdp','log_prices','log_consumption','log_investment','interest'] if frequency=='Q' else ['log_ip','log_prices']
    growth='log_gdp' if frequency=='Q' else 'log_ip'
    g=d.groupby('country',sort=False)
    dy=g[growth].diff();dp=g.log_prices.diff()
    lag_count=4 if frequency=='Q' else 12
    for lag in range(1,lag_count+1):
        d[f'growth_l{lag}']=dy.groupby(d.country).shift(lag)
        d[f'inflation_l{lag}']=dp.groupby(d.country).shift(lag)
    for c in ['primary_balance','net_interest','unemployment']:
        if c in d:d[c+'_lag']=g[c].shift(1)
    d['growth_state']=g[growth].shift(1)-g[growth].shift(1+lag_count)
    d['inflation_state']=g.log_prices.shift(1)-g.log_prices.shift(1+lag_count)
    # Centering is fixed using observed predictor support before any LP fit.
    pred=d[d.ea_member & d.MP_median.notna() & d.domestic_noncb.notna() & d.cb.notna()]
    r0=float(pred.refinance_share.median())
    d['rollover_centered']=(d.refinance_share-r0)/.1
    d['hold_group']=d.country+'_'+d.source.fillna('missing')
    d['roll_group']=d.source_group
    return d,r0,outcomes

def focal_states(d,model):
    if model in ['ownership','ownership_matched','rollover']:
        names=['total','domestic_noncb','central_bank']
        a=np.column_stack([d.debt,d.domestic_noncb,d.cb])/10.
        if model=='rollover':
            names+=['total_x_refinancing','domestic_noncb_x_refinancing','central_bank_x_refinancing']
            a=np.column_stack([a,a*d.rollover_centered.values[:,None]])
    elif model=='joint_original':
        names=['short_total','long_total','short_nonfinancial','long_nonfinancial','short_financial','long_financial']
        a=d[names].to_numpy(float)/10.
    else:raise ValueError(model)
    return a,names

def prepared(d,model,frequency='Q',shock='median'):
    d=d.copy();A,names=focal_states(d,model)
    mp='MP_median' if shock=='median' else 'MP_pm';info='CBI_median' if shock=='median' else 'CBI_pm'
    d['mp']=d[mp];d['info']=d[info]
    for j,name in enumerate(names):
        d['a_'+name]=A[:,j]
        d['f_'+name]=d.mp*A[:,j]
        d['i_'+name]=d['info']*A[:,j]
        for lag in [1,2]:
            d[f'f_{name}_lag{lag}']=d.groupby('country')['f_'+name].shift(lag)
            d[f'i_{name}_lag{lag}']=d.groupby('country')['i_'+name].shift(lag)
    d['est_group']=d.roll_group if model in ['rollover','ownership_matched'] else d.hold_group
    return d,names

def nuisance(g,names,frequency,with_country_shock=True):
    cols=[];labels=[]
    def add(a,name):cols.append(np.asarray(a,float));labels.append(name)
    add(np.ones(len(g)),'intercept')
    for kind in ['est_group','time_index']:
        for level in sorted(g[kind].unique())[1:]:add((g[kind]==level).astype(float),kind+'_'+str(level))
    season=g.country+'_'+g.season.astype(str)
    for level in sorted(season.unique())[1:]:add((season==level).astype(float),'country_season_'+str(level))
    if with_country_shock:
        for level in sorted(g.est_group.unique()):
            mask=(g.est_group==level).astype(float)
            add(mask*g.mp,'MP_group_'+level);add(mask*g['info'],'CBI_group_'+level)
    else:
        add(g.mp,'MP_level');add(g['info'],'CBI_level')
    for name in names:
        add(g['a_'+name],'level_'+name);add(g['i_'+name],'information_'+name)
        for lag in [1,2]:
            add(g[f'f_{name}_lag{lag}'],f'MP_{name}_lag{lag}')
            add(g[f'i_{name}_lag{lag}'],f'CBI_{name}_lag{lag}')
    lag_count=4 if frequency=='Q' else 12
    for lag in range(1,lag_count+1):
        for var in ['growth','inflation']:add(g[f'{var}_l{lag}'],f'{var}_l{lag}')
    for c in ['primary_balance_lag','net_interest_lag','unemployment_lag']:
        if c in g:add(g[c],c)
    for c in ['growth_state','inflation_state']:
        add(g[c],c);add(g[c]*g.mp,'MP_'+c);add(g[c]*g['info'],'CBI_'+c)
    return np.column_stack(cols),labels

def contrast_vectors(names,model):
    out={};k=len(names)
    for j,name in enumerate(names):
        c=np.zeros(k);c[j]=1.;out[name]=c
    if model=='joint_original':
        c=np.zeros(k);c[names.index('short_nonfinancial')]=1.;c[names.index('long_nonfinancial')]=-1.
        out['nonfinancial_ownership_x_original_maturity']=c
    return out

def fit(d,names,model,outcome,horizon,frequency='Q',with_country_shock=True,
        holdings_source=None,maturity_source=None,omit_country=None,exclude_covid=False,
        return_validation=False,additional_nuisance=None):
    g=d.copy()
    spacing=g.groupby('country').time_index.diff().dropna()
    if not spacing.eq(1).all():
        raise ValueError('LP inputs must preserve a complete sorted country calendar; restrict shock eligibility rather than deleting dates')
    future=g.groupby('country')[outcome].shift(-horizon)
    before=g.groupby('country')[outcome].shift(1)
    g['response']=future-before
    g=g[g.ea_member & g.mp.notna()].copy()
    if model=='ownership_matched':g=g[g.refinance_share.notna()]
    if holdings_source:g=g[g.source==holdings_source]
    if maturity_source:g=g[g.maturity_source==maturity_source]
    if omit_country:g=g[g.country!=omit_country]
    if exclude_covid:
        periods=pd.PeriodIndex(g.period,freq=frequency)
        first=pd.Period('2020Q1' if frequency=='Q' else '2020-01',freq=frequency)
        last=pd.Period('2021Q4' if frequency=='Q' else '2021-12',freq=frequency)
        # Exclude every outcome window touching COVID, not only shock dates.
        g=g[~((periods-1<=last)&(periods+horizon>=first))].copy()
    xcols=['f_'+n for n in names]
    req=['response','mp','info','growth_state','inflation_state']+xcols
    for n in names:
        req+=['a_'+n,'i_'+n]+[f'{pre}_{n}_lag{lag}' for pre in ['f','i'] for lag in [1,2]]
    for lag in range(1,5 if frequency=='Q' else 13):req += [f'growth_l{lag}',f'inflation_l{lag}']
    req += [c for c in ['primary_balance_lag','net_interest_lag','unemployment_lag'] if c in g]
    req += additional_nuisance or []
    g=g.dropna(subset=req).copy()
    # Require several independent calendar cycles within each source regime.
    min_country,min_source=(12,8) if frequency=='Q' else (36,24)
    for _ in range(3):
        n0=len(g)
        g=g[g.groupby('country').country.transform('size')>=min_country]
        g=g[g.groupby('est_group').est_group.transform('size')>=min_source]
        if n0==len(g):break
    if len(g)<50 or g.country.nunique()<3:
        return dict(status='not_estimable',reason='Insufficient supported country-periods',n=len(g),countries=int(g.country.nunique()))
    F=g[xcols].to_numpy(float);Y=g.response.to_numpy(float)
    X0,labels=nuisance(g,names,frequency,with_country_shock)
    if additional_nuisance:
        X0=np.column_stack([X0,g[additional_nuisance].to_numpy(float)])
        labels+=list(additional_nuisance)
    Q,R,piv=qr(X0,mode='economic',pivoting=True,check_finite=False)
    tol=max(X0.shape)*np.finfo(float).eps*abs(R[0,0])*20
    rank=int((np.abs(np.diag(R))>tol).sum())
    Q=Q[:,:rank]
    Z=F-Q@(Q.T@F);yr=Y-Q@(Q.T@Y)
    singular=np.linalg.svd(Z,compute_uv=False)
    if singular[-1]<1e-8*singular[0]:
        return dict(status='not_estimable',reason='Focal interaction not identified after complete nuisance projection',n=len(g),countries=int(g.country.nunique()),singular_values=singular.tolist())
    bread=np.linalg.inv(Z.T@Z);beta=bread@(Z.T@yr);e=yr-Z@beta
    n=len(g);p=rank+len(names)
    if n<=p+5:return dict(status='not_estimable',reason='Insufficient residual degrees of freedom',n=n,p=p)
    # Preserve gaps in calendar time when forming lagged cross-score products.
    ti=g.time_index.to_numpy(int);t0,t1=int(ti.min()),int(ti.max())
    S=np.zeros((t1-t0+1,len(names)));np.add.at(S,ti-t0,Z*e[:,None])
    influence=S@bread
    bandwidth=12 if frequency=='Q' else 36
    cov=influence.T@influence
    for lag in range(1,min(bandwidth,len(influence)-1)+1):
        v=influence[lag:].T@influence[:-lag]
        cov+=(1-lag/(bandwidth+1))*(v+v.T)
    T=int(g.time_index.nunique());factor=T/(T-1)*(n-1)/(n-p)
    cov*=factor;influence*=np.sqrt(factor)
    dof=T-1;crit=t.ppf(.975,dof)
    estimates=[]
    for term,c in contrast_vectors(names,model).items():
        b=float(c@beta);v=float(c@cov@c)
        if v<=0:raise ValueError('Nonpositive contrast variance: '+term)
        se=np.sqrt(v)
        estimates.append(dict(term=term,estimate=b,se=float(se),ci_low=float(b-crit*se),ci_high=float(b+crit*se),p_value=float(2*t.sf(abs(b/se),dof))))
    # Additional country-cluster inference, separate from serial/cross-country HAC.
    codes,levels=pd.factorize(g.country);C=np.zeros((len(levels),len(names)));np.add.at(C,codes,Z*e[:,None])
    vc=bread@(C.T@C)@bread*len(levels)/(len(levels)-1)*(n-1)/(n-p)
    model_result=dict(status='ok',outcome=outcome,horizon=int(horizon),frequency=frequency,model=model,
        n=n,p=p,nuisance_rank=rank,countries=int(g.country.nunique()),country_names=sorted(g.country.unique()),
        time_periods=T,time_start=int(t0),time_end=int(t1),first_period=g.period.min(),last_period=g.period.max(),
        HAC_bandwidth=bandwidth,df=dof,finite_sample_factor=float(factor),coefficient_names=names,beta=beta.tolist(),
        covariance_HAC=cov.tolist(),covariance_country_cluster=vc.tolist(),estimates=estimates,
        influence_by_time=influence.tolist(),high_debt_observations=int((g.debt>100).sum()),max_debt=float(g.debt.max()),
        sources=g.groupby(['source','maturity_source']).size().rename('n').reset_index().to_dict('records'),
        max_focal_condition=float(singular[0]/singular[-1]),with_country_shock_slopes=with_country_shock,
        holdings_source_filter=holdings_source,maturity_source_filter=maturity_source,omitted_country=omit_country,
        exclude_windows_touching_covid=exclude_covid,
        additional_nuisance=additional_nuisance or [],
        dropped_dependent_nuisance=[labels[j] for j in piv[rank:]],residual_ss=float(e@e))
    if return_validation:
        return model_result,dict(X0=X0[:,piv[:rank]],F=F,Y=Y,Z=Z,e=e,time=ti-t0,g=g)
    return model_result


