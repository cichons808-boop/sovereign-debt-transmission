"""Empirical notebook, dependence-aware dispersion and scientific figures."""
from __future__ import annotations

import gzip
import hashlib
import json
import math

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import numpy as np
import pandas as pd
from scipy import stats

from .data import AUDIT,BASE,PROCESSED,save_csv
from .estimation import RESULTS,write_run
from .moderators import DEFINITIONS,registry
from .run import checkpoint

FIG=BASE/'figures';FIG.mkdir(exist_ok=True)
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':9,'axes.spines.top':False,
    'axes.spines.right':False,'axes.grid':True,'grid.alpha':.16,'figure.facecolor':'white',
    'savefig.facecolor':'white','pdf.fonttype':42})
COLORS=['#167c80','#d2862d','#6a68a6','#b85555']


def read_records(path):
    with gzip.open(path,'rt',encoding='utf-8') as handle:
        for line in handle:yield json.loads(line)


def coefficient_frames():
    baseline=pd.read_csv(RESULTS/'baseline'/'coefficients.csv.gz',low_memory=False)
    chunks=[]
    for path in sorted((RESULTS/'chunks').glob('*/coefficients.csv.gz')):
        d=pd.read_csv(path,low_memory=False);d['chunk']=path.parent.name;chunks.append(d)
    return baseline,pd.concat(chunks,ignore_index=True) if chunks else pd.DataFrame()


def dispersion_bootstrap():
    rows=[]
    for path in sorted((RESULTS/'baseline').glob('*/specifications.jsonl.gz')):
        groups={}
        for r in read_records(path):
            if r.get('status')!='ok' or r.get('scope')!='country' or r.get('variant')!='all':continue
            groups.setdefault((r['universe'],r['outcome'],r['horizon']),[]).append(r)
        for key,records in groups.items():
            if len(records)<5:continue
            estimates=np.array([r['beta'][r['columns'].index('shock')] for r in records])
            lower=min(min(r['time_grid']) for r in records)
            upper=max(max(r['time_grid']) for r in records)
            influences=np.zeros((upper-lower+1,len(records)))
            for j,r in enumerate(records):
                k=r['columns'].index('shock')
                influences[np.array(r['time_grid'])-lower,j]=np.array(r['influence'])[:,k]
            length=max(key[2]+1,2 if records[0]['frequency']=='A' else 4)+1
            rng=np.random.default_rng(20261122+key[2]);draws=499
            observed=np.var(estimates,ddof=1);boot=[]
            for _ in range(draws):
                offset=int(rng.integers(length))
                block=(np.arange(len(influences))+offset)//length
                weights=rng.choice([-1.,1.],size=int(block.max()+1))[block]
                errors=weights@influences
                boot.append(float(np.var(errors,ddof=1)))
            rows.append(dict(universe=key[0],outcome=key[1],horizon=key[2],n_countries=len(records),
                observed_variance=float(observed),null_sampling_variance_median=float(np.median(boot)),
                p_common_calendar_block_dispersion=float((1+np.sum(np.array(boot)>=observed))/(draws+1)),
                mean=float(estimates.mean()),median=float(np.median(estimates)),
                block_length=length,draws=draws,effective_time_blocks=len(influences)/length,
                interpretation='approximate_equal_response_null;common_calendar_errors_retained;not_a_causal_country_trait_test'))
    out=pd.DataFrame(rows);save_csv(out,RESULTS/'baseline'/'dispersion_block_bootstrap.csv')
    return out


