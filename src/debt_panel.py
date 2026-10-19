"""Build the expanded panel; all source choices precede new estimation.

Preserve annual ownership dating, shocks, LP windows and original covariance
rules. Retain real measurement dates and portfolio definitions. No missing
debt observation is interpolated and no annual measurement is called quarterly.
"""
from pathlib import Path
from datetime import datetime,timezone
import json,gzip,zipfile,re,hashlib
import numpy as np
import pandas as pd
from debt_sources import P,RAW,OUT,save
from macro_data import EA_ENTRY,ISO3

from local_projection import load_panel
R0=load_panel('Q')[1]
OWN_COLS=['debt','foreign','cb','domestic_noncb']

def ownership():
    imf=pd.read_csv(OUT/'official_imf_annual_selected.csv.gz')
    imf['foreign_official_gdp']=imf.foreign_official
    imf['domestic_bank_gdp']=imf.domestic_bank
    imf['domestic_nonbank_gdp']=imf.domestic_nonbank
    euro=pd.read_csv(OUT/'holdings_annual_eurostat.csv')
    old=pd.read_csv(OUT/'holdings_annual_FHL.csv')
    old=old.merge(pd.read_csv(P/'data/processed/fhl_holdings.csv').assign(
        country=lambda z:z.Country_Code.map(__import__('macro_data').ISO2),year=lambda z:z.Year.astype(int)).loc[lambda z:z.country.notna(),
        ['country','year','foreign_official_gdp','domestic_bank_gdp','domestic_nonbank_gdp']],
        on=['country','year'],how='left',validate='one_to_one')
    euro['priority']=np.where(euro.country.isin(EA_ENTRY),0,1)
    imf['priority']=np.where(imf.country.isin(EA_ENTRY),1,0)
    old['priority']=2
    allrows=pd.concat([euro,imf,old],ignore_index=True,sort=False)
    allrows=allrows.dropna(subset=OWN_COLS)
    allrows=allrows.sort_values(['country','year','priority']).drop_duplicates(['country','year'])
    # Preserve the published sector values; enforce the exhaustive three-stock
    # identity by an explicitly recorded rounding residual in the non-CB stock.
    allrows['published_domestic_noncb']=allrows.domestic_noncb
    allrows['domestic_noncb']=allrows.debt-allrows.foreign-allrows.cb
    allrows['sector_rounding_adjustment']=allrows.domestic_noncb-allrows.published_domestic_noncb
    assert allrows.sector_rounding_adjustment.abs().max()<.31
    allrows['published_domestic_nonbank_gdp']=allrows.domestic_nonbank_gdp
    allrows['domestic_nonbank_gdp']=allrows.domestic_noncb-allrows.domestic_bank_gdp
    allrows['holdings_year']=allrows.year
    assert not allrows.duplicated(['country','year']).any()
    save(allrows,'official_expanded_ownership_annual.csv.gz')
    return allrows

def candidates():
    frames=[]
    # Keep the existing long marketable-debt histories. New national sources
    # supply consistent portfolios for the countries absent from those histories.
    d=pd.read_csv(OUT/'maturity_quarterly_DGM.csv')
    d=d.rename(columns={'quarter':'period','maturity_source':'source'})
    d['date']=pd.PeriodIndex(d.period,freq='Q').to_timestamp(how='end').normalize()
    d['frequency']='Q';d['priority']=10;d['sector']='source government portfolio'
    d['portfolio']='source marketable government debt';d['valuation']='face';d['source_file']='maturity_summary.xlsx'
    frames.append(d)
    for name in ['poland_maturity_monthly','hungary_maturity','chile_maturity_annual','india_maturity_annual','slovenia_maturity_annual','estonia_maturity_annual','luxembourg_maturity_annual','latvia_maturity']:
        f=OUT/('official_'+name+'.csv.gz')
        if not f.exists():continue
        a=pd.read_csv(f);a['priority']=10
        if name.startswith('poland'):a.loc[a.source.str.endswith('domestic_securities'),'priority']=11
        frames.append(a)
    a=pd.read_csv(OUT/'official_brazil_maturity_monthly.csv.gz')
    a=a[a.source.eq('BR_Tesouro_DPMFi')].copy();a['priority']=10;frames.append(a)
    a=pd.read_csv(OUT/'official_eurostat_maturity_annual.csv.gz')
    a['priority']=np.where(a.sector.eq('S13'),15,35);frames.append(a)
    a=pd.read_csv(OUT/'official_qpsd_maturity_all.csv.gz')
    a['priority']=a.source.map({'QPSD_GG':20,'QPSD_CG':30,'QPSD_BC':40})
    # Korea's fourteen Q4 measurements are genuinely annual observations.
    a.loc[a.country.eq('KR'),'frequency']='A'
    # China's historical Q2/Q4 releases have a semiannual, rather than
    # manufactured quarterly, measurement interval.
    a.loc[a.country.eq('CN') & (a.period<='2018Q4'),'frequency']='S'
    frames.append(a)
    a=pd.read_csv(OUT/'official_bis_maturity_all.csv.gz')
    a['priority']=a.sector.map({'S13':50,'S1311':60})+a.valuation.map({'N':0,'F':1,'M':5})
    a['source']='BIS_NA_SEC_'+a.sector+'_'+a.valuation
    a['date']=pd.PeriodIndex(a.period,freq='Q').to_timestamp(how='end').normalize()
    a['numerator']=a.S+a.LS;a['denominator']=a['T'];a['source_file']='bis_all_government_maturity_subset.csv.gz'
    frames.append(a)
    d=pd.concat(frames,ignore_index=True,sort=False)
    d['date']=pd.to_datetime(d.date)
    d=d.dropna(subset=['country','refinance_share','date'])
    assert d.refinance_share.between(0,1.01).all()
    # Monthly stock data enter as real observed end-quarter snapshots. All
    # monthly originals remain in the national exports and raw workbook.
    d=d[~d.frequency.eq('M') | d.date.dt.month.mod(3).eq(0)].copy()
    d['obs_q']=pd.PeriodIndex(d.date,freq='Q').asi8
    d['max_age']=d.frequency.map({'Q':0,'M':0,'S':1,'A':3})
    annual=d[d.date.dt.month.eq(12) & ~d.frequency.eq('A')].copy()
    annual['frequency']='A_snapshot';annual['max_age']=3;annual['priority']+=.25
    d=pd.concat([d,annual],ignore_index=True,sort=False)
    d['maturity_source']=d.source
    d['candidate_id']=np.arange(len(d))
    save(d,'official_expanded_maturity_candidates.csv.gz')
    return d

