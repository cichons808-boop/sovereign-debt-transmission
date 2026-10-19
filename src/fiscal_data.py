"""Quarterly creditor states, fiscal outcomes and predetermined macro conditions."""
from pathlib import Path
import gzip,json,re,zipfile
import numpy as np
import pandas as pd
from macro_data import ISO2,EA_ENTRY
from debt_sources import save

P=Path(__file__).resolve().parents[1];D=P/'data/processed';RAW=P/'data/raw/fiscal_transmission'
EM=set('BR CL CN HU IN MX PL TH'.split())

def euro(name):
    o=json.loads(gzip.decompress((RAW/name).read_bytes()));values=o['value']
    if isinstance(values,list):values={str(i):v for i,v in enumerate(values) if v is not None}
    ix=np.asarray(list(values),int);coords=np.asarray(np.unravel_index(ix,o['size'])).T
    rows={}
    for j,k in enumerate(o['id']):
        codes=o['dimension'][k]['category']['index'];codes=sorted(codes,key=codes.get) if isinstance(codes,dict) else codes
        rows[k]=np.asarray(codes)[coords[:,j]]
    rows['value']=[values[str(i)] for i in ix];a=pd.DataFrame(rows)
    a['country']=a.geo.replace({'EL':'GR','UK':'GB'});a['period']=a.time.str.replace('-Q','Q',regex=False)
    return a

def macro_states():
    z=zipfile.ZipFile(RAW/'bis_reer.zip');d=pd.read_csv(z.open(z.namelist()[0]),low_memory=False)
    d=d[d.FREQ.eq('M')&d.EER_TYPE.eq('R')&d.EER_BASKET.eq('B')]
    times=[c for c in d if re.fullmatch(r'\d{4}-\d{2}',c)]
    r=d[['REF_AREA']+times].melt(id_vars='REF_AREA',var_name='month',value_name='reer')
    r['reer']=pd.to_numeric(r.reer,errors='coerce');r['period']=pd.PeriodIndex(r.month,freq='M').asfreq('Q').astype(str)
    r=r.groupby(['REF_AREA','period']).reer.agg(['mean','count']).reset_index().rename(columns={'REF_AREA':'country'})
    r['log_reer']=100*np.log(r['mean'].where(r['count'].eq(3)&r['mean'].gt(0)))
    save(r,'fiscal_reer_quarterly.csv.gz')
    ca=[]
    for f in sorted(RAW.glob('current_account_*_fred.csv')):
        a=pd.read_csv(f);country=f.name.split('_')[2]
        a['period']=pd.PeriodIndex(pd.to_datetime(a.iloc[:,0]),freq='Q').astype(str)
        a['current_account']=pd.to_numeric(a.iloc[:,1],errors='coerce');a['country']=country
        a['ca_source']='OECD_FRED_quarterly_SA';a['ca_frequency']='Q';a['priority']=0
        ca.append(a[['country','period','current_account','ca_source','ca_frequency','priority']])
    a=euro('current_account_eurostat.json.gz');a['current_account']=a.value;a['ca_source']='Eurostat_quarterly_NSA';a['ca_frequency']='Q';a['priority']=1
    ca.append(a[['country','period','current_account','ca_source','ca_frequency','priority']])
    c=pd.concat(ca,ignore_index=True).dropna(subset=['current_account']).sort_values('priority').drop_duplicates(['country','period'])
    save(c,'fiscal_current_account_quarterly.csv.gz')
    o=json.loads(gzip.decompress((RAW/'current_account_annual_wdi.json.gz').read_bytes()));assert o[0]['pages']==1
    annual=pd.DataFrame([dict(country=ISO2.get(v['countryiso3code']),year=int(v['date'])+1,current_account_annual=v['value']) for v in o[1]])
    annual=annual.dropna(subset=['country','current_account_annual'])
    save(annual,'fiscal_current_account_annual.csv.gz')
    a=pd.read_csv(RAW/'wti_fred.csv');a['period']=pd.PeriodIndex(pd.to_datetime(a.iloc[:,0]),freq='Q').astype(str)
    a['wti']=pd.to_numeric(a.iloc[:,1],errors='coerce');w=a.groupby('period').wti.mean()
    o=json.loads((RAW/'spy_yahoo.json').read_text())['chart']['result'][0]
    a=pd.DataFrame({'date':pd.to_datetime(o['timestamp'],unit='s',utc=True).tz_localize(None),
        'spy_adjusted':o['indicators']['adjclose'][0]['adjclose']})
    a['period']=pd.PeriodIndex(a.date,freq='Q').astype(str)
    s=a.dropna().groupby('period').spy_adjusted.last()
    g=pd.concat([w,s],axis=1).sort_index()
    g['wti_return']=100*np.log(g.wti/g.wti.shift(1));g['spy_return']=100*np.log(g.spy_adjusted/g.spy_adjusted.shift(1))
    g.index.name='period';save(g.reset_index(),'fiscal_global_conditions.csv.gz')
    return r[['country','period','log_reer']],c,annual,g

