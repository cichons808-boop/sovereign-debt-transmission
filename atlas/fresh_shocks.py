"""Reconstruct current public event shocks and validate published methodology.

ECB: Jarocinski--Karadi algorithm on current EA-EMPD GC_ME observations.
US: reproduce Acosta et al. official PCA code, then an explicitly labelled
    JK-style monetary/information decomposition (our construction, not author data).
UK: use the official target/path/QE factors as distinct series, never splice.
"""
from __future__ import annotations

import io
import json
import zipfile

import numpy as np
import pandas as pd

from .data import (AUDIT, BASE, EA_ENTRY, PROCESSED, RAW, URLS, country_metadata,
                   fetch, prepare_lags, quarterly_macro, save_csv)

FRESH_URLS = {
    'ea_mpd_current_other.xlsx':'https://www.ecb.europa.eu/pub/pdf/other/Dataset_EA-MPD.xlsx',
    'ea_mpd_latest.xlsx':'https://www.ecb.europa.eu/pub/pdf/annex/Dataset_EA-MPD.xlsx',
    'usmpd_latest.xlsx':'https://www.frbsf.org/wp-content/uploads/USMPD.xlsx?2026-11-20',
    'usmpd_surprises.zip':'https://www.frbsf.org/wp-content/uploads/monetary-policy-surprises.zip?2026-11-20',
    'ukmpd_latest.xlsx':'https://www.bankofengland.co.uk/-/media/boe/files/working-paper/2023/measuring-monetary-policy-in-the-uk-the-ukmpesd.xlsx',
    'gsw_yields_current.csv':'https://www.federalreserve.gov/data/yield-curve-tables/feds200628.csv',
    'jk_main.m':'https://raw.githubusercontent.com/marekjarocinski/jkshocks_update_ecb/main/code/main.m',
    'jk_mypc.m':'https://raw.githubusercontent.com/marekjarocinski/jkshocks_update_ecb/main/code/mypc.m',
    'jk_signrestr_median.m':'https://raw.githubusercontent.com/marekjarocinski/jkshocks_update_ecb/main/code/signrestr_median.m',
}
URLS.update(FRESH_URLS)


def median_rotation(matrix,quantile=.5):
    """Direct translation of author's signrestr_median.m (QR, not VAR)."""
    matrix=np.asarray(matrix,float)
    mask=np.isfinite(matrix).all(axis=1)
    clean=matrix[mask]
    q,r=np.linalg.qr(clean,mode='reduced')
    signs=np.diag(np.sign(np.diag(r)))
    q=q@signs;r=signs@r
    if r[0,1]>0:
        angle=(1-quantile)*np.arctan(r[0,1]/r[1,1])+quantile*np.pi/2
    else:
        angle=quantile*np.arctan(-r[1,1]/r[0,1])
    rot=np.array([[np.cos(angle),np.sin(angle)],[-np.sin(angle),np.cos(angle)]])
    diag=np.diag([r[0,0]*np.cos(angle),r[0,0]*np.sin(angle)])
    result=np.full_like(matrix,np.nan)
    result[mask]=q@rot@diag
    effects=np.linalg.solve(diag,rot.T@r)
    assert effects[0,1]<0 and effects[1,1]>0
    assert np.max(np.abs(result[mask].sum(axis=1)-clean[:,0]))<1e-10
    return result,dict(angle=float(angle),loading_matrix=effects.tolist(),
        uncentered_cross_product=float(result[mask,0]@result[mask,1]),n=int(mask.sum()))


