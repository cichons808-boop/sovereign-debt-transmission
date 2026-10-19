from plot_io import save_pdf
"""Journal figures and tables from the complete fiscal-transmission results."""
from pathlib import Path
import hashlib,json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

P=Path(__file__).resolve().parents[1]/'output';ROOT=P.parent;R=ROOT/'results';D=ROOT/'data/processed';T=P/'tables';F=P/'figures'
INK='#243F57';TEAL='#147D78';GOLD='#B1843E';GRAY='#687780'
LABEL={'ea':'Euro area','own':'Own-policy economies','advanced':'Advanced own-policy','emerging':'Emerging own-policy','pooled':'Including euro area'}
plt.rcParams.update({'font.family':'serif','font.size':9,'axes.titlesize':10,'axes.labelsize':9,'xtick.labelsize':8,'ytick.labelsize':8,
    'axes.spines.top':False,'axes.spines.right':False,'pdf.fonttype':42,'savefig.facecolor':'white'})

def number(x,n=3):return f'{float(x):.{n}f}'
def pv(x):return '$<0.001$' if x<.001 else number(x)
ADJ=pd.read_csv(R/'fiscal_simultaneous.csv')
def pa(sample,model,out,h,term):
    z=ADJ[ADJ['sample'].eq(sample)&ADJ.model.eq(model)&ADJ.outcome.eq(out)&ADJ.horizon.eq(h)&ADJ.term.eq(term)]
    z=z[~z.family.eq('full_curves')]
    return pv(z.iloc[0].p_maxT) if len(z) else '--'
def ci(r):return '['+number(r.ci_low)+', '+number(r.ci_high)+']'
def table(name,header,rows,align):
    text=[r'\begin{tabular}{@{}'+align+r'@{}}',r'\toprule',' & '.join(header)+r' \\',r'\midrule']
    text += [' & '.join(str(x) for x in row)+r' \\' for row in rows]
    text += [r'\bottomrule',r'\end{tabular}'];(T/(name+'.tex')).write_text('\n'.join(text)+'\n')
def save(fig,name):
    save_pdf(fig,F/(name+'.pdf'),bbox_inches='tight');plt.close(fig)
def line(ax,d,color,label,style='-'):
    d=d.sort_values('horizon');ax.plot(d.horizon,d.estimate,color=color,label=label,ls=style,lw=1.8)
    ax.fill_between(d.horizon,d.ci_low,d.ci_high,color=color,alpha=.12,lw=0)
def clean(ax):ax.axhline(0,color=GRAY,lw=.6);ax.grid(axis='y',alpha=.15);ax.set_axisbelow(True)

