"""External comparison using each non-EA country's own policy surprise.

Orthogonalized Bolhuis-Das-Yao shocks have basis-point units and use a
poor-man monetary/information split; they are not pooled with the JK median
ECB shock. Global policy spillovers are explicitly controlled.
"""
import json,gzip,hashlib
from datetime import datetime,timezone
import numpy as np
import pandas as pd
from macro_data import ISO2,ISO3,EA_ENTRY,attach
from local_projection import load_panel,prepared,fit,RES,P,DATA

def macro():
    manifests=[]
    for name in ['macro_sources.json']:
        manifests+=json.loads((P/'data'/name).read_text())
    records=[r for r in manifests if r['status']=='ok'];rows=[];audit=[]
    for c in sorted(set(r['country'] for r in records)):
        gg=[r for r in records if r['country']==c and r['kind']=='real_gdp_growth']
        levels=[r for r in records if r['country']==c and r['kind']=='real_gdp']
        pp=[r for r in records if r['country']==c and r['kind'].startswith('CPI')]
        if (not gg and not levels) or not pp:continue
        # Prefer the freshest real growth series; it is an observed quarterly
        # volume-growth measure, chain-linked here to an arbitrary log level.
        grow=bool(gg);rg=max(gg or levels,key=lambda x:x['last']);rp=max(pp,key=lambda x:x['last'])
        idx=pd.period_range('1995Q1','2026Q2',freq='Q');d=pd.DataFrame(index=idx)
        def series(r):
            a=pd.read_csv(P/'data/raw'/r['filename']);a['period']=pd.PeriodIndex(pd.to_datetime(a.iloc[:,0]),freq='Q')
            assert not a.period.duplicated().any()
            return pd.to_numeric(a.iloc[:,1],errors='coerce').set_axis(a.period)
        s=series(rg).reindex(idx);pr=series(rp).reindex(idx)
        def chain(s):
            # Use the longest uninterrupted observed segment; never bridge a
            # missing quarter by treating it as zero real growth.
            valid=s.notna();block=valid.ne(valid.shift(fill_value=False)).cumsum()
            sizes=s[valid].groupby(block[valid]).size();longest=sizes.idxmax();mask=valid&(block==longest)
            out=pd.Series(np.nan,index=idx);out.loc[mask]=100*np.log1p(s.loc[mask]/100).cumsum()
            return out
        logg=chain(s) if grow else 100*np.log(s.where(s>0))
        logp=chain(pr) if rp['kind']=='CPI_growth' else 100*np.log(pr.where(pr>0))
        d['log_gdp']=logg;d['log_prices']=logp;d['country']=c;d['period']=idx
        rows.append(d.reset_index(drop=True));audit.append(dict(country=c,gdp_series=rg['series'],gdp_kind=rg['kind'],gdp_first=str(logg.first_valid_index()),gdp_last=str(logg.last_valid_index()),
            price_series=rp['series'],price_kind=rp['kind'],price_first=str(logp.first_valid_index()),price_last=str(logp.last_valid_index()),
            gdp_transformation='100*cumsum(log(1+qoq_growth/100)); arbitrary base cancels in LP differences' if grow else '100*log(real GDP volume)'))
    (DATA/'global_macro_selection.csv').write_text(pd.DataFrame(audit).to_csv(index=False))
    return pd.concat(rows,ignore_index=True)

def shocks():
    x=pd.read_excel(P/'data/raw/bolhuis_hf.xlsx',sheet_name='data');x['period']=pd.PeriodIndex(pd.to_datetime(x.market_Date),freq='Q')
    frames=[];audit=[]
    for iso,g in x.groupby('iso3'):
        start,end=g.period.min(),g.period.max()
        # Drop the first potentially partial quarter. Retain the last only
        # when the file reaches its last calendar month (US ends May 2022).
        first=start+1;last=end if pd.to_datetime(g.market_Date).max().month%3==0 else end-1
        idx=pd.period_range(first,last,freq='Q');z=g.groupby('period')[['orth_MP1','orth_CBI1']].sum().reindex(idx,fill_value=0)/10.
        z=z.rename(columns={'orth_MP1':'MP_median','orth_CBI1':'CBI_median'})
        z['MP_pm']=z.MP_median;z['CBI_pm']=z.CBI_median;z['pc1_hf']=z.MP_median+z.CBI_median
        z['issuer']=iso;z['period']=idx;frames.append(z.reset_index(drop=True));audit.append(dict(issuer=iso,first=str(first),last=str(last),quarters=len(idx),first_event=str(g.market_Date.min()),last_event=str(g.market_Date.max())))
    (DATA/'global_shock_coverage.csv').write_text(pd.DataFrame(audit).to_csv(index=False))
    return pd.concat(frames,ignore_index=True)

