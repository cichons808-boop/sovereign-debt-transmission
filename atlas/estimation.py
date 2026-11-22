"""Small Local Projections with explicit rank checks and calendar-score HAC.

Economic regressors: shock, shock*Z, Z, lagged outcome growth (four maximum).
Country and calendar fixed effects are absorbed by alternating projections.
This is deliberately separate from the legacy multivariate/PDS estimators.
"""
from __future__ import annotations

import hashlib
import json
import gzip
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import linalg, stats

from .data import BASE, save_csv
from .data import EA_ENTRY

RESULTS = BASE / 'results'
RESULTS.mkdir(exist_ok=True)


def calendar_hac(scores: np.ndarray, time: np.ndarray, bandwidth: int):
    """Unnormalised Newey-West meat, with exact calendar gaps retained.

    For panels sum scores across all countries at each date first. Thus any
    contemporaneous cross-country dependence and LP-window overlap enter meat.
    This is the time-score/Driscoll-Kraay large-T approach, not country i.i.d.
    """
    calendar=np.arange(int(time.min()),int(time.max())+1)
    total=np.zeros((len(calendar),scores.shape[1]))
    np.add.at(total,time.astype(int)-calendar[0],scores)
    meat=total.T@total
    for lag in range(1,min(bandwidth,len(calendar)-1)+1):
        cross=total[lag:].T@total[:-lag]
        meat+=(1-lag/(bandwidth+1))*(cross+cross.T)
    return meat,total,calendar


def absorb(values, effects, tol=1e-11, maxiter=3000):
    residual=np.array(values,float,copy=True)
    for iteration in range(maxiter):
        previous=residual.copy()
        for codes in effects:
            sums=np.zeros((codes.max()+1,residual.shape[1]))
            np.add.at(sums,codes,residual)
            counts=np.bincount(codes)
            residual-= (sums/np.maximum(counts[:,None],1))[codes]
        if np.max(np.abs(residual-previous))<tol:
            return residual,iteration+1
    raise ValueError('Fixed-effect absorption did not converge')


def response_frame(panel,outcome,horizon):
    frame=panel.copy()
    frame['response']=frame.groupby('country')['log_'+outcome].shift(-horizon)-frame['before_'+outcome]
    frame['lag_d']=frame['lag_d_'+outcome]
    # Require all observed outcome dates through the horizon. This guards
    # against discontinuous chains or unnoticed gaps in the window.
    good=np.isfinite(frame['before_'+outcome])
    for j in range(horizon+1):
        good &= frame.groupby('country')['log_'+outcome].shift(-j).notna()
    frame.loc[~good,'response']=np.nan
    return frame


