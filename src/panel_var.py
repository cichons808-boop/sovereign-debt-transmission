"""PDS panel VARX: identified monetary shocks, unpenalized dynamics and exposures.

GDP, prices and REER enter as quarterly log changes. Four endogenous lags and
six current monetary-state regressors are never penalized. State paths and
other exogenous innovations are held fixed in the response calculation.
"""
import os
os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
import json,gc,hashlib
import numpy as np
import pandas as pd
from scipy.stats import t
from scipy.linalg import lstsq
import selection as ml
from specification import setup
from local_projection import fit,nuisance
VARS=['log_gdp','log_prices','log_reer'];H=12;L=4

def var_design(g,names,ex):
    x,labels=nuisance(g,names,'Q');x=np.column_stack([x,g[ex].to_numpy(float)]);labels+=ex
    def keep(s):
        if s.startswith(('growth_l','inflation_l')) or s in ['macro_reer_state','growth_state','inflation_state']:return False
        if s.startswith(('MP_','CBI_')) and '_lag' in s:return False
        if s.startswith('macro_') and (('_mp_l' in s) or ('_info_l' in s)):return False
        return True
    eligible=[j for j,s in enumerate(labels) if keep(s)]
    force=[j for j in eligible if ml.mandatory(labels[j])];optional=[j for j in eligible if not ml.mandatory(labels[j])]
    c,q,rank,piv=ml.independent(x[:,force]);w=x[:,optional];wr=w-q@(q.T@w)
    yes=np.linalg.norm(wr,axis=0)>1e-9*np.maximum(1,np.linalg.norm(w,axis=0))
    return c,q,rank,w[:,yes],wr[:,yes],[labels[optional[j]] for j in np.flatnonzero(yes)],[labels[force[j]] for j in piv]

def responses(theta,k):
    # Rows of theta are regressors, columns are equations.
    a=np.stack([theta[k+3*l:k+3*(l+1)].T for l in range(L)])
    result=[]
    for j in [1,4]:
        seq=[theta[j].copy()]
        for h in range(1,H+1):seq.append(sum(a[l-1]@seq[h-l] for l in range(1,min(L,h)+1)))
        result.append(np.cumsum(np.asarray(seq),axis=0))
    return np.asarray(result)