def jk_pc(frame,stock='STOXX50'):
    columns=['OIS_1M','OIS_3M','OIS_6M','OIS_1Y']
    source=frame[columns].apply(pd.to_numeric,errors='coerce')
    x=source.fillna(0).to_numpy(float)
    x=x/x.std(axis=0,ddof=1)
    u,s,v=np.linalg.svd(x,full_matrices=False)
    score=u[:,0]*s[0]
    # MATLAB's PCA sign convention: largest absolute loading is positive.
    score*=np.sign(v[0,np.argmax(np.abs(v[0]))])
    score[source.isna().all(axis=1)]=np.nan
    raw=score/np.nanstd(score,ddof=1)*source.OIS_1Y.std()/100
    raw=np.round(raw,8)
    stocks=pd.to_numeric(frame[stock],errors='coerce').to_numpy(float)
    matrix=np.column_stack([raw,stocks])
    components,diagnostics=median_rotation(matrix)
    out=pd.DataFrame(dict(date=pd.to_datetime(frame.date),pc1=raw,equity=stocks,
        mp_poor_man=raw*(raw*stocks<0),info_poor_man=raw*(raw*stocks>=0),
        mp_median=components[:,0],info_median=components[:,1]))
    return out,diagnostics


def ecb_reconstruct():
    # First reproduce the old published monthly series on its ORIGINAL raw data.
    old=pd.read_excel(fetch('ea_mpd_latest.xlsx'),sheet_name='Monetary Event Window')
    old['date']=pd.to_datetime(old.date,dayfirst=True)
    excluded=pd.to_datetime(['2001-09-13','2001-09-17','2008-10-08'])
    old=old[~old.date.isin(excluded)].reset_index(drop=True)
    rebuilt,old_diag=jk_pc(old)
    rebuilt['month']=rebuilt.date.dt.to_period('M')
    old_month=rebuilt.groupby('month').mp_median.sum()
    published=pd.read_csv(fetch('jk_ecb_monthly.csv'))
    published['month']=pd.PeriodIndex.from_fields(year=published.year,month=published.month,freq='M')
    comparison=published.merge(old_month.rename('reproduced'),on='month',how='inner')
    error=float((comparison.MP_median-comparison.reproduced).abs().max())
    if error>1e-6:raise AssertionError('JK legacy replication failed: '+str(error))
    old_diag.update(legacy_monthly_max_absolute_error=error,legacy_months_compared=len(comparison))
    save_csv(comparison.assign(month=comparison.month.astype(str)),AUDIT/'jk_legacy_replication_check.csv')
    current=pd.read_excel(fetch('ea_mpd_current_other.xlsx'),sheet_name='EA-EMPD')
    current['date']=pd.to_datetime(current.Date_time).dt.normalize()
    meetings=current[current.Event_type.eq('GC_ME') & ~current.date.isin(excluded)].copy()
    rebuilt,diagnostics=jk_pc(meetings,stock='STOXX50E')
    rebuilt['issuer']='ECB';rebuilt['construction']='JK_median_on_EA_EMPD_GC_ME_our_reconstruction'
    # Same-date comparison is diagnostic only: the current quote methodology
    # and the PCA/rotation estimation sample differ, so don't splice vintages.
    overlap=rebuilt.merge(jk_pc(old)[0],on='date',suffixes=('_current','_old'))
    diagnostics.update(old_diag)
    diagnostics.update(current_last_event=str(rebuilt.date.max().date()),current_events=len(rebuilt),
        common_events=len(overlap),overlap_mp_correlation=float(overlap.mp_median_current.corr(overlap.mp_median_old)),
        newly_available_events=int((rebuilt.date>old.date.max()).sum()),
        not_official_JK_release=True,full_history_reestimated=True,
        speeches_excluded_to_preserve_event_definition=True)
    save_csv(rebuilt,PROCESSED/'fresh_ECB_event_shocks.csv')
    (AUDIT/'ecb_reconstruction_validation.json').write_text(json.dumps(diagnostics,indent=2))
    return rebuilt


