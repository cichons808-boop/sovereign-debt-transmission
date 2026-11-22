"""Worldwide lower-identification-class reaction-function reconstruction.

These are policy-rule residuals, NOT high-frequency monetary surprises.
Annual design reproduces CWY eq. (2): three lags each of real GDP growth,
inflation, exchange-rate depreciation and policy-rate changes. Quarterly
design is a separately labelled one-lag extension. No annual data are expanded
into quarterly observations. Every first-stage attempt is recorded.
"""
from __future__ import annotations

import json
import xml.etree.ElementTree as ET
import zipfile

import numpy as np
import pandas as pd
import pycountry
from scipy import stats,linalg

from .data import (AUDIT,BASE,EA_ENTRY,PROCESSED,RAW,URLS,country_metadata,fetch,
                   iso3,prepare_lags,quarterly_macro,save_csv,wdi)
from .estimation import calendar_hac

RECON_URLS={
    'bis_policy_fresh.zip':'https://data.bis.org/static/bulk/WS_CBPOL_csv_flat.zip',
    'bis_usd_fx_fresh.zip':'https://data.bis.org/static/bulk/WS_XRU_csv_flat.zip',
    'mfs_ir_primary_bulk.csv':'https://api.imf.org/external/sdmx/2.1/data/IMF.STA,MFS_IR,8.0.1/.DISR_RT_PT_A_PT.M?format=csvfile',
    'mfs_ir_policy_monthly.csv':'https://api.imf.org/external/sdmx/2.1/data/IMF.STA,MFS_IR,8.0.1/.MFS166_RT_PT_A_PT.M?format=csvfile',
    'mfs_ir_refinance_monthly.csv':'https://api.imf.org/external/sdmx/2.1/data/IMF.STA,MFS_IR,8.0.1/.MFS171_RT_PT_A_PT.M?format=csvfile',
    'mfs_ir_repo_monthly.csv':'https://api.imf.org/external/sdmx/2.1/data/IMF.STA,MFS_IR,8.0.1/.MFS161_RT_PT_A_PT.M?format=csvfile',
    'ifs_policy_metadata.json':'https://api.db.nomics.world/v22/series/IMF/IFS?dimensions=%7B%22INDICATOR%22%3A%5B%22FPOLM_PA%22%5D%7D&limit=1000&observations=1',
    'ifs_central_discount.json':'https://api.db.nomics.world/v22/series/IMF/IFS?dimensions=%7B%22INDICATOR%22%3A%5B%22FID_PA%22%5D%7D&limit=1000&observations=1',
    'wb_fx.json':'https://api.worldbank.org/v2/country/all/indicator/PA.NUS.FCRF?date=1960:2025&format=json&per_page=20000',
    'wb_annual_gdp_growth.json':'https://api.worldbank.org/v2/country/all/indicator/NY.GDP.MKTP.KD.ZG?date=1960:2025&format=json&per_page=20000',
    'wb_annual_inflation.json':'https://api.worldbank.org/v2/country/all/indicator/FP.CPI.TOTL.ZG?date=1960:2025&format=json&per_page=20000',
}
URLS.update(RECON_URLS)

COMMON_AUTHORITY_MEMBERS={
    'BCEAO':set('BEN BFA CIV GNB MLI NER SEN TGO'.split()),
    'BEAC':set('CMR CAF COG GAB GNQ TCD'.split()),
    'ECCB':set('AIA ATG DMA GRD KNA LCA MSR VCT'.split()),
}
COMMON_MEMBERS=set().union(*COMMON_AUTHORITY_MEMBERS.values())


def read_sdmx(path):
    """IMF may return valid SDMX XML despite format=csvfile; inspect bytes."""
    body=path.read_bytes()
    if body.lstrip().startswith(b'<'):
        rows=[]
        for series in ET.fromstring(body).iter():
            if series.tag.split('}')[-1]!='Series':continue
            for obs in series:
                if 'OBS_VALUE'in obs.attrib:
                    rows.append({**series.attrib,**obs.attrib})
        return pd.DataFrame(rows)
    return pd.read_csv(path)