def country_summaries(baseline):
    a=baseline[baseline.scope.eq('country')&baseline.term.eq('shock')].copy()
    main=a[a.variant.eq('all')].copy()
    robust=a[a.variant.eq('exclude_largest_shock')][['universe','outcome','country','horizon','estimate','p_raw']]
    robust=robust.rename(columns={'estimate':'estimate_without_largest_shock','p_raw':'p_without_largest_shock'})
    main=main.merge(robust,on=['universe','outcome','country','horizon'],how='left',validate='one_to_one')
    main['positive_point_estimate']=main.estimate.gt(0)
    main['positive_raw_p05']=main.estimate.gt(0)&main.p_raw.lt(.05)
    main['positive_raw_p05_after_largest_omission']=main.estimate_without_largest_shock.gt(0)&main.p_without_largest_shock.lt(.05)
    save_csv(main,RESULTS/'baseline'/'country_response_sensitivity.csv.gz')
    rows=[]
    for key,g in main.groupby(['universe','country','outcome']):
        g=g.sort_values('horizon');sign=np.sign(g.estimate.to_numpy())
        rows.append(dict(universe=key[0],country=key[1],outcome=key[2],
            first_horizon=int(g.horizon.min()),last_horizon=int(g.horizon.max()),
            largest_contraction_horizon=int(g.loc[g.estimate.idxmin(),'horizon']),
            largest_positive_horizon=int(g.loc[g.estimate.idxmax(),'horizon']),
            horizon_sign_changes=int(np.sum(sign[1:]*sign[:-1]<0)),
            positive_horizons=int(g.positive_point_estimate.sum()),
            raw_significant_positive_horizons=int(g.positive_raw_p05.sum()),
            note='peak_timing_is_selected_descriptively;positive_point_is_not_expansionary_classification'))
    save_csv(pd.DataFrame(rows),RESULTS/'baseline'/'country_response_timing.csv')
    classes=pd.read_csv(AUDIT/'country_classifications.csv')
    joined=main.merge(classes[['country','development','region']],on='country',how='left')
    grouped=[]
    for grouping in ['development','region']:
        g=joined.groupby(['universe','outcome','horizon',grouping],dropna=False).agg(
            countries=('country','nunique'),mean=('estimate','mean'),median=('estimate','median')).reset_index()
        g['group_type']=grouping;g=g.rename(columns={grouping:'group'});grouped.append(g)
    save_csv(pd.concat(grouped,ignore_index=True),RESULTS/'baseline'/'group_response_distribution.csv')
    return main


def effective_coverage():
    rows=[]
    for path in sorted((RESULTS/'baseline').glob('*/attempts.csv.gz')):
        a=pd.read_csv(path,low_memory=False)
        country=a[a.scope.eq('country')&a.variant.eq('all')&a.horizon.eq(0)]
        row=dict(universe=path.parent.name,attempted=len(a),estimated=int(a.status.eq('ok').sum()),
            gdp_eligible=country.loc[country.status.eq('ok')&country.outcome.eq('gdp'),'country'].nunique(),
            cpi_eligible=country.loc[country.status.eq('ok')&country.outcome.eq('cpi'),'country'].nunique(),
            raw_shock_countries=country.country.nunique())
        source=pd.read_csv(PROCESSED/(row['universe']+'.csv.gz'),low_memory=False)
        observed=source[source.shock.notna()]
        row.update(issuers=observed.issuer.nunique(),first=observed.period.min(),last=observed.period.max(),
                   frequency=source.frequency.iloc[0],shock_unit=source.shock_unit.dropna().iloc[0])
        rows.append(row)
    out=pd.DataFrame(rows);save_csv(out,AUDIT/'final_effective_LP_coverage.csv')
    return out


def marginal_responses():
    rows=[]
    grids={'F01':[25,50,75,100,150],'F04':[0,10,25,50,75],
           'R01':[.1,.2,.3,.4,.5],'E01':[-100,-50,0,50,100]}
    for path in sorted((RESULTS/'chunks').glob('*/specifications.jsonl.gz')):
        code=path.parent.name
        for r in read_records(path):
            if r.get('status')!='ok' or r.get('scope')!='global' or r.get('variant')!='all':continue
            if r.get('model')!='D_global_moderator' or 'interaction'not in r.get('columns',[]):continue
            if 'shock'not in r['columns']:continue
            beta=np.array(r['beta']);vc=np.array(r['covariance'])
            for value in grids.get(code,[]):
                z=(value-DEFINITIONS[code]['center'])/DEFINITIONS[code]['scale']
                contrast=np.zeros(len(beta));contrast[r['columns'].index('shock')]=1
                contrast[r['columns'].index('interaction')]=z
                point=float(contrast@beta);se=float(np.sqrt(contrast@vc@contrast))
                df=r['inference_df'];critical=stats.t.ppf(.975,df)
                rows.append(dict(chunk=code,universe=r['universe'],outcome=r['outcome'],horizon=r['horizon'],
                    z_raw=value,response=point,se=se,p_raw=float(2*stats.t.sf(abs(point/se),df)),
                    ci95_low=point-critical*se,ci95_high=point+critical*se,shock_unit=r['shock_unit'],
                    n=r['n'],countries=r['n_countries'],
                    interpretation='conditional_fitted_response;fixed_exposure_grid;not_causal_effect_of_changing_Z'))
    out=pd.DataFrame(rows);save_csv(out,RESULTS/'conditional_response_grid.csv')
    return out