def fit(frame, *, panel, moderator=False, min_n=20, frequency='A', influence=False):
    columns=['shock','interaction','z','lag_d'] if moderator else ['shock','lag_d']
    required=['response','time','country']+columns
    d=frame.dropna(subset=required).copy()
    base=dict(status='not_estimable',n=len(d),economic_regressors=len(columns))
    if len(d)<min_n:
        return {**base,'reason':'insufficient_observations','minimum_n':min_n}
    if d.shock.std()<1e-8 or d.shock.ne(0).sum()<8:
        return {**base,'reason':'insufficient_shock_variation'}
    if moderator and (d.z.std()<1e-7 or d.z.nunique()<8):
        return {**base,'reason':'insufficient_moderator_variation'}
    if panel:
        # Do not retain one-date country blocks in a fixed-effect model.
        d=d[d.groupby('country').country.transform('size')>=8].copy()
        if len(d)<min_n or d.country.nunique()<3:
            return {**base,'n':len(d),'reason':'insufficient_supported_panel'}
        if not moderator and d.groupby('time').shock.nunique().max()==1:
            return {**base,'n':len(d),'reason':'focal_term_absorbed',
                    'absorbed_terms':['shock'],'n_countries':d.country.nunique(),
                    'n_issuers':d.issuer.nunique() if 'issuer'in d else None}
    economic=d[columns].to_numpy(float)
    y=d.response.to_numpy(float)
    nuisance=[]; labels=[]
    def effect(keys,label):
        codes=pd.factorize(keys,sort=True)[0]
        nuisance.append(codes);labels.append(label)
    if panel:
        effect(d.country+'_'+d.season.astype(str) if frequency=='Q' else d.country,
               'country_season' if frequency=='Q' else 'country')
        effect(d.time,'calendar')
    else:
        effect(d.season if frequency=='Q' else pd.Series('intercept',index=d.index),
               'season' if frequency=='Q' else 'intercept')
    transformed,niterations=absorb(np.column_stack([y,economic]),nuisance)
    yr=transformed[:,0];X=transformed[:,1:]
    # Identify economic terms sequentially, keeping the interaction focal and
    # reporting any shock main effect absorbed by calendar fixed effects.
    original_norm=np.linalg.norm(economic,axis=0)
    residual_norm=np.linalg.norm(X,axis=0)
    keep=residual_norm>np.maximum(1e-9,original_norm*1e-10)
    absorbed=[columns[j] for j in np.flatnonzero(~keep)]
    if ('interaction' if moderator else 'shock') in absorbed:
        return {**base,'reason':'focal_term_absorbed','absorbed_terms':absorbed}
    columns=[c for c,k in zip(columns,keep) if k]
    X=X[:,keep]
    # Standardize the numerical design only; returned coefficients retain units.
    scale=np.sqrt(np.sum(X**2,axis=0))
    scaled=X/scale
    singular=np.linalg.svd(scaled,compute_uv=False)
    rank=int(np.sum(singular>singular[0]*1e-10))
    condition=float(singular[0]/singular[-1])
    if rank<X.shape[1]:
        return {**base,'reason':'economic_design_rank_deficient','rank':rank,'condition':condition,
                'absorbed_terms':absorbed}
    # Exact rank of nuisance dummies; only needed for the small-sample factor.
    # There are at most several hundred FE columns in the intended atlas.
    if len(nuisance)==1:
        fe_rank=int(nuisance[0].max()+1)
    else:
        # Rank of the two-way dummy design = vertices - connected components
        # of its bipartite incidence graph, including unbalanced panels.
        a,b=nuisance;n_a=int(a.max()+1);n_b=int(b.max()+1)
        parent=np.arange(n_a+n_b)
        def root(i):
            while parent[i]!=i:
                parent[i]=parent[parent[i]];i=parent[i]
            return i
        for left,right in zip(a,b+n_a):
            u,v=root(left),root(right)
            if u!=v:parent[v]=u
        components=len({root(i) for i in range(len(parent))})
        fe_rank=n_a+n_b-components
    p=fe_rank+X.shape[1];n=len(d)
    if n-p<8:
        return {**base,'reason':'insufficient_residual_df','p':p}
    bread=np.linalg.inv(X.T@X)
    beta=np.linalg.lstsq(scaled,yr,rcond=1e-10)[0]/scale
    e=yr-X@beta
    # Scale-aware horizon bandwidth: h+1 at a minimum, annual floor 2 /
    # quarterly floor 4, no multiplication across artificially consecutive rows.
    horizon=int(d.attrs.get('horizon',frame.attrs.get('horizon',0)))
    bandwidth=max(horizon+1,2 if frequency=='A' else 4)
    time=d.time.to_numpy(int)
    scores=X*e[:,None]
    meat,total,calendar=calendar_hac(scores,time,bandwidth)
    T=d.time.nunique()
    factor=n/(n-p)
    covariance=bread@meat@bread*factor
    covariance=(covariance+covariance.T)/2
    if np.min(np.linalg.eigvalsh(covariance))<-1e-8 or (np.diag(covariance)<=0).any():
        return {**base,'reason':'nonpositive_HAC_variance'}
    # T-1 df is a transparent finite-sample approximation, not an exact pivot.
    dof=min(n-p,T-1)
    se=np.sqrt(np.diag(covariance))
    critical=stats.t.ppf(.975,dof)
    estimates=[]
    for j,name in enumerate(columns):
        estimates.append(dict(term=name,estimate=float(beta[j]),se=float(se[j]),
            p_raw=float(2*stats.t.sf(abs(beta[j]/se[j]),dof)),
            ci95_low=float(beta[j]-critical*se[j]),ci95_high=float(beta[j]+critical*se[j])))
    if panel and moderator and 'interaction'in columns:
        # Restricted block-wild score diagnostic. A calendar multiplier is
        # shared by all countries/issuers; this never resamples union countries
        # as though their common monetary innovation were independent.
        j=columns.index('interaction');others=[k for k in range(len(columns)) if k!=j]
        restricted=yr-X[:,others]@np.linalg.lstsq(X[:,others],yr,rcond=None)[0]
        _,null_scores,null_calendar=calendar_hac(X*restricted[:,None],time,bandwidth)
        effect=null_scores@bread[:,j]
        block_length=bandwidth+1
        rng=np.random.default_rng(20261122+horizon)
        draws=399;boot=[]
        for _ in range(draws):
            offset=int(rng.integers(block_length))
            blocks=(np.arange(len(effect))+offset)//block_length
            weights=rng.choice([-1.0,1.0],size=int(blocks.max()+1))[blocks]
            boot.append(float(weights@effect))
        estimates[j]['p_block_wild_informational']=float((1+np.sum(np.abs(boot)>=abs(beta[j])))/(draws+1))
        estimates[j]['block_wild_draws']=draws
        estimates[j]['block_length']=block_length
        estimates[j]['effective_calendar_blocks']=len(effect)/block_length
        estimates[j]['few_time_blocks_warning']=bool(len(effect)/block_length<10)
    leverages=np.sum((X@bread)*X,axis=1)
    keys=d[['country','time']].to_csv(index=False).encode()
    consecutive=(np.diff(time)==1) if not panel else np.zeros(len(time)-1,dtype=bool)
    residual_lag_corr=np.corrcoef(e[1:][consecutive],e[:-1][consecutive])[0,1] if consecutive.sum()>3 else np.nan
    row=dict(status='ok',n=n,p=p,residual_df=n-p,fe_rank=fe_rank,
        n_countries=d.country.nunique(),n_issuers=d.issuer.nunique() if 'issuer'in d else None,
        issuer_list=sorted(d.issuer.dropna().unique()) if 'issuer'in d else [],
        n_dates=int(T),first_period=str(d.period.min()),last_period=str(d.period.max()),
        sample_key_sha256=hashlib.sha256(keys).hexdigest(),sample_keys=d[['country','time']].values.tolist(),
        economic_regressors=len(columns),absorbed_terms=absorbed,columns=columns,beta=beta.tolist(),
        covariance=covariance.tolist(),estimates=estimates,inference='calendar_score_Bartlett_HAC',
        bandwidth=bandwidth,inference_df=int(dof),finite_sample_factor=float(factor),
        condition_number_standardized=condition,rank=rank,
        max_economic_leverage=float(leverages.max()),shock_sd=float(d.shock.std()),
        shock_nonzero=int(d.shock.ne(0).sum()),absorption_iterations=niterations,
        rss=float(e@e),residual_lag1_corr=float(residual_lag_corr),
        shared_shock_warning=bool('shared_union_shock'in d and d.shared_union_shock.fillna(False).any()),
        few_issuers_warning=bool('issuer'in d and d.issuer.nunique()<10))
    if influence:
        row.update(time_grid=calendar.tolist(),influence=(total@bread*np.sqrt(factor)).tolist())
    return row


