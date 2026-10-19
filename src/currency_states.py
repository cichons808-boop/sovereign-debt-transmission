"""Pre-shock FX-denomination, trade and exchange-regime sensitivity grid.

No nonresident stock is used as an FX-denomination proxy. FX shares describe
government securities, not all government liabilities. Fixed country-specific
sources avoid manufacturing currency-share changes at a source splice.
"""
import json,gzip
import numpy as np
import pandas as pd
from pathlib import Path
from local_projection import P,DATA,RES,prepared,fit
from macro_data import ISO2
from international_data import external_controls
from creditor_sectors import prepare

EM=set('BR CL HU IN MX PL'.split())

def build_states():
    raw=json.loads((P/'data/raw/wdi_trade_openness.json').read_text())
    assert raw[0]['pages']==1
    trade=pd.DataFrame([dict(country=ISO2.get(r['countryiso3code']),hold_year=int(r['date']),trade_openness=r['value']) for r in raw[1]])
    # Stable (2021) release, explicitly without extending its endpoint.
    x=pd.read_excel(P/'data/raw/irr_regime_2021.xlsx',sheet_name='Coarse',header=None)
    labels=x.iloc[5].astype(str).str.strip()
    aliases={'AU':'Australia','BR':'Brazil','CA':'Canada','CH':'Switzerland','CL':'Chile','GB':'Kingdom',
             'HU':'Hungary','IN':'India','IL':'Israel','JP':'Japan','KR':'Korea','MX':'Mexico','NO':'Norway',
             'NZ':'Zealand','PL':'Poland','SE':'Sweden','US':'States'}
    rr=[]
    for c,label in aliases.items():
        matches=np.flatnonzero(labels.eq(label));assert len(matches)==1,(c,label,matches)
        z=x.iloc[7:,[1,int(matches[0])]].copy();z.columns=['month','regime']
        z=z[z.month.astype(str).str.match(r'^\d{4}M12$')]
        z['hold_year']=z.month.str[:4].astype(int);z['country']=c
        z['regime']=pd.to_numeric(z.regime,errors='coerce')
        rr.append(z[['country','hold_year','regime']])
    regimes=pd.concat(rr,ignore_index=True)
    # DGM same-portfolio currency data, for the nine countries with long
    # remaining-maturity histories; verify the denomination identity first.
    fx=[];catalog=[]
    for sheet in ['AU','CA','CH','UK','JP','NO','NZ','SE','US']:
        a=pd.read_excel(P/'data/raw/maturity_summary.xlsx',sheet_name=sheet,header=None).iloc[2:]
        t=pd.to_numeric(a.iloc[:,1]);local=pd.to_numeric(a.iloc[:,44]);foreign=pd.to_numeric(a.iloc[:,45])
        assert np.max(np.abs(local+foreign-t)/t)<1e-10
        q=pd.PeriodIndex(pd.to_datetime(a.iloc[:,0]),freq='Q')
        country='GB' if sheet=='UK' else sheet
        g=pd.DataFrame(dict(country=country,quarter=q,fx_share=(foreign/t).to_numpy(),
                            fx_source='DGM_marketable_face'))
        g=g[g.quarter.dt.quarter.eq(4)].copy();g['hold_year']=g.quarter.dt.year
        fx.append(g[['country','hold_year','fx_share','fx_source']])
        catalog.append(dict(country=country,source='DGM_marketable_face',sector='source marketable portfolio',
                            valuation='face',first=int(g.hold_year.min()),last=int(g.hold_year.max()),years=len(g)))
    # Retain DGM separately. The grid uses one common long-term government-
    # bond definition from the enhanced annual BIS C4 data. In particular,
    # Mexico's quarterly total starts later than its foreign-currency leg;
    # annual C4 has a consistent domestic-plus-foreign denominator since 2005.
    dgm=pd.concat(fx,ignore_index=True).rename(columns={'fx_share':'fx_share_DGM','fx_source':'fx_source_DGM'})
    b=pd.read_csv(DATA/'bis_currency_extract.csv.gz',dtype=str,keep_default_na=False)
    b=b[b.FREQ.eq('A') & b.COUNTERPART_AREA.eq('XW') & b.COUNTERPART_SECTOR.eq('S1') &
        b.CONSOLIDATION.eq('N') & b.ACCOUNTING_ENTRY.eq('L') & b.STO.eq('LE') &
        b.INSTR_ASSET.eq('F3') & b.MATURITY.eq('L') & b.UNIT_MEASURE.eq('USD') &
        b.CUST_BREAKDOWN.eq('_T') & b.CURRENCY_DENOM.isin(['XDC','X1'])]
    times=[c for c in b if c.isdigit()]
    fx=[];catalog=[]
    for country,g in b.groupby('REF_AREA'):
        candidates=[]
        for (sector,valuation),gg in g.groupby(['REF_SECTOR','VALUATION']):
            if set(gg.CURRENCY_DENOM)!= {'XDC','X1'}:continue
            assert not gg.CURRENCY_DENOM.duplicated().any()
            z=gg.set_index('CURRENCY_DENOM')[times].apply(pd.to_numeric,errors='coerce').T
            z['fx_share']=z['X1']/(z['XDC']+z['X1'])
            z=z[z.fx_share.notna() & (z['XDC']+z['X1']).gt(0)]
            assert z.fx_share.between(0,1+1e-9).all()
            n_history=int(((z.index>='1999')&(z.index<='2018')).sum())
            candidates.append((sector=='S13',n_history,{'N':2,'F':1,'M':0}[valuation],sector,valuation,z))
        if not candidates:continue
        _,n_history,_,sector,valuation,z=max(candidates,key=lambda r:r[:3])
        z['country']=country;z['hold_year']=z.index.astype(int)
        z['fx_source']='BIS_C4_'+sector+'_'+valuation
        fx.append(z[['country','hold_year','fx_share','fx_source']].reset_index(drop=True))
        catalog.append(dict(country=country,source='BIS_C4_annual_long_term_all_markets',sector=sector,valuation=valuation,
                            first=int(z.hold_year.min()),last=int(z.hold_year.max()),years=len(z),overlap_1999_2018=n_history))
    fx=pd.concat(fx,ignore_index=True);assert not fx.duplicated(['country','hold_year']).any()
    fx=fx.merge(dgm,on=['country','hold_year'],how='outer',validate='one_to_one')
    state=trade.merge(regimes,on=['country','hold_year'],how='outer',validate='one_to_one').merge(fx,on=['country','hold_year'],how='outer',validate='one_to_one')
    state.to_csv(DATA/'currency_states.csv',index=False)
    pd.DataFrame(catalog).to_csv(DATA/'currency_source_selection.csv',index=False)
    return state



