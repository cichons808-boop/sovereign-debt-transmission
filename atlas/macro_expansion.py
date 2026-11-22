"""Worldwide observed quarterly GDP and three-observed-month CPI averages."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pycountry

from .data import AUDIT,PROCESSED,URLS,country_metadata,fetch,save_csv
from .reconstruct import read_sdmx

URLS.update({
    'imf_qnea_real_gdp_all.xml':'https://api.imf.org/external/sdmx/2.1/data/IMF.STA,QNEA,7.0.0/.B1GQ.Q...Q?format=csvfile',
    'imf_cpi_headline_srp_monthly.xml':'https://api.imf.org/external/sdmx/2.1/data/IMF.STA,CPI,5.0.0/.CPI._T.SRP_IX.M?format=csvfile',
    'imf_cpi_headline_ix_monthly.xml':'https://api.imf.org/external/sdmx/2.1/data/IMF.STA,CPI,5.0.0/.CPI._T.IX.M?format=csvfile',
})


def run():
    countries=country_metadata();iso={c.alpha_3 for c in pycountry.countries}
    gdp=read_sdmx(fetch('imf_qnea_real_gdp_all.xml'))
    assert gdp.DERIVATION_TYPE.eq('O').all()
    gdp['country']=gdp.COUNTRY;gdp=gdp[gdp.country.isin(iso)].copy()
    gdp['period']=gdp.TIME_PERIOD.str.replace('-Q','Q',regex=False)
    gdp['gdp_value']=pd.to_numeric(gdp.OBS_VALUE,errors='coerce')
    gdp['gdp_source']='IMF_QNEA_B1GQ_constant_XDC_'+gdp.S_ADJUSTMENT
    gdp['gdp_seasonal_adjustment']=gdp.S_ADJUSTMENT
    options=gdp.dropna(subset=['gdp_value']).groupby(['country','gdp_source','gdp_seasonal_adjustment']).agg(
        n=('gdp_value','size'),first=('period','min'),last=('period','max')).reset_index()
    options['sa_preference']=options.gdp_seasonal_adjustment.ne('SA').astype(int)
    chosen=options.sort_values(['country','last','sa_preference','n'],ascending=[True,False,True,False]).drop_duplicates('country')
    gdp=gdp.merge(chosen[['country','gdp_source']],on=['country','gdp_source'],validate='many_to_one')
    assert not gdp.duplicated(['country','period']).any()
    cpi=[]
    for name in ['imf_cpi_headline_srp_monthly.xml','imf_cpi_headline_ix_monthly.xml']:
        d=read_sdmx(fetch(name));d['country']=d.COUNTRY
        d=d[d.country.isin(iso)].copy()
        d['month']=pd.PeriodIndex(d.TIME_PERIOD.str.replace('-M','-',regex=False),freq='M')
        d['cpi_value']=pd.to_numeric(d.OBS_VALUE,errors='coerce')
        d['cpi_source']='IMF_CPI_headline_'+d.TYPE_OF_TRANSFORMATION
        # Retain only directly reported observations and explicit provider
        # rebasing; any other derivation class is recorded rather than inferred.
        cpi.append(d)
    cpi=pd.concat(cpi,ignore_index=True)
    opts=cpi.dropna(subset=['cpi_value']).groupby(['country','cpi_source']).agg(
        n=('cpi_value','size'),first=('month','min'),last=('month','max')).reset_index()
    opts['standardized_preference']=opts.cpi_source.ne('IMF_CPI_headline_SRP_IX').astype(int)
    selected=opts.sort_values(['country','last','n','standardized_preference'],
        ascending=[True,False,False,True]).drop_duplicates('country')
    cpi=cpi.merge(selected[['country','cpi_source']],on=['country','cpi_source'],validate='many_to_one')
    assert not cpi.duplicated(['country','month']).any()
    cpi['period']=cpi.month.dt.asfreq('Q').astype(str)
    prices=cpi.groupby(['country','period','cpi_source']).agg(cpi_level=('cpi_value','mean'),
        observed_months=('cpi_value','count')).reset_index()
    prices.loc[prices.observed_months.ne(3),'cpi_level']=np.nan
    entities=sorted(set(gdp.country)|set(prices.country))
    # Fully observed source calendars, including countries with CPI but no GDP.
    idx=pd.MultiIndex.from_product([entities,pd.period_range('1960Q1','2026Q3',freq='Q').astype(str)],
                                   names=['country','period'])
    out=pd.DataFrame(index=idx).reset_index().merge(gdp[['country','period','gdp_value','gdp_source',
        'gdp_seasonal_adjustment']],on=['country','period'],how='left',validate='one_to_one')
    out=out.merge(prices,on=['country','period'],how='left',validate='one_to_one')
    out['log_gdp']=100*np.log(out.gdp_value.where(out.gdp_value>0))
    out['log_cpi']=100*np.log(out.cpi_level.where(out.cpi_level>0))
    index=pd.PeriodIndex(out.period,freq='Q')
    out['time']=index.year*4+index.quarter-1;out['year']=index.year;out['season']=index.quarter
    out=out.merge(countries,on='country',how='left',validate='many_to_one')
    save_csv(out,PROCESSED/'global_native_quarterly_macro.csv.gz')
    save_csv(options,AUDIT/'quarterly_gdp_source_candidates.csv')
    save_csv(chosen,AUDIT/'quarterly_gdp_selected.csv')
    save_csv(selected.assign(first=selected['first'].astype(str),last=selected['last'].astype(str)),
             AUDIT/'quarterly_cpi_selected_monthly_source.csv')
    deriv=cpi.groupby(['cpi_source','DERIVATION_TYPE'],dropna=False).size().rename('n').reset_index() if 'DERIVATION_TYPE'in cpi else pd.DataFrame()
    save_csv(deriv,AUDIT/'cpi_observation_derivation_classes.csv')
    summary=out.groupby('country').agg(gdp_quarters=('log_gdp','count'),cpi_quarters=('log_cpi','count')).reset_index()
    save_csv(summary,AUDIT/'worldwide_quarterly_macro_coverage.csv')
    print('observed worldwide macro',len(entities),'economies',out.loc[out.log_gdp.notna(),'country'].nunique(),
          'GDP',out.loc[out.log_cpi.notna(),'country'].nunique(),'CPI',flush=True)
    return out


if __name__=='__main__':run()