def fit_record(panel_data,outcome,horizon,*,scope,country=None,variant='all',moderator=False,
               use_influence=False):
    # Selecting one COMPLETE country calendar before shifting is exactly
    # equivalent to the grouped shifts on the full world panel, and avoids
    # copying every other country's observations thousands of times.
    source_data=panel_data if country is None else panel_data[panel_data.country.eq(country)]
    frame=response_frame(source_data,outcome,horizon)
    # Apply eligibility filters AFTER constructing the calendar response.
    if country is not None:frame=frame[frame.country.eq(country)].copy()
    if scope=='AE':frame=frame[frame.development.eq('AE')].copy()
    elif scope=='EMDE':frame=frame[frame.development.eq('EMDE')].copy()
    elif scope=='independent':frame=frame[~frame.issuer.isin(['ECB','DEU_PRE_EURO','FRA_PRE_EURO']) & ~frame.inherited.eq(True)].copy()
    elif scope=='euro_area':
        entry=frame.country.map(EA_ENTRY)
        date=frame.time if panel_data.frequency.iloc[0]=='Q' else frame.time*4
        frame=frame[entry.notna()&date.ge(entry)].copy()
    elif scope.startswith('region:'):frame=frame[frame.region.eq(scope[7:])].copy()
    if variant=='domestic_only':frame=frame[~frame.inherited.eq(True)].copy()
    elif variant=='published_identified_only':frame=frame[frame.source.eq(1)].copy()
    elif variant=='exclude_covid_windows':
        start,end=(2020,2021) if panel_data.frequency.iloc[0]=='A' else (2020*4,2021*4+3)
        frame=frame[~((frame.time-1<=end)&(frame.time+horizon>=start))].copy()
    elif variant=='exclude_largest_shock':
        # Per-recipient-series largest absolute shock, specified independently
        # of outcomes. This is an influence diagnostic, not preferred selection.
        tops=source_data.loc[source_data.shock.notna()].groupby('country').shock.apply(lambda x:x.abs().idxmax())
        frame=frame[~frame.index.isin(tops.values)].copy()
    elif variant=='stable_source_only':
        # Keep the modal construction class per country. No selection by fit.
        modes=source_data.groupby('country').source_method.agg(lambda s:s.mode().iloc[0] if len(s.mode()) else '')
        frame=frame[frame.source_method.eq(frame.country.map(modes))].copy()
    if moderator:
        frame['interaction']=frame.shock*frame.z
    frequency=panel_data.frequency.iloc[0]
    local=country is not None
    minimum=(25 if moderator else 20) if frequency=='A' else (50 if moderator else 40)
    if not local:minimum=100
    frame.attrs['horizon']=horizon
    spec=dict(universe=panel_data.universe.iloc[0],frequency=frequency,outcome=outcome,horizon=horizon,
        scope='country' if local else scope,country=country,variant=variant,
        model='B_state_dependent' if local and moderator else 'A_baseline' if local else
              'D_global_moderator' if moderator and scope=='global' else
              'C_group_moderator' if moderator else 'panel_baseline',
        moderator=panel_data.attrs.get('moderator') if moderator else None,
        estimand=panel_data.estimand.dropna().iloc[0] if 'estimand'in panel_data else 'domestic_or_documented_inherited',
        shock_unit=panel_data.shock_unit.dropna().iloc[0])
    spec['specification_id']=hashlib.sha256(json.dumps(spec,sort_keys=True).encode()).hexdigest()[:20]
    try:
        result=fit(frame,panel=not local,moderator=moderator,min_n=minimum,frequency=frequency,influence=use_influence)
    except Exception as exc:
        result=dict(status='failed',reason=type(exc).__name__+': '+str(exc),n=len(frame))
    return {**spec,**result}