def us_pc(frame,yields):
    columns=['MP1','MP2','ED2','ED3','ED4']
    d=frame.dropna(subset=columns).copy()
    x=d[columns].to_numpy(float)
    x=(x-x.mean(axis=0))/x.std(axis=0,ddof=1)
    u,s,v=np.linalg.svd(x,full_matrices=False)
    score=u[:,0]*s[0]
    dates=pd.to_datetime(d.Date).dt.normalize()
    join=pd.DataFrame(dict(date=dates,score=score)).merge(yields,on='date',how='left')
    valid=join.dropna()
    slope=np.linalg.lstsq(np.column_stack([np.ones(len(valid)),valid.score]),valid.dy1,rcond=None)[0][1]
    return pd.DataFrame(dict(date=dates,pc1=slope*score)),dict(normalization_slope=float(slope),
        normalization_n=len(valid),event_n=len(d),normalization_yields_last=str(yields.date.max().date()))


def us_reconstruct():
    package=zipfile.ZipFile(fetch('usmpd_surprises.zip'))
    yields=pd.read_csv(io.BytesIO(package.read('y1.csv')))
    yields['date']=pd.to_datetime(yields.Date);yields['dy1']=yields.SVENY01.diff()
    yields=yields[['date','dy1']]
    source=pd.read_excel(fetch('usmpd_latest.xlsx'),sheet_name='Monetary Events')
    rebuilt,diagnostics=us_pc(source,yields)
    official=pd.read_csv(io.BytesIO(package.read('mps.csv')))
    official['date']=pd.to_datetime(official.Date)
    compare=rebuilt.merge(official[['date','ME']],on='date')
    diagnostics['official_factor_max_abs_error']=float((compare.pc1-compare.ME).abs().max())
    diagnostics['official_factor_correlation']=float(compare.pc1.corr(compare.ME))
    # The package's yield normalization vintage need not match its CSV vintage.
    # If the scale differs, retain the official published factor for the new
    # decomposition and report the exact scale discrepancy; never silently rescale.
    diagnostics['exact_factor_replication']=bool(diagnostics['official_factor_max_abs_error']<1e-8)
    diagnostics['median_official_to_rebuilt_scale']=float((compare.ME/compare.pc1).replace([np.inf,-np.inf],np.nan).median())
    official=official.rename(columns={'ME':'pc1'})
    source['date']=pd.to_datetime(source.Date).dt.normalize()
    merged=official[['date','pc1']].merge(source[['date','SP500','SPFUT']],on='date',validate='one_to_one')
    # USMPD has actual S&P futures for all events; preserve that uniform
    # instrument, rather than silently switching between cash and futures.
    merged['equity']=pd.to_numeric(merged.SPFUT,errors='coerce')
    components,rotation=median_rotation(merged[['pc1','equity']].to_numpy(float))
    merged['mp_median']=components[:,0];merged['info_median']=components[:,1]
    merged['mp_poor_man']=merged.pc1*(merged.pc1*merged.equity<0)
    merged['info_poor_man']=merged.pc1*(merged.pc1*merged.equity>=0)
    merged['issuer']='USA';merged['construction']='JK_style_on_official_USMPD_ME_PC_our_decomposition'
    diagnostics.update(rotation)
    diagnostics.update(latest_event=str(merged.date.max().date()),equity_instrument='SPFUT',
                       not_official_pure_MP_release=True,raw_factor_source='author_provided_mps.csv')
    save_csv(compare,AUDIT/'us_pca_replication_check.csv')
    save_csv(merged,PROCESSED/'fresh_USA_event_shocks.csv')
    (AUDIT/'usa_reconstruction_validation.json').write_text(json.dumps(diagnostics,indent=2))
    return merged


def uk_factors():
    factors=pd.read_excel(fetch('ukmpd_latest.xlsx'),sheet_name='factors')
    surprises=pd.read_excel(fetch('ukmpd_latest.xlsx'),sheet_name='surprises')
    factors['date']=pd.to_datetime(factors.Datetime).dt.normalize()
    factors['issuer']='GBR';factors['construction']='official_UKMPD_Target_Path_QE_separate'
    save_csv(factors,PROCESSED/'fresh_GBR_event_factors.csv')
    readme=pd.read_excel(fetch('ukmpd_latest.xlsx'),sheet_name='readme',header=None)
    notes='\n'.join(' | '.join(str(v) for v in row if pd.notna(v)) for row in readme.values)
    (AUDIT/'ukmpd_source_notes.txt').write_text(notes)
    return factors