def main():
    q=pd.read_csv(D/'official_imf_quarterly_all.csv.gz');q=q.dropna(subset=['country','debt','foreign','cb','domestic_noncb']).copy()
    q['imf_original_residual']=q.debt-q.foreign-q.cb-q.domestic_noncb
    assert q.imf_original_residual.abs().max()<.1
    q['domestic_noncb']=q.debt-q.foreign-q.cb
    q['domestic_nonbank']=q.domestic_noncb-q.domestic_bank
    debt=q[['country','period','debt']].rename(columns={'debt':'debt_ratio_observed'})
    e=euro('eurostat_gg_debt_quarterly.json.gz')[['country','period','value']].rename(columns={'value':'eurostat_debt'})
    debt=debt.merge(e,on=['country','period'],how='outer',validate='one_to_one')
    debt['debt_ratio_observed']=debt.eurostat_debt.combine_first(debt.debt_ratio_observed)
    z=pd.read_csv(D/'official_qpsd_observed.csv.gz')
    z=z[z.indicator.eq('DP.DOD.DECT.CR.GG.Z1')][['country','period','value']].rename(columns={'value':'qpsd_debt'})
    debt=debt.merge(z,on=['country','period'],how='outer',validate='one_to_one')
    debt['debt_ratio_observed']=debt.debt_ratio_observed.combine_first(debt.qpsd_debt)
    save(debt,'fiscal_observed_gg_debt.csv.gz')
    # Retain the actual observation quarter before advancing to the shock date.
    q['ownership_measurement_period']=q.period
    q['period']=(pd.PeriodIndex(q.period,freq='Q')+1).astype(str)
    cols=['debt','foreign','cb','domestic_noncb','foreign_official','domestic_bank','domestic_nonbank']
    q=q.rename(columns={c:c+'_quarterly' for c in cols})
    qr=q[['country','period','source','ownership_measurement_period']+[c+'_quarterly' for c in cols]].rename(columns={'source':'quarterly_source'})
    reer,ca,annual,globaldata=macro_states();coverage=[]
    for sample in ['ea','external']:
        a=pd.read_csv(D/f'official_expanded_panel_{sample}.csv.gz')
        a=a.merge(qr,on=['country','period'],how='left',validate='one_to_one')
        observed=a[[c+'_quarterly' for c in cols[:4]]].notna().all(axis=1)
        a['ownership_frequency']=np.where(observed,'Q','A')
        a['ownership_measurement_period']=a.ownership_measurement_period.where(observed,a.hold_year.astype(str)+'Q4')
        for original,new in [('debt','debt'),('foreign','foreign'),('cb','cb'),('domestic_noncb','domestic_noncb'),
                             ('foreign_official_gdp','foreign_official'),('domestic_bank_gdp','domestic_bank'),('domestic_nonbank_gdp','domestic_nonbank')]:
            a[original]=a[new+'_quarterly'].where(observed,a[original])
        a['source']=a.quarterly_source.where(observed,a.source)
        a=a.merge(debt[['country','period','debt_ratio_observed']],on=['country','period'],how='left',validate='one_to_one')
        a=a.merge(reer,on=['country','period'],how='left',validate='one_to_one')
        a=a.merge(ca[['country','period','current_account','ca_source','ca_frequency']],on=['country','period'],how='left',validate='one_to_one')
        a=a.merge(annual,on=['country','year'],how='left',validate='many_to_one')
        a=a.merge(globaldata.reset_index(),on='period',how='left',validate='many_to_one')
        a=a.sort_values(['country','time_index']).reset_index(drop=True)
        group=a.groupby('country',sort=False)
        a['debt_accumulation']=(group.debt_ratio_observed.shift(1)-group.debt_ratio_observed.shift(5))/10
        a['reer_state']=(group.log_reer.shift(1)-group.log_reer.shift(5))/10
        a['ca_state']=group.current_account.shift(1)
        a['ca_state_source']=group.ca_source.shift(1)
        a['ca_state_frequency']=group.ca_frequency.shift(1)
        fallback=a.ca_state.isna() & a.current_account_annual.notna()
        a.loc[fallback,'ca_state']=a.loc[fallback,'current_account_annual']
        a.loc[fallback,'ca_state_source']='WDI_previous_year';a.loc[fallback,'ca_state_frequency']='A'
        a['ca_state']/=5
        a['wti_state']=group.wti_return.shift(1)/10;a['spy_state']=group.spy_return.shift(1)/10
        a['hold_group']=a.country+'_'+a.source.fillna('missing')
        a['roll_group']=a.hold_group+'_'+a.maturity_source.fillna('missing')
        a['source_group']=a.roll_group
        a['policy_group']='euro_area' if sample=='ea' else np.where(a.country.isin(EM),'emerging','advanced')
        a['policy_issuer']='ECB' if sample=='ea' else a.country
        assert not a.duplicated(['country','period']).any()
        assert a.groupby('country').time_index.diff().dropna().eq(1).all()
        assert (a.debt-a.foreign-a.cb-a.domestic_noncb).abs().max()<1e-10
        save(a,f'fiscal_panel_{sample}.csv.gz')
        eligible=a[a.ea_member & a.MP_median.notna() & a.domestic_noncb.notna()]
        for (country,frequency),g in eligible.groupby(['country','ownership_frequency']):
            coverage.append(dict(sample=sample,country=country,ownership_frequency=frequency,n=len(g),first=g.period.min(),last=g.period.max(),
                ca_quarters=int(g.ca_state_frequency.eq('Q').sum()),ca_annual_states=int(g.ca_state_frequency.eq('A').sum()),
                reer_quarters=int(g.reer_state.notna().sum()),debt_outcome_quarters=int(g.debt_ratio_observed.notna().sum())))
    save(pd.DataFrame(coverage),'fiscal_quarterly_coverage.csv')
    print(pd.DataFrame(coverage).groupby(['sample','ownership_frequency']).agg(countries=('country','nunique'),rows=('n','sum')).to_string())

if __name__=='__main__':main()
