"""One characteristic per chunk, with dates, nulls, failures and checkpoints."""
from __future__ import annotations

import gzip
import hashlib
import json
import subprocess

import numpy as np
import pandas as pd
from scipy import stats

from .data import AUDIT,BASE,PROCESSED,ROOT,URLS,fetch,iso3,save_csv,wdi
from .estimation import RESULTS,calendar_hac,fit_record,write_run
from .run import checkpoint,horizons,panels,scopes

URLS.update({
    'wb_energy_imports.json':'https://api.worldbank.org/v2/country/all/indicator/EG.IMP.CONS.ZS?format=json&date=1960:2025&per_page=20000',
    'wb_central_government_debt.json':'https://api.worldbank.org/v2/country/all/indicator/GC.DOD.TOTL.GD.ZS?format=json&date=1960:2025&per_page=20000',
})

DEFINITIONS={
 'F01':dict(name='General-government gross debt / GDP',unit='percent_of_GDP',scale=10.,center=50.,
     mechanism='Interest income to creditors versus debt-service, fiscal adjustment and risk-premium channels',
     direction='ambiguous; gamma>0 would mean less contraction / more price-level response as debt rises',
     source='IMF WEO October 2026',indicator='GGXWDG_NGDP',verified=True,
     literature='BIS WP 1365 (2026); existing repository creditor-residence research',
     concern='historical WEO estimates/revisions; debt is endogenous; one lag does not make Z exogenous'),
 'F02':dict(name='Central-government debt / GDP',unit='percent_of_GDP',scale=10.,center=50.,
     mechanism='Government financing and creditor income',direction='ambiguous',source='World Bank WDI / IMF GFS',
     indicator='GC.DOD.TOTL.GD.ZS',verified=True,concern='central versus general government are distinct sectors'),
 'F03':dict(name='Debt held by domestic residents / GDP',unit='percent_of_GDP',scale=10.,center=20.,
     mechanism='Domestic receipt of sovereign interest income',direction='ambiguous',source='Fang-Hardy-Lewis / IMF / Eurostat',
     indicator='fhl_holdings.domestic_gdp',verified=True,concern='includes central bank; portfolio and valuation differences'),
 'F04':dict(name='Domestic private sovereign holdings excluding central bank / GDP',unit='percent_of_GDP',scale=10.,center=20.,
     mechanism='Resident creditor interest income versus bank-sovereign exposure and fiscal adjustment',direction='ambiguous',
     source='Fang-Hardy-Lewis full 101-country file; official IMF/Eurostat extension',
     indicator='fhl_holdings.domestic_private_gdp; official_expanded_ownership_annual.domestic_noncb',verified=True,
     literature='Fang, Hardy and Lewis (2025); Arslanalp and Tsuda; existing repository',
     concern='domestic outside-central-bank is a provider sector definition; nonbank public entities may be included'),
 'F05':dict(name='Foreign-held sovereign debt / GDP',unit='percent_of_GDP',scale=10.,center=20.,
     mechanism='Foreign leakage of interest income and external financing',direction='ambiguous',source='FHL / IMF',
     indicator='fhl_holdings.foreign_gdp',verified=True,concern='residence differs from nationality and currency'),
 'F06':dict(name='Foreign-held share of sovereign debt',unit='share',scale=.1,center=.3,
     mechanism='Creditor residence',direction='ambiguous',source='FHL / IMF',
     indicator='foreign_gdp / total_gdp from same source',verified=True,concern='joint denominator; revaluation'),
 'F07':dict(name='Central-bank-held government debt / GDP',unit='percent_of_GDP',scale=10.,center=10.,
     mechanism='Remittances and consolidated public-sector interest flows',direction='ambiguous',source='FHL / IMF',
     indicator='fhl_holdings.central_bank_gdp',verified=True,concern='QE and endogenous balance sheets'),
 'F08':dict(name='Domestic banks sovereign holdings / GDP',unit='percent_of_GDP',scale=10.,center=10.,
     mechanism='Sovereign-bank nexus and bank interest receipts',direction='ambiguous',source='FHL / IMF',
     indicator='fhl_holdings.domestic_bank_gdp',verified=True,concern='loans versus securities; bank balance sheets'),
 'F09':dict(name='Domestic nonbank sovereign holdings / GDP',unit='percent_of_GDP',scale=10.,center=10.,
     mechanism='Nonbank creditor interest income',direction='ambiguous',source='FHL / IMF',
     indicator='fhl_holdings.domestic_nonbank_gdp',verified=True,concern='pension funds and households have different MPCs'),
 'F10':dict(name='Foreign official sovereign holdings / GDP (inferred completion of truncated item)',
     unit='percent_of_GDP',scale=10.,center=5.,mechanism='Official external financing and interest-income leakage',
     direction='ambiguous',source='FHL / IMF',indicator='fhl_holdings.foreign_official_gdp',verified=True,
     concern='the user catalogue ended mid-F10; this measure is an explicitly inferred completion'),
 'R01':dict(name='Sovereign principal refinancing within one year',unit='share_of_source_government_portfolio',scale=.1,center=.2,
     mechanism='Faster repricing of sovereign interest payments and creditor income',direction='ambiguous',
     source='Observed debt schedules in existing official-expansion inventory',
     indicator='official_expanded_maturity_candidates.refinance_share',verified=True,
     literature='De Graeve and Mazzolini / BIS WP 1365 (2026); existing repository',
     concern='remaining maturity, not original maturity; government portfolios and valuations differ by source'),
 'E01':dict(name='Net energy imports / energy use',unit='percent_of_energy_use',scale=10.,center=0.,
     mechanism='Energy import costs, currency adjustment and supply sensitivity',direction='ambiguous',
     source='World Bank WDI / IEA',indicator='EG.IMP.CONS.ZS',verified=True,
     literature='CWY cost/exchange-rate channels; no priority/novelty claim',
     concern='not a monetary-policy-specific exposure; net exporters have negative values; global energy shocks'),
 'P01':dict(name='Private nonfinancial debt service ratio',unit='percent_of_income',scale=1.,center=10.,
     mechanism='Borrower cash-flow and debt-service squeeze',direction='usually more contraction at higher DSR, conditional on identification',
     source='BIS WS_DSR',indicator='WS_DSR; precise sector key pending download audit',verified=False,
     concern='BIS DSR is a constructed aggregate with maturity assumptions'),
 'C01':dict(name='Remunerated central-bank reserves',unit='pending_definition',scale=1.,center=0.,
     mechanism='Policy-rate-sensitive payments to banks and depositors',direction='ambiguous',
     source='Central-bank balance sheets and remuneration rules',indicator='',verified=False,
     concern='reserve volumes alone do not identify remuneration; regime dates must be verified'),
}


