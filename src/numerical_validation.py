"""Numerical checks against independent full OLS and VAR simulations."""
import json
import numpy as np
from selection import P,R,independent,select_controls,hac_loadings
from panel_var import responses

def algorithm_check():
    rng=np.random.default_rng(20261018);n=2000;p=30
    w=rng.normal(size=(n,p));x=w[:,0]+.8*w[:,1]+rng.normal(size=n)
    y=.6*x+1.5*w[:,0]-1.2*w[:,1]+rng.normal(size=n)
    c,q,rank,_=independent(np.ones((n,1)));wr=w-q@(q.T@w);time=np.arange(n)
    chosen,logs=select_controls(c,q,w,wr,y,x[:,None],time,rank)
    scaled,_=select_controls(c,q,w,wr,y,7*x[:,None],time,rank)
    assert chosen[0] and chosen[1] and np.array_equal(chosen,scaled)
    design=np.column_stack([c,w[:,chosen],x]);coef=np.linalg.lstsq(design,y,rcond=None)[0][-1]
    assert abs(coef-.6)<.08 and all(z['converged'] for z in logs)
    constant=hac_loadings(np.ones((100,1)),np.ones(100),np.arange(100),1)
    assert constant[0]<1e-6
    result=dict(known_coefficient=.6,estimated=float(coef),selected_indices=np.flatnonzero(chosen).tolist(),all_lasso_converged=True,target_scale_invariance=True,centered_score_check=True,seed=20261018,n=n,candidates=p)
    (R/'ml_algorithm_validation.json').write_text(json.dumps(result,indent=2)+'\n')
    return result

def main():
    algorithm_check()
    full=json.loads((R/'fiscal_accumulation.json').read_text());new=json.loads((R/'ml_accumulation.json').read_text());errors=[]
    for f in new:
        if f['estimator']!='full':continue
        old=next(a for a in full if a['variant']=='debt accumulation' and all(a[k]==f[k] for k in ['sample','outcome','horizon']))
        assert f['n']==old['n'];err=float(max(abs(np.array(f['beta'])-old['beta'])));assert err<1e-7;errors.append(err)
    vf=json.loads((R/'ml_var.json').read_text());simulation=[];gradient=[]
    for f in vf:
        theta=np.array(f['theta']);ir=responses(theta,6);a=[theta[6+3*l:6+3*(l+1)].T for l in range(4)]
        for j in [0,1]:
            b=theta[[1,4][j]];history=[];level=np.zeros(3)
            for h in range(13):
                dy=(b if h==0 else np.zeros(3))+sum(a[l-1]@history[h-l] for l in range(1,min(4,h)+1));history.append(dy);level+=dy
                simulation.append(float(max(abs(level-ir[j,h]))))
        for pos in [3,4,15,20,31,45]:
            plus=theta.copy();minus=theta.copy();plus.flat[pos]+=1e-6;minus.flat[pos]-=1e-6
            finite=(responses(plus,6)-responses(minus,6))/2e-6
            cm=theta.astype(complex);cm.flat[pos]+=1e-20j;exact=responses(cm,6).imag/1e-20
            gradient.append(float(np.max(abs(finite-exact))))
    assert max(simulation)<1e-10 and max(gradient)<1e-7
    for name in ['ml_lp','ml_accumulation','ml_forced_spillover_sensitivity','ml_var_matched_lp','ml_currency_control','ml_ecb_harmonized']:
        fits=json.loads((R/(name+'.json')).read_text());assert all(f['all_lasso_converged'] for f in fits)
    original=json.loads((R/'input_hashes.json').read_text())
    import hashlib
    for path,expected in original.items():assert hashlib.sha256((P/path).read_bytes()).hexdigest()==expected
    output=dict(status='passed',all_regularized_models_converged=True,estimation_inputs_unchanged=True,accumulation_full_model_max_error=max(errors),VAR_direct_simulation_max_error=max(simulation),VAR_delta_gradient_max_error=max(gradient),selection_validation=json.loads((R/'ml_algorithm_validation.json').read_text()),LP_full_model_validation=json.loads((R/'ml_lp_validation.json').read_text()))
    (R/'ml_validation.json').write_text(json.dumps(output,indent=2)+'\n');print({k:v for k,v in output.items() if k not in ['LP_full_model_validation','selection_validation']})
if __name__=='__main__':main()