def main():
    d=pd.read_csv(R/'fiscal_main.csv');a=pd.read_csv(R/'fiscal_accumulation.csv');s=pd.read_csv(R/'fiscal_sectors.csv')
    # Matched ownership comparisons: all groups and all curve points, without
    # highlighting whichever horizon happened to have the largest t statistic.
    fig,axes=plt.subplots(3,2,figsize=(8.4,8.1),sharex=True)
    for row,sample in enumerate(['ea','advanced','emerging']):
        for col,(out,title) in enumerate([('log_gdp','Real GDP'),('log_prices','Consumer prices')]):
            ax=axes[row,col];z=d[d['sample'].eq(sample)&d.outcome.eq(out)&d.term.eq('domestic_noncb')]
            for model,color,label,style in [('ownership_matched',INK,'Ownership','-'),('rollover',TEAL,'Ownership + refinancing','--')]:line(ax,z[z.model.eq(model)],color,label,style)
            clean(ax);ax.set_title(LABEL[sample]+': '+title,loc='left');n=int(z[z.horizon.eq(4)].iloc[0].n);g=int(z.iloc[0].countries)
            ax.text(.03,.96,f'{g} countries; N(4) = {n:,}',transform=ax.transAxes,va='top',fontsize=8)
            ax.set_xticks([0,4,8,12])
    for ax in axes[-1]:ax.set_xlabel('Quarters after monetary surprise')
    h,l=axes[0,0].get_legend_handles_labels();fig.legend(h,l,loc='upper center',ncol=2,frameon=False)
    fig.supylabel('Response contrast (percentage points)',x=.01,fontsize=10)
    fig.tight_layout(rect=[.025,0,1,.96]);save(fig,'fiscal_regime_curves')
    # Refinancing interaction, one coefficient curve for each setting.
    fig,axes=plt.subplots(1,2,figsize=(8.4,3.25))
    for ax,out,title in zip(axes,['log_gdp','log_prices'],['Real GDP','Consumer prices']):
        for sample,color,style in [('ea',GRAY,':'),('advanced',INK,'-'),('emerging',TEAL,'--')]:
            line(ax,d[d['sample'].eq(sample)&d.model.eq('rollover')&d.outcome.eq(out)&d.term.eq('domestic_noncb_x_refinancing')],color,LABEL[sample],style)
        clean(ax);ax.set_title(title,loc='left');ax.set_xlabel('Quarters after surprise');ax.set_xticks([0,4,8,12])
    axes[0].set_ylabel('Refinancing interaction');h,l=axes[0].get_legend_handles_labels();fig.legend(h,l,loc='upper center',ncol=3,frameon=False)
    fig.tight_layout(rect=[0,0,1,.9]);save(fig,'fiscal_refinancing')
    fig,axes=plt.subplots(1,2,figsize=(8.4,3.25))
    block_weights=pd.read_csv(R/'fiscal_policy_block_weights.csv')
    for ax,out,title in zip(axes,['log_gdp','log_prices'],['Real GDP','Consumer prices']):
        for sample,color,label,style in [('pooled',INK,'38 country units','-'),('own',TEAL,'19 units, excluding euro','--')]:
            line(ax,d[d['sample'].eq(sample)&d.model.eq('rollover')&d.outcome.eq(out)&d.term.eq('domestic_noncb')],color,label,style)
        z=block_weights[block_weights.outcome.eq(out)&block_weights.term.eq('domestic_noncb')].sort_values('horizon')
        ax.errorbar(z.horizon,z.estimate,yerr=[z.estimate-z.ci_low,z.ci_high-z.estimate],fmt='o:',color=GOLD,label='Equal policy-block weights',lw=1.1,capsize=2,markersize=3)
        clean(ax);ax.set_title(title,loc='left');ax.set_xlabel('Quarters after surprise');ax.set_xticks([0,4,8,12])
    axes[0].set_ylabel('Ownership contrast');h,l=axes[0].get_legend_handles_labels();fig.legend(h,l,loc='upper center',ncol=3,frameon=False,fontsize=8)
    fig.tight_layout(rect=[0,0,1,.9]);save(fig,'fiscal_euro_block')
    # Debt and exchange-rate channels show the declared focal horizons only.
    fig,axes=plt.subplots(1,2,figsize=(8.4,3.35))
    for ax,out,title in zip(axes,['debt_ratio_observed','log_reer'],['General-government debt / GDP','Real effective exchange rate']):
        for off,sample,color,marker in [(-.22,'ea',GRAY,'o'),(0,'advanced',INK,'s'),(.22,'emerging',TEAL,'^')]:
            z=d[d['sample'].eq(sample)&d.model.eq('rollover')&d.outcome.eq(out)&d.term.eq('domestic_noncb')].sort_values('horizon')
            ax.errorbar(z.horizon+off,z.estimate,yerr=[z.estimate-z.ci_low,z.ci_high-z.estimate],fmt=marker,color=color,label=LABEL[sample],capsize=3,lw=1)
        clean(ax);ax.set_title(title,loc='left');ax.set_xticks([4,8,12]);ax.set_xlabel('Quarters after surprise')
    axes[0].set_ylabel('Ownership response contrast');h,l=axes[0].get_legend_handles_labels();fig.legend(h,l,loc='upper center',ncol=3,frameon=False)
    fig.tight_layout(rect=[0,0,1,.9]);save(fig,'fiscal_channels')
    # Institutional event windows fixed in the design before extraction.
    raw=pd.read_csv(D/'fiscal_retail_ecb_monthly.csv.gz');wide=raw.pivot(index=['country','month'],columns='measure',values='value').reset_index()
    fig,axes=plt.subplots(2,2,figsize=(8.4,6.3))
    for row,country,event,refs in [(0,'BE','2023-09',['FR','NL']),(1,'PT','2023-06',['ES','IT'])]:
        ep=pd.Period(event,'M');months=[str(ep+k) for k in range(-12,13)];x=np.arange(-12,13)
        baseline='2023-07' if country=='BE' else str(ep-1)
        own=wide[wide.country.eq(country)].set_index('month').reindex(months)
        comps=[wide[wide.country.eq(c)].set_index('month').reindex(months) for c in refs]
        for col,measure in enumerate(['deposit_stock','term_rate']):
            ax=axes[row,col]
            transform=lambda v:100*v[measure]/v.loc[baseline,measure] if measure=='deposit_stock' else v[measure]
            ax.plot(x,transform(own),lw=1.9,color=INK,label='Belgium' if country=='BE' else 'Portugal')
            ax.plot(x,np.mean([transform(v).to_numpy() for v in comps],axis=0),lw=1.7,ls='--',color=TEAL,label='+'.join(refs)+' mean')
            ax.axvline(0,color=GOLD,lw=1)
            if country=='BE':
                ax.axvspan(-1,0,color=GOLD,alpha=.12)
                ax.text(-1.3,.96,'Subscription',rotation=90,ha='right',va='top',transform=ax.get_xaxis_transform(),fontsize=7,color=GOLD)
                ax.text(.35,.96,'Settlement',rotation=90,ha='left',va='top',transform=ax.get_xaxis_transform(),fontsize=7,color=GOLD)
            ax.grid(axis='y',alpha=.15);ax.set_xticks([-12,-6,0,6,12]);ax.set_xlabel('Months from '+event)
            ax.set_ylabel(baseline+' = 100' if measure=='deposit_stock' else 'Percent per year')
            ax.set_title(('Belgium' if country=='BE' else 'Portugal')+(': deposits' if col==0 else ': new term-deposit rate'),loc='left');ax.legend(frameon=False,fontsize=8)
    fig.tight_layout();save(fig,'fiscal_retail_events')
    p=pd.read_csv(D/'fiscal_poland_repricing_monthly.csv.gz');dates=pd.to_datetime(p.date)
    fig,axes=plt.subplots(1,2,figsize=(8.4,3.3))
    axes[0].stackplot(dates,p.ror_million_pln/1000,p.dor_million_pln/1000,colors=[INK,TEAL],alpha=.9,labels=['ROR','DOR']);axes[0].set_ylabel('PLN billion');axes[0].set_title('Outstanding monthly-reset principal',loc='left');axes[0].legend(frameon=False)
    axes[1].plot(dates,p.annualized_policy_component_bn_pln,color=INK,label='Policy-rate component')
    axes[1].plot(dates,p.annual_sensitivity_100bp_bn_pln,color=TEAL,ls='--',label='Sensitivity to +100bp')
    axes[1].set_ylabel('PLN billion per year');axes[1].set_title('Contractual gross interest exposure',loc='left');axes[1].legend(frameon=False,fontsize=8)
    for ax in axes:ax.grid(axis='y',alpha=.15);ax.tick_params(axis='x',rotation=30)
    fig.tight_layout();save(fig,'fiscal_poland_repricing')
    # Main tables are complete by declared group and horizon.
    rows=[]
    for sample in ['ea','advanced','emerging']:
        for h in [4,8,12]:
            z=d[d['sample'].eq(sample)&d.model.eq('rollover')&d.outcome.eq('log_gdp')&d.horizon.eq(h)].set_index('term')
            b=z.loc['domestic_noncb'];g=z.loc['domestic_noncb_x_refinancing']
            rows.append([LABEL[sample],h,number(b.estimate),pv(b.p_value),pa(sample,'rollover','log_gdp',h,b.name),number(g.estimate),pv(g.p_value),pa(sample,'rollover','log_gdp',h,g.name),f'{int(b.n):,} / {int(b.countries)}'])
    table('fiscal_gdp',['Monetary setting','$h$',r'$\beta_P$','$p$',r'$p_{\max}$',r'$\gamma_P$','$p$',r'$p_{\max}$',r'$N/G$'],rows,'lrrrrrrrr')
    rows=[]
    for sample in ['ea','own','advanced','emerging','pooled']:
        for out,label in [('debt_ratio_observed','Debt / GDP'),('log_reer','REER')]:
            for h in [4,8,12]:
                z=d[d['sample'].eq(sample)&d.model.eq('rollover')&d.outcome.eq(out)&d.horizon.eq(h)&d.term.eq('domestic_noncb')].iloc[0]
                rows.append([LABEL[sample],label,h,number(z.estimate),ci(z),pv(z.p_value),pa(sample,'rollover',out,h,z.term),f'{int(z.n):,} / {int(z.countries)}'])
    for sample in ['ea','own','advanced','emerging','pooled']:
        sr=[r for r in rows if r[0]==LABEL[sample]]
        table('fiscal_channels_'+sample,['Setting','Outcome','$h$',r'$\beta_P$',r'95\% CI','$p$',r'$p_{\max}$',r'$N/G$'],sr,'llrlrrrr')
    rows=[]
    for sample in ['ea','advanced','emerging','own','pooled']:
        for out,label in [('log_gdp','GDP'),('log_prices','Prices')]:
            for h in [4,8,12]:
                z=a[a['sample'].eq(sample)&a.variant.eq('debt accumulation')&a.outcome.eq(out)&a.horizon.eq(h)&a.term.eq('debt_accumulation')].iloc[0]
                rows.append([LABEL[sample],label,h,number(z.estimate),ci(z),pv(z.p_value),pa(sample,'rollover',out,h,z.term),f'{int(z.n):,} / {int(z.countries)}'])
    for group in ['primary','pooled']:
        sr=[r for r in rows if (r[0] in [LABEL[x] for x in ['ea','advanced','emerging']])==(group=='primary')]
        table('fiscal_accumulation_'+group,['Setting','Outcome','$h$',r'$\delta_{\Delta D}$',r'95\% CI','$p$',r'$p_{\max}$',r'$N/G$'],sr,'llrlrrrr')
    rows=[]
    for sample in ['own','pooled']:
        for out,label in [('log_gdp','GDP'),('log_prices','Prices')]:
            for h in [4,8,12]:
                z=d[d['sample'].eq(sample)&d.model.eq('rollover')&d.outcome.eq(out)&d.horizon.eq(h)&d.term.eq('domestic_noncb')].iloc[0]
                rows.append([LABEL[sample],label,h,number(z.estimate),ci(z),pv(z.p_value),pa(sample,'rollover',out,h,z.term),f'{int(z.n):,} / {int(z.countries)}'])
    table('fiscal_block',['Sample','Outcome','$h$',r'$\beta_P$',r'95\% CI','$p$',r'$p_{\max}$',r'$N/G$'],rows,'llrlrrrr')
    rows=[]
    for out,label in [('log_gdp','GDP'),('log_prices','Prices')]:
        for h in [4,8,12]:
            z=block_weights[block_weights.outcome.eq(out)&block_weights.horizon.eq(h)].set_index('term')
            b=z.loc['domestic_noncb'];g=z.loc['domestic_noncb_x_refinancing']
            rows.append([label,h,number(b.estimate),pv(b.p_value),pa('equal_policy_weight','rollover',out,h,b.name),number(g.estimate),pv(g.p_value),pa('equal_policy_weight','rollover',out,h,g.name)])
    table('fiscal_block_weights',['Outcome','$h$',r'$\beta_P$','$p$',r'$p_{\max}$',r'$\gamma_P$','$p$',r'$p_{\max}$'],rows,'lrrrrrrr')
    cc=pd.read_csv(R/'fiscal_country_coverage.csv');rows=[]
    for _,z in cc[cc['sample'].isin(['ea','advanced','emerging'])].iterrows():
        rows.append([LABEL[z['sample']],z.country,int(z.n),int(z.quarterly_owner_rows),int(z.annual_owner_rows),z['first']+'--'+z['last']])
    table('fiscal_coverage',['Setting','Country','$N$',r'$N_Q$',r'$N_A$','Shock dates'],rows,'llrrrl')
    ev=pd.read_csv(R/'fiscal_retail_event_changes.csv');rows=[]
    for country in ['BE','PT']:
        for h in [0,6,12]:
            z=ev[ev.country.eq(country)&ev.horizon_months.eq(h)].set_index('measure');stock=z.loc['deposit_stock'];rate=z.loc['term_rate']
            rows.append([country,h,number(stock.change,2),number(stock.relative_change,2),number(rate.change,2),number(rate.relative_change,2)])
    table('fiscal_events',['Country','Months',r'$\Delta$ deposits',r'Relative',r'$\Delta$ rate',r'Relative'],rows,'lrrrrr')
    rows=[]
    for year in [2022,2023,2024,2025]:
        z=p[p.month.str.startswith(str(year))].iloc[-1]
        rows.append([year,number(z.principal_bn_pln,2),number(z.policy_rate,2),number(z.annualized_policy_component_bn_pln),number(z.annual_sensitivity_100bp_bn_pln),number(z.annualized_policy_component_percent_gdp,3)])
    table('fiscal_poland',['Year','Principal',r'NBP rate',r'Policy component',r'$+100$bp exposure',r'Component / GDP'],rows,'lrrrrr')
    # Full focal matrix in the appendix, one setting per compact table.
    for sample in ['ea','advanced','emerging','own','pooled']:
        rows=[]
        for out,label in [('log_gdp','GDP'),('log_prices','Prices')]:
            for h in [4,8,12]:
                for term,tl in [('domestic_noncb',r'$\beta_P$'),('domestic_noncb_x_refinancing',r'$\gamma_P$')]:
                    z=d[d['sample'].eq(sample)&d.model.eq('rollover')&d.outcome.eq(out)&d.horizon.eq(h)&d.term.eq(term)].iloc[0]
                    rows.append([label,h,tl,number(z.estimate),ci(z),pv(z.p_value),pa(sample,'rollover',out,h,term),f'{int(z.n):,}'])
        table('fiscal_full_'+sample,['Outcome','$h$','Term','Estimate',r'95\% CI','$p$',r'$p_{\max}$','$N$'],rows,'lrllrrrr')
    print('Six figures and complete setting-specific tables generated.')

if __name__=='__main__':main()