def registry():
    records=[]
    for code,d in DEFINITIONS.items():
        path=PROCESSED/(code+'_observed_annual.csv.gz')
        observed=pd.read_csv(path) if path.exists() else pd.DataFrame()
        fhl_columns={'F03':'domestic_gdp','F05':'foreign_gdp','F07':'central_bank_gdp',
            'F08':'domestic_bank_gdp','F09':'domestic_nonbank_gdp','F10':'foreign_official_gdp'}
        if observed.empty and code in [*fhl_columns,'F06']:
            source=pd.read_csv(ROOT/'data/processed/fhl_holdings.csv')
            values=source.foreign_gdp/source.total_gdp if code=='F06' else source[fhl_columns[code]]
            observed=pd.DataFrame(dict(country=source.Country_Code,year=source.Year,value=values)).dropna()
        observed_info=dict(available_countries=None,first_observed_year=None,last_observed_year=None,
            countries_with_eight_distinct_values=None,data_quality='source_audit_pending')
        if not observed.empty:
            varying=observed.groupby('country').value.nunique()
            observed_info=dict(available_countries=int(observed.country.nunique()),
                first_observed_year=int(observed.year.min()),last_observed_year=int(observed.year.max()),
                countries_with_eight_distinct_values=int(varying.ge(8).sum()),
                data_quality='documented_actual_observations;provider_definition_and_portfolio_caveats_apply')
        records.append(dict(id=code,**d,**observed_info,native_frequency='A' if code not in ['P01','C01'] else 'pending_audit',
            planned_outcomes='real_GDP_level|headline_CPI_level',
            novelty='exploratory_extension_no_claim_of_first_discovery',
            source_verification='verified_identifier' if d.get('verified') else 'candidate_only_not_tested',
            status='completed_core' if (RESULTS/'chunks'/code/'COMPLETED.json').exists() else
                   'queued' if code in ['F01','F04','R01','E01'] else 'unstarted'))
    save_csv(pd.DataFrame(records),BASE/'variable_registry.csv')
    return records