def rates():
    frames=[]
    z=zipfile.ZipFile(fetch('bis_policy_fresh.zip'))
    with z.open(z.namelist()[0]) as handle:
        d=pd.read_csv(handle,low_memory=False)
    d=d[d['FREQ:Frequency'].str.startswith('M:')].copy()
    d['country']=d['REF_AREA:Reference area'].str.split(':').str[0].map(iso3)
    d['month']=pd.PeriodIndex(d['TIME_PERIOD:Time period or range'],freq='M')
    d['rate']=pd.to_numeric(d['OBS_VALUE:Observation Value'],errors='coerce')
    d['source']='BIS_CBPOL_EOP';d['kind']='policy';d['priority']=0
    frames.append(d[['country','month','rate','source','kind','priority']])
    for filename,kind,priority in [('mfs_ir_policy_monthly.csv','policy',1),
        ('mfs_ir_refinance_monthly.csv','refinancing',2),('mfs_ir_repo_monthly.csv','repo',3),
        ('mfs_ir_primary_bulk.csv','discount',4)]:
        d=read_sdmx(fetch(filename))
        d['country']=d.COUNTRY
        d['month']=pd.PeriodIndex(d.TIME_PERIOD.str.replace('-M','-',regex=False),freq='M')
        d['rate']=pd.to_numeric(d.OBS_VALUE,errors='coerce')
        d['source']='IMF_MFS_IR_'+d.INDICATOR
        d['kind']=kind;d['priority']=priority
        frames.append(d[['country','month','rate','source','kind','priority']])
    # Retired IFS adds genuinely observed older series not returned by modern
    # flows. It remains a separate candidate source, never row-wise backfilled.
    for filename,kind,priority in [('ifs_policy_metadata.json','policy',5),('ifs_central_discount.json','discount',6)]:
        payload=json.loads(fetch(filename).read_text())
        if len(payload['series']['docs'])!=payload['series']['num_found']:
            raise ValueError('Incomplete IFS download')
        for s in payload['series']['docs']:
            if s['dimensions']['FREQ']!='M':continue
            country=iso3(s['dimensions']['REF_AREA'])
            if not country:continue
            frames.append(pd.DataFrame(dict(country=country,month=pd.PeriodIndex(s['period'],freq='M'),
                rate=pd.to_numeric(pd.Series(s['value']),errors='coerce'),source='IMF_IFS_'+s['series_code'],
                kind=kind,priority=priority)))
    all_rates=pd.concat(frames,ignore_index=True).dropna(subset=['country','rate'])
    # Country code may be an IMF aggregate or non-ISO group. Do not treat it as
    # a new state/issuer or fabricate a GDP outcome for an aggregate.
    all_rates=all_rates[all_rates.country.isin({c.alpha_3 for c in pycountry.countries})]
    assert not all_rates.duplicated(['country','month','source']).any()
    options=all_rates.groupby(['country','source','kind','priority']).agg(n=('rate','size'),
        first=('month','min'),last=('month','max')).reset_index()
    # Prefer an actual policy instrument over a discount-rate proxy, then the
    # freshest endpoint, longest coverage and documented priority. Whole-series
    # selection avoids hidden splices between average and end-period rates.
    options['policy_class']=options.kind.map({'policy':0,'refinancing':1,'repo':1,'discount':2})
    chosen=options.sort_values(['country','policy_class','last','n','priority'],
        ascending=[True,True,False,False,True]).drop_duplicates('country')
    selected=all_rates.merge(chosen[['country','source']],on=['country','source'],validate='many_to_one')
    save_csv(options.assign(first=options['first'].astype(str),last=options['last'].astype(str)),
             AUDIT/'policy_rate_all_source_candidates.csv')
    save_csv(chosen.assign(first=chosen['first'].astype(str),last=chosen['last'].astype(str)),
             AUDIT/'policy_rate_country_source_selection.csv')
    save_csv(selected.assign(month=selected.month.astype(str)),PROCESSED/'observed_policy_rates_monthly.csv.gz')
    return selected


