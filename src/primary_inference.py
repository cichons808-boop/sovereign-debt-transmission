from pathlib import Path
import os,sys,json,itertools
os.environ['OPENBLAS_NUM_THREADS']='1'
os.environ['OMP_NUM_THREADS']='1'
import numpy as np
import pandas as pd
from scipy.stats import t as student_t

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT
import selection as ml
from sensitivity import mean_response
from local_projection import fit
from specification import setup
OUT=BASE/'results';OUT.mkdir(parents=True,exist_ok=True)

def wild(v,names,extra):
    c,q,r,w,wr,labels,_=ml.designs(v,names,extra)
    chosen,_=ml.select_controls(c,q,w,wr,v['Y'],v['F'],v['g'].time_index.to_numpy(int),r)
    nuisance=np.column_stack([c,w[:,chosen]])
    j=names.index('domestic_noncb_x_refinancing')
    _,q0,r0,_=ml.independent(np.column_stack([nuisance,np.delete(v['F'],j,axis=1)]))
    _,qx,rank,_=ml.independent(np.column_stack([nuisance,v['F']]))
    y=v['Y']; target=v['F'][:,j];z=target-q0@(q0.T@target);zz=z@z
    e0=y-q0@(q0.T@y);e=y-qx@(qx.T@y);b=float(z@y/zz)
    countries,gi=np.unique(v['g'].country.to_numpy(),return_inverse=True);G=len(countries);n=len(y)
    fact=G/(G-1)*(n-1)/(n-rank)
    scores=np.bincount(gi,weights=z*e,minlength=G)
    se=np.sqrt(fact*(scores@scores))/zz;tobs=b/se
    def stats(weights):
        values=[]
        for start in range(0,len(weights),300):
            wy=e0[:,None]*weights[start:start+300,gi].T
            bs=z@wy/zz;res=wy-qx@(qx.T@wy)
            sc=np.zeros((G,res.shape[1]))
            np.add.at(sc,gi,z[:,None]*res)
            ses=np.sqrt(fact*np.sum(sc*sc,axis=0))/zz
            values.extend((bs/ses).tolist())
        return np.asarray(values)
    weights=np.column_stack([np.ones(2**(G-1)),np.array(list(itertools.product([-1.,1.],repeat=G-1)))])
    exact=stats(weights)
    rng=np.random.default_rng(20261019)
    webb=stats(rng.choice([-np.sqrt(1.5),-1.,-np.sqrt(.5),np.sqrt(.5),1.,np.sqrt(1.5)],size=(9999,G)))
    return dict(estimate=b,country_cluster_se=se,country_cluster_t=tobs,
        country_cluster_p=2*student_t.sf(abs(tobs),G-1),
        rademacher_p=float(np.mean(np.abs(exact)>=abs(tobs)-1e-12)),
        webb_p=float((1+np.sum(np.abs(webb)>=abs(tobs)))/(len(webb)+1)),
        n=n,rank=rank,countries=G,patterns=len(weights),webb_draws=len(webb),
        selected_count=int(chosen.sum()),conditional_on_selected_controls=True)

def main():
    data=ml.populations();means=[];wilds=[];old=json.loads((BASE/'results/ml_lp.json').read_text())
    for sample in ['advanced','emerging']:
        d,ex,names=setup(data[sample],'rollover',True)
        for outcome in ['log_gdp','log_prices']:
            for h in [1,2,4,8,12]:
                _,v=fit(d,names,'rollover',outcome,h,additional_nuisance=ex,return_validation=True)
                mr=mean_response(v,names,ex,'pds');mr.update(sample=sample,outcome=outcome,horizon=h);means.append(mr)
                if sample=='advanced' and outcome=='log_prices' and h in [1,2,4]:
                    b=wild(v,names,ex);b.update(sample=sample,outcome=outcome,horizon=h)
                    reference=next(f for f in old if f['sample']==sample and f['outcome']==outcome and f['horizon']==h and f['estimator']=='pds')
                    j=names.index('domestic_noncb_x_refinancing')
                    assert abs(b['estimate']-reference['beta'][j])<1e-8
                    wilds.append(b)
                print(sample,outcome,h,mr.get('estimate'),flush=True)
    pd.DataFrame(means).to_csv(OUT/'mean_responses_gdp_prices.csv',index=False)
    pd.DataFrame(wilds).to_csv(OUT/'primary_PDS_wild_bootstrap.csv',index=False)
    print(pd.DataFrame(wilds).to_string(index=False),flush=True)

if __name__=='__main__':main()
