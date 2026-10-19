"""Inference, country influence and institutional timing exhibits."""
import json,hashlib
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch,FancyArrowPatch
from exhibit_style import P,R,D,F,INK,TEAL,GOLD,GRAY,LABEL,table,save,number,pv,ci

def main():
    a=pd.read_csv(R/'fiscal_simultaneous.csv');rows=[]
    for _,z in a[a.family.eq('main')&a.model.eq('group_difference')].iterrows():
        rows.append(['GDP' if z.outcome=='log_gdp' else 'Prices',int(z.horizon),r'$\beta_P$' if z.term=='domestic_noncb' else r'$\gamma_P$',number(z.estimate),ci(z),pv(z.p_value),pv(z.p_maxT)])
    table('fiscal_group_tests',['Outcome','$h$','Contrast','AE $-$ EM',r'95\% CI','$p$',r'$p_{\max}$'],rows,'lrllrrr')
    m=pd.read_csv(R/'fiscal_model_dimensions.csv');rows=[]
    for s in ['ea','advanced','emerging','own','pooled']:
        for h in [4,8,12]:
            z=m[m['sample'].eq(s)&m.outcome.eq('log_gdp')&m.horizon.eq(h)].iloc[0]
            rows.append([LABEL[s],h,int(z.n),int(z.p),int(z.residual_df),int(z.time_periods),int(z.df)])
    table('fiscal_dimensions',['Setting','$h$','$N$','Rank $p$','$N-p$','$T$','HAC df'],rows,'lrrrrrr')
    loo=pd.read_csv(R/'fiscal_leave_one_out.csv');rows=[]
    for (s,o,h,k),g in loo.groupby(['sample','outcome','horizon','term'],sort=False):
        rows.append([('AE' if s=='advanced' else 'EM'),('GDP' if o=='log_gdp' else 'Prices'),h,r'$\beta_P$' if k=='domestic_noncb' else r'$\gamma_P$',number(g.estimate.min()),number(g.estimate.max()),number(g.p_value.min()),number(g.p_value.max())])
    table('fiscal_loo_summary',['Group','Outcome','$h$','Term','Min. coef.','Max. coef.','Min. $p$','Max. $p$'],rows,'llrlrrrr')
    fig,axs=plt.subplots(2,2,figsize=(8.3,6.8),sharex='col')
    main=pd.read_csv(R/'fiscal_main.csv')
    for row,s in enumerate(['advanced','emerging']):
        for col,k in enumerate(['domestic_noncb','domestic_noncb_x_refinancing']):
            ax=axs[row,col];z=loo[loo['sample'].eq(s)&loo.outcome.eq('log_gdp')&loo.horizon.eq(8)&loo.term.eq(k)].sort_values('omitted_country')
            ax.errorbar(z.estimate,np.arange(len(z)),xerr=[z.estimate-z.ci_low,z.ci_high-z.estimate],fmt='o',color=INK if row==0 else TEAL,capsize=2,lw=1,ms=3)
            b=main[main['sample'].eq(s)&main.model.eq('rollover')&main.outcome.eq('log_gdp')&main.horizon.eq(8)&main.term.eq(k)].iloc[0].estimate
            ax.axvline(b,color=GOLD,ls='--',lw=1);ax.axvline(0,color=GRAY,lw=.7)
            ax.set_yticks(np.arange(len(z)),z.omitted_country);ax.invert_yaxis();ax.grid(axis='x',alpha=.15)
            ax.set_title(('Advanced' if row==0 else 'Emerging')+(': ownership' if col==0 else ': refinancing'),loc='left')
            if row==1:ax.set_xlabel('Two-year GDP contrast; country omitted at left')
    fig.tight_layout();save(fig,'fiscal_leave_one_out')
    w=pd.read_csv(R/'fiscal_wild_bootstrap.csv');rows=[]
    for _,z in w.iterrows():
        rows.append(['AE' if z['sample']=='advanced' else 'EM','GDP' if z.outcome=='log_gdp' else 'Prices',int(z.horizon),r'$\beta_P$' if z.term=='domestic_noncb' else r'$\gamma_P$',pv(z.p_HAC),pv(z.p_wcr11_rademacher),pv(z.p_wcr11_webb)])
    table('fiscal_wild',['Group','Outcome','$h$','Term','Time HAC','Wild signs','Wild Webb'],rows,'llrlrrr')
    fx=pd.read_csv(R/'fiscal_currency_control.csv');rows=[]
    for s in ['own','advanced','emerging']:
        for h in [4,8,12]:
            z=fx[fx['sample'].eq(s)&fx.outcome.eq('log_gdp')&fx.horizon.eq(h)]
            for k,lab in [('domestic_noncb',r'$\beta_P$'),('domestic_noncb_x_refinancing',r'$\gamma_P$')]:
                b=z[z.variant.eq('matched baseline')&z.term.eq(k)].iloc[0];v=z[z.variant.eq('FX control')&z.term.eq(k)].iloc[0]
                rows.append([{'own':'All','advanced':'AE','emerging':'EM'}[s],h,lab,number(b.estimate),pv(b.p_value),number(v.estimate),pv(v.p_value),f'{int(v.n)}/{int(v.countries)}',int(v.n-v.p)])
    table('fiscal_currency',['Group','$h$','Term','Matched','$p$','FX control','$p$','$N/G$','$N-p$'],rows,'lrlrrrrrr')
    eq=pd.read_csv(R/'fiscal_equity_proxy.csv');rows=[]
    for s in ['ea','advanced','emerging']:
        for h in [4,8,12]:
            z=eq[eq['sample'].eq(s)&eq.outcome.eq('log_gdp')&eq.horizon.eq(h)]
            for k,lab in [('domestic_noncb',r'$\beta_P$'),('domestic_noncb_x_refinancing',r'$\gamma_P$')]:
                b=z[z.proxy.eq('SPY adjusted ETF')&z.term.eq(k)].iloc[0];v=z[z.proxy.eq('OECD US equity index')&z.term.eq(k)].iloc[0]
                rows.append([{'ea':'Euro','advanced':'AE','emerging':'EM'}[s],h,lab,number(b.estimate),number(v.estimate),ci(v),pv(v.p_value),int(v.n)])
    table('fiscal_equity',['Group','$h$','Term','SPY','OECD',r'95\% CI (OECD)','$p$','$N$'],rows,'lrlrrrrr')
    b=pd.read_csv(R/'fiscal_belgium_timing.csv');rows=[]
    for before,g in b.groupby('baseline_month',sort=False):
        for end in ['2023-08','2023-09','2024-03','2024-09']:
            z=g[g.end_month.eq(end)].set_index('measure');x=z.loc['term_rate'];y=z.loc['deposit_stock']
            rows.append([before,end,number(y.change,2),number(y.relative_change,2),number(x.change,2),number(x.relative_change,2)])
    table('fiscal_belgium_timing',['Baseline','End',r'$\Delta$ deposits','Relative',r'$\Delta$ rate','Relative'],rows,'llrrrr')
    # A conceptual map uses distinct contracts, with no implied mediation test.
    fig,ax=plt.subplots(figsize=(8.4,3.25));ax.set_xlim(0,10);ax.set_ylim(0,4);ax.axis('off')
    def box(x,y,w,h,title,detail,color=INK):
        ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle='round,pad=.08,rounding_size=.07',lw=.9,edgecolor=color,facecolor='#f6f8f8'))
        ax.text(x+w/2,y+h*.68,title,ha='center',va='center',color=color,fontsize=9,fontweight='bold')
        ax.text(x+w/2,y+h*.31,detail,ha='center',va='center',color=GRAY,fontsize=8)
    def arrow(a,b):ax.add_patch(FancyArrowPatch(a,b,arrowstyle='-|>',mutation_scale=10,lw=.9,color=GRAY,connectionstyle='arc3,rad=0'))
    box(.1,1.5,1.45,.9,'Policy surprise','Market-identified\n+10 basis points')
    box(2.1,2.8,2.1,.95,'Creditor residence','Who holds the claim?')
    box(2.1,1.5,2.1,.95,'Principal maturity','When is debt refinanced?')
    box(2.1,.2,2.1,.95,'Coupon reset','When does interest reprice?')
    box(4.9,2.2,2.15,1.1,'Balance sheets','Fiscal financing, bank\nfunding and external portfolios')
    box(4.9,.45,2.15,1.1,'Interest exposure','Holdings × reset share\n× rate change')
    box(7.7,1.55,2.15,1.15,'Observed responses','GDP • prices • REER\ndebt ratio • deposits')
    for y in [3.27,1.97,.67]:arrow((1.63,1.96),(2.01,y))
    for a,b in [((4.29,3.27),(4.8,2.85)),((4.29,1.97),(4.8,2.65)),((4.29,.67),(4.8,1.0)),((7.14,2.7),(7.61,2.3)),((7.14,1.0),(7.61,1.9))]:arrow(a,b)
    fig.tight_layout(pad=.3);save(fig,'fiscal_transmission_map')
    # Country-demeaned observed ownership displays the actual identifying range.
    import sys
    from specification import setup
    d=pd.read_csv(D/'fiscal_panel_external.csv.gz');d,_,_=setup(d,'rollover',True)
    keys=pd.read_csv(R/'fiscal_sample_keys.csv.gz');keys=keys[keys['sample'].isin(['advanced','emerging'])&keys.outcome.eq('log_gdp')&keys.horizon.eq(8)]
    vals=keys[['sample','country','period']].merge(d[['country','period','a_domestic_noncb','refinance_share']],on=['country','period'],validate='one_to_one')
    vals['ownership_gdp']=vals.a_domestic_noncb*10;vals['ownership_within']=vals.ownership_gdp-vals.groupby('country').ownership_gdp.transform('mean')
    vals.to_csv(R/'fiscal_identifying_variation.csv',index=False)
    fig,axs=plt.subplots(1,2,figsize=(8.4,3.7),sharey=True)
    for ax,s,color in zip(axs,['advanced','emerging'],[INK,TEAL]):
        z=vals[vals['sample'].eq(s)];cs=sorted(z.country.unique())
        bp=ax.boxplot([z[z.country.eq(c)].ownership_within for c in cs],tick_labels=cs,showfliers=False,patch_artist=True,widths=.6)
        for patch in bp['boxes']:patch.set_facecolor(color);patch.set_alpha(.25)
        ax.axhline(0,color=GRAY,lw=.6);ax.grid(axis='y',alpha=.15);ax.set_title(LABEL[s],loc='left');ax.set_xlabel('Observed country distribution')
    axs[0].set_ylabel('Resident holdings minus country mean\n(percentage points of GDP)');fig.tight_layout();save(fig,'fiscal_within_ownership')
    print('Audit tables, country-influence plots and transmission map generated.')

if __name__=='__main__':main()