def write_run(records, directory):
    """Every attempted specification is retained, including failures and nulls."""
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    def clean(value):
        if isinstance(value,dict):return {k:clean(v) for k,v in value.items()}
        if isinstance(value,list):return [clean(v) for v in value]
        if isinstance(value,np.generic):return clean(value.item())
        if isinstance(value,float) and not np.isfinite(value):return None
        return value
    for record in records:
        if str(record.get('model','')).startswith('E_'):
            key={k:record.get(k) for k in ['universe','outcome','horizon','scope','country','variant',
                'model','moderator','exposure_last_year']}
            record['specification_id']=hashlib.sha256(json.dumps(key,sort_keys=True).encode()).hexdigest()[:20]
    with gzip.open(directory/'specifications.jsonl.gz','wt',encoding='utf-8') as handle:
        for record in records:handle.write(json.dumps(clean(record),allow_nan=False)+'\n')
    coefficients=[];attempts=[]
    for record in records:
        meta={k:v for k,v in record.items() if not isinstance(v,(dict,list))}
        attempts.append(meta)
        for estimate in record.get('estimates',[]):coefficients.append({**meta,**estimate})
    estimates=pd.DataFrame(coefficients)
    if not estimates.empty:
        # Descriptive FDR alongside, never replacing or hiding raw p-values.
        estimates['q_BH_informational']=np.nan
        for _,idx in estimates.groupby(['universe','model','outcome','variant','term'],dropna=False).groups.items():
            p=estimates.loc[idx,'p_raw'].to_numpy();order=np.argsort(p);m=len(p)
            adjusted=np.minimum.accumulate((p[order]*m/np.arange(1,m+1))[::-1])[::-1]
            restored=np.empty(m);restored[order]=np.minimum(adjusted,1)
            estimates.loc[idx,'q_BH_informational']=restored
        save_csv(estimates,directory/'coefficients.csv.gz')
    save_csv(pd.DataFrame(attempts),directory/'attempts.csv.gz')
    return estimates


def pooled_heterogeneity(records):
    """Descriptive variance decomposition; dependence-robust bootstrap is separate."""
    rows=[]
    good=[r for r in records if r.get('status')=='ok' and r.get('scope')=='country' and r.get('variant')=='all']
    for r in good:
        term=next(x for x in r['estimates'] if x['term']=='shock')
        rows.append({k:r[k] for k in ['universe','outcome','horizon','country']}|term)
    if not rows:return pd.DataFrame()
    d=pd.DataFrame(rows);out=[]
    for keys,g in d.groupby(['universe','outcome','horizon']):
        k=len(g);variance=g.estimate.var(ddof=1)
        out.append(dict(zip(['universe','outcome','horizon'],keys))|dict(n_countries=k,
            mean=g.estimate.mean(),median=g.estimate.median(),cross_country_variance=variance,
            mean_sampling_variance=(g.se**2).mean(),
            excess_variance_descriptive=max(0,variance-(g.se**2).mean()),
            positive_estimates=int(g.estimate.gt(0).sum()),
            positive_raw_p05=int((g.estimate.gt(0)&g.p_raw.lt(.05)).sum()),
            negative_raw_p05=int((g.estimate.lt(0)&g.p_raw.lt(.05)).sum()),
            note='variance_subtraction_is_descriptive_not_a_dependence_robust_heterogeneity_test'))
    return pd.DataFrame(out)