def annual_macro(countries):
    data=wdi('wb_gdp.json','gdp_level').merge(wdi('wb_cpi.json','cpi_level'),on=['country','year'],how='outer')
    data=data.merge(wdi('wb_annual_gdp_growth.json','growth'),on=['country','year'],how='outer')
    data=data.merge(wdi('wb_annual_inflation.json','inflation'),on=['country','year'],how='outer')
    data=data.merge(wdi('wb_fx.json','fx'),on=['country','year'],how='outer')
    idx=pd.MultiIndex.from_product([countries.country.unique(),range(1960,2026)],names=['country','year'])
    data=pd.DataFrame(index=idx).reset_index().merge(data,on=['country','year'],how='left',validate='one_to_one')
    data['time']=data.year;data['period']=data.year.astype(str);data['season']=1
    data['log_gdp']=100*np.log(data.gdp_level.where(data.gdp_level>0))
    data['log_cpi']=100*np.log(data.cpi_level.where(data.cpi_level>0))
    data=data.sort_values(['country','year'])
    data['depreciation']=100*data.groupby('country').fx.transform(lambda x:np.log(x.where(x>0)).diff())
    return data.merge(countries,on='country',how='left',validate='many_to_one')


def annual_rates(monthly):
    # Only an actually observed December policy value defines year-end policy.
    # No last-observation-carried-forward over an unobserved December.
    d=monthly[monthly.month.dt.month.eq(12)].copy()
    d['year']=d.month.dt.year
    return d[['country','year','rate','source','kind']]


def regression_shocks(data,frequency,annual_lags=3):
    records=[];result=data.copy().sort_values(['country','time']).reset_index(drop=True)
    result['rate_change']=result.groupby('country').rate.diff()
    lag_count=annual_lags if frequency=='A' else 1
    features=[]
    for variable in ['growth','inflation','depreciation','rate_change']:
        for lag in range(1,lag_count+1):
            key=f'{variable}_lag{lag}';features.append(key)
            result[key]=result.groupby('country')[variable].shift(lag)
    result['shock_raw']=np.nan;result['shock_expanding_raw']=np.nan
    for country,g in result.groupby('country'):
        valid=g.dropna(subset=['rate_change']+features)
        design=np.column_stack([np.ones(len(valid)),valid[features].to_numpy(float)])
        meta=dict(country=country,frequency=frequency,n=len(valid),features=['intercept']+features,
                  rate_source='|'.join(sorted(g.source.dropna().unique())))
        minimum=max(20 if frequency=='A' else 50,design.shape[1]+8)
        if len(valid)<minimum:
            records.append({**meta,'status':'not_estimable','reason':'insufficient_observed_lag_support',
                            'required':minimum});continue
        # Numeraire USD exchange rates or an exact peg may have zero changes.
        # Dropping such redundant nuisance columns is explicit, not a failure
        # to identify the residual from the estimable reaction function.
        norm=np.linalg.norm(design,axis=0)
        nonzero=norm>1e-12
        reduced=design[:,nonzero]
        _,qr,piv=linalg.qr(reduced/np.linalg.norm(reduced,axis=0),mode='economic',pivoting=True)
        rank=int((np.abs(np.diag(qr))>1e-9).sum())
        retained_original=np.flatnonzero(nonzero)[piv[:rank]]
        dropped=[meta['features'][i] for i in range(design.shape[1]) if i not in retained_original]
        design=design[:,retained_original];norm=np.linalg.norm(design,axis=0)
        meta['dropped_redundant_regressors']=dropped
        meta['features']=[meta['features'][i] for i in retained_original]
        target=valid.rate_change.to_numpy(float)
        beta=np.linalg.lstsq(design/norm,target,rcond=None)[0]/norm
        residual=target-design@beta
        if np.std(residual,ddof=1)<1e-7:
            records.append({**meta,'status':'not_estimable','reason':'zero_policy_innovation_variance'});continue
        result.loc[valid.index,'shock_raw']=residual
        # Recursive coefficients use only strictly earlier observed dates. This
        # diagnostic series is saved separately and never silently substituted.
        for j in range(max(20,design.shape[1]+8),len(valid)):
            past=design[:j]
            if np.linalg.matrix_rank(past)<design.shape[1]:continue
            b=np.linalg.lstsq(past,target[:j],rcond=None)[0]
            result.loc[valid.index[j],'shock_expanding_raw']=target[j]-design[j]@b
        bread=np.linalg.inv(design.T@design)
        meat,_,_=calendar_hac(design*residual[:,None],valid.time.to_numpy(int),lag_count+1)
        vc=bread@meat@bread*len(valid)/(len(valid)-design.shape[1])
        se=np.sqrt(np.maximum(np.diag(vc),0))
        records.append({**meta,'status':'ok','first_period':valid.period.min(),'last_period':valid.period.max(),
            'beta':beta.tolist(),'se_HAC':se.tolist(),'covariance_HAC':vc.tolist(),
            'p_raw':(2*stats.t.sf(np.abs(beta/np.maximum(se,1e-30)),len(valid)-design.shape[1])).tolist(),
            'rank':rank,'shock_sd_source_unit':float(residual.std(ddof=1)),
            'r_squared':float(1-residual@residual/np.sum((target-target.mean())**2)),
            'important_limit':'lag_only_full_sample_Taylor_residual_not_an_exogenous_HF_shock;generated_regressor_uncertainty_not_in_LP_SE'})
    result['normalization_scale']=result.groupby('country').shock_raw.transform('std')
    result['shock']=result.shock_raw/result.normalization_scale
    result['shock_unit']='one_full_source_country_SD_reconstructed_Taylor_innovation_not_10bp'
    result['issuer']=result.country
    result['inherited']=False;result['shared_union_shock']=False
    result['source_method']='reconstructed_Taylor_'+str(lag_count)+'lag_'+result.kind.fillna('missing')
    result['frequency']=frequency
    tag=frequency+str(lag_count)+'L'
    (AUDIT/f'Taylor_first_stage_{tag}.json').write_text(json.dumps(records,indent=2,default=str))
    save_csv(pd.DataFrame([{k:v for k,v in r.items() if not isinstance(v,list)} for r in records]),
             AUDIT/f'Taylor_first_stage_{tag}_status.csv')
    return prepare_lags(result)