def build():
    m=macro();s=shocks();base,r0,_=load_panel('Q')
    # Attach the same actually observed ownership and maturity data to new
    # macro outcomes. Imported macro series are not spliced into EA outcomes.
    h=pd.read_csv(DATA/'holdings_annual_selected.csv');j=pd.read_csv(DATA/'joint_original_maturity.csv');dg=pd.read_csv(DATA/'maturity_quarterly_DGM.csv');rm=pd.read_csv(DATA/'maturity_annual_eurostat.csv')
    # attach() needs a common shock lookup; replace it immediately with own
    # issuer-specific observations below, before any regression preparation.
    dummy=s[s.issuer=='DEU'].set_index('period')[['MP_median','CBI_median','MP_pm','CBI_pm','pc1_hf']]
    new=attach(m.copy(),h,j,dg,rm,dummy,'Q')
    new['period']=new.period.astype(str);new['issuer']=new.country.map(ISO3)
    new=new.drop(columns=['MP_median','CBI_median','MP_pm','CBI_pm','pc1_hf'])
    ss=s.copy();ss['period']=ss.period.astype(str)
    new=new.merge(ss,on=['issuer','period'],how='left',validate='many_to_one')
    new['ea_member']=True  # Eligibility here means an own-policy observation.
    # For a genuinely separate external test keep non-EA monetary issuers.
    new=new[~new.country.isin(EA_ENTRY)].copy()
    # Common macro controls are available globally. Fiscal controls are not
    # silently imputed or used to remove otherwise eligible countries.
    new=new.drop(columns=[c for c in new if c.endswith('_lag') or c.startswith('growth_l') or c.startswith('inflation_l')],errors='ignore')
    new=new.sort_values(['country','time_index']);g=new.groupby('country',sort=False)
    dy=g.log_gdp.diff();dp=g.log_prices.diff()
    for lag in range(1,5):
        new[f'growth_l{lag}']=dy.groupby(new.country).shift(lag);new[f'inflation_l{lag}']=dp.groupby(new.country).shift(lag)
    new['growth_state']=g.log_gdp.shift(1)-g.log_gdp.shift(5);new['inflation_state']=g.log_prices.shift(1)-g.log_prices.shift(5)
    # Centering fixed at the EA predictor-support median to retain the same
    # reference point and units; it is not chosen from outcome fit.
    new['rollover_centered']=(new.refinance_share-r0)/.1
    new['hold_group']=new.country+'_'+new.source.fillna('missing');new['roll_group']=new.source_group
    for issuer,label in [('USA','Fed'),('DEU','ECB')]:
        external=ss[ss.issuer==issuer].set_index('period')
        new[label+'_MP']=new.period.map(external.MP_median);new[label+'_CBI']=new.period.map(external.CBI_median)
    payload=new.to_csv(index=False).encode();(DATA/'panel_global_external.csv.gz').write_bytes(gzip.compress(payload,mtime=0))
    return new,r0

def external_controls(d,names,banks=('Fed','ECB')):
    extra=[];cols={}
    for bank in banks:
        for shock in ['MP','CBI']:
            col=bank+'_'+shock
            for group in sorted(d.est_group.unique()):
                lab='external_'+col+'_'+group;cols[lab]=(d.est_group==group)*d[col];extra.append(lab)
            for name in names:
                lab='external_'+col+'_'+name;cols[lab]=d[col]*d['a_'+name];extra.append(lab)
    return pd.concat([d,pd.DataFrame(cols,index=d.index)],axis=1),extra


