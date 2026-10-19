"""Build period-level data before estimating shock x debt x refinancing LPs."""
from pathlib import Path
import json,sys,hashlib,gzip
import numpy as np
import pandas as pd
from jsonstat import decode

P=Path(__file__).resolve().parents[1]; RAW=P/'data/raw'; OUT=P/'data/processed';OUT.mkdir(exist_ok=True)
ISO3=dict(x.split(':') for x in '''AT:AUT BE:BEL BG:BGR CY:CYP CZ:CZE DE:DEU DK:DNK EE:EST GR:GRC ES:ESP FI:FIN FR:FRA HR:HRV HU:HUN IE:IRL IT:ITA LT:LTU LU:LUX LV:LVA MT:MLT NL:NLD NO:NOR PL:POL PT:PRT RO:ROU SE:SWE SI:SVN SK:SVK GB:GBR CH:CHE IS:ISL TR:TUR AL:ALB AU:AUS CA:CAN JP:JPN NZ:NZL US:USA BR:BRA CN:CHN IN:IND MX:MEX ZA:ZAF KR:KOR CL:CHL IL:ISR TH:THA'''.split())
ISO2={v:k for k,v in ISO3.items()}
EA_ENTRY={x:pd.Period('1999Q1','Q') for x in 'AT BE DE ES FI FR IE IT LU NL PT'.split()}
for c,period in [('GR','2001Q1'),('SI','2007Q1'),('CY','2008Q1'),('MT','2008Q1'),('SK','2009Q1'),('EE','2011Q1'),('LV','2014Q1'),('LT','2015Q1'),('HR','2023Q1'),('BG','2026Q1')]:EA_ENTRY[c]=pd.Period(period,'Q')

def country(s):return s.replace({'EL':'GR','UK':'GB'})

def euro(name):
    d=decode(RAW/(name+'.json'))
    d['country']=country(d.geo)
    return d[d.country.isin(ISO3)].copy()

def annual_holdings():
    raw=pd.concat([decode(p) for p in sorted(RAW.glob('ggd_*.json'))],ignore_index=True)
    raw['country']=country(raw.geo);raw['year']=raw.time.astype(int)
    d=raw[(raw.na_item=='GD') & (raw.sector=='S13') & (raw.maturity=='TOTAL')]
    wide=d.pivot_table(index=['country','year'],columns='sector2',values='value')
    names={'S1_S2':'debt','S1':'domestic','S2':'foreign','S121':'cb','S122_S123':'banks',
           'S124-S129':'other_financial','S11_S14_S15':'nonfinancial','S14_S15':'households','S11':'nonfinancial_firms','S12':'financial'}
    wide=wide.rename(columns=names)
    for col in names.values():
        if col not in wide:wide[col]=np.nan
    wide['domestic']=wide.domestic.fillna(wide.debt-wide.foreign)
    wide['domestic_noncb']=wide.domestic-wide.cb
    wide['financial']=wide.financial.fillna(wide.banks+wide.other_financial+wide.cb)
    wide['nonfinancial']=wide.nonfinancial.fillna(wide.domestic-wide.financial)
    wide['source']='Eurostat'
    f=pd.read_csv(P/'data/processed/fhl_holdings.csv',float_precision='round_trip')
    f['country']=f.Country_Code.map(ISO2);f=f[f.country.notna()].copy();f['year']=f.Year.astype(int)
    f=f.set_index(['country','year'])
    ff=pd.DataFrame(index=f.index)
    for a,b in [('debt','total_gdp'),('domestic','domestic_gdp'),('foreign','foreign_gdp'),('cb','central_bank_gdp'),('banks','domestic_bank_gdp'),('domestic_noncb','domestic_private_gdp')]:ff[a]=f[b]
    ff['source']='FHL'
    overlap=wide.join(ff,how='inner',lsuffix='_eurostat',rsuffix='_FHL')
    overlap.to_csv(OUT/'holdings_source_overlap.csv')
    # Do not patch individual sectors between data systems. Pick a complete
    # source row, preserving the identity of the full three-stock decomposition.
    complete_cols=['debt','foreign','cb','domestic_noncb']
    ee=wide.dropna(subset=complete_cols).copy();ff=ff.dropna(subset=complete_cols)
    selected=pd.concat([ee,ff.loc[~ff.index.isin(ee.index)]],sort=False).sort_index()
    identity=selected.domestic_noncb+selected.cb+selected.foreign-selected.debt
    assert (identity.abs()<.31).all()
    for col in complete_cols:
        assert (selected[col]>=-.15).all(),(col,selected.loc[selected[col]<-.15])
        selected.loc[(selected[col]<0)&(selected[col]>=-.15),col]=0.
    selected['holdings_year']=selected.index.get_level_values('year')
    selected.to_csv(OUT/'holdings_annual_selected.csv')
    wide.to_csv(OUT/'holdings_annual_eurostat.csv')
    ff.to_csv(OUT/'holdings_annual_FHL.csv')
    # Actual joint holder x ORIGINAL-maturity cells, without making a
    # holder-by-remaining-maturity assumption.
    j=raw[(raw.na_item=='GD') & raw.sector2.isin(['S1_S2','S11_S14_S15','S12','S2']) & raw.maturity.isin(['Y_LE1','Y_GT1'])]
    j=j.pivot_table(index=['country','year'],columns=['sector2','maturity'],values='value')
    joint=pd.DataFrame(index=j.index)
    for m,pre in [('Y_LE1','short'),('Y_GT1','long')]:
        for sec,label in [('S1_S2','total'),('S11_S14_S15','nonfinancial'),('S12','financial'),('S2','foreign')]:
            joint[pre+'_'+label]=j[(sec,m)] if (sec,m) in j else np.nan
    joint=joint.dropna(subset=[a+'_'+b for a in ['short','long'] for b in ['nonfinancial','financial','foreign']])
    for pre in ['short','long']:
        total=joint[[pre+'_'+b for b in ['nonfinancial','financial','foreign']]].sum(axis=1)
        assert ((joint[pre+'_total']-total).abs().dropna()<.41).all()
        joint[pre+'_total']=joint[pre+'_total'].fillna(total)
    joint.to_csv(OUT/'joint_original_maturity.csv')
    return selected.reset_index(),ee.reset_index(),ff.reset_index(),joint.reset_index()