def quarterly_reconstruction(monthly,countries):
    # Genuine quarterly macro data, never a repetition of annual GDP.
    d=quarterly_macro(countries)
    fxzip=zipfile.ZipFile(fetch('bis_usd_fx_fresh.zip'))
    with fxzip.open(fxzip.namelist()[0]) as handle:fx=pd.read_csv(handle,low_memory=False)
    fx=fx[fx['FREQ:Frequency'].str.startswith('Q:')&fx['COLLECTION:Collection'].str.startswith('A:')].copy()
    fx['country']=fx['REF_AREA:Reference area'].str.split(':').str[0].map(iso3)
    fx['period']=fx['TIME_PERIOD:Time period or range'].str.replace('-Q','Q',regex=False)
    fx['fx']=pd.to_numeric(fx['OBS_VALUE:Observation Value'],errors='coerce')
    # Select one exact observed quarterly currency series per economy; changes
    # of currency are not patched into a continuous depreciation series here.
    fx=fx.sort_values('period').drop_duplicates(['country','period'],keep='last')
    d=d.merge(fx[['country','period','fx']],on=['country','period'],how='left',validate='one_to_one')
    r=monthly[monthly.month.dt.month.isin([3,6,9,12])].copy()
    r['period']=r.month.dt.asfreq('Q').astype(str)
    d=d.merge(r[['country','period','rate','source','kind']],on=['country','period'],how='left',validate='one_to_one')
    d=d.sort_values(['country','time'])
    d['growth']=d.groupby('country').log_gdp.diff()
    d['inflation']=d.groupby('country').log_cpi.diff(4)
    d['depreciation']=100*d.groupby('country').fx.transform(lambda x:np.log(x.where(x>0)).diff())
    # A member-country Taylor rule using a common ECB rate would not identify
    # a separate domestic policy innovation. Those rows are deliberately ineligible.
    for country,entry in EA_ENTRY.items():d.loc[d.country.eq(country)&d.time.ge(entry),'rate']=np.nan
    d.loc[d.country.isin(COMMON_MEMBERS),'rate']=np.nan
    q=regression_shocks(d,'Q');q['universe']='T_reconstructed_quarterly'
    save_csv(q,PROCESSED/'T_reconstructed_quarterly.csv.gz')
    return q


