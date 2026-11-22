"""Source acquisition, native-frequency panels, and identification/coverage audits.

Run from repository root: python -m atlas.run audit
No interpolation, annual-to-quarter conversion, or fabricated zero shocks.
"""
from __future__ import annotations

import gzip
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pycountry
import requests

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'atlas'
RAW = BASE / 'raw'
PROCESSED = BASE / 'data'
AUDIT = BASE / 'audit'
for directory in (RAW, PROCESSED, AUDIT):
    directory.mkdir(exist_ok=True)

URLS = {
    'cwy_mirror.xlsx': 'https://raw.githubusercontent.com/nmeskovski/informality-monetary-transmission/main/replication/data/data_raw_monetary-transmission.xlsx',
    'bolhuis_current.xlsx': 'https://drive.google.com/uc?export=download&id=17dSBVdi64bFhMbkQU-nTMdJv97OAyH0m',
    'bolhuis_11172025.xlsx': 'https://drive.google.com/uc?export=download&id=1BZ37xmp71oT5PgtxvWVb2M2RSh7562o1',
    'jk_ecb_monthly.csv': 'https://raw.githubusercontent.com/marekjarocinski/jkshocks_update_ecb/main/shocks_ecb_mpd_me_m.csv',
    'imf_debt.json': 'https://www.imf.org/external/datamapper/api/v1/GGXWDG_NGDP',
    'imf_countries.json': 'https://www.imf.org/external/datamapper/api/v1/countries',
    'imf_indicators.json': 'https://www.imf.org/external/datamapper/api/v1/indicators',
    'bis_country_groups_2026.pdf': 'https://www.bis.org/pages/statistics/country-groupings.pdf',
    'wb_countries.json': 'https://api.worldbank.org/v2/country?format=json&per_page=400',
    'wb_gdp.json': 'https://api.worldbank.org/v2/country/all/indicator/NY.GDP.MKTP.KD?format=json&date=1960:2025&per_page=20000',
    'wb_cpi.json': 'https://api.worldbank.org/v2/country/all/indicator/FP.CPI.TOTL?format=json&date=1960:2025&per_page=20000',
    'wb_central_debt.json': 'https://api.worldbank.org/v2/indicator/GC.DOD.TOTL.GD.ZS?format=json',
    'wb_energy_import_meta.json': 'https://api.worldbank.org/v2/indicator/EG.IMP.CONS.ZS?format=json',
}

EA_ENTRY = {c: 1999 * 4 for c in 'AUT BEL DEU ESP FIN FRA IRL ITA LUX NLD PRT'.split()}
EA_ENTRY.update({c: y * 4 for c, y in [('GRC', 2001), ('SVN', 2007), ('CYP', 2008),
    ('MLT', 2008), ('SVK', 2009), ('EST', 2011), ('LVA', 2014), ('LTU', 2015),
    ('HRV', 2023), ('BGR', 2026)]})
# Static classification follows BIS January 2026, which explicitly follows WEO.
# Unlisted dependent territories are left unclassified, not guessed as EMDE.
ADVANCED = set(('AUS CAN TWN CZE DNK HKG ISL ISR JPN KOR MAC NZL NOR SGP SWE CHE GBR USA '
                'AND LIE SMR VAT').split()) | set(EA_ENTRY)
SOURCE_NAMES = {1: 'domestic_published_identified', 2: 'domestic_daily_swap',
                3: 'domestic_daily_bond', 4: 'domestic_survey',
                5: 'domestic_taylor_residual', 6: 'anchor_inherited'}
ANCHORS = {1: 'USA', 2: 'ECB', 3: 'DEU_PRE_EURO', 4: 'GBR', 5: 'FRA_PRE_EURO'}


