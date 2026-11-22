"""Separate worldwide external Fed/ECB experiments; never domestic substitutes."""
import numpy as np
import pandas as pd

from .data import AUDIT,PROCESSED,country_metadata,prepare_lags,save_csv
from .reconstruct import annual_macro


def run():
    macro=annual_macro(country_metadata())
    quarterly=pd.read_csv(PROCESSED/'global_native_quarterly_macro.csv.gz',low_memory=False)
    panels=[];coverage=[]
    for issuer,cutoff in [('USA',2025),('ECB',2025)]:
        events=pd.read_csv(PROCESSED/f'fresh_{issuer}_event_shocks.csv',parse_dates=['date'])
        events['year']=events.date.dt.year
        years=events.groupby('year').mp_median.agg(['sum','count','size'])
        # First and terminal calendar years are not presumed complete. For USA,
        # 2025 is the last full year; for ECB current GC_ME data end June 2026.
        first=events.year.min()+1
        years=years[(years.index>=first)&(years.index<=cutoff)&years['count'].eq(years['size'])]
        source=years['sum']
        a=macro.copy();a['shock_raw']=a.year.map(source);a['shock']=a.shock_raw/.1
        a['normalization_scale']=.1;a['issuer']=issuer;a['inherited']=False
        a['shared_union_shock']=True;a['frequency']='A'
        a['source_method']='external_reconstructed_intraday_MP_component'
        a['shock_unit']='10bp_'+issuer+'_factor_cumulative_annual_not_domestic_policy'
        a['universe']='W_external_'+issuer+'_annual'
        a['estimand']='external_'+issuer+'_spillover'
        # Own issuer countries and member-country domestic ECB observations are
        # removed from this explicitly external experiment.
        if issuer=='USA':a.loc[a.country.eq('USA'),'shock']=np.nan
        else:
            from .data import EA_ENTRY
            for c,t in EA_ENTRY.items():a.loc[a.country.eq(c)&a.year.ge(t//4),'shock']=np.nan
        a=prepare_lags(a);save_csv(a,PROCESSED/(a.universe.iloc[0]+'.csv.gz'));panels.append(a)
        qs=pd.read_csv(PROCESSED/f'fresh_{issuer}_mp_median_complete_quarters.csv')
        q=quarterly.merge(qs[['period','shock_raw']],on='period',how='left',validate='many_to_one')
        q['shock']=q.shock_raw/.1;q['normalization_scale']=.1;q['issuer']=issuer
        q['inherited']=False;q['shared_union_shock']=True;q['frequency']='Q'
        q['source_method']='external_reconstructed_intraday_MP_component'
        q['shock_unit']='10bp_'+issuer+'_factor_cumulative_quarterly_not_domestic_policy'
        q['universe']='W_external_'+issuer+'_quarterly';q['estimand']='external_'+issuer+'_spillover'
        if issuer=='USA':q.loc[q.country.eq('USA'),'shock']=np.nan
        else:
            for c,t in EA_ENTRY.items():q.loc[q.country.eq(c)&q.time.ge(t),'shock']=np.nan
        q=prepare_lags(q);save_csv(q,PROCESSED/(q.universe.iloc[0]+'.csv.gz'));panels.append(q)
        for d in [a,q]:
            obs=d[d.shock.notna()]
            coverage.append(dict(universe=d.universe.iloc[0],countries_with_shock=obs.country.nunique(),
                independent_issuers=1,shock_first=obs.period.min(),shock_last=obs.period.max(),
                countries_with_gdp=obs.loc[obs.log_gdp.notna(),'country'].nunique(),
                countries_with_cpi=obs.loc[obs.log_cpi.notna(),'country'].nunique(),
                identification='external_spillover_not_domestic_response'))
    save_csv(pd.DataFrame(coverage),AUDIT/'worldwide_external_shock_coverage.csv')
    print(pd.DataFrame(coverage).to_string(index=False),flush=True)
    return panels


if __name__=='__main__':run()