def country_inventory(countries,monthly,annual,quarterly):
    universe=pd.DataFrame([dict(country=c.alpha_3,iso_country_name=c.name) for c in pycountry.countries])
    additional=countries.loc[~countries.country.isin(universe.country),['country','country_name']].rename(columns={'country_name':'iso_country_name'})
    universe=pd.concat([universe,additional],ignore_index=True)
    universe=universe.merge(countries,on='country',how='left',validate='one_to_one')
    rate=monthly.groupby('country').agg(rate_first=('month','min'),rate_last=('month','max'),
        rate_observations=('rate','size'),rate_source=('source','first'),rate_kind=('kind','first')).reset_index()
    universe=universe.merge(rate,on='country',how='left')
    for label,d in [('annual',annual),('quarterly',quarterly)]:
        s=d[d.shock.notna()].groupby('country').agg(**{label+'_shock_n':('shock','size'),
            label+'_shock_first':('period','min'),label+'_shock_last':('period','max')}).reset_index()
        universe=universe.merge(s,on='country',how='left')
    cwy=pd.read_csv(AUDIT/'cwy_country_year_identification.csv')
    s=cwy.groupby('country').agg(CWY_n=('shock','size'),CWY_last=('year','max')).reset_index()
    universe=universe.merge(s,on='country',how='left')
    universe['status']=np.where(universe.annual_shock_n.fillna(0).gt(0),'reconstructed_annual',
        np.where(universe.CWY_n.fillna(0).gt(0),'published_CWY_only',
                 np.where(universe.rate_observations.fillna(0).gt(0),'rate_found_first_stage_insufficient','source_gap_open')))
    universe['next_action']=np.where(universe.status.eq('source_gap_open'),
        'search_national_central_bank_IMF_DSBB_and_replication_packages;verify_monetary_authority_first',
        np.where(universe.status.eq('rate_found_first_stage_insufficient'),
        'extend_observed_historical_policy_or_macro_inputs;no_synthetic_fill',
        'audit_new_country_specific_HF_or_narrative_sources_and_recent_endpoints'))
    # This is an inventory, not a claim that every national website was searched.
    universe['individual_national_source_search']='not_yet_completed'
    for filename,label in [('T_reconstructed_annual_1L.csv.gz','annual_1L'),
        ('H_BDY_daily.csv.gz','BDY'),('H_ECB_reconstructed_2026.csv.gz','ECB_2026'),
        ('W_external_USA_annual.csv.gz','external_Fed_annual')]:
        path=PROCESSED/filename
        if not path.exists():continue
        p=pd.read_csv(path,low_memory=False)
        observed=p[p.shock.notna()].groupby('country').agg(**{
            label+'_shock_n':('shock','size'),label+'_shock_last':('period','max')}).reset_index()
        universe=universe.merge(observed,on='country',how='left',validate='one_to_one')
    universe['latest_domestic_reconstruction_class']='not_reconstructed'
    if 'annual_1L_shock_n' in universe:
        universe.loc[universe.annual_1L_shock_n.fillna(0).gt(0),'latest_domestic_reconstruction_class']='annual_Taylor_1L_weaker_identification'
    universe.loc[universe.quarterly_shock_n.fillna(0).gt(0),'latest_domestic_reconstruction_class']='quarterly_Taylor_1L_weaker_identification'
    save_csv(universe,AUDIT/'worldwide_country_gap_inventory.csv')


def run():
    countries=country_metadata();monthly=rates();a=annual_macro(countries)
    a=a.merge(annual_rates(monthly),on=['country','year'],how='left',validate='one_to_one')
    for country,entry in EA_ENTRY.items():a.loc[a.country.eq(country)&a.year.ge(entry//4),'rate']=np.nan
    a.loc[a.country.isin(COMMON_MEMBERS),'rate']=np.nan
    raw=a.copy()
    a=regression_shocks(raw,'A');a['universe']='T_reconstructed_annual'
    save_csv(a,PROCESSED/'T_reconstructed_annual.csv.gz')
    short=regression_shocks(raw,'A',annual_lags=1);short['universe']='T_reconstructed_annual_1L'
    save_csv(short,PROCESSED/'T_reconstructed_annual_1L.csv.gz')
    q=quarterly_reconstruction(monthly,countries)
    country_inventory(countries,monthly,a,q)
    for d in [a,short,q]:
        obs=d[d.shock.notna()]
        print(d.universe.iloc[0],obs.country.nunique(),len(obs),obs.period.max(),flush=True)
    return a,q


if __name__=='__main__':run()