def plot_coverage(coverage):
    fig,ax=plt.subplots(figsize=(10,7.5))
    y=np.arange(len(coverage));ax.barh(y-.18,coverage.gdp_eligible,height=.34,color=COLORS[0],label='Real GDP')
    ax.barh(y+.18,coverage.cpi_eligible,height=.34,color=COLORS[1],label='Headline CPI')
    ax.set_yticks(y,coverage.universe.str.replace('_',' ',regex=False),fontsize=8)
    ax.invert_yaxis();ax.set_xlabel('Countries / territories eligible for country LP at h = 0')
    ax.set_title('Effective LP coverage after joining actual observations',loc='left',weight='bold',pad=12)
    ax.legend(loc='lower right');fig.tight_layout();fig.savefig(FIG/'eligible_country_coverage.png',dpi=160);plt.close(fig)


def plot_chunks(chunks):
    for code in chunks.chunk.unique():
        selected=chunks[chunks.chunk.eq(code)&chunks.scope.eq('global')&chunks.variant.eq('all')&chunks.term.eq('interaction')]
        families=[f for f in ['W_CWY_annual','H_BDY_daily','H_ECB_reconstructed_2026','T_reconstructed_quarterly'] if f in selected.universe.unique()]
        fig,axes=plt.subplots(2,len(families),figsize=(12.8,6),squeeze=False)
        for j,family in enumerate(families):
            for i,outcome in enumerate(['gdp','cpi']):
                ax=axes[i,j];g=selected[selected.universe.eq(family)&selected.outcome.eq(outcome)].sort_values('horizon')
                if not g.empty:
                    ax.fill_between(g.horizon,g.ci95_low,g.ci95_high,color=COLORS[j%4],alpha=.17)
                    ax.plot(g.horizon,g.estimate,color=COLORS[j%4],lw=1.8)
                    ax.scatter(g.loc[g.p_raw.lt(.05),'horizon'],g.loc[g.p_raw.lt(.05),'estimate'],s=18,color=COLORS[j%4])
                ax.axhline(0,color='#555555',lw=.7)
                ax.set_title(family.replace('_',' '),fontsize=8)
                ax.set_xlabel('Years' if 'annual'in family else 'Quarters')
                if j==0:ax.set_ylabel(('Real GDP' if outcome=='gdp' else 'CPI level')+' interaction')
        fig.suptitle(code+' — '+DEFINITIONS[code]['name'],x=.02,ha='left',fontsize=12,weight='bold')
        fig.text(.02,.012,'95% pointwise calendar-HAC intervals. Dots: raw p < .05. Source units differ across columns; no pooled shock series.',fontsize=8)
        fig.tight_layout(rect=[0,.035,1,.94]);fig.savefig(FIG/(code+'_global_interactions.png'),dpi=155);plt.close(fig)