def maturity():
    x=pd.ExcelFile(RAW/'maturity_summary.xlsx');rows=[]
    rename={'UK':'GB','AU':'AU'}
    for sheet in x.sheet_names:
        a=pd.read_excel(x,sheet_name=sheet,header=None).iloc[2:].copy()
        a.iloc[:,1:55]=a.iloc[:,1:55].apply(pd.to_numeric,errors='coerce')
        for _,r in a.iterrows():
            if pd.isna(r.iloc[0]):continue
            period=pd.Period(pd.Timestamp(r.iloc[0]),'Q');total=float(r.iloc[1]);bins=r.iloc[2:21].astype(float).values
            assert np.isclose(bins.sum(),total,rtol=1e-8,atol=1.)
            rows.append(dict(country=rename.get(sheet,sheet),quarter=str(period),q=period.ordinal,
                             refinance_share=float(bins[:4].sum()/total),maturity_years=float(r.iloc[41]),
                             floating_share=float(r.iloc[48]/total),short_yield=float(r.iloc[51]),long_yield=float(r.iloc[52]),
                             maturity_source='DeGraeveMazzolini',maturity_period=str(period)))
    dg=pd.DataFrame(rows);dg.to_csv(OUT/'maturity_quarterly_DGM.csv',index=False)
    r=euro('rmd_all');r['year']=r.time.astype(int)
    rr=r.pivot_table(index=['country','year'],columns=['na_item','maturity'],values='value')
    e=pd.DataFrame(index=rr.index)
    e['due_within_year']=rr[('GD','Y_LE1')]
    total=rr[('GD','TOTAL')]
    # A missing reported total can be recovered only from observed disjoint
    # remaining-maturity bins, never from a currency proxy.
    total=total.fillna(rr[('GD','Y_LE1')]+rr[('GD','Y_GT1')])
    e['refinance_share']=e.due_within_year/total
    e['variable_long_share']=rr[('GD_VAR','Y_GT1')]/total
    e['repricing_proxy_share']=e.refinance_share+e.variable_long_share
    e['maturity_source']='EurostatRMD';e['maturity_period']=e.index.get_level_values('year').astype(str)
    av=euro('rmd_average_all');av=av[(av.na_item=='GD') & (av.maturity=='TOTAL')].copy();av['year']=av.time.astype(int)
    av=av.set_index(['country','year']).value
    e['maturity_years']=av
    assert e.refinance_share.dropna().between(0,1.02).all()
    e.to_csv(OUT/'maturity_annual_eurostat.csv')
    return dg,e.reset_index()

