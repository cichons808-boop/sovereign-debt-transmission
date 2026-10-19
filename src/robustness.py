"""Country influence, currency exposure and finite-sample diagnostics.

Runs complete leave-one-out sets, a single motivated FX-debt specification with
its exact-support baseline, and null-imposed wild-country inference. No row is
removed from the reported main estimates on the basis of these diagnostics.
"""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from local_projection import fit,prepared
from specification import setup,EM
from international_data import external_controls
from country_bootstrap import wild

P=Path(__file__).resolve().parents[1];D=P/'data/processed';R=P/'results';HS=[4,8,12]
TERMS=['domestic_noncb','domestic_noncb_x_refinancing']

def dump(n,x):(R/('fiscal_'+n+'.json')).write_text(json.dumps(x,indent=2,allow_nan=False)+'\n')
def flat(f,**extra):
    return [{**{k:f.get(k) for k in ['sample','model','outcome','horizon','n','p','countries','df','time_periods']},**extra,**e} for e in f.get('estimates',[]) if e['term'] in TERMS]

def main():
    own=pd.read_csv(D/'fiscal_panel_external.csv.gz',float_precision='round_trip');own['ea_member']=own.ea_member.astype(bool)
    own.loc[own.country.eq('US'),['Fed_MP','Fed_CBI']]=0.
    allfits=json.loads((R/'fiscal_main.json').read_text());df=[]
    for f in allfits:
        if f['model']=='rollover' and f['horizon'] in HS:
            df.append({k:f[k] for k in ['sample','model','outcome','horizon','n','p','countries','time_periods','df']}|{'residual_df':f['n']-f['p'],'focal_parameters':len(f['coefficient_names']),'nuisance_parameters':f['nuisance_rank']})
    pd.DataFrame(df).to_csv(R/'fiscal_model_dimensions.csv',index=False)
    loo=[];boots=[];scales=[];within=[]
    for sample in ['advanced','emerging']:
        data=own.copy();data['ea_member']&=~data.country.isin(EM) if sample=='advanced' else data.country.isin(EM)
        d,ex,names=setup(data,'rollover',True)
        for out in ['log_gdp','log_prices']:
            for h in HS:
                f,v=fit(d,names,'rollover',out,h,additional_nuisance=ex,return_validation=True);f['sample']=sample
                for term in TERMS:
                    w=wild(f,v,term,validate=(h==8 and out=='log_gdp'))
                    e=next(e for e in f['estimates'] if e['term']==term)
                    boots.append(dict(w,sample=sample,outcome=out,horizon=h,p_HAC=e['p_value']))
                if h==8 and out=='log_gdp':
                    g=v['g'];mp=g.mp.to_numpy();sd=float(np.std(mp,ddof=1))
                    bp=10*sd
                    for e in f['estimates']:
                        if e['term'] in TERMS:scales.append(dict(sample=sample,outcome=out,horizon=h,term=e['term'],shock_sd_bp=bp,estimate_10bp=e['estimate'],estimate_one_sd=e['estimate']*sd))
                    g=g.copy();g['ownership_gdp']=g.a_domestic_noncb*10
                    for state in ['ownership_gdp','debt','refinance_share']:
                        if state not in g:continue
                        a=g[state].astype(float);de=a-a.groupby(g.country).transform('mean')
                        within.append(dict(sample=sample,state=state,n=len(a),overall_sd=float(a.std()),within_sd=float(de.std()),within_variance_share=float(de.var()/a.var())))
                for country in f['country_names']:
                    z=fit(d,names,'rollover',out,h,additional_nuisance=ex,omit_country=country);z['sample']=sample
                    loo.extend(flat(z,omitted_country=country,status=z['status']))
                print('Leave-one-out',sample,out,h,'done',flush=True)
    pd.DataFrame(loo).to_csv(R/'fiscal_leave_one_out.csv',index=False)
    pd.DataFrame(boots).to_csv(R/'fiscal_wild_bootstrap.csv',index=False)
    assert len(pd.read_csv(R/'fiscal_leave_one_out.csv'))==228
    assert len(pd.read_csv(R/'fiscal_wild_bootstrap.csv'))==24
    pd.DataFrame(scales).to_csv(R/'fiscal_effect_scaling.csv',index=False)
    pd.DataFrame(within).to_csv(R/'fiscal_within_variation.csv',index=False)
    # FX share: BIS C4 same-portfolio long-term general-government securities,
    # foreign currency / (domestic currency + foreign currency), preceding year.
    fx=pd.read_csv(D/'currency_states.csv')[['country','hold_year','fx_share','fx_source']]
    own=own.drop(columns=['fx_share','fx_source'],errors='ignore').merge(fx,on=['country','hold_year'],how='left',validate='many_to_one')
    fxrows=[];fxfits=[]
    for sample in ['own','advanced','emerging']:
        base=own.copy()
        if sample=='advanced':base['ea_member']&=~base.country.isin(EM)
        if sample=='emerging':base['ea_member']&=base.country.isin(EM)
        d,ex,names=setup(base,'rollover',True);cols={};a=d.fx_share/.1;cols['currency_level']=a
        for sh in ['mp','info']:
            lab='currency_'+sh;cols[lab]=d[sh]*a
            for lag in [1,2]:cols[lab+f'_l{lag}']=cols[lab].groupby(d.country).shift(lag)
        aug=pd.concat([d,pd.DataFrame(cols,index=d.index)],axis=1)
        for out in ['log_gdp','log_prices']:
            for h in HS:
                got=fit(aug,names,'rollover',out,h,additional_nuisance=ex+list(cols),return_validation=True)
                if not isinstance(got,tuple):fxrows.append(dict(sample=sample,outcome=out,horizon=h,variant='FX control',**got));continue
                f,v=got;matched=d.copy();matched['ea_member']&=matched.index.isin(v['g'].index)
                b,vb=fit(matched,names,'rollover',out,h,additional_nuisance=ex,return_validation=True)
                assert np.array_equal(v['g'].index,vb['g'].index)
                for ff,variant in [(b,'matched baseline'),(f,'FX control')]:
                    ff.update(sample=sample,variant=variant);fxfits.append(ff);fxrows.extend(flat(ff,variant=variant))
        print('Currency control',sample,'done',flush=True)
    pd.DataFrame(fxrows).to_csv(R/'fiscal_currency_control.csv',index=False);dump('currency_control',fxfits)
    print(pd.DataFrame(boots).query('outcome=="log_gdp" and horizon==8')[['sample','term','p_HAC','p_wcr11_rademacher','p_wcr11_webb']].to_string(index=False))
    dump('diagnostics_validation',dict(status='passed',leave_one_out_rows=len(loo),wild_bootstrap_rows=len(boots),FX_matched_rows=True,
        wild_refit_max_error=max(b['bootstrap_validation_max_error'] for b in boots),no_main_observations_removed=True))

if __name__=='__main__':main()