def save_csv(frame: pd.DataFrame, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    body = frame.to_csv(index=False, float_format='%.15g').encode()
    path.write_bytes(gzip.compress(body, mtime=0) if str(path).endswith('.gz') else body)


def fetch(name: str, url: str | None = None, refresh=False):
    """Immutable cache by default; record successful/failed network attempts."""
    url = url or URLS[name]
    path = RAW / name
    if path.exists() and not refresh:
        return path
    record = dict(file=name, url=url, retrieved_utc=datetime.now(timezone.utc).isoformat())
    try:
        response = requests.get(url, timeout=50)
        record.update(http_status=response.status_code, bytes=len(response.content))
        response.raise_for_status()
        path.write_bytes(response.content)
        record['sha256'] = hashlib.sha256(response.content).hexdigest()
    except Exception as exc:
        record.update(status='failed', error=str(exc))
        raise
    finally:
        with (AUDIT / 'download_attempts.jsonl').open('a') as handle:
            handle.write(json.dumps(record) + '\n')
    return path


def materialize_sources():
    for name in URLS:
        fetch(name)
    rows = []
    for name, url in URLS.items():
        path = RAW / name
        rows.append(dict(file=str(path.relative_to(ROOT)), url=url, bytes=path.stat().st_size,
                         sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                         provenance='third_party_replication_mirror_unverified_against_official_bytes'
                         if name == 'cwy_mirror.xlsx' else 'primary_provider'))
    for path in sorted((ROOT / 'data' / 'processed').glob('*')):
        rows.append(dict(file=str(path.relative_to(ROOT)), url='existing_repository@c884bf6',
                         bytes=path.stat().st_size, sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                         provenance='legacy_repository_see_data/sources.csv'))
    save_csv(pd.DataFrame(rows), AUDIT / 'source_manifest.csv')


def country_metadata():
    records = json.loads(fetch('wb_countries.json').read_text())[1]
    countries = pd.DataFrame([dict(country=x['id'], country_name=x['name'],
        region=x['region']['value'], income_group=x['incomeLevel']['value'],
        iso2=x['iso2Code']) for x in records if x['region']['id'] != 'NA'])
    countries['development'] = np.where(countries.country.isin(ADVANCED), 'AE', 'EMDE')
    countries.loc[countries.country.isin(['ABW','CUW','SXM','BMU','CYM','PRI','GUM','ASM',
        'VIR','FRO','IMN','GRL','GIB','NCL','PYF','CHI','TCA','VGB','MAF']), 'development'] = 'unclassified_territory'
    return countries


def iso_map(countries):
    mapper = dict(zip(countries.country_name, countries.country))
    mapper.update({v['label']: k for k,v in json.loads(fetch('imf_countries.json').read_text())['countries'].items()})
    mapper.update({'Czech Republic':'CZE', "Cote d'Ivoire":'CIV', 'Macao SAR':'MAC',
        'Micronesia':'FSM', 'Taiwan':'TWN', 'Turkey':'TUR', 'Korea, Rep.':'KOR',
        'Iran, Islamic Rep.':'IRN', 'Egypt, Arab Rep.':'EGY', 'Hong Kong SAR, China':'HKG',
        'Venezuela, RB':'VEN', 'Yemen, Rep.':'YEM', 'Slovak Republic':'SVK',
        'Congo, Rep.':'COG', 'Congo, Dem. Rep.':'COD'})
    return mapper


def iso3(iso2):
    c = pycountry.countries.get(alpha_2=iso2)
    return c.alpha_3 if c else None


def wdi(name, variable):
    payload = json.loads(fetch(name).read_text())
    if payload[0]['pages'] != 1:
        raise ValueError('Unretrieved WDI pages: ' + name)
    return pd.DataFrame([dict(country=x['countryiso3code'], year=int(x['date']),
        **{variable: x['value']}) for x in payload[1] if x.get('countryiso3code')])


def wide_world(countries):
    workbook = fetch('cwy_mirror.xlsx')
    shock = pd.read_excel(workbook, sheet_name='data_CWY_annual')
    shock = shock.rename(columns={'Country':'cwy_country_name','Year':'year','MPS':'shock_raw'})
    shock['country'] = shock.cwy_country_name.map(iso_map(countries))
    unresolved = shock.loc[shock.shock_raw.notna() & shock.country.isna(), 'cwy_country_name'].unique()
    if len(unresolved):
        raise ValueError('Unmapped CWY countries: ' + str(unresolved))
    shock = shock[shock.country.notna()].copy()
    shock['source_method'] = shock.source.map(SOURCE_NAMES)
    shock['inherited'] = shock.source.eq(6)
    shock['issuer'] = shock.country
    shock.loc[shock.inherited, 'issuer'] = shock.loc[shock.inherited, 'anchor'].map(ANCHORS)
    # One recipient-series SD, fixed on all nonmissing source observations before
    # outcomes/moderators/horizons. This is NOT a 10-bp normalization.
    shock['normalization_scale'] = shock.groupby('country').shock_raw.transform('std')
    shock['shock'] = shock.shock_raw / shock.normalization_scale
    shock['shock_unit'] = 'one_full_source_recipient_series_SD_not_10bp'
    shock['period'] = shock.year.astype(str)
    shock['time'] = shock.year
    gdp = wdi('wb_gdp.json', 'gdp_level')
    cpi = wdi('wb_cpi.json', 'cpi_level')
    macro = gdp.merge(cpi, on=['country','year'], how='outer', validate='one_to_one')
    # Complete annual calendar precedes all shifts. Never shift a gappy join.
    idx = pd.MultiIndex.from_product([sorted(shock.country.unique()), range(1960,2026)],
                                    names=['country','year'])
    frame = pd.DataFrame(index=idx).reset_index().merge(macro,on=['country','year'],how='left',validate='one_to_one')
    frame = frame.merge(shock.drop(columns=['period','time']),on=['country','year'],how='left',validate='one_to_one')
    frame['period'] = frame.year.astype(str)
    frame['time'] = frame.year
    for outcome,col in [('gdp','gdp_level'),('cpi','cpi_level')]:
        frame['log_'+outcome] = 100*np.log(frame[col].where(frame[col]>0))
    frame['season'] = 1
    frame['universe'] = 'W_CWY_annual'
    frame['frequency'] = 'A'
    frame = frame.merge(countries,on='country',how='left',validate='many_to_one')
    frame.country_name = frame.country_name.fillna(frame.cwy_country_name)
    frame.loc[frame.country.eq('TWN'), 'development'] = 'AE'
    actual = shock.dropna(subset=['shock_raw'])
    save_csv(actual[['country','cwy_country_name','year','source','source_method','anchor','issuer',
                    'inherited','shock_raw','normalization_scale','shock']], AUDIT/'cwy_country_year_identification.csv')
    monthly = pd.read_excel(workbook, sheet_name='data_CWY_month')
    observed = monthly[monthly.MPS.notna()]
    save_csv(observed.groupby('country').agg(n=('MPS','size'),first_year=('year','min'),
        last_year=('year','max'),methods=('source',lambda x: '|'.join(map(str, sorted(set(x)))))).reset_index(),
        AUDIT/'cwy_monthly_coverage.csv')
    return frame


def quarterly_macro(countries):
    current=PROCESSED/'global_native_quarterly_macro.csv.gz'
    if current.exists():
        return pd.read_csv(current,low_memory=False)
    # These two legacy panels retain observed quarterly macro series, with
    # source choices audited in data/macro_sources.json and global_macro_selection.csv.
    frames = []
    ea = set(EA_ENTRY)
    for filename, restrict in [('official_expanded_panel_ea.csv.gz', True),
                               ('official_expanded_panel_external.csv.gz', False)]:
        d = pd.read_csv(ROOT/'data/processed'/filename)
        d['country'] = d.country.map(iso3)
        d = d[d.country.isin(ea) if restrict else ~d.country.isin(ea)]
        d = d[['country','period','log_gdp','log_prices']].rename(columns={'log_prices':'log_cpi'})
        frames.append(d)
    frame = pd.concat(frames,ignore_index=True)
    assert not frame.duplicated(['country','period']).any()
    frame['time'] = pd.PeriodIndex(frame.period,freq='Q').year*4+pd.PeriodIndex(frame.period,freq='Q').quarter-1
    frame['year'] = frame.time//4
    frame['season'] = frame.time%4+1
    return frame.merge(countries,on='country',how='left',validate='many_to_one')


def high_frequency(countries):
    macro = quarterly_macro(countries)
    events = pd.read_excel(fetch('bolhuis_current.xlsx'), sheet_name='data')
    events['quarter'] = pd.PeriodIndex(events.market_Date,freq='Q')
    pieces=[]; audit=[]
    for issuer,g in events.groupby('iso3'):
        # A daily-event file is not an announcement calendar: do not assume
        # the first/last observed event is a complete boundary quarter.
        # Retain only strictly interior quarters. Empty quarters remain missing:
        # a missing event calendar cannot establish that their true shock is zero.
        first,last=g.quarter.min()+1,g.quarter.max()-1
        idx=pd.period_range(first,last,freq='Q')
        q=g.groupby('quarter')[['orth_MP1','orth_CBI1','mps','orth']].sum(min_count=1).reindex(idx)
        counts=g.groupby('quarter').size().reindex(idx,fill_value=0)
        # A missing value on an observed event invalidates that quarter.
        bad=g.groupby('quarter').orth_MP1.apply(lambda x:x.isna().any())
        q.loc[q.index.isin(bad.index[bad]),'orth_MP1'] = np.nan
        q['period']=idx.astype(str);q['time']=idx.year*4+idx.quarter-1
        q['issuer']='ECB' if issuer=='DEU' else issuer
        q['event_count']=counts.values
        pieces.append(q.reset_index(drop=True))
        audit.append(dict(issuer=q.issuer.iloc[0],first_event=str(g.market_Date.min()),
            last_event=str(g.market_Date.max()),first_complete_quarter=str(first),
            last_complete_quarter=str(last),n_events=len(g),
            empty_interior_quarters_left_missing=int(counts.eq(0).sum()),boundary_rule='drop_both_boundary_quarters'))
    shocks=pd.concat(pieces,ignore_index=True)
    out=macro.copy()
    out['issuer']=out.country
    for country,entry in EA_ENTRY.items():
        mask=out.country.eq(country)&out.time.ge(entry)
        out.loc[mask,'issuer']='ECB'
    out=out.merge(shocks,on=['issuer','period','time'],how='left',validate='many_to_one')
    out['shock_raw']=out.orth_MP1
    out['shock']=out.shock_raw/10.0
    out['normalization_scale']=10.0
    out['shock_unit']='10bp_daily_swap_monetary_component_not_policy_rate_change'
    out['universe']='H_BDY_daily'
    out['frequency']='Q'
    out['inherited']=False
    out['shared_union_shock']=out.issuer.eq('ECB')
    out['source_method']='daily_swap_orthogonalized_poor_man_MP_split'
    save_csv(pd.DataFrame(audit),AUDIT/'bdy_issuer_coverage.csv')
    variants=events.groupby('iso3').agg(n=('mps','size'),first=('market_Date','min'),last=('market_Date','max'),
        mps_sd=('mps','std'),orth_sd=('orth','std'),mp_sd=('orth_MP1','std'),info_sd=('orth_CBI1','std'))
    save_csv(variants.reset_index(),AUDIT/'bdy_shock_definitions.csv')
    jk=pd.read_csv(fetch('jk_ecb_monthly.csv'))
    jk['quarter']=pd.PeriodIndex(year=jk.year,month=jk.month,freq='M').asfreq('Q')
    q=jk.groupby('quarter').agg(raw=('MP_median','sum'),raw_count=('MP_median','count'),months=('month','size'))
    q=q[q.months.eq(3)&q.raw_count.eq(3)].copy()
    q['period']=q.index.astype(str)
    intraday=macro[macro.country.isin(EA_ENTRY)].copy()
    intraday=intraday[intraday.apply(lambda r:r.time>=EA_ENTRY[r.country],axis=1)]
    intraday=intraday.merge(q[['period','raw']],on='period',how='left',validate='many_to_one')
    intraday['issuer']='ECB';intraday['shock_raw']=intraday.raw
    intraday['shock']=intraday.raw/.1;intraday['normalization_scale']=.1
    intraday['shock_unit']='10bp_OIS1Y_scaled_intraday_MP_factor'
    intraday['universe']='H_JK_ECB_intraday';intraday['frequency']='Q'
    intraday['inherited']=False;intraday['shared_union_shock']=True
    intraday['source_method']='intraday_OIS_equity_sign_decomposition_median_rotation'
    save_csv(jk, AUDIT/'jk_downloaded_monthly.csv')
    return out,intraday


def prepare_lags(frame):
    frame=frame.sort_values(['country','time']).reset_index(drop=True)
    for _,g in frame.groupby('country'):
        if not g.time.diff().dropna().eq(1).all():
            # Entry into a currency union only removes a leading block.
            raise ValueError('Noncontiguous input calendar')
    for outcome in ['gdp','cpi']:
        group=frame.groupby('country')['log_'+outcome]
        growth=group.diff()
        frame['lag_d_'+outcome]=growth.groupby(frame.country).shift(1)
        frame['before_'+outcome]=group.shift(1)
    return frame


def build_audit():
    materialize_sources()
    countries=country_metadata()
    save_csv(countries, AUDIT/'country_classifications.csv')
    w=prepare_lags(wide_world(countries))
    h,jk=high_frequency(countries)
    panels=[w,prepare_lags(h),prepare_lags(jk)]
    comparison=[];coverage=[];tails=[]
    for d in panels:
        name=d.universe.iloc[0]
        save_csv(d,PROCESSED/(name+'.csv.gz'))
        obs=d[d.shock.notna()]
        for country,g in d.groupby('country'):
            valid=g[g.shock.notna()]
            if valid.empty: continue
            row=dict(universe=name,country=country,n_shocks=len(valid),first=valid.period.min(),last=valid.period.max(),
                shock_sd=valid.shock.std(),source_methods='|'.join(sorted(valid.source_method.dropna().unique())),
                issuers='|'.join(sorted(valid.issuer.dropna().unique())),
                inherited_observations=int(valid.inherited.sum()))
            for outcome in ['gdp','cpi']:
                mask=valid[['log_'+outcome,'before_'+outcome,'lag_d_'+outcome]].notna().all(axis=1)
                row['n_'+outcome+'_h0']=int(mask.sum())
            coverage.append(row)
        cv=pd.DataFrame([x for x in coverage if x['universe']==name])
        threshold=20 if d.frequency.iloc[0]=='A' else 40
        comparison.append(dict(dataset=name,downloaded_countries=d.loc[d.shock_raw.notna(),'country'].nunique(),
            countries_with_nonzero_shock_variance=obs.country.nunique(),
            independent_policy_issuers=obs.issuer.nunique(),native_frequency=d.frequency.iloc[0],
            first=obs.period.min(),last=obs.period.max(),countries_gdp_h0=int(cv.n_gdp_h0.gt(0).sum()),
            countries_cpi_h0=int(cv.n_cpi_h0.gt(0).sum()),
            countries_eligible_gdp_h0=int(cv.n_gdp_h0.ge(threshold).sum()),
            countries_eligible_cpi_h0=int(cv.n_cpi_h0.ge(threshold).sum()),
            inherited_countries=obs.loc[obs.inherited,'country'].nunique(),download_status='downloaded',
            identification=obs.source_method.iloc[0] if name!='W_CWY_annual' else 'heterogeneous_6_classes'))
        tails.append(obs.loc[obs.shock.abs().nlargest(15).index,
            ['universe','country','period','issuer','shock_raw','shock','shock_unit']])
    comparison.extend([
        dict(dataset='Emeksiz_Kamber_Otten_Pasricha_2026',published_policy_economies=16,
             native_frequency='event_30minute',last='published_2025_not_file_verified',
             download_status='author_link_HTTP404_no_observations_downloaded',
             identification='intraday_target_and_path_separate_no_MP_CBI_split'),
        dict(dataset='CWY_monthly',download_status='downloaded_not_estimated',native_frequency='M',
             identification='annual_Taylor_residuals_not_available_monthly;see_coverage_file'),
        dict(dataset='Bauer_Swanson_US',published_policy_economies=1,native_frequency='event',
             download_status='primary_source_located_not_downloaded_not_estimated',
             identification='intraday_orthogonalized_surprise'),
        dict(dataset='UKMPD',published_policy_economies=1,native_frequency='event',
             download_status='primary_source_located_not_downloaded_not_estimated',
             identification='UK_event_study_target_path_QE'),
        dict(dataset='EA_EMPD_and_EA_CED',published_policy_economies=1,native_frequency='event',
             download_status='primary_source_located_not_downloaded_not_estimated',
             identification='ECB_decisions_and_speeches_different_event_universe')])
    save_csv(pd.DataFrame(comparison),AUDIT/'dataset_comparison.csv')
    save_csv(pd.DataFrame(coverage),AUDIT/'effective_country_coverage.csv')
    save_csv(pd.concat(tails),AUDIT/'largest_shocks.csv')
    return panels


def load_panels():
    return [pd.read_csv(p,low_memory=False) for p in sorted(PROCESSED.glob('*annual.csv.gz'))] + [
        pd.read_csv(PROCESSED/(n+'.csv.gz'),low_memory=False) for n in ['H_BDY_daily','H_JK_ECB_intraday']]