def annual_characteristic(code,refresh=False):
    preserved=PROCESSED/(code+'_observed_annual.csv.gz')
    if preserved.exists() and not refresh:
        return pd.read_csv(preserved)
    if code=='F01':
        raw=json.loads(fetch('imf_debt.json').read_text())['values']['GGXWDG_NGDP']
        rows=[dict(country=c,year=int(y),value=v,source='IMF_WEO_October_2026_GGXWDG_NGDP')
            for c,series in raw.items() for y,v in series.items() if str(y).isdigit() and int(y)<=2025]
        out=pd.DataFrame(rows)
    elif code in ['E01','F02']:
        name='wb_energy_imports.json' if code=='E01' else 'wb_central_government_debt.json'
        out=wdi(name,'value');out['source']='WorldBank_WDI_'+DEFINITIONS[code]['indicator']
    elif code=='F04':
        # Use ALL 101 countries, rather than the old project selection.
        f=pd.read_csv(ROOT/'data/processed/fhl_holdings.csv')
        f=f.rename(columns={'Country_Code':'country','Year':'year','domestic_private_gdp':'value'})
        f['source']='FHL_full_101_countries'
        modern=pd.read_csv(ROOT/'data/processed/official_expanded_ownership_annual.csv.gz')
        modern['country']=modern.country.map(iso3)
        modern=modern.rename(columns={'domestic_noncb':'value'})
        out=pd.concat([f[['country','year','value','source']],modern[['country','year','value','source']]],ignore_index=True)
        # Choose one full source series per country by freshest endpoint and
        # observed support, avoiding undefined annual cross-source patchwork.
        options=out.dropna(subset=['value','country']).groupby(['country','source']).agg(
            last=('year','max'),n=('value','size')).reset_index()
        chosen=options.sort_values(['country','last','n'],ascending=[True,False,False]).drop_duplicates('country')
        save_csv(options,AUDIT/'F04_all_source_candidates.csv')
        save_csv(chosen,AUDIT/'F04_selected_source.csv')
        out=out.merge(chosen[['country','source']],on=['country','source'],validate='many_to_one')
    elif code=='R01':
        d=pd.read_csv(ROOT/'data/processed/official_expanded_maturity_candidates.csv.gz',low_memory=False)
        d['country']=d.country.map(iso3)
        dates=pd.to_datetime(d.date,errors='coerce')
        # Annual states are actual year-end schedules or observed Q4/December
        # schedules. Do not misdate an early-year observation as year-end.
        d=d[dates.dt.month.eq(12)&d.refinance_share.notna()&d.country.notna()].copy()
        d['year']=pd.to_datetime(d.date).dt.year
        d['source_key']=d.source.fillna('')+'|'+d.sector.fillna('')+'|'+d.portfolio.fillna('')+'|'+d.valuation.fillna('')
        # The original parser's source priority was declared independently of
        # outcomes. Fix one portfolio/source per country before any LP.
        options=d.groupby(['country','source_key']).agg(n=('refinance_share','size'),
            last=('year','max'),priority=('priority','min')).reset_index()
        chosen=options.sort_values(['country','priority','last','n'],ascending=[True,True,False,False]).drop_duplicates('country')
        d=d.merge(chosen[['country','source_key']],on=['country','source_key'],validate='many_to_one')
        d=d.sort_values(['country','year','priority','date']).drop_duplicates(['country','year'])
        out=d.rename(columns={'refinance_share':'value','source':'provider_source','source_key':'source'})
        save_csv(chosen,AUDIT/'R01_selected_source_portfolio.csv')
        save_csv(d,AUDIT/'R01_year_end_schedule_witness.csv')
    else:raise ValueError('Not yet implemented: '+code)
    out=out[['country','year','value','source']].dropna(subset=['country','value'])
    out['year']=out.year.astype(int)
    assert not out.duplicated(['country','year']).any()
    if code!='E01':out=out[out.value.ge(-1e-8)].copy()
    if code=='R01':out=out[out.value.le(1.000001)].copy()
    save_csv(out,PROCESSED/(code+'_observed_annual.csv.gz'))
    return out


