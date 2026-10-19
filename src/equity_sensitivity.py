"""Official US equity-price proxy sensitivity on exactly matched samples."""
from pathlib import Path
import json,hashlib,urllib.request
import numpy as np
import pandas as pd
from specification import setup,EM
from local_projection import fit

P=Path(__file__).resolve().parents[1];D=P/'data/processed';R=P/'results';RAW=P/'data/raw/fiscal_transmission'

def main():
    url='https://fred.stlouisfed.org/graph/?g=1&id=SPASTT01USM661N&cosd=1990-01-01&coed=2026-10-18'
    # Standard FRED CSV endpoint; retain the exact downloaded bytes.
    url='https://fred.stlouisfed.org/graph/fredgraph.csv?id=SPASTT01USM661N&cosd=1990-01-01&coed=2026-10-18'
    path=RAW/'us_equity_oecd_fred.csv'
    if not path.is_file():raise FileNotFoundError(path)
    x=pd.read_csv(path);x['month']=pd.to_datetime(x.iloc[:,0]).dt.to_period('M');x['value']=pd.to_numeric(x.iloc[:,1],errors='coerce')
    assert x.value.gt(0).sum()>300
    x['period']=x.month.dt.asfreq('Q');q=x.groupby('period').agg(value=('value','last'),months=('value','count'))
    q=q[q.months.eq(3)].copy();q=q.reindex(pd.period_range(q.index.min(),q.index.max(),freq='Q'))
    q['official_equity_state']=100*np.log(q.value/q.value.shift(1)).shift(1)/10
    q.reset_index(names='period').to_csv(D/'fiscal_official_equity_state.csv',index=False)
    own=pd.read_csv(D/'fiscal_panel_external.csv.gz',float_precision='round_trip');own['ea_member']=own.ea_member.astype(bool)
    own.loc[own.country.eq('US'),['Fed_MP','Fed_CBI']]=0.
    ea=pd.read_csv(D/'fiscal_panel_ea.csv.gz',float_precision='round_trip');ea['ea_member']=ea.ea_member.astype(bool)
    rows=[];fits=[]
    for sample in ['ea','advanced','emerging']:
        base=(ea if sample=='ea' else own).copy()
        if sample=='advanced':base['ea_member']&=~base.country.isin(EM)
        if sample=='emerging':base['ea_member']&=base.country.isin(EM)
        alternative=base.copy();alternative['spy_state']=pd.PeriodIndex(base.period,freq='Q').map(q.official_equity_state)
        d,ex,names=setup(alternative,'rollover',sample!='ea');b,be,bn=setup(base,'rollover',sample!='ea')
        for out in ['log_gdp','log_prices']:
            for h in [4,8,12]:
                f,v=fit(d,names,'rollover',out,h,additional_nuisance=ex,return_validation=True)
                matched=b.copy();matched['ea_member']&=matched.index.isin(v['g'].index)
                fb,vb=fit(matched,bn,'rollover',out,h,additional_nuisance=be,return_validation=True)
                assert np.array_equal(v['g'].index,vb['g'].index)
                for ff,proxy in [(fb,'SPY adjusted ETF'),(f,'OECD US equity index')]:
                    ff.update(sample=sample,proxy=proxy);fits.append(ff)
                    for e in ff['estimates']:
                        if e['term'] in ['domestic_noncb','domestic_noncb_x_refinancing']:
                            rows.append({k:ff[k] for k in ['sample','proxy','outcome','horizon','n','p','countries']}|e)
    pd.DataFrame(rows).to_csv(R/'fiscal_equity_proxy.csv',index=False)
    (R/'fiscal_equity_proxy.json').write_text(json.dumps(fits,indent=2)+'\n')
    print(pd.DataFrame(rows).query('sample=="advanced" and outcome=="log_gdp" and horizon==8').to_string(index=False))

if __name__=='__main__':main()