def plot_country_book(main):
    annual_order=['W_CWY_annual','T_reconstructed_annual_1L','W_external_USA_annual']
    quarterly_order=['H_ECB_reconstructed_2026','H_USA_reconstructed_2026','H_GBR_Target_2026',
        'H_BDY_daily','T_reconstructed_quarterly','W_external_USA_quarterly']
    names=pd.read_csv(AUDIT/'country_classifications.csv').set_index('country').country_name.to_dict()
    index=[]
    country_data=main.groupby('country')
    with PdfPages(FIG/'country_IRFs.pdf') as pdf:
        for country in sorted(main.country.unique()):
            d=country_data.get_group(country)
            chosen=[]
            for order in [annual_order,quarterly_order]:
                chosen.append(next((family for family in order if family in set(d.universe)),None))
            fig,axes=plt.subplots(2,2,figsize=(10.5,7.5))
            for i,family in enumerate(chosen):
                for j,outcome in enumerate(['gdp','cpi']):
                    ax=axes[i,j]
                    if family is None:
                        ax.text(.5,.5,'No eligible country LP',ha='center',va='center',transform=ax.transAxes);continue
                    g=d[d.universe.eq(family)&d.outcome.eq(outcome)].sort_values('horizon')
                    if g.empty:
                        ax.text(.5,.5,'Insufficient observed outcome support',ha='center',va='center',transform=ax.transAxes)
                    else:
                        ax.fill_between(g.horizon,g.ci95_low,g.ci95_high,color=COLORS[j],alpha=.18)
                        ax.plot(g.horizon,g.estimate,color=COLORS[j],lw=1.7)
                        sig=g.p_raw.lt(.05);ax.scatter(g.loc[sig,'horizon'],g.loc[sig,'estimate'],s=17,color=COLORS[j])
                        ax.text(.02,.02,f'N = {int(g.n.min())}–{int(g.n.max())}; {g.first_period.min()}–{g.last_period.max()}',
                                transform=ax.transAxes,fontsize=7,color='#555555')
                    ax.axhline(0,color='#555555',lw=.7)
                    ax.set_title(('Real GDP' if outcome=='gdp' else 'Headline CPI')+' | '+family.replace('_',' '),fontsize=8)
                    ax.set_ylabel('Cumulative log-level change (%)')
                    ax.set_xlabel('Years after shock' if i==0 else 'Quarters after shock')
            fig.suptitle(names.get(country,country)+' ('+country+')',x=.07,ha='left',weight='bold',fontsize=14)
            fig.text(.07,.025,'95% pointwise HAC intervals. Dots: raw p < .05. External Fed responses are spillovers.\n'
                'Annual world/Taylor shocks use one country-series SD; event factors use their documented units. Positive estimates are not proof of expansion.',fontsize=7)
            fig.tight_layout(rect=[.02,.07,.98,.94]);pdf.savefig(fig);plt.close(fig)
            index.append(dict(country=country,country_name=names.get(country,country),
                annual_panel=chosen[0],quarterly_panel=chosen[1],pdf_page=len(index)+1))
    save_csv(pd.DataFrame(index),FIG/'country_IRF_index.csv')
    return len(index)


def compact_exports():
    """Persist every attempted model with covariance and diagnostics compactly.

    Large internal score arrays and repeated observation keys are reproducible
    from the preserved panels/code and their sample-key hashes. They are cache
    objects, not omitted coefficient results. The working full records remain.
    """
    directories=[]
    for path in sorted(RESULTS.rglob('specifications.jsonl.gz')):
        # Avoid a second copy of the same current records in aggregate files.
        if path.parent==RESULTS/'baseline':continue
        if path.parent.parent.name=='chunks':continue
        destination=path.with_name('attempt_records.jsonl.gz')
        with gzip.open(destination,'wt',encoding='utf-8',compresslevel=9) as handle:
            for record in read_records(path):
                for key in ['sample_keys','influence','time_grid']:record.pop(key,None)
                if str(record.get('model','')).startswith('E_'):
                    key={k:record.get(k) for k in ['universe','outcome','horizon','scope','country','variant','model','moderator','exposure_last_year']}
                    record['specification_id']=hashlib.sha256(json.dumps(key,sort_keys=True).encode()).hexdigest()[:20]
                def clean(v):
                    if isinstance(v,list):return [clean(x) for x in v]
                    if isinstance(v,dict):return {k:clean(x) for k,x in v.items()}
                    if isinstance(v,float) and not np.isfinite(v):return None
                    return v
                handle.write(json.dumps(clean(record),allow_nan=False)+'\n')
        directories.append(dict(path=str(destination.relative_to(BASE)),bytes=destination.stat().st_size))
    save_csv(pd.DataFrame(directories),AUDIT/'permanent_attempt_records.csv')


