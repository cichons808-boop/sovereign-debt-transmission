"""Check source integrity, sample construction, estimates and published quantities."""
from pathlib import Path
import json,hashlib
import numpy as np
import pandas as pd
P=Path(__file__).resolve().parents[1];R=P/'results';D=P/'data/processed'

def main():
    source=pd.read_csv(P/'data/sources.csv',keep_default_na=False)
    for row in source.itertuples():
        f=P/row.file
        assert f.stat().st_size==row.bytes
        assert hashlib.sha256(f.read_bytes()).hexdigest()==row.sha256
    for name in ['fiscal_panel_ea','fiscal_panel_external']:
        d=pd.read_csv(D/(name+'.csv.gz'))
        assert not d.duplicated(['country','period']).any()
        assert d.groupby('country').time_index.diff().dropna().eq(1).all()
        assert (d.debt-d.foreign-d.cb-d.domestic_noncb).abs().max()<1e-9
        z=d.dropna(subset=['ownership_measurement_period'])
        assert (pd.PeriodIndex(z.ownership_measurement_period,freq='Q')<pd.PeriodIndex(z.period,freq='Q')).all()
    allfits=[]
    for name in ['ml_lp', 'ml_accumulation', 'ml_forced_spillover_sensitivity', 'ml_var_matched_lp', 'ml_currency_control', 'ml_ecb_harmonized', 'ml_current_account_sensitivity', 'mechanisms']:
        fits=json.loads((R/(name+'.json')).read_text())
        for f in fits:
            if f.get('status','ok')!='ok':continue
            assert f['n']>f['p']+5
            assert f.get('all_lasso_converged',True)
            cov=np.array(f['covariance_HAC'])
            assert np.max(np.abs(cov-cov.T))<1e-8
            assert np.linalg.eigvalsh(cov).min()>-1e-8
            for j,e in enumerate(f['estimates']):
                assert abs(e['se']**2-cov[j,j])<1e-8
            allfits.append(f)
    import fitz
    figures=list((P/'output/figures').glob('*.pdf'))
    for f in figures:
        assert f.read_bytes().rstrip().endswith(b'%%EOF')
        with fitz.open(f) as doc:assert len(doc)==1
    report=dict(verified_figure_files=len(figures),status='passed',raw_source_files=len(source),regression_fits=len(allfits),source_hashes_verified=True,complete_calendars=True,predetermined_ownership=True,creditor_identity=True,positive_semidefinite_covariances=True,all_selectors_converged=True)
    a=pd.read_csv(R/'ml_lp.csv')
    assert len(json.loads((R/'ml_lp.json').read_text()))==396
    for h,b in [(1,.3067268174069027),(2,.34882819731908804),(4,.3734709211380104)]:
        z=a[a['sample'].eq('advanced')&a.estimator.eq('pds')&a.outcome.eq('log_prices')&a.horizon.eq(h)&a.term.eq('domestic_noncb_x_refinancing')].iloc[0]
        assert abs(z.estimate-b)<1e-7 and z.n==728
    s=pd.read_csv(R/'ml_simultaneous.csv')
    assert s.groupby('family').size().to_dict()=={'channels':90,'forced_spillovers':36,'full_curves':168,'main':48}
    w=pd.read_csv(R/'primary_PDS_wild_bootstrap.csv')
    assert len(w)==3 and w.patterns.eq(1024).all() and w.webb_draws.eq(9999).all()
    v=json.loads((R/'ml_var.json').read_text());assert all(x['stable'] for x in v)
    ref=json.loads((R/'ml_validation.json').read_text());assert ref['status']=='passed'
    engine=json.loads((R/'engine_validation.json').read_text())
    assert engine['status']=='passed' and engine['regression']['designs_checked']==54
    mechanism=pd.read_csv(R/'mechanism_contrasts.csv')
    assert len(mechanism)==36 and mechanism.family_size.eq(36).all()
    mfits=json.loads((R/'mechanisms.json').read_text())
    assert len(mfits)==12
    for f in mfits:
        assert f['n']==(728 if f['sample']=='advanced' else 403)
        assert f['countries']==(11 if f['sample']=='advanced' else 8)
    report.update(matrix_engine_verified=True,independent_SVD_designs=54,
                  mechanism_family_size=36,mechanism_support_preserved=True)
    report.update(primary_price_h2=float(a[a['sample'].eq('advanced')&a.estimator.eq('pds')&a.outcome.eq('log_prices')&a.horizon.eq(2)&a.term.eq('domestic_noncb_x_refinancing')].iloc[0].estimate),LP_reporting_families=s.groupby('family').size().to_dict(),stable_VAR_systems=len(v),independent_numerical_validation=True)
    (R/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
