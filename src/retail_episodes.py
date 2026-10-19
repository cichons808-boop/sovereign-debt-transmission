"""Observed institutional episodes and contractual interest-rate exposure."""
from pathlib import Path
import json,re,zipfile
import numpy as np
import pandas as pd
from fiscal_data import euro
from debt_sources import save

P=Path(__file__).resolve().parents[1];D=P/'data/processed';R=P/'results';RAW=P/'data/raw/fiscal_transmission'

def main():
    rows=[]
    for c in ['BE','PT','NL','FR','ES','IT','U2']:
        for kind,label in [('L21','overnight_rate'),('L22','term_rate'),('deposits','deposit_stock')]:
            f=RAW/(f'deposits_{c}_mirror.json' if kind=='deposits' else f'mir_{c}_{kind}_mirror.json')
            o=json.loads(f.read_text())['series']['docs'][0]
            for month,value in zip(o['period'],o['value']):
                if re.fullmatch(r'\d{4}-\d{2}',month):
                    rows.append(dict(country=c,month=month,measure=label,value=pd.to_numeric(value,errors='coerce'),series=o['series_code']))
    allrows=pd.DataFrame(rows);save(allrows,'fiscal_retail_ecb_monthly.csv.gz')
    wide=allrows.pivot(index=['country','month'],columns='measure',values='value').reset_index()
    results=[]
    for country,event,benchmark in [('BE','2023-09',['FR','NL']),('PT','2023-06',['ES','IT'])]:
        e=pd.Period(event,freq='M');a=wide[wide.country.eq(country)].set_index('month')
        base=wide[wide.country.isin(benchmark)].groupby('month')[['overnight_rate','term_rate','deposit_stock']].mean()
        before='2023-07' if country=='BE' else str(e-1)
        for h in ([-1,0,3,6,12] if country=='BE' else [0,3,6,12]):
            end=str(e+h)
            for label in ['overnight_rate','term_rate','deposit_stock']:
                change=lambda v:100*np.log(v.loc[end,label]/v.loc[before,label]) if label=='deposit_stock' else v.loc[end,label]-v.loc[before,label]
                own=change(a)
                # Compare country growth rates, rather than the growth rate
                # of a mean stock that would weight large banking systems.
                ref=np.mean([change(wide[wide.country.eq(c)].set_index('month')) for c in benchmark])
                results.append(dict(country=country,event=event,baseline_month=before,horizon_months=h,measure=label,
                    before=a.loc[before,label],after=a.loc[end,label],change=own,
                    benchmark_change=ref,relative_change=own-ref,benchmark='+'.join(benchmark),
                    interpretation='Descriptive event-time change, not a causal treatment estimate'))
    pd.DataFrame(results).to_csv(R/'fiscal_retail_event_changes.csv',index=False)
    sensitivity=[]
    for before in ['2023-06','2023-07','2023-08']:
        for end in ['2023-08','2023-09','2024-03','2024-09']:
            for measure in ['term_rate','deposit_stock']:
                def delta(c):
                    z=wide[wide.country.eq(c)].set_index('month')
                    return 100*np.log(z.loc[end,measure]/z.loc[before,measure]) if measure=='deposit_stock' else z.loc[end,measure]-z.loc[before,measure]
                sensitivity.append(dict(country='BE',baseline_month=before,end_month=end,measure=measure,
                    change=delta('BE'),relative_change=delta('BE')-np.mean([delta(c) for c in ['FR','NL']]),
                    baseline_status='During subscription and anticipation' if before=='2023-08' else 'Before August announcement'))
    pd.DataFrame(sensitivity).to_csv(R/'fiscal_belgium_timing.csv',index=False)
    a=pd.read_excel(P/'data/raw/official_expansion/poland_state_treasury.xlsx',sheet_name='debt by instrument',header=None)
    positions={str(a.iloc[i,0]).strip():i for i in range(len(a))}
    assert positions['ROR bonds']==37 and positions['DOR bonds']==38
    dates=pd.to_datetime(a.iloc[1,1:],errors='coerce')
    poland=pd.DataFrame({'date':dates,'ror_million_pln':pd.to_numeric(a.iloc[37,1:],errors='coerce').values,
        'dor_million_pln':pd.to_numeric(a.iloc[38,1:],errors='coerce').values})
    poland=poland.dropna(subset=['date']);poland=poland[poland.date.ge('2022-06-01')].copy()
    poland['month']=poland.date.dt.to_period('M').astype(str)
    poland['principal_bn_pln']=(poland.ror_million_pln+poland.dor_million_pln)/1000
    poland['annual_sensitivity_100bp_bn_pln']=poland.principal_bn_pln*.01
    poland['monthly_sensitivity_100bp_million_pln']=poland.principal_bn_pln*1000*.01/12
    z=zipfile.ZipFile(RAW/'bis_policy_rates.zip');b=pd.read_csv(z.open(z.namelist()[0]),low_memory=False)
    b=b[b.FREQ.eq('M')&b.REF_AREA.eq('PL')];assert len(b)==1
    rate={c:pd.to_numeric(b.iloc[0][c],errors='coerce') for c in b if re.fullmatch(r'\d{4}-\d{2}',c)}
    poland['policy_rate']=poland.month.map(rate)
    poland['annualized_policy_component_bn_pln']=poland.principal_bn_pln*poland.policy_rate/100
    g=euro('poland_nominal_gdp.json.gz').sort_values('period');g['annual_gdp_million_pln']=g.value.rolling(4,min_periods=4).sum()
    poland['period']=poland.date.dt.to_period('Q').astype(str)
    poland=poland.merge(g[['period','annual_gdp_million_pln']],on='period',how='left',validate='many_to_one')
    poland['annual_sensitivity_100bp_percent_gdp']=poland.annual_sensitivity_100bp_bn_pln*1000/poland.annual_gdp_million_pln*100
    poland['annualized_policy_component_percent_gdp']=poland.annualized_policy_component_bn_pln*1000/poland.annual_gdp_million_pln*100
    assert poland.principal_bn_pln.gt(0).all() and not poland.month.duplicated().any()
    save(poland,'fiscal_poland_repricing_monthly.csv.gz')
    summary=dict(quarterly_panel_case_frequency='Monthly national stocks and ECB rates retained at original frequency',
        poland={year:g.iloc[-1].replace({np.nan:None}).to_dict() for year,g in poland.assign(year=poland.date.dt.year).groupby('year')},
        formula='Gross annual coupon sensitivity to +100bp = 0.01 times observed ROR+DOR principal; policy component = principal times reference rate. Neither is a measured causal GDP response or realized cash payment.',
        belgium=dict(issue_billion_eur=21.896,coupon_percent=3.3,annual_gross_coupon_billion_eur=21.896*.033,maturity='2024-09-04',
            subscription_start='2023-08-24',subscription_end='2023-09-01',settlement='2023-09-04',baseline_month='2023-07'),
        interpretation='Institutional event evidence on deposit competition and observed creditor-by-repricing exposure')
    for year,v in summary['poland'].items():v['date']=str(v['date'])
    h0=summary['poland'][2023]['principal_bn_pln'];h1=summary['poland'][2025]['principal_bn_pln']
    r0=summary['poland'][2023]['policy_rate']/100;r1=summary['poland'][2025]['policy_rate']/100
    summary['poland_2023_2025_decomposition']=dict(principal_effect=r0*(h1-h0),rate_effect=h0*(r1-r0),
        interaction=(h1-h0)*(r1-r0),total_change=h1*r1-h0*r0,
        units='PLN billion annualized reference-rate component; exact two-date product decomposition')
    assert abs(sum(summary['poland_2023_2025_decomposition'][k] for k in ['principal_effect','rate_effect','interaction'])-(h1*r1-h0*r0))<1e-12
    (R/'fiscal_retail_summary.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n')
    print(pd.DataFrame(results).query('measure=="term_rate"')[['country','horizon_months','change','relative_change']].to_string(index=False))
    print(poland[['month','principal_bn_pln','annual_sensitivity_100bp_bn_pln','policy_rate']].tail().to_string(index=False))

if __name__=='__main__':main()