def attach(d,characteristic,code):
    out=d.copy()
    out['z_source_year']=out.year-1
    z=characteristic.rename(columns={'year':'z_source_year','value':'z_raw','source':'z_source'})
    out=out.merge(z,on=['country','z_source_year'],how='left',validate='many_to_one')
    definition=DEFINITIONS[code]
    out['z']=(out.z_raw-definition['center'])/definition['scale']
    out['z_native_frequency']='A'
    out.attrs['moderator']=code
    assert (out.z_source_year<out.year).all()
    return out


def meta_exposure(d,z,code,outcome,horizon):
    """Predetermined early-exposure comparison with common-score covariance.

    The first five observed annual characteristics define exposure; all LP
    shock dates are strictly later than that window. No future average is used.
    """
    local=[];exposures=[]
    for country,g in z.groupby('country'):
        g=g.sort_values('year').head(5)
        if len(g)<5:continue
        exposure=(g.value.mean()-DEFINITIONS[code]['center'])/DEFINITIONS[code]['scale']
        cutoff=int(g.year.max())
        subset=d[d.country.eq(country)].copy()
        if subset.empty or not subset.shock.notna().any():continue
        subset.loc[subset.year.le(cutoff),'shock']=np.nan
        record=fit_record(subset,outcome,horizon,scope='country',country=country,use_influence=True)
        record.update(model='E_country_LP_after_exposure_window',moderator=code,
                      exposure=float(exposure),exposure_last_year=cutoff)
        local.append(record)
        if record['status']=='ok':exposures.append((record,float(exposure)))
    meta=dict(universe=d.universe.iloc[0],frequency=d.frequency.iloc[0],outcome=outcome,horizon=horizon,
        scope='global_country_exposure',country=None,variant='predetermined_first_five_years',moderator=code,
        model='E_uncertain_country_response_association',status='not_estimable',n=len(exposures))
    if len(exposures)<5:return local+[meta|dict(reason='fewer_than_five_supported_country_responses')]
    x=np.array([[1.,exposure] for _,exposure in exposures])
    b=np.array([next(t for t in r['estimates'] if t['term']=='shock')['estimate'] for r,_ in exposures])
    if np.linalg.matrix_rank(x)<2:return local+[meta|dict(reason='constant_country_exposure')]
    projection=np.linalg.inv(x.T@x)@x.T
    beta=projection@b;residual=b-x@beta
    h=np.sum(x*(x@np.linalg.inv(x.T@x)),axis=1)
    vc_hc3=projection@np.diag((residual/(1-h))**2)@projection.T
    times=sorted(set(t for r,_ in exposures for t in r['time_grid']))
    calendar=np.arange(min(times),max(times)+1)
    influences=np.zeros((len(calendar),len(exposures)))
    for j,(r,_) in enumerate(exposures):
        k=r['columns'].index('shock')
        influences[np.array(r['time_grid'])-calendar[0],j]=np.array(r['influence'])[:,k]
    bandwidth=max(horizon+1,2 if d.frequency.iloc[0]=='A' else 4)
    sampling,_,_=calendar_hac(influences,calendar,bandwidth)
    vc_sampling=projection@sampling@projection.T
    # Present both components. Their sum intentionally counts some individual
    # estimation noise twice; it is a conservative diagnostic, not a precise
    # random-effects likelihood or a causal second-stage design.
    vc=vc_hc3+vc_sampling
    dof=min(len(exposures)-2,len(calendar)-1)
    se=np.sqrt(np.maximum(np.diag(vc),0));critical=stats.t.ppf(.975,dof)
    estimates=[dict(term=t,estimate=float(beta[j]),se=float(se[j]),p_raw=float(2*stats.t.sf(abs(beta[j]/se[j]),dof)),
        ci95_low=float(beta[j]-critical*se[j]),ci95_high=float(beta[j]+critical*se[j]),
        se_response_sampling=float(np.sqrt(vc_sampling[j,j])),se_country_HC3=float(np.sqrt(vc_hc3[j,j])))
        for j,t in enumerate(['intercept','exposure_association'])]
    meta.update(status='ok',estimates=estimates,beta=beta.tolist(),covariance=vc.tolist(),
        covariance_country_HC3=vc_hc3.tolist(),covariance_country_response_sampling=vc_sampling.tolist(),
        association_not_causal=True,uncertainty_note='common_calendar_HAC_sampling_plus_HC3;potential_double_count_reported',
        country_list=[r['country'] for r,_ in exposures],bandwidth=bandwidth)
    return local+[meta]