def notebook(coverage,chunks,main,marginals,dispersion,pages):
    counts=[]
    for p in sorted((RESULTS/'chunks').glob('*/COMPLETED.json')):counts.append(json.loads(p.read_text()))
    summary=pd.DataFrame(counts)
    table=coverage[['universe','frequency','raw_shock_countries','issuers','gdp_eligible','cpi_eligible','last']].to_markdown(index=False)
    global_rows=chunks[chunks.term.eq('interaction')&chunks.scope.eq('global')&chunks.variant.eq('all')].copy()
    global_rows=global_rows[((global_rows.frequency.eq('A'))&global_rows.horizon.eq(2))|
                            ((global_rows.frequency.eq('Q'))&global_rows.horizon.eq(8))]
    cols=['chunk','universe','outcome','horizon','estimate','se','p_raw','p_block_wild_informational','n','n_countries','n_issuers']
    results=global_rows[[x for x in cols if x in global_rows]].to_markdown(index=False,floatfmt='.5g')
    snapshot=dict(baseline_attempted=int(coverage.attempted.sum()),baseline_estimated=int(coverage.estimated.sum()),
        chunk_attempted=int(summary.specifications.sum()),chunk_estimated=int(summary.estimated.sum()),
        chunks=summary.moderator.tolist(),country_IRF_pages=pages,
        observed_rate_economies=len(pd.read_csv(AUDIT/'policy_rate_country_source_selection.csv')),
        unresolved_national_source_searches=True,full_catalogue_complete=False)
    (AUDIT/'atlas_summary.json').write_text(json.dumps(snapshot,indent=2))
    text=f'''# Global Monetary Transmission Atlas — empirical notebook

Snapshot: **22 November 2026**. Real data and executed Local Projections; exploratory results, not a finished paper.

## Executed work

Baseline specifications attempted: **{snapshot['baseline_attempted']:,}**; estimated: **{snapshot['baseline_estimated']:,}**. Four one-characteristic chunks: **{', '.join(snapshot['chunks'])}**; specifications attempted: **{snapshot['chunk_attempted']:,}**; estimated: **{snapshot['chunk_estimated']:,}**. Exclusions, null results, common-shock absorption and failures are retained in the attempt records. Counts include prespecified horizons, groups and sensitivity specifications; they are not counts of independent scientific discoveries.

Raw policy/discount/refinancing rates cover **{snapshot['observed_rate_economies']} countries and territories**. Country coverage is different from independent monetary authority coverage. The worldwide external-Fed experiment is explicitly a separate spillover design; it does not fill gaps in domestic shock identification.

## What is genuinely current

USMPD raw event observations reach **28 October 2026**. The PCA factor was independently reproduced with maximum absolute error 1.53e-16, followed by an explicitly labelled JK-style monetary/information decomposition. The current EA-EMPD contains meetings through **11 June 2026** and speeches through **30 June 2026**. The old JK method was first reproduced on the old raw workbook (maximum monthly error 8.56e-9), then re-estimated on the current meeting observations. UKMPD official target/path factors reach **30 April 2026** and stay separate from the other instruments.

The newest-named BDY download still ends in 2022. CWY annual observations end in 2019 and mix six identification classes; approximately 60% of their country-year observations inherit anchor shocks. Actual country-year sources are saved. Annual and quarterly Taylor-rule reconstructions extend history using observed IMF/BIS policy rates and genuine macro observations. They are weaker-identification innovations, not exogenous market surprises. Their first-stage uncertainty is not included in the LP HAC standard errors.

## Effective country LP coverage

Eligibility requires at least 20 annual or 40 quarterly observations, sufficient nonzero shock variation and full rank. Not every downloaded macro observation satisfies these requirements.

{table}

![Eligible country coverage](figures/eligible_country_coverage.png)

## One structural characteristic at a time

The LP has shock, shock × Z, lagged Z and one lag of outcome growth, with country/calendar effects where identified and seasonality where needed. Annual characteristics retain annual observation dates and enter quarterly equations only as prior-calendar-year exposure states. Annual GDP/CPI are never interpolated into quarters. Quarterly CPI averages require three observed months.

The four executed chunks concern general-government debt/GDP (F01), domestic sovereign creditors outside the central bank/GDP (F04), principal refinancing within one year (R01), and net energy imports/energy use (E01). F01/F04 scale Z by 10 percentage points of GDP; R01 by a 0.10 portfolio share; E01 by 10 percentage points of energy use. Source portfolios and definitions are recorded. Remaining registry items are unstarted.

## Global interactions at prespecified horizons

These are two-year or eight-quarter interactions. Positive gamma means a higher response at higher Z; it is not an expansionary total response. Annual country-SD units and event basis-point units are different estimands.

{results}

Raw HAC p-values remain visible. The calendar-block wild diagnostic can materially weaken an apparently small raw p-value; few time blocks limit this diagnostic too. BH q-values are provided as information in coefficient files. None selects the reported model or deletes a null.

## What the first chunks reveal

- **Debt/GDP:** BDY daily-event identification shows a positive GDP interaction at eight quarters (approximately +0.109 percentage point per 10-bp factor and +10 pp debt/GDP; raw p approximately 0.001; block-wild p approximately 0.045). This does not establish an expansionary total response. The broad CWY and current ECB reconstructions do not provide uniform confirmation.
- **Creditor residence:** the single-characteristic specification does not provide a uniform positive income-channel result. The current ECB price interaction can be negative, while output estimates vary with horizon and the set of supported countries. This simpler specification is not the old repository's creditor reallocation contrast conditional on other debt stocks.
- **Refinancing:** the current ECB price interaction at eight quarters is +0.445 per 10-bp factor and +10 pp of principal due within one year (raw p 0.029; calendar-block wild p 0.098; 15 countries sharing one issuer). The weaker block diagnostic and null BDY/CWY comparisons prevent a robust inflationary-channel conclusion.
- **Net energy imports:** the prespecified two-year/eight-quarter GDP and CPI global interactions are insignificant at 5% in all seven supported comparison families. This is an informative null in this simple model, not evidence that energy structure never matters.

The exact fixed-exposure conditional responses, with covariance propagated from beta and gamma, are in `results/conditional_response_grid.csv`. When time effects absorb a common shock main effect, only relative exposure responses are identified; no absolute conditional response is invented.

## Country heterogeneity

`results/baseline/dispersion_block_bootstrap.csv` compares observed cross-country dispersion with the sampling dispersion generated by shared calendar-block perturbations of the actual country LP scores. This retains common currency-union innovations and correlated global residuals. A simple variance-minus-average-standard-error calculation is only descriptive. Country means, medians, sign changes and peak horizons are saved. Peak timing is selected descriptively and does not receive an unadjusted significance claim.

At eight quarters the approximate common-response dispersion diagnostic gives p = 0.118 for BDY GDP and p = 0.460 for the current ECB GDP reconstruction. The CWY annual GDP comparison at two years gives p = 0.060. Thus the apparent spread of country point estimates is not, by itself, decisive evidence of structural heterogeneity beyond sampling noise. These diagnostics use limited calendar blocks and are not formal proof of homogeneity either.

`figures/country_IRFs.pdf` contains **{pages} country/territory pages**, with real-GDP and CPI responses at native annual and quarterly frequencies where eligible. The index names the exact selected shock family for each country/frequency. Other estimated families and every horizon remain in the coefficient files. Positive point estimates are never automatically labelled expansionary.

## Files for checking the findings

- [Country IRF book](figures/country_IRFs.pdf) and [page index](figures/country_IRF_index.csv).
- [F01 debt](notebooks/chunk_F01.md), [F04 ownership](notebooks/chunk_F04.md), [R01 refinancing](notebooks/chunk_R01.md), [E01 energy](notebooks/chunk_E01.md).
- [Numerical validation](audit/numerical_validation.json), [fresh shock endpoints](audit/fresh_shocks_actual_endpoints.csv), [worldwide country gaps](audit/worldwide_country_gap_inventory.csv).
- Coefficient files retain raw p-values, standard errors, intervals, dates, N, country/issuer counts, identification status and informational q-values. Compact permanent model records also retain the complete economic coefficient covariance and diagnostic metadata. Large internal score arrays/sample-key lists can be regenerated from saved panels, code and sample-key hashes.

## Completed, partial and unstarted

Completed: worldwide source audit and macro expansion; specified shock reconstructions and their numerical overlap checks; the saved baseline universe; four named core chunks, including country/state, panel/group, separate external-Fed and supported early-exposure association diagnostics.

Partial: adding genuinely quarterly CPI histories for economies with short monthly reporting (notably Australia/New Zealand), exhaustive domestic shock identification for every state, searches of every national central-bank archive, current common-authority reaction rules outside the euro area, country-specific high-frequency/narrative replacements, fully harmonized sovereign portfolio definitions, generated-Taylor-shock bootstrap uncertainty, all requested institutional/regime comparisons, and every possible country/sensitivity graph.

Unstarted: the rest of the structural-variable registry and the portion of the user's catalogue absent after the truncated F10 item. Public download failures are recorded; no observations are manufactured to close gaps. Unfinished tasks do not continue in the background.
'''
    (BASE/'RESEARCH_NOTEBOOK.md').write_text(text)
    return snapshot


def run():
    checkpoint('report','running')
    registry();baseline,chunks=coefficient_frames();main=country_summaries(baseline)
    coverage=effective_coverage();plot_coverage(coverage);plot_chunks(chunks)
    marginal=marginal_responses();dispersion=dispersion_bootstrap()
    pages=plot_country_book(main)
    compact_exports()
    result=notebook(coverage,chunks,main,marginal,dispersion,pages)
    checkpoint('report','completed',**result)
    return result


if __name__=='__main__':run()
