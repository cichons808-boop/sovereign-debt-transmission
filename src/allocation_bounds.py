"""Observed-data allocation bounds, not bounds on a causal LP coefficient.

Marginal owner and remaining-maturity distributions do not identify their
joint distribution. We quantify the ambiguity and then use actual original-
maturity cells to tighten it where both tables share the same reference year.
"""
import json
import numpy as np
import pandas as pd
from scipy.optimize import linprog
from local_projection import P,DATA,RES

def lp_bounds(r,with_original=False):
    # Variables: remaining-short NF, private financial, CB, foreign;
    # and unobserved original-short holdings of the CB within S12.
    eps=.05  # Each percent-of-GDP input is rounded to one decimal place.
    nf=float(r.nonfinancial);fin=float(r.financial);cb=float(r.cb);fr=float(r.foreign)
    if min(nf,fin-cb,cb,fr)<-.11:return None
    caps=np.maximum([nf,fin-cb,cb,fr],0)+np.array([eps,3*eps,eps,eps])
    S=float(r.due_within_year)
    A=[np.r_[np.ones(4),0],np.r_[-np.ones(4),0]];b=[S+eps,-S+eps]
    bounds=[(0,float(c)) for c in caps]+[(0,float(cb+eps))]
    if with_original:
        a,bf,c=float(r.short_nonfinancial),float(r.short_financial),float(r.short_foreign)
        A += [np.array([-1,0,0,0,0]),np.array([0,0,0,-1,0]),
              np.array([0,-1,0,0,-1]),np.array([0,0,-1,0,1]),np.array([0,0,0,0,1])]
        b += [-a+eps,-c+eps,-bf+eps,0,bf+eps]
    objective=np.array([1,1,0,0,0])
    lo=linprog(objective,A_ub=np.array(A),b_ub=b,bounds=bounds,method='highs')
    hi=linprog(-objective,A_ub=np.array(A),b_ub=b,bounds=bounds,method='highs')
    if not lo.success or not hi.success:return None
    return float(lo.fun),float(-hi.fun)

def main():
    q=pd.read_csv(DATA/'panel_quarterly.csv.gz')
    q=q[q.ea_member.astype(bool)&q.MP_median.notna()].dropna(subset=['debt','domestic_noncb','refinance_share']).copy()
    q['remaining_short_total']=q.debt*q.refinance_share
    q['short_domestic_noncb_lower']=np.maximum(0,q.domestic_noncb+q.remaining_short_total-q.debt)
    q['short_domestic_noncb_upper']=np.minimum(q.domestic_noncb,q.remaining_short_total)
    q['ambiguity_fraction_of_all_short_debt']=(q.short_domestic_noncb_upper-q.short_domestic_noncb_lower)/q.remaining_short_total
    q['independence_allocation']=q.domestic_noncb*q.refinance_share
    cols=['country','period','source','maturity_source','debt','domestic_noncb','cb','foreign','refinance_share',
          'remaining_short_total','short_domestic_noncb_lower','short_domestic_noncb_upper','ambiguity_fraction_of_all_short_debt','independence_allocation']
    q[cols].to_csv(RES/'marginal_allocation_bounds.csv',index=False)
    ee=pd.read_csv(DATA/'holdings_annual_eurostat.csv');rm=pd.read_csv(DATA/'maturity_annual_eurostat.csv');j=pd.read_csv(DATA/'joint_original_maturity.csv')
    both=ee.merge(rm,on=['country','year'],suffixes=('','_rmd')).merge(j,on=['country','year'],suffixes=('','_joint'))
    both['rmd_total']=both.due_within_year/both.refinance_share
    both=both.dropna(subset=['debt','nonfinancial','financial','cb','foreign','due_within_year','rmd_total'])
    both=both[(both.rmd_total-both.debt).abs()<.25].copy()
    rows=[];failures=[]
    for _,r in both.iterrows():
        a=lp_bounds(r,False);b=lp_bounds(r,True)
        if a is None or b is None:failures.append(dict(country=r.country,year=int(r.year)));continue
        assert b[0]>=a[0]-1e-8 and b[1]<=a[1]+1e-8
        rows.append(dict(country=r.country,year=int(r.year),debt=r.debt,remaining_short_total=r.due_within_year,
            marginal_lower=a[0],marginal_upper=a[1],original_informed_lower=b[0],original_informed_upper=b[1],
            marginal_width=a[1]-a[0],original_informed_width=b[1]-b[0],
            proportional_width_reduction=1-(b[1]-b[0])/(a[1]-a[0])))
    pair=pd.DataFrame(rows);pair.to_csv(RES/'original_informed_allocation_bounds.csv',index=False)
    summary=dict(interpretation='Bounds on the allocation of remaining-short debt to resident non-central-bank holders; not causal-effect bounds and not observed joint remaining-maturity holdings',
        primary_marginal_observations=len(q),primary_countries=q.country.nunique(),
        median_ambiguity_fraction=float(q.ambiguity_fraction_of_all_short_debt.median()),
        fraction_with_full_allocation_ambiguity=float((q.ambiguity_fraction_of_all_short_debt>.999999).mean()),
        matched_Eurostat_country_years=len(pair),matched_Eurostat_countries=pair.country.nunique(),
        median_width_before=float(pair.marginal_width.median()),median_width_after=float(pair.original_informed_width.median()),
        median_proportional_reduction=float(pair.proportional_width_reduction.median()),
        infeasible_due_to_rounded_or_incompatible_cells=failures,
        rounding_rule='Input intervals of +/-0.05 percentage point GDP, private-financial subtraction tolerance +/-0.15. Remaining-short total within +/-0.05. Require same-year total debt agreement within 0.25 pp GDP.',
        maturity_caveat='The first panel calculation combines general-government ownership with DGM marketable-debt maturity where used. The tightening exercise uses only same-year Eurostat S13 tables.')
    (RES/'allocation_bounds_summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary,indent=2),flush=True)

if __name__=='__main__':main()
