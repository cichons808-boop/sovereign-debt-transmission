"""Interpretation, source support and fixed-dictionary sensitivity diagnostics."""
import json,gc,hashlib
import numpy as np
import pandas as pd
from scipy.stats import t
from scipy.linalg import lstsq
import selection as ml
from local_projection import fit,nuisance
from specification import setup
from reporting_families import record,difference
from simultaneous_inference import correct

def derivative(g,label,names):
    if label.startswith('MP_group_'):return float((g.est_group==label[len('MP_group_'):]).mean())
    if label.startswith('focal_'):return float(g['a_'+label[len('focal_'):]].mean())
    if label in ['MP_growth_state','MP_inflation_state']:return float(g[label[len('MP_'):]].mean())
    if label.startswith('macro_') and label.endswith('_mp'):return float(g[label[:-3]].mean())
    return 0.

def mean_response(v,names,ex,method):
    g=v['g'];raw,labels=nuisance(g,names,'Q');raw=np.column_stack([raw,g[ex].to_numpy(float)]);labels+=ex
    if method=='full':use=np.ones(len(labels),bool)
    else:
        c,q,r,w,wr,optional,_=ml.designs(v,names,ex)
        chosen=ml.select_controls(c,q,w,wr,v['Y'],v['F'],g.time_index.to_numpy(int),r)[0] if method=='pds' else np.zeros(len(optional),bool)
        selected={optional[j] for j in np.flatnonzero(chosen)};use=np.array([ml.mandatory(s) or s in selected for s in labels])
    xx=np.column_stack([raw[:,use],v['F']]);labs=[s for s,k in zip(labels,use) if k]+['focal_'+n for n in names]
    a=np.array([derivative(g,s,names) for s in labs]);sc=np.linalg.norm(xx,axis=0);sc[sc==0]=1
    u,sv,vh=np.linalg.svd(xx/sc,full_matrices=False);rank=int((sv>max(xx.shape)*np.finfo(float).eps*sv[0]*20).sum());vh=vh[:rank];u=u[:,:rank];sv=sv[:rank]
    az=a/sc;projection=vh.T@(vh@az);err=float(np.linalg.norm(az-projection)/max(np.linalg.norm(az),1e-12))
    result=dict(estimator=method,estimable=err<1e-7,relative_estimability_error=err,n=len(g),rank=rank)
    if result['estimable']:
        weight=u@((vh@az)/sv);coef=float(weight@v['Y']);beta=vh.T@((u.T@v['Y'])/sv);e=v['Y']-(xx/sc)@beta
        ti=g.time_index.to_numpy(int);psi=np.zeros(ti.max()-ti.min()+1);np.add.at(psi,ti-ti.min(),weight*e)
        factor=g.time_index.nunique()/(g.time_index.nunique()-1)*(len(g)-1)/(len(g)-rank);psi*=np.sqrt(factor)
        var=psi@psi
        for lag in range(1,min(12,len(psi)-1)+1):var+=2*(1-lag/13)*(psi[lag:]@psi[:-lag])
        se=float(np.sqrt(var));crit=t.ppf(.975,g.time_index.nunique()-1)
        result.update(estimate=coef,se=se,ci_low=coef-crit*se,ci_high=coef+crit*se,p_value=float(2*t.sf(abs(coef/se),g.time_index.nunique()-1)))
    return result