def main():
    config=dict(model='Post-double-selection panel VARX',endogenous=VARS,transformation='first differences of 100 log levels',lags=L,shock='original observed high-frequency monetary and information surprises',focal='six current shock-by-debt/refinancing terms',mandatory_dynamics='all twelve endogenous lag coefficients in every equation',optional='original nuisance dictionary without lagged exogenous shock products',penalty='same centered quarterly-HAC plugin PDS penalty as the LP',response='conditional on fixed future fiscal states and zero further exogenous innovations',inference='joint multiequation HAC(12), complex-step delta method',support='exact common country-quarter rows for all LP benchmarks and the VARX')
    (ml.P/'config/var.json').write_text(json.dumps(config,indent=2)+'\n')
    populations=ml.populations();results=[];matched=[];keys=[]
    for sample in ['ea','advanced','emerging']:
        data=populations[sample].copy()
        for v in VARS:
            data['dy_'+v]=data.groupby('country')[v].diff()
            for lag in range(1,L+1):data[f'var_{v}_l{lag}']=data.groupby('country')['dy_'+v].shift(lag)
        d,ex,names=setup(data,'rollover',sample!='ea')
        _,vg=fit(d,names,'rollover','log_gdp',12,additional_nuisance=ex,return_validation=True)
        _,vp=fit(d,names,'rollover','log_prices',12,additional_nuisance=ex,return_validation=True)
        idx=vg['g'].index.intersection(vp['g'].index)
        lagcols=[f'var_{v}_l{lag}' for lag in range(1,L+1) for v in VARS]
        ycols=['dy_'+v for v in VARS]
        idx=d.loc[idx].dropna(subset=lagcols+ycols).index
        d['ea_member']&=d.index.isin(idx)
        _,support=fit(d,names,'rollover','log_gdp',12,additional_nuisance=ex,return_validation=True)
        g=support['g'];idx=g.index;d['ea_member']&=d.index.isin(idx)
        c,q,rank,w,wr,labels,mandatory_labels=var_design(g,names,ex)
        F=np.column_stack([g[['f_'+n for n in names]].to_numpy(float),g[lagcols].to_numpy(float)])
        Y=g[ycols].to_numpy(float);fnames=names+lagcols
        chosen,logs=ml.select_controls(c,q,w,wr,Y,F,g.time_index.to_numpy(int),rank)
        cc=np.column_stack([c,w[:,chosen]]);cc,qq,rr,_=ml.independent(cc)
        z=F-qq@(qq.T@F);yr=Y-qq@(qq.T@Y);bread=np.linalg.inv(z.T@z);theta=bread@(z.T@yr);e=yr-z@theta
        n=len(g);p=rr+F.shape[1];T=int(g.time_index.nunique());ti=g.time_index.to_numpy(int);lo=int(ti.min());hi=int(ti.max())
        rowinf=(z@bread)[:,:,None]*e[:,None,:];influence=np.zeros((hi-lo+1,F.shape[1],3));np.add.at(influence,ti-lo,rowinf)
        influence=influence.reshape(len(influence),-1);factor=T/(T-1)*(n-1)/(n-p);influence*=np.sqrt(factor)
        cov=influence.T@influence
        for lag in range(1,min(12,len(influence)-1)+1):
            a=influence[lag:].T@influence[:-lag];cov+=(1-lag/13)*(a+a.T)
        irf=responses(theta,len(names));jac=np.zeros((irf.size,theta.size))
        for j in range(theta.size):
            b=theta.astype(complex);b.flat[j]+=1e-20j;jac[:,j]=responses(b,len(names)).imag.reshape(-1)/1e-20
        ircov=jac@cov@jac.T;irinf=influence@jac.T
        a=np.stack([theta[len(names)+3*l:len(names)+3*(l+1)].T for l in range(L)])
        companion=np.zeros((3*L,3*L));companion[:3]=np.hstack(a);companion[3:,:-3]=np.eye(3*(L-1));radius=float(max(abs(np.linalg.eigvals(companion))))
        rows=[];crit=t.ppf(.975,T-1)
        for j,term in enumerate(ml.FOCAL):
            for h in range(H+1):
                for k,out in enumerate(VARS):
                    pos=np.ravel_multi_index((j,h,k),irf.shape);b=float(irf[j,h,k]);se=float(np.sqrt(max(ircov[pos,pos],0)))
                    rows.append(dict(term=term,horizon=h,outcome=out,estimate=b,se=se,ci_low=b-crit*se,ci_high=b+crit*se,p_value=float(2*t.sf(abs(b/se),T-1))))
        keyhash=hashlib.sha256(g[['country','period']].to_csv(index=False).encode()).hexdigest()
        result=dict(sample=sample,estimator='pds_varx',model='conditional VARX',n=n,p=p,residual_df=n-p,countries=int(g.country.nunique()),country_names=sorted(g.country.unique()),time_periods=T,df=T-1,time_start=lo,time_end=hi,
            first_period=g.period.min(),last_period=g.period.max(),selected_count=int(chosen.sum()),optional_candidates=len(labels),selected_labels=[labels[j] for j in np.flatnonzero(chosen)],mandatory_labels=mandatory_labels,selection_equations=logs,all_lasso_converged=all(x['converged'] for x in logs),spectral_radius=radius,stable=radius<1,pair_sha256=keyhash,coefficient_names=fnames,theta=theta.tolist(),coefficient_covariance_HAC=cov.tolist(),estimates=rows,irf_shape=list(irf.shape),irf_influence_by_time=irinf.tolist())
        results.append(result)
        kk=g[['country','period']].copy();kk['sample']=sample;keys.append(kk)
        for out in ['log_gdp','log_prices']:
            for h in [4,8,12]:
                _,v=fit(d,names,'rollover',out,h,additional_nuisance=ex,return_validation=True)
                assert np.array_equal(v['g'].index,idx)
                for method in ['minimal','full','pds']:
                    f=ml.estimate(v,names,ex,method);f.update(sample=sample,outcome=out,horizon=h,model='rollover',pair_sha256=keyhash);matched.append(f)
                del v;gc.collect()
        print('VARX',sample,'n',n,'p',p,'selected',int(chosen.sum()),'radius',radius,flush=True)
        (ml.R/'ml_var.json').write_text(json.dumps(results,indent=2,allow_nan=False)+'\n');ml.dump(matched,'ml_var_matched_lp')
        pd.DataFrame([dict(sample=f['sample'],n=f['n'],p=f['p'],selected_count=f['selected_count'],spectral_radius=f['spectral_radius'],**e) for f in results for e in f['estimates']]).to_csv(ml.R/'ml_var.csv',index=False)
        pd.concat(keys).to_csv(ml.R/'ml_var_sample_keys.csv',index=False)
        del vg,vp,support,g,c,q,w,wr,F,Y,cc,qq,z,e,rowinf,influence;gc.collect()
if __name__=='__main__':main()