def chunk_note(code,estimates,records,characteristic,coverage):
    definition=DEFINITIONS[code]
    path=BASE/'notebooks'/f'chunk_{code}.md';path.parent.mkdir(exist_ok=True)
    gamma=estimates[estimates.term.eq('interaction')&estimates.scope.eq('global')&estimates.variant.eq('all')].copy() if not estimates.empty else pd.DataFrame()
    # Prespecified landmark horizons, never the minimum p-value over horizons.
    if not gamma.empty:
        gamma=gamma[((gamma.frequency.eq('A'))&gamma.horizon.isin([0,2,5]))|
                    ((gamma.frequency.eq('Q'))&gamma.horizon.isin([0,4,8,12]))]
        cols=['universe','outcome','horizon','estimate','se','p_raw','q_BH_informational','n','n_countries','n_issuers']
        table=gamma[[c for c in cols if c in gamma]].to_markdown(index=False,floatfmt='.5g')
    else:table='No global interactions were estimable.'
    failures=pd.Series([r.get('reason','ok') for r in records if r['status']!='ok']).value_counts()
    text=f'''# Chunk {code}: {definition['name']}

Status: core country/panel/external specifications executed; Model E diagnostics executed where supported. This is exploratory research, not a causal finding about changing the characteristic itself.

Mechanism: {definition['mechanism']}.

Theoretical direction: {definition['direction']}. No expected sign is treated as an empirical result.

Source / verified series: {definition['source']} / `{definition['indicator']}`.

Dating: only the prior calendar year's genuinely observed characteristic is used. Its native frequency remains annual in quarterly LPs. It is a predetermined exposure state, never an interpolated quarterly observation. Missing prior years are not filled.

Scaling: one unit of Z is {definition['scale']} {definition['unit']}; centering is fixed at {definition['center']}. The interaction is a change in the shock response per one unit of Z. A positive gamma does not by itself imply that the total GDP response is positive.

Identification concern: {definition['concern']}.

Observed characteristic coverage: {characteristic.country.nunique()} economies, {characteristic.year.min()}–{characteristic.year.max()}, {len(characteristic)} country-year values. Effective LP support is in `coverage.csv` and differs by outcome and horizon.

Attempted specifications: {len(records)}; estimated: {sum(r['status']=='ok' for r in records)}; failures: {sum(r['status']=='failed' for r in records)}. Rank/variation/sample exclusions remain in the attempt log.

## Global interactions at prespecified horizons

{table}

Raw p-values are the main reported test statistics. BH q-values and restricted block-wild p-values are informational. Calendar score HAC preserves common monetary issuers and overlapping outcome windows. Few effective time blocks limit inference, especially at long horizons.

## Interpretation limits

The CWY world sample mixes identification methods and inherited shocks. Taylor innovations are a separate weaker identification class. External Fed/ECB models measure spillovers. Intraday US/ECB reconstructions retain their own units and vintages. None are spliced into a single artificial shock series.

No coefficient ranking or raw p-value identifies an expansionary monetary response on its own. The total conditional response and its uncertainty must be inspected; time effects absorb common shock main effects in external/currency-union panels.

## Recorded exclusions / failures

{failures.to_string()}
'''
    path.write_text(text)
    return path