def main():
    data=ml.populations();allfits=json.loads((ml.R/'ml_lp.json').read_text());means=[];scale=[];loos=[]
    for sample in ['ea','advanced','emerging']:
        d,ex,names=setup(data[sample],'rollover',sample!='ea')
        for h in [4,8,12]:
            _,v=fit(d,names,'rollover','log_gdp',h,additional_nuisance=ex,return_validation=True)
            for method in ['minimal','full','pds']:
                r=mean_response(v,names,ex,method);r.update(sample=sample,outcome='log_gdp',horizon=h);means.append(r)
                ff=next(f for f in allfits if f['sample']==sample and f['estimator']==method and f['outcome']=='log_gdp' and f['horizon']==h)
                k=names.index('domestic_noncb');j=names.index('domestic_noncb_x_refinancing');a=np.zeros(len(names));a[k]=1;a[j]=float(v['g'].rollover_centered.mean())
                b=float(a@np.array(ff['beta']));se=float(np.sqrt(a@np.array(ff['covariance_HAC'])@a));p=v['g'].domestic_noncb;within=float((p-p.groupby(v['g'].country).transform('mean')).std())
                scale.append(dict(sample=sample,estimator=method,horizon=h,reference_contrast=ff['beta'][k],mean_refinancing=float(v['g'].refinance_share.mean()),at_mean_refinancing=b,se_at_mean_refinancing=se,within_ownership_sd=within,sd_ownership_contrast_at_mean_r=b*within/10,shock_sd_bp=float(v['g'].mp.std()*10),one_shock_sd_and_ownership_sd=b*within/10*float(v['g'].mp.std()),average_response_estimable=r['estimable'],average_response=r.get('estimate')))
            del v;gc.collect()
        if sample!='ea':
            for out,hs in [('log_gdp',[4,8,12]),('log_prices',[1,2,4,8,12] if sample=='advanced' else [4,8,12])]:
                for h in hs:
                    for country in sorted(data[sample].loc[data[sample].ea_member,'country'].unique()):
                        _,v=fit(d,names,'rollover',out,h,additional_nuisance=ex,omit_country=country,return_validation=True)
                        f=ml.estimate(v,names,ex,'pds')
                        for e in f['estimates']:
                            if e['term'] in ml.FOCAL:loos.append(dict(sample=sample,outcome=out,horizon=h,omitted_country=country,n=f['n'],p=f['p'],selected_count=f['selected_count'],**e))
                        del v;gc.collect()
                    print('PDS omissions',sample,out,h,flush=True)
        pd.DataFrame(means).to_csv(ml.R/'ml_mean_responses.csv',index=False);pd.DataFrame(scale).to_csv(ml.R/'ml_economic_scale.csv',index=False);pd.DataFrame(loos).to_csv(ml.R/'ml_leave_one_out.csv',index=False)
    # FX attrition is identified row by row, before any fitted comparison.
    base=data['advanced'].copy();fx=pd.read_csv(ml.D/'currency_states.csv')[['country','hold_year','fx_share','fx_source']]
    base=base.drop(columns=['fx_share','fx_source'],errors='ignore').merge(fx,on=['country','hold_year'],how='left',validate='many_to_one')
    d,ex,names=setup(base,'rollover',True);cols={};a=d.fx_share/.1;cols['currency_level']=a
    for sh in ['mp','info']:
        lab='currency_'+sh;cols[lab]=d[sh]*a
        for lag in [1,2]:cols[lab+f'_l{lag}']=cols[lab].groupby(d.country).shift(lag)
    aug=pd.concat([d,pd.DataFrame(cols,index=d.index)],axis=1);fxfits=[];default=ml.mandatory
    for out in ['log_gdp','log_prices']:
        for h in [4,8,12]:
            _,va=fit(aug,names,'rollover',out,h,additional_nuisance=ex+list(cols),return_validation=True)
            matched=d.copy();matched['ea_member']&=matched.index.isin(va['g'].index)
            _,vb=fit(matched,names,'rollover',out,h,additional_nuisance=ex,return_validation=True);assert np.array_equal(va['g'].index,vb['g'].index)
            for vv,ee,role in [(vb,ex,'FX support baseline'),(va,ex+list(cols),'FX controls forced')]:
                ml.mandatory=(lambda s:default(s) or s.startswith('currency_')) if role=='FX controls forced' else default
                f=ml.estimate(vv,names,ee,'pds');f.update(sample='advanced',outcome=out,horizon=h,model='rollover',variant=role);fxfits.append(f)
            ml.mandatory=default
            if out=='log_gdp' and h==8:
                _,vfull=fit(d,names,'rollover',out,h,additional_nuisance=ex,return_validation=True)
                lost=vfull['g'].loc[~vfull['g'].index.isin(va['g'].index),['country','period','fx_share']].copy()
                lost['reason']=np.where(lost.fx_share.isna(),'current lagged annual FX state unavailable','lagged FX-shock interaction unavailable')
                assert len(lost)==100;lost.to_csv(ml.R/'ml_fx_attrition_rows.csv',index=False)
                lost.groupby(['country','reason']).agg(n=('period','size'),first=('period','min'),last=('period','max')).to_csv(ml.R/'ml_fx_attrition_summary.csv')
    ml.dump(fxfits,'ml_currency_control')
    # Quarterly-vs-seasonal current account definition on exact GDP8 support.
    ca=[]
    for sample in ['ea','advanced','emerging']:
        base=data[sample].copy();d,ex,names=setup(base,'rollover',sample!='ea');_,v=fit(d,names,'rollover','log_gdp',8,additional_nuisance=ex,return_validation=True)
        base['ca_state']=base.groupby('country').ca_state.transform(lambda s:s.rolling(4,min_periods=4).mean());dd,ee,nn=setup(base,'rollover',sample!='ea');dd['ea_member']&=dd.index.isin(v['g'].index)
        _,va=fit(dd,nn,'rollover','log_gdp',8,additional_nuisance=ee,return_validation=True);assert np.array_equal(v['g'].index,va['g'].index)
        for method in ['full','pds']:
            f=ml.estimate(va,nn,ee,method);f.update(sample=sample,outcome='log_gdp',horizon=8,model='rollover',variant='four-quarter mean current-account state');ca.append(f)
    ml.dump(ca,'ml_current_account_sensitivity')
    # ECB series comparison: identical countries, shock dates, controls, outcomes.
    common=data['ea_bolhuis'].copy();jk=data['ea'].set_index(['country','period']);harmonized=[]
    for origin in ['bolhuis','jk']:
        base=common.copy()
        if origin=='jk':
            index=pd.MultiIndex.from_frame(base[['country','period']]);base['MP_median']=jk.MP_median.reindex(index).to_numpy();base['CBI_median']=jk.CBI_median.reindex(index).to_numpy()
        d,ex,names=setup(base,'rollover',True)
        for out in ['log_gdp','log_prices','log_reer','debt_ratio_observed']:
            for h in [4,8,12]:
                _,v=fit(d,names,'rollover',out,h,additional_nuisance=ex,return_validation=True)
                for method in ['full','pds']:
                    f=ml.estimate(v,names,ex,method);f.update(sample='ea_bolhuis',outcome=out,horizon=h,model='rollover',shock_origin=origin,pair_sha256=hashlib.sha256(v['g'][['country','period']].to_csv(index=False).encode()).hexdigest());harmonized.append(f)
        print('Harmonized ECB',origin,flush=True)
    for a in harmonized:
        b=next(f for f in harmonized if f['shock_origin']!=a['shock_origin'] and all(f[k]==a[k] for k in ['outcome','horizon','estimator']));assert a['pair_sha256']==b['pair_sha256']
    ml.dump(harmonized,'ml_ecb_harmonized')
    # Simultaneous VARX bands and focal cross-setting differences, same score law.
    vf=json.loads((ml.R/'ml_var.json').read_text());records=[]
    for f in vf:
        for j,e in enumerate(f['estimates']):
            records.append(dict(sample=f['sample'],model='pds_varx',n=f['n'],countries=f['countries'],p=f['p'],df=f['df'],start=f['time_start'],end=f['time_end'],psi=np.array(f['irf_influence_by_time'])[:,j],**e))
    # Vector order agrees with term, horizon and equation order in VAR output.
    for out in ['log_gdp','log_prices','log_reer']:
        for h in [4,8,12]:
            for term in ml.FOCAL:
                a=next(r for r in records if r['sample']=='advanced' and r['outcome']==out and r['horizon']==h and r['term']==term)
                b=next(r for r in records if r['sample']=='emerging' and r['outcome']==out and r['horizon']==h and r['term']==term)
                lo=min(a['start'],b['start']);hi=max(a['end'],b['end']);psi=np.zeros(hi-lo+1)
                for sign,r in [(1,a),(-1,b)]:psi[r['start']-lo:r['end']-lo+1]+=sign*r['psi']
                var=psi@psi
                for lag in range(1,min(12,len(psi)-1)+1):var+=2*(1-lag/13)*(psi[lag:]@psi[:-lag])
                se=float(np.sqrt(var));coef=a['estimate']-b['estimate'];df=min(a['df'],b['df']);crit=t.ppf(.975,df)
                records.append(dict(a,sample='advanced minus emerging',start=lo,end=hi,psi=psi,estimate=coef,se=se,df=df,ci_low=coef-crit*se,ci_high=coef+crit*se,p_value=float(2*t.sf(abs(coef/se),df))))
    rows=correct('var_full_curves',records);pd.DataFrame(rows).to_csv(ml.R/'ml_var_simultaneous.csv',index=False)
    print('Audit complete',flush=True)
if __name__=='__main__':main()