def quarterly_events(events,value,issuer,*,verified_last_complete_month):
    """Native event sums. Partial terminal quarters stay out of quarterly LPs."""
    d=events.copy();d['quarter']=pd.PeriodIndex(d.date,freq='Q')
    first=d.quarter.min()+1
    month=pd.Period(verified_last_complete_month,freq='M')
    last=month.asfreq('Q') if month.month%3==0 else month.asfreq('Q')-1
    idx=pd.period_range(first,last,freq='Q')
    q=d.groupby('quarter')[value].sum(min_count=1).reindex(idx)
    counts=d.groupby('quarter')[value].agg(['count','size'])
    incomplete=counts.index[counts['count'].ne(counts['size'])]
    q.loc[q.index.isin(incomplete)]=np.nan
    # Empty quarters stay missing; no external monetary-policy calendar here.
    out=pd.DataFrame(dict(period=idx.astype(str),shock_raw=q.values,issuer=issuer))
    out['time']=idx.year*4+idx.quarter-1
    save_csv(out,PROCESSED/f'fresh_{issuer}_{value}_complete_quarters.csv')
    return out


def attach_current(events,issuer,name,unit,last_month,value='mp_median'):
    macro=quarterly_macro(country_metadata())
    if issuer=='ECB':
        macro=macro[macro.country.isin(EA_ENTRY)].copy()
        macro=macro[macro.apply(lambda row:row.time>=EA_ENTRY[row.country],axis=1)]
    else:macro=macro[macro.country.eq(issuer)].copy()
    q=quarterly_events(events,value,issuer,verified_last_complete_month=last_month)
    d=macro.merge(q,on=['period','time'],how='left',validate='many_to_one')
    d['shock']=d.shock_raw/.1;d['normalization_scale']=.1
    d['issuer']=issuer;d['shock_unit']=unit
    d['universe']=name;d['frequency']='Q';d['inherited']=False
    d['shared_union_shock']=issuer=='ECB'
    d['source_method']='reconstructed_intraday_sign_rotation' if value=='mp_median' else 'official_UKMPD_'+value
    d=prepare_lags(d)
    save_csv(d,PROCESSED/(name+'.csv.gz'))
    return d


def run():
    ecb=ecb_reconstruct();usa=us_reconstruct();uk=uk_factors()
    panels=[attach_current(ecb,'ECB','H_ECB_reconstructed_2026','10bp_OIS1Y_scaled_MP_factor','2026-06'),
        attach_current(usa,'USA','H_USA_reconstructed_2026','10bp_GSW1Y_scaled_intraday_MP_component','2026-09')]
    # UKMPD factors have their own normalization; don't label them basis-point
    # policy surprises without the normalization evidence. Keep source-unit runs.
    for factor in ['Target','Path']:
        d=attach_current(uk,'GBR','H_GBR_'+factor+'_2026','UKMPD_'+factor+'_source_unit','2026-03',value=factor)
        d['shock']=d.shock_raw
        d['normalization_scale']=1.0
        save_csv(d,PROCESSED/(d.universe.iloc[0]+'.csv.gz'));panels.append(d)
    coverage=[]
    for name,d,value in [('ECB',ecb,'mp_median'),('USA',usa,'mp_median'),('GBR',uk,'Target')]:
        coverage.append(dict(issuer=name,first_event=str(d.date.min()),last_event=str(d.date.max()),
            observations=len(d),nonmissing=int(d[value].notna().sum()),
            source_frequency='event',current_relative_to_2026_11_22=True))
    save_csv(pd.DataFrame(coverage),AUDIT/'fresh_shocks_actual_endpoints.csv')
    return panels


if __name__=='__main__':
    for panel in run():
        print(panel.universe.iloc[0],panel.shock.count(),panel.loc[panel.shock.notna(),'period'].max(),flush=True)