def run_chunk(code,force=False):
    registry();directory=RESULTS/'chunks'/code;directory.mkdir(parents=True,exist_ok=True)
    complete=directory/'COMPLETED.json'
    if complete.exists() and not force:
        checkpoint('chunk','reused_checkpoint',moderator=code);return
    checkpoint('chunk','running',moderator=code)
    z=annual_characteristic(code);records=[];coverage=[]
    # The richest world universe, stronger identification comparisons and
    # current lower-identification reconstruction remain separate experiments.
    names={'W_CWY_annual','H_BDY_daily','H_ECB_reconstructed_2026','H_USA_reconstructed_2026',
           'T_reconstructed_annual_1L','T_reconstructed_quarterly',
           'W_external_USA_annual','W_external_USA_quarterly'}
    for raw in panels():
        name=raw.universe.iloc[0]
        if name not in names:continue
        d=attach(raw,z,code)
        supported=d[d.shock.notna()&d.z.notna()]
        for country,g in supported.groupby('country'):
            coverage.append(dict(universe=name,country=country,n=len(g),native_z_years=g.z_source_year.nunique(),
                first=g.period.min(),last=g.period.max(),within_sd=g.z_raw.std(),
                z_min=g.z_raw.min(),z_max=g.z_raw.max(),source='|'.join(sorted(g.z_source.unique()))))
        country_list=sorted(supported.country.unique())
        for outcome in ['gdp','cpi']:
            for horizon in horizons(d):
                for country in country_list:
                    records.append(fit_record(d,outcome,horizon,scope='country',country=country,moderator=True))
                for scope in scopes(d):
                    records.append(fit_record(d,outcome,horizon,scope=scope,moderator=True))
                # Prespecified sensitivity, no selection on the sign/p-value.
                for variant in (['domestic_only','stable_source_only'] if name=='W_CWY_annual' else ['exclude_covid_windows']):
                    records.append(fit_record(d,outcome,horizon,scope='global',moderator=True,variant=variant))
                # Early-exposure comparisons at the whole IRF, propagating the
                # country first-stage uncertainty and common calendar shocks.
                if name in ['W_CWY_annual','H_BDY_daily','H_ECB_reconstructed_2026']:
                    records+=meta_exposure(raw,z,code,outcome,horizon)
        checkpoint('chunk_universe','estimated',moderator=code,universe=name,
                   supported_countries=len(country_list),specifications_so_far=len(records))
        # Write each completed universe, so a session interruption is recoverable.
        write_run([r for r in records if r['universe']==name],directory/name)
    estimates=write_run(records,directory)
    save_csv(pd.DataFrame(coverage),directory/'coverage.csv')
    note=chunk_note(code,estimates,records,z,coverage)
    complete.write_text(json.dumps(dict(moderator=code,specifications=len(records),
        estimated=sum(r['status']=='ok' for r in records),
        failed=sum(r['status']=='failed' for r in records),notebook=str(note.relative_to(BASE))),indent=2))
    registry()
    checkpoint('chunk','completed',moderator=code,specifications=len(records),
               estimated=sum(r['status']=='ok' for r in records))
    # Authorized additive milestone on the dedicated local research branch.
    subprocess.run(['git','add','--sparse','atlas'],cwd=ROOT,check=True,stdout=subprocess.DEVNULL)
    subprocess.run(['git','commit','-m',f'atlas: complete one-characteristic chunk {code}'],cwd=ROOT,check=True,
                   stdout=subprocess.DEVNULL)


if __name__=='__main__':
    import sys
    run_chunk(sys.argv[1] if len(sys.argv)>1 else 'F01')