def attach_states(base,h,c):
    base=base.copy();base['period']=pd.PeriodIndex(base.period,freq='Q')
    base['year']=base.period.dt.year;base['hold_year']=base.year-1
    keep=['country','year','source','holdings_year','foreign_official_gdp','domestic_bank_gdp','domestic_nonbank_gdp']+OWN_COLS
    h=h[keep].rename(columns={'year':'hold_year'})
    base=base.merge(h,on=['country','hold_year'],how='left',validate='many_to_one')
    picked=[]
    for country,g in base.groupby('country'):
        cc=c[c.country.eq(country)]
        for i,r in g.iterrows():
            # Completed previous quarter; publication-release information is
            # not asserted. These are predetermined stocks at a revised vintage.
            ref=r.period.ordinal-1
            z=cc[(cc.obs_q<=ref) & ((ref-cc.obs_q)<=cc.max_age)]
            if len(z):
                best=z.sort_values(['priority','date','candidate_id'],ascending=[True,False,True]).iloc[0]
                row={k:best.get(k) for k in ['refinance_share','maturity_source','frequency','date','sector','portfolio','valuation','source_file','source_detail','candidate_id']}
                row.update(index=i,maturity_age_quarters=ref-int(best.obs_q))
                picked.append(row)
    selected=pd.DataFrame(picked).set_index('index').rename(columns={'frequency':'maturity_frequency','date':'maturity_date',
        'sector':'maturity_sector','portfolio':'maturity_portfolio','valuation':'maturity_valuation','source_file':'maturity_file','source_detail':'maturity_detail'})
    base=base.join(selected)
    base['maturity_period']=base.maturity_date.dt.strftime('%Y-%m-%d')
    base['source_group']=base.country+'_'+base.source.fillna('missing')+'_'+base.maturity_source.fillna('missing')
    base['hold_group']=base.country+'_'+base.source.fillna('missing');base['roll_group']=base.source_group
    base['time_index']=base.period.map(lambda x:x.ordinal);base['season']=base.period.dt.quarter
    base=base.sort_values(['country','time_index']).reset_index(drop=True)
    g=base.groupby('country',sort=False);dy=g.log_gdp.diff();dp=g.log_prices.diff()
    for lag in range(1,5):
        base[f'growth_l{lag}']=dy.groupby(base.country).shift(lag);base[f'inflation_l{lag}']=dp.groupby(base.country).shift(lag)
    base['growth_state']=g.log_gdp.shift(1)-g.log_gdp.shift(5);base['inflation_state']=g.log_prices.shift(1)-g.log_prices.shift(5)
    for col in ['primary_balance','net_interest']:
        if col in base:base[col+'_lag']=g[col].shift(1)
    base['rollover_centered']=(base.refinance_share-R0)/.1
    assert base.groupby('country').time_index.diff().dropna().eq(1).all()
    assert not base.duplicated(['country','period']).any()
    base['period']=base.period.astype(str)
    return base

def cpi():
    z=zipfile.ZipFile(RAW/'bis_long_cpi.zip')
    member=next(n for n in z.namelist() if n.endswith('.csv'))
    d=pd.read_csv(z.open(member),low_memory=False)
    d=d[d.FREQ.eq('M') & d.UNIT_MEASURE.astype(str).eq('628')].copy()
    times=[s for s in d if re.fullmatch(r'\d{4}-\d{2}',s)]
    assert not d.REF_AREA.duplicated().any()
    m=d[['REF_AREA']+times].melt(id_vars='REF_AREA',var_name='month',value_name='value')
    m['value']=pd.to_numeric(m.value,errors='coerce');m['period']=pd.PeriodIndex(m.month,freq='M').asfreq('Q')
    q=m.groupby(['REF_AREA','period']).value.agg(['mean','count']).reset_index()
    q['log_prices']=100*np.log(q['mean'].where(q['count'].eq(3)&q['mean'].gt(0)))
    q=q.rename(columns={'REF_AREA':'country'});q['period']=q.period.astype(str)
    save(q,'official_bis_cpi_quarterly.csv.gz')
    return q[['country','period','log_prices']]