def series_q(name,filters=None):
    d=euro(name)
    if filters:
        for k,v in filters.items():d=d[d[k]==v]
    d['period']=pd.PeriodIndex(d.time.str.replace('-','',regex=False),freq='Q')
    return d.set_index(['country','period']).value

def macro_quarterly():
    gdp=series_q('gdp_quarterly_all');idx=pd.MultiIndex.from_product([sorted(gdp.index.get_level_values(0).unique()),pd.period_range('1995Q1','2026Q2',freq='Q')],names=['country','period'])
    d=pd.DataFrame(index=idx);d['gdp']=gdp
    d['consumption']=series_q('consumption_quarterly_all');d['investment']=series_q('investment_quarterly_all')
    hm=euro('hicp_current_monthly');hm['month']=pd.PeriodIndex(hm.time,freq='M');hm['period']=hm.month.dt.asfreq('Q')
    h=hm.groupby(['country','period']).value.agg(['mean','count']);d['prices']=h['mean'].where(h['count']==3)
    f=euro('fiscal_quarterly_all');f['period']=pd.PeriodIndex(f.time.str.replace('-','',regex=False),freq='Q')
    f=f.pivot_table(index=['country','period'],columns='na_item',values='value')
    for name,code in [('interest','D41PAY'),('interest_received','D41REC'),('balance','B9')]:d[name]=f[code]
    d['net_interest']=d.interest-d.interest_received;d['primary_balance']=d.balance+d.net_interest
    for col in ['gdp','prices','consumption','investment']:
        d['log_'+col]=100*np.log(d[col].where(d[col]>0))
    return d.reset_index()


def shocks():
    m=pd.read_csv(RAW/'shocks_ecb_mpd_me_m.csv',float_precision='round_trip')
    m['period']=pd.PeriodIndex.from_fields(year=m.year,month=m.month,freq='M')
    m=m.set_index('period')
    for c in ['MP_median','CBI_median','MP_pm','CBI_pm','pc1_hf']:m[c]=m[c]/.1
    q=m.groupby(m.index.asfreq('Q')).agg({c:'sum' for c in ['MP_median','CBI_median','MP_pm','CBI_pm','pc1_hf']})
    counts=m.groupby(m.index.asfreq('Q')).size();q=q[counts==3]
    m.to_csv(OUT/'shocks_monthly.csv');q.to_csv(OUT/'shocks_quarterly.csv')
    return m,q

def attach(d,holdings,joint,dg,rm,shock,freq):
    d['country']=country(d.country);d['year']=d.period.dt.year;d['hold_year']=d.year-1
    d=d.merge(holdings.rename(columns={'year':'hold_year'}),on=['country','hold_year'],how='left',validate='many_to_one')
    d=d.merge(joint.rename(columns={'year':'hold_year'}),on=['country','hold_year'],how='left',validate='many_to_one',suffixes=('','_joint'))
    for c in ['MP_median','CBI_median','MP_pm','CBI_pm','pc1_hf']:d[c]=d.period.map(shock[c])
    if freq=='Q':
        d['maturity_q']=d.period.map(lambda x:x.ordinal-1)
    else:
        # At every monthly announcement use a completed previous quarter,
        # preventing within-quarter maturity information from leaking forward.
        d['maturity_q']=d.period.map(lambda x:x.asfreq('Q').ordinal-1)
    dg=dg.rename(columns={'q':'maturity_q'})
    d=d.merge(dg.drop(columns=['quarter']),on=['country','maturity_q'],how='left',validate='many_to_one')
    rm=rm.rename(columns={'year':'hold_year'})
    d=d.merge(rm,on=['country','hold_year'],how='left',validate='many_to_one',suffixes=('','_annual'))
    for c in ['refinance_share','maturity_source','maturity_period','maturity_years']:
        d[c]=d[c].fillna(d[c+'_annual'])
    d['ea_member']=d.apply(lambda r: r.period.asfreq('Q')>=EA_ENTRY[r.country] if r.country in EA_ENTRY else False,axis=1)
    d['source_group']=d.country+'_'+d.source.fillna('missing')+'_'+d.maturity_source.fillna('missing')
    d['time_index']=d.period.map(lambda x:x.ordinal)
    d['season']=d.period.dt.quarter if freq=='Q' else d.period.dt.month
    d['period']=d.period.astype(str)
    assert not d.duplicated(['country','period']).any()
    return d.sort_values(['country','time_index'])


