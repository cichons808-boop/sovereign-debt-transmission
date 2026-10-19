"""Publication tables and figures from the regularized transmission estimates."""
from pathlib import Path
import json,hashlib
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from exhibit_style import table,save,clean,number,pv,INK,TEAL,GOLD,GRAY,LABEL
P=Path(__file__).resolve().parents[1]/'output';R=P.parent/'results';T=P/'tables'
TERMS=['domestic_noncb','domestic_noncb_x_refinancing'];HS=[4,8,12];GROUPS=['ea','advanced','emerging']
LAB=LABEL|{'ea_bolhuis':'Euro area (Bolhuis)','advanced minus emerging':'Advanced minus emerging'}
OUT={'log_gdp':'GDP','log_prices':'Prices','log_reer':'REER','debt_ratio_observed':'Debt/GDP'}

def main():
    all=pd.read_csv(R/'ml_lp.csv');d=all[all.estimator.eq('pds')];adj=pd.read_csv(R/'ml_simultaneous.csv');var=pd.read_csv(R/'ml_var_simultaneous.csv');vf=pd.read_csv(R/'ml_var.csv');matched=pd.read_csv(R/'ml_var_matched_lp.csv')
    def pa(s,o,h,k,fam='main'):
        z=adj[adj['sample'].eq(s)&adj.outcome.eq(o)&adj.horizon.eq(h)&adj.term.eq(k)&adj.family.eq(fam)]
        return pv(z.iloc[0].p_maxT) if len(z) else '--'
    def pick(s,o,h,k,method='pds',data=all):return data[data['sample'].eq(s)&data.outcome.eq(o)&data.horizon.eq(h)&data.term.eq(k)&data.estimator.eq(method)].iloc[0]
    for out,name in [('log_gdp','ml_gdp'),('log_prices','ml_prices')]:
        rows=[]
        for s in GROUPS:
            for h in HS:
                b=pick(s,out,h,TERMS[0]);g=pick(s,out,h,TERMS[1]);rows.append([LAB[s],h,number(b.estimate),pv(b.p_value),pa(s,out,h,b.term),number(g.estimate),pv(g.p_value),pa(s,out,h,g.term),f'{int(b.n):,}/{int(b.countries)}'])
        table(name,['Setting','$h$',r'$\beta_P$','$p$',r'$p_{\max}$',r'$\gamma_P$','$p$',r'$p_{\max}$','$N/G$'],rows,'lrrrrrrrr')
    rows=[]
    for out in ['log_gdp','log_prices']:
        for h in HS:
            for k,tl in zip(TERMS,[r'$\beta_P$',r'$\gamma_P$']):
                z=adj[adj.family.eq('main')&adj['sample'].eq('advanced minus emerging')&adj.outcome.eq(out)&adj.horizon.eq(h)&adj.term.eq(k)].iloc[0]
                rows.append([OUT[out],h,tl,number(z.estimate),'['+number(z.ci_low)+', '+number(z.ci_high)+']',pv(z.p_value),pv(z.p_maxT)])
    table('ml_group_tests',['Outcome','$h$','Term','Difference',r'95\% CI','$p$',r'$p_{\max}$'],rows,'lrllrrr')
    rows=[]
    for s in GROUPS:
        for method in ['minimal','full','pds']:
            z=pick(s,'log_gdp',8,TERMS[0],method);rows.append([LAB[s],method.upper() if method=='pds' else method.title(),int(z.n),int(z.p),int(z.residual_df),int(z.selected_count) if method=='pds' else '--',number(z.estimate),number(z.se)])
        z=vf[vf['sample'].eq(s)].iloc[0];rows.append([LAB[s],'PDS VARX',int(z.n),int(z.p),int(z.n-z.p),int(z.selected_count),'--','--'])
    table('ml_dimensions',['Setting','Estimator','$N$','$p$','$N-p$','Selected',r'$\beta_{P,8}$','SE'],rows,'llrrrrrr')
    rows=[]
    for s in GROUPS:
        for h in HS:
            b=pick(s,'log_gdp',h,TERMS[0],data=matched)
            vb=var[var['sample'].eq(s)&var.outcome.eq('log_gdp')&var.horizon.eq(h)&var.term.eq(TERMS[0])].iloc[0]
            g=pick(s,'log_prices',h,TERMS[1],data=matched)
            vg=var[var['sample'].eq(s)&var.outcome.eq('log_prices')&var.horizon.eq(h)&var.term.eq(TERMS[1])].iloc[0]
            rows.append([LAB[s],h,number(b.estimate),number(vb.estimate),pv(vb.p_maxT),number(g.estimate),number(vg.estimate),pv(vg.p_maxT),int(b.n)])
    table('ml_var_compare',['Setting','$h$',r'LP $\beta_P^Y$',r'VAR $\beta_P^Y$',r'$p_{\max}$',r'LP $\gamma_P^P$',r'VAR $\gamma_P^P$',r'$p_{\max}$','$N$'],rows,'lrrrrrrrr')
    rows=[]
    for h in range(13):
        z=pick('advanced','log_prices',h,TERMS[1]);v=var[var['sample'].eq('advanced')&var.outcome.eq('log_prices')&var.horizon.eq(h)&var.term.eq(TERMS[1])].iloc[0]
        vals=[pick('advanced','log_prices',h,TERMS[1],m).estimate for m in ['minimal','full','pds']]
        rows.append([h,*[number(x) for x in vals],pa('advanced','log_prices',h,TERMS[1],'full_curves'),number(v.estimate),pv(v.p_maxT)])
    table('ml_price_curve',['$h$','Minimal LP','Full LP','PDS LP',r'LP $p_{\max}$','PDS VARX',r'VAR $p_{\max}$'],rows,'rrrrrrr')
    fig,axes=plt.subplots(3,2,figsize=(8.2,6.8),sharex=True)
    for r,s in enumerate(GROUPS):
        for col,(out,k,title) in enumerate([('log_gdp',TERMS[0],'GDP ownership'),('log_prices',TERMS[1],'Price refinancing interaction')]):
            ax=axes[r,col]
            for method,color,ls,lw in [('full',GRAY,'--',1.3),('pds',INK,'-',1.9)]:
                z=all[all['sample'].eq(s)&all.estimator.eq(method)&all.outcome.eq(out)&all.term.eq(k)].sort_values('horizon');ax.plot(z.horizon,z.estimate,color=color,ls=ls,lw=lw,label='Full controls' if method=='full' else 'PDS controls')
                if method=='pds':ax.fill_between(z.horizon,z.ci_low,z.ci_high,color=color,alpha=.13,lw=0)
            clean(ax);ax.set_xticks([0,4,8,12]);ax.set_title(LAB[s]+': '+title,loc='left',fontsize=9.5)
    for ax in axes[-1]:ax.set_xlabel('Quarters after surprise')
    axes[1,0].set_ylabel('Response contrast (log percentage points)')
    h,l=axes[0,0].get_legend_handles_labels();fig.legend(h,l,loc='upper center',ncol=2,frameon=False);fig.tight_layout(rect=[0,0,1,.965]);save(fig,'ml_transmission_curves')
    fig,axes=plt.subplots(1,2,figsize=(8.2,3.3))
    for ax,frame,title,family in [(axes[0],adj,'Direct local projections','full_curves'),(axes[1],var,'Four-lag panel VARX','var_full_curves')]:
        for s,color,ls in [('ea',GRAY,':'),('advanced',INK,'-'),('emerging',TEAL,'--')]:
            z=frame[frame['sample'].eq(s)&frame.outcome.eq('log_prices')&frame.term.eq(TERMS[1])&frame.family.eq(family)].sort_values('horizon')
            ax.plot(z.horizon,z.estimate,color=color,ls=ls,lw=1.7,label=LAB[s]);ax.fill_between(z.horizon,z.simultaneous_low,z.simultaneous_high,color=color,alpha=.10,lw=0)
        clean(ax);ax.set_title(title,loc='left');ax.set_xticks([0,4,8,12]);ax.set_xlabel('Quarters after surprise')
    axes[0].set_ylabel('Ownership × refinancing price gradient');h,l=axes[0].get_legend_handles_labels();fig.legend(h,l,loc='upper center',ncol=3,frameon=False,fontsize=8);fig.tight_layout(rect=[0,0,1,.91]);save(fig,'ml_prices_var')
    rows=[];sc=pd.read_csv(R/'ml_economic_scale.csv');means=pd.read_csv(R/'ml_mean_responses.csv')
    for s in ['advanced','emerging']:
        for h in HS:
            z=sc[sc['sample'].eq(s)&sc.estimator.eq('pds')&sc.horizon.eq(h)].iloc[0];m=means[means['sample'].eq(s)&means.estimator.eq('pds')&means.horizon.eq(h)].iloc[0]
            rows.append([LAB[s],h,number(m.estimate),number(m.se),number(z.at_mean_refinancing),number(z.sd_ownership_contrast_at_mean_r),number(z.one_shock_sd_and_ownership_sd)])
    table('ml_scale',['Setting','$h$','Mean response','SE',r'$\beta_P(\bar r_g)$',r'$1\sigma_P$',r'$1\sigma_P,1\sigma_m$'],rows,'lrrrrrr')
    fig,axes=plt.subplots(1,2,figsize=(8.2,3.2))
    for ax,s in zip(axes,['advanced','emerging']):
        z=means[means['sample'].eq(s)&means.estimator.eq('pds')].sort_values('horizon');ax.errorbar(z.horizon,z.estimate,yerr=[z.estimate-z.ci_low,z.ci_high-z.estimate],color=INK,fmt='o-',lw=1.6,capsize=3,label='Average GDP response')
        z=sc[sc['sample'].eq(s)&sc.estimator.eq('pds')].sort_values('horizon');ax.plot(z.horizon,z.sd_ownership_contrast_at_mean_r,color=TEAL,ls='--',marker='s',label='One within-country SD of ownership')
        clean(ax);ax.set_title(LAB[s],loc='left');ax.set_xticks(HS);ax.set_xlabel('Quarters after surprise')
    axes[0].set_ylabel('Log percentage points per 10bp surprise');h,l=axes[0].get_legend_handles_labels();fig.legend(h,l,loc='upper center',ncol=2,frameon=False,fontsize=8);fig.tight_layout(rect=[0,0,1,.9]);save(fig,'ml_scale_baseline')
    for s in ['ea','advanced','emerging','own','pooled','ea_bolhuis']:
        rows=[]
        for out in ['log_gdp','log_prices','debt_ratio_observed','log_reer']:
            for h in HS:
                z=pick(s,out,h,TERMS[0]);g=pick(s,out,h,TERMS[1]);family='main' if s in GROUPS and out in ['log_gdp','log_prices'] else 'channels'
                rows.append([OUT[out],h,number(z.estimate),number(z.se),pa(s,out,h,z.term,family),number(g.estimate),number(g.se),pa(s,out,h,g.term,family),int(z.n)])
        table('ml_complete_'+s,['Outcome','$h$',r'$\beta_P$','SE',r'$p_{\max}$',r'$\gamma_P$','SE',r'$p_{\max}$','$N$'],rows,'lrrrrrrrr')
    a=pd.read_csv(R/'ml_accumulation.csv');rows=[]
    for s in ['ea','advanced','emerging','own','pooled']:
        for out in ['log_gdp','log_prices']:
            for h in HS:
                z=a[a.estimator.eq('pds')&a['sample'].eq(s)&a.outcome.eq(out)&a.horizon.eq(h)&a.term.eq('debt_accumulation')].iloc[0];rows.append([LAB[s],OUT[out],h,number(z.estimate),number(z.se),pv(z.p_value),pa(s,out,h,z.term,'channels'),int(z.n)])
    table('ml_accumulation',['Setting','Outcome','$h$',r'$\delta_{\Delta D}$','SE','$p$',r'$p_{\max}$','$N$'],rows,'llrrrrrr')
    # Convex averages of independently estimated groups versus common slopes.
    rows=[];aggregate=[]
    for method in ['full','pds']:
        for out in ['log_gdp','log_reer']:
            for h in HS:
                b={s:pick(s,out,h,TERMS[0],method).estimate for s in ['advanced','emerging','ea_bolhuis']}
                own=pick('own',out,h,TERMS[0],method).estimate;pool=pick('pooled',out,h,TERMS[0],method).estimate
                c=(19*b['ea_bolhuis']+11*b['advanced']+8*b['emerging'])/38;p=(b['ea_bolhuis']+11*b['advanced']+8*b['emerging'])/20
                rows.append([method.upper(),OUT[out],h,number(b['ea_bolhuis']),number(b['advanced']),number(b['emerging']),number(c),number(p),number(own),number(pool)])
                aggregate.append(dict(estimator=method,outcome=out,horizon=h,euro=b['ea_bolhuis'],advanced=b['advanced'],emerging=b['emerging'],convex_country=c,convex_policy=p,common_own=own,common_pooled=pool))
    pd.DataFrame(aggregate).to_csv(R/'ml_aggregation_comparison.csv',index=False)
    table('ml_aggregation',['Model','Outcome','$h$','Euro','AE','EM','Country avg.','Policy avg.','Own pooled','All pooled'],rows,'llrrrrrrrr')
    e=pd.read_csv(R/'ml_ecb_harmonized.csv');rows=[]
    for method in ['full','pds']:
        for out in ['log_gdp','log_reer']:
            for h in HS:
                zz=e[e.estimator.eq(method)&e.outcome.eq(out)&e.horizon.eq(h)&e.term.eq(TERMS[0])].set_index('shock_origin');b=zz.loc['bolhuis'];j=zz.loc['jk'];rows.append([method.upper(),OUT[out],h,number(b.estimate),number(b.se),number(j.estimate),number(j.se),int(b.n)])
    table('ml_ecb_harmonized',['Model','Outcome','$h$','Bolhuis','SE','JK','SE','$N$'],rows,'llrrrrrr')
    rows=[];fx=pd.read_csv(R/'ml_currency_control.csv')
    for out in ['log_gdp','log_prices']:
        for h in HS:
            zz=fx[fx.outcome.eq(out)&fx.horizon.eq(h)&fx.term.eq(TERMS[0])].set_index('variant');a=zz.loc['FX support baseline'];b=zz.loc['FX controls forced'];rows.append([OUT[out],h,number(a.estimate),number(a.se),number(b.estimate),number(b.se),int(a.n)])
    table('ml_currency',['Outcome','$h$','Matched PDS','SE','PDS + FX','SE','$N$'],rows,'lrrrrrr')
    f=pd.read_csv(R/'ml_forced_spillover_sensitivity.csv');rows=[]
    for s in GROUPS:
        for out in ['log_gdp','log_prices']:
            for h in HS:
                zz=f[f['sample'].eq(s)&f.outcome.eq(out)&f.horizon.eq(h)].set_index('term');b=zz.loc[TERMS[0]];g=zz.loc[TERMS[1]]
                rows.append([LAB[s],OUT[out],h,number(b.estimate),pv(b.p_value),pa(s,out,h,b.name,'forced_spillovers'),number(g.estimate),pv(g.p_value),pa(s,out,h,g.name,'forced_spillovers')])
    table('ml_spillovers',['Setting','Outcome','$h$',r'$\beta_P$','$p$',r'$p_{\max}$',r'$\gamma_P$','$p$',r'$p_{\max}$'],rows,'llrrrrrrr')
    loo=pd.read_csv(R/'ml_leave_one_out.csv');rows=[]
    for (s,o,h,k),z in loo.groupby(['sample','outcome','horizon','term'],sort=False):
        rows.append([LAB[s],OUT[o],int(h),r'$\beta_P$' if k==TERMS[0] else r'$\gamma_P$',number(z.estimate.min()),number(z.estimate.max()),pv(z.p_value.min()),pv(z.p_value.max())])
    table('ml_loo',['Setting','Outcome','$h$','Term','Min.','Max.','Min. $p$','Max. $p$'],rows,'llrlrrrr')
    print('Regularized exhibits generated',flush=True)
if __name__=='__main__':main()