def fx_states(data):
    c=pd.read_csv(OUT/'official_imf_currency_annual_all.csv.gz')
    c=c[c.measure.eq('local_currency_share') & c.share.notna() & c.country.notna()].copy()
    c['fx_share']=1-c.share;c['fx_source']='IMF_AT_'+c.imf_group;c['hold_year']=c.year
    dgm=pd.read_csv(OUT/'currency_states.csv')
    dgm=dgm.dropna(subset=['fx_share_DGM']).copy();dgm['fx_share']=dgm.fx_share_DGM
    dgm['fx_source']='DGM_marketable_face';dgm['portfolio']='source marketable debt'
    d=pd.concat([c[['country','hold_year','fx_share','fx_source','portfolio']],dgm[['country','hold_year','fx_share','fx_source','portfolio']]],ignore_index=True)
    picks=[];audit=[]
    # One currency definition for a country throughout its history. Choose by
    # observed predictor-year coverage over the fixed common shock window,
    # then freshness. There is no search over regression coefficients.
    for country,g in d.groupby('country'):
        groups=list(g.groupby('fx_source'))
        source,z=max(groups,key=lambda item:(int(item[1].hold_year.between(1999,2021).sum()),int(item[1].hold_year.max())))
        picks.append(z);audit.append(dict(country=country,fx_source=source,years=int(len(z)),first=int(z.hold_year.min()),last=int(z.hold_year.max())))
    d=pd.concat(picks,ignore_index=True);assert not d.duplicated(['country','hold_year']).any()
    save(d,'official_expanded_fx_annual.csv.gz');save(pd.DataFrame(audit),'official_expanded_fx_selection.csv')
    return data.merge(d,on=['country','hold_year'],how='left',validate='many_to_one')

def main():
    h=ownership();c=candidates()
    old=pd.read_csv(OUT/'panel_quarterly.csv.gz')
    keep=['country','period','log_gdp','log_prices','log_consumption','log_investment','interest','primary_balance','net_interest',
        'MP_median','CBI_median','MP_pm','CBI_pm','pc1_hf','ea_member']
    ea=attach_states(old[keep],h,c);save(ea,'official_expanded_panel_ea.csv.gz')
    old=pd.read_csv(OUT/'panel_global_external.csv.gz')
    ext=old[['country','period','log_gdp']].copy()
    obj=json.loads(gzip.decompress((RAW/'gem_real_gdp_CN_TH_quarterly.json.gz').read_bytes()))
    new=pd.DataFrame([dict(country={'CHN':'CN','THA':'TH'}[r['country']['id']],period=r['date'],
        log_gdp=100*np.log(r['value']) if r['value'] is not None and r['value']>0 else np.nan) for r in obj[1]])
    idx=pd.MultiIndex.from_product([['CN','TH'],pd.period_range('1995Q1','2026Q2',freq='Q').astype(str)],names=['country','period'])
    new=new.set_index(['country','period']).reindex(idx).reset_index()
    ext=pd.concat([ext,new],ignore_index=True).merge(cpi(),on=['country','period'],how='left',validate='one_to_one')
    ext=attach_states(ext,h,c)
    from international_data import shocks
    s=shocks();s['period']=s.period.astype(str)
    ext['issuer']=ext.country.map(ISO3)
    ext=ext.merge(s,on=['issuer','period'],how='left',validate='many_to_one')
    ext['ea_member']=True
    for issuer,label in [('USA','Fed'),('DEU','ECB')]:
        ss=s[s.issuer.eq(issuer)].set_index('period')
        ext[label+'_MP']=ext.period.map(ss.MP_median);ext[label+'_CBI']=ext.period.map(ss.CBI_median)
    ext=fx_states(ext);save(ext,'official_expanded_panel_external.csv.gz')
    audit=[]
    for sample,d in [('euro_area',ea),('own_policy',ext)]:
        eligible=d[d.ea_member & d.MP_median.notna()]
        for label,cols in [('ownership',OWN_COLS),('ownership_refinancing',OWN_COLS+['refinance_share'])]:
            for country,g in eligible.dropna(subset=cols).groupby('country'):
                audit.append(dict(sample=sample,model=label,country=country,observations=len(g),first=g.period.min(),last=g.period.max(),
                    ownership_sources='; '.join(sorted(g.source.unique())),maturity_sources='; '.join(sorted(g.maturity_source.dropna().unique()))))
    save(pd.DataFrame(audit),'official_expanded_predictor_coverage.csv')
    print(pd.DataFrame(audit).groupby(['sample','model']).agg(countries=('country','nunique'),observations=('observations','sum')).to_string(),flush=True)

if __name__=='__main__':main()
