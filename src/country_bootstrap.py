"""Null-imposed WCR11, exact enumeration of bootstrap *weights*, not an exact test.

The compressed calculation below is algebraically the same as refitting the
unrestricted regression in every draw and calculating its CR1 studentizer.
Country clustering allows unrestricted dependence within a country, but assumes
independence across countries; it complements, rather than dominates, time HAC.
"""
import json
import numpy as np
import pandas as pd
from scipy.linalg import qr
from scipy.stats import t
from local_projection import P, DATA, RES, fit, prepared
from international_data import external_controls
from macro_data import ISO2

SEED=20261018



def wild(f,v,term,validate=False):
    j=f['coefficient_names'].index(term)
    Z=v['Z'];Y=v['Y'];F=v['F'];X0=v['X0']
    q=Z@np.linalg.inv(Z.T@Z)[:,j]
    b=f['beta'][j];r=q/(q@q)
    eR=v['e']+b*r
    codes,levels=pd.factorize(v['g'].country,sort=True);G=len(levels);n=len(Y);p=f['p']
    Q=qr(np.column_stack([X0,F]),mode='economic',check_finite=False)[0]
    assert Q.shape[1]==p
    R=np.zeros((n,G));R[np.arange(n),codes]=eR
    a=q@R;H=Q.T@R
    L=np.zeros((G,p));np.add.at(L,codes,q[:,None]*Q)
    K=np.diag(a)-L@H
    cf=G/(G-1)*(n-1)/(n-p)
    sco=np.bincount(codes,weights=q*v['e'],minlength=G)
    observed_se=np.sqrt(cf*(sco@sco))
    target_se=np.sqrt(np.array(f['covariance_country_cluster'])[j,j])
    assert abs(observed_se-target_se)<1e-8
    t_obs=b/observed_se
    # All 2**G sign patterns reduce to 2**(G-1) for a two-sided t statistic.
    integers=np.arange(2**(G-1),dtype=np.uint32)
    W=np.ones((len(integers),G));W[:,1:]=2*((integers[:,None]>>np.arange(G-1))&1)-1.
    def student(weights):
        bs=weights@a;sc=weights@K.T
        se=np.sqrt(cf*np.sum(sc**2,axis=1))
        return bs/se
    tr=student(W)
    pr=float(np.mean(np.abs(tr)>=abs(t_obs)-1e-12))
    rng=np.random.default_rng(SEED)
    webb=np.array([-np.sqrt(1.5),-1.,-np.sqrt(.5),np.sqrt(.5),1.,np.sqrt(1.5)])
    WW=webb[rng.integers(0,6,size=(9999,G))]
    tw=student(WW);pw=float((1+np.sum(np.abs(tw)>=abs(t_obs)))/10000)
    validation_error=0.
    if validate:
        # Direct QR full OLS refits and CR1 residual scores for 20 independent
        # draws catch incorrect null restriction, projection or studentization.
        for w,tc in zip(WW[:20],tw[:20]):
            ys=eR*w[codes]
            direct_b=q@ys;es=ys-Q@(Q.T@ys)
            cs=np.bincount(codes,weights=q*es,minlength=G)
            td=direct_b/np.sqrt(cf*(cs@cs))
            validation_error=max(validation_error,abs(td-tc))
        assert validation_error<1e-8
    return dict(term=term,estimate=float(b),n=n,countries=G,
        se_country_cluster=float(observed_se),t_country_cluster=float(t_obs),
        p_country_cluster=float(2*t.sf(abs(t_obs),G-1)),
        p_wcr11_rademacher=pr,rademacher_patterns=len(W),p_wcr11_webb=pw,webb_draws=9999,
        bootstrap_validation_max_error=float(validation_error))


