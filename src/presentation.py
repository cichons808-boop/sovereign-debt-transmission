"""Vector diagrams and empirical figures from the complete estimation outputs."""
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Patch
from matplotlib.lines import Line2D
from matplotlib.colors import ListedColormap
from plot_io import save_pdf

ROOT=Path(__file__).resolve().parents[1]
R=ROOT/'results'; F=ROOT/'output/figures'
NAVY,TEAL,GOLD,GRAY='#243F57','#147D78','#B1843E','#687780'
GROUPS=[('ea','Euro area',GRAY),('advanced','Advanced own-policy',NAVY),('emerging','Emerging own-policy',TEAL)]
plt.rcParams.update({'font.family':'serif','font.size':11,'axes.titlesize':11.5,
 'axes.labelsize':10.5,'xtick.labelsize':9,'ytick.labelsize':9,
 'axes.spines.top':False,'axes.spines.right':False,'axes.edgecolor':'#A6AFB4',
 'axes.linewidth':.65,'pdf.fonttype':42,'savefig.facecolor':'white',
 'mathtext.fontset':'dejavuserif'})


def finish(fig,name):
    F.mkdir(parents=True,exist_ok=True)
    save_pdf(fig,F/(name+'.pdf'),bbox_inches='tight',pad_inches=.12)
    plt.close(fig)


def clean(ax):
    ax.axhline(0,color=GRAY,lw=.7)
    ax.grid(axis='y',color='#E3E8EB',lw=.6)
    ax.set_axisbelow(True)


def box(ax,x,y,w,h,title,text,color=NAVY):
    ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle='round,pad=0.012,rounding_size=0.014',
                  facecolor='#F7F9FA',edgecolor=color,lw=1.1))
    ax.text(x+w/2,y+h*.72,title,ha='center',va='center',color=color,fontsize=10.8,fontweight='bold')
    ax.text(x+w/2,y+h*(.34 if title else .5),text,ha='center',va='center',fontsize=9.7,linespacing=1.45)


def arrow(ax,a,b,color=GRAY):
    ax.add_patch(FancyArrowPatch(a,b,arrowstyle='-|>',mutation_scale=12,lw=1.,color=color))


def research_design():
    fig,ax=plt.subplots(figsize=(8.6,4.8));ax.axis('off');ax.set(xlim=(0,1),ylim=(0,1))
    box(ax,.02,.67,.27,.24,'Public balance sheets','Debt and creditor stocks\nPrincipal due in one year')
    box(ax,.02,.33,.27,.24,'Monetary surprises','Published high-frequency\npolicy / information shocks',TEAL)
    box(ax,.365,.50,.27,.27,'Quarterly panel','38 economies; 3 settings\nPredetermined states\nSource and time effects')
    box(ax,.72,.67,.26,.24,'Direct projections','Minimal / full / PDS\nHorizons: 0-12 quarters')
    box(ax,.72,.33,.26,.24,'Panel VARX','Four endogenous lags\nMatched direct LP',TEAL)
    for a,b in [((.30,.79),(.35,.69)),((.30,.45),(.35,.59)),((.64,.69),(.71,.79)),((.64,.59),(.71,.45))]:arrow(ax,a,b)
    box(ax,.22,.015,.56,.20,'Responses and interpretation','GDP, prices, debt, REER; joint intervals\nRetail offers and contract dates',GOLD)
    arrow(ax,(.49,.48),(.49,.23))
    finish(fig,'research_design')


def ownership_contrast():
    fig,ax=plt.subplots(figsize=(8.6,4.5));ax.axis('off');ax.set(xlim=(0,1),ylim=(0,1))
    ax.text(.50,.965,'Same total debt and central-bank holdings in all four configurations',
            ha='center',va='top',fontsize=11,color=GRAY)
    ax.text(.31,.84,'Resident holdings P',ha='center',color=NAVY,fontsize=11)
    ax.text(.70,.84,'Resident holdings P + 10 points of GDP',ha='center',color=NAVY,fontsize=11)
    for y,row in [(.60,'r'),(.28,'r+0.10')]:
        box(ax,.16,y,.30,.16,'',r'$R_h(P, '+row+r')$')
        box(ax,.55,y,.30,.16,'',r'$R_h(P+10, '+row+r')$')
        arrow(ax,(.47,y+.08),(.54,y+.08),TEAL)
    ax.text(.13,.68,'Lower\nrefinancing',ha='right',va='center',fontsize=10.5)
    ax.text(.13,.36,'Higher\nrefinancing',ha='right',va='center',fontsize=10.5)
    ax.text(.50,.535,r'$\Delta R_h^{low}=R_h(P+10,r)-R_h(P,r)$',ha='center',fontsize=12,color=TEAL)
    ax.text(.50,.215,r'$\Delta R_h^{high}=R_h(P+10,r+0.10)-R_h(P,r+0.10)$',ha='center',fontsize=12,color=TEAL)
    ax.text(.50,.065,r'$\gamma_{P,h}=\Delta R_h^{high}-\Delta R_h^{low}$',ha='center',fontsize=15,color=NAVY)
    finish(fig,'ownership_refinancing_contrast')


def coverage():
    d=pd.read_csv(R/'fiscal_sample_keys.csv.gz')
    d=d[d.outcome.eq('log_gdp')&d.horizon.eq(4)&d['sample'].isin(['ea','advanced','emerging'])].copy()
    if d.duplicated(['sample','country','period']).any():
        raise ValueError('Coverage figure requires unique estimation observations')
    if not set(d.ownership_frequency).issubset({'Q','A'}):
        raise ValueError('Unknown ownership observation frequency')
    dates=pd.period_range(d.period.min(),d.period.max(),freq='Q');positions={str(x):j for j,x in enumerate(dates)}
    ticks=[j for j,q in enumerate(dates) if q.quarter==1 and q.year%5==0]
    labels=[str(dates[j].year) for j in ticks]
    fig=plt.figure(figsize=(8.5,6.6))
    panels=[('ea','A  Euro area',[.055,.14,.365,.77],.965,.936),
            ('advanced','B  Advanced own-policy',[.565,.50,.365,.41],.965,.936),
            ('emerging','C  Emerging own-policy',[.565,.14,.365,.277],.482,.453)]
    for sample,title,bounds,title_y,stats_y in panels:
        ax=fig.add_axes(bounds)
        z=d[d['sample'].eq(sample)];cs=sorted(z.country.unique())
        matrix=np.zeros((len(cs),len(dates)))
        for row,c in enumerate(cs):
            country=z[z.country.eq(c)]
            for item in country.itertuples():matrix[row,positions[item.period]]=2 if item.ownership_frequency=='Q' else 1
            ax.text(1.035,row,str(len(country)),transform=ax.get_yaxis_transform(),
                    ha='left',va='center',fontsize=10.5,color=NAVY,clip_on=False)
        ax.imshow(matrix,aspect='auto',interpolation='none',cmap=ListedColormap(['#FFFFFF',GOLD,NAVY]),vmin=0,vmax=2)
        # Keep the common calendar while marking the later, unused tail explicitly.
        if sample!='ea':
            last=positions[z.period.max()]+.5
            ax.axvspan(last,len(dates)-.5,facecolor='#EEF1F3',zorder=2)
            ax.axvline(last,color=GRAY,lw=.8,ls=(0,(2,2)),zorder=3)
            ax.text((last+len(dates)-.5)/2,(len(cs)-1)/2,'After sample end',
                    ha='center',va='center',rotation=90,fontsize=9,color=GRAY,zorder=4)
        ax.set_yticks(range(len(cs)),cs,fontsize=11)
        ax.set_xticks(ticks,labels,fontsize=10)
        ax.tick_params(axis='y',length=0,pad=6)
        ax.tick_params(axis='x',length=3,color=GRAY)
        for k in range(len(cs)+1):ax.axhline(k-.5,color='#E4E8EB',lw=.45,zorder=3)
        for spine in ax.spines.values():spine.set_visible(False)
        ax.set_xlim(-.5,len(dates)-.5);ax.set_ylim(len(cs)-.5,-.5)
        ax.text(1.035,1.016,'N',transform=ax.transAxes,ha='left',va='bottom',
                fontsize=10.5,color=GRAY)
        fig.text(bounds[0],title_y,title,ha='left',va='top',fontsize=12,color=NAVY)
        fig.text(bounds[0],stats_y,f'{len(cs)} economies; N = {len(z):,}; {z.period.min()}-{z.period.max()}',
                 ha='left',va='top',fontsize=9.5,color=GRAY)
        if sample=='advanced':
            ax.tick_params(axis='x',labelbottom=False,bottom=False)
        else:
            ax.set_xlabel('Quarter of monetary surprise',fontsize=10.5,labelpad=6)
    fig.legend(handles=[Patch(facecolor=NAVY,label='Quarterly\nownership state'),
                        Patch(facecolor=GOLD,label='Previous-year\nownership state'),
                        Patch(facecolor='white',edgecolor=GRAY,label='Not in\nestimation sample')],
               loc='lower center',bbox_to_anchor=(.51,-.005),ncol=3,frameon=False,
               fontsize=10.5,columnspacing=2.4,handlelength=1.6)
    finish(fig,'country_quarter_coverage')


def matched_propagation():
    lp=pd.read_csv(R/'ml_var_matched_lp.csv');lp=lp[lp.estimator.eq('pds')]
    var=pd.read_csv(R/'ml_var.csv')
    fig,axes=plt.subplots(3,2,figsize=(8.6,6.8),sharex=True,sharey='col')
    for row,(sample,label,color) in enumerate(GROUPS):
        for col,(out,term,title) in enumerate([('log_gdp','domestic_noncb','GDP: ownership gradient'),
                ('log_prices','domestic_noncb_x_refinancing','Prices: refinancing interaction')]):
            ax=axes[row,col]
            for frame,offset,marker,style,name in [(lp,-.14,'o','-','Direct LP'),(var,.14,'s','--','Panel VARX')]:
                z=frame[frame['sample'].eq(sample)&frame.outcome.eq(out)&frame.term.eq(term)&frame.horizon.isin([4,8,12])].sort_values('horizon')
                ax.errorbar(z.horizon+offset,z.estimate,yerr=[z.estimate-z.ci_low,z.ci_high-z.estimate],
                    fmt=marker+style,color=color,lw=1.4,capsize=3,ms=4.8,mfc=color if marker=='o' else 'white',label=name)
            clean(ax);ax.set_title(label+'\n'+title,loc='left',fontsize=10.5)
            ax.set_xticks([4,8,12]);ax.margins(x=.13)
    for ax in axes[-1]:ax.set_xlabel('Quarters after surprise')
    axes[1,0].set_ylabel('Log percentage points');axes[1,1].set_ylabel('Log percentage points')
    fig.legend(handles=[Line2D([0],[0],marker='o',color=NAVY,label='PDS direct LP'),
                        Line2D([0],[0],marker='s',ls='--',mfc='white',color=NAVY,label='PDS panel VARX')],
               loc='upper center',ncol=2,frameon=False,fontsize=10)
    fig.tight_layout(rect=[0,0,1,.95],h_pad=1.7,w_pad=2.0)
    finish(fig,'matched_lp_varx')


def fiscal_external():
    d=pd.read_csv(R/'ml_simultaneous.csv');d=d[d.family.eq('channels')]
    fig,axes=plt.subplots(1,2,figsize=(8.6,3.7))
    for ax,out,title in [(axes[0],'debt_ratio_observed','A  General-government debt / GDP'),(axes[1],'log_reer','B  Real effective exchange rate')]:
        for off,(sample,label,color),marker in zip([-.22,0,.22],GROUPS,['o','s','^']):
            z=d[d['sample'].eq(sample)&d.outcome.eq(out)&d.term.eq('domestic_noncb')].sort_values('horizon')
            ax.errorbar(z.horizon+off,z.estimate,yerr=[z.estimate-z.simultaneous_low,z.simultaneous_high-z.estimate],
                fmt='none',color=color,lw=.7,alpha=.5,capsize=2)
            ax.errorbar(z.horizon+off,z.estimate,yerr=[z.estimate-z.ci_low,z.ci_high-z.estimate],
                fmt=marker,color=color,lw=1.7,ms=5,capsize=3,label=label)
        clean(ax);ax.set_title(title,loc='left');ax.set_xticks([4,8,12]);ax.set_xlabel('Quarters after surprise');ax.margins(x=.12)
    axes[0].set_ylabel('Points of GDP');axes[1].set_ylabel('Log percentage points')
    handles,labels=axes[0].get_legend_handles_labels();fig.legend(handles,labels,loc='upper center',ncol=3,frameon=False,fontsize=9)
    fig.tight_layout(rect=[0,0,1,.90],w_pad=2)
    finish(fig,'fiscal_external_gradients')


def external_mechanisms():
    d=pd.read_csv(R/'mechanism_contrasts.csv')
    fig,axes=plt.subplots(1,2,figsize=(8.6,3.9),sharey=True)
    for ax,sample,label,color in [(axes[0],'advanced','A  Advanced own-policy',NAVY),(axes[1],'emerging','B  Emerging own-policy',TEAL)]:
        for frame,term,offset,marker,name in [(d,'matched baseline gamma',-.065,'o','Baseline PDS'),
                    (d,'augmented gamma',.065,'s','FX + external balance')]:
            z=frame[frame['sample'].eq(sample)&frame.term.eq(term)&frame.horizon.isin([1,2,4])]
            if 'outcome' in z:z=z[z.outcome.eq('log_prices')]
            z=z.sort_values('horizon')
            ax.errorbar(z.horizon+offset,z.estimate,yerr=[z.estimate-z.ci_low,z.ci_high-z.estimate],
                    fmt=marker,color=color,mfc=color if marker=='o' else 'white',capsize=3,lw=1.2,ms=5,label=name)
        clean(ax);ax.set_title(label,loc='left');ax.set_xticks([1,2,4]);ax.set_xlabel('Quarters after surprise');ax.margins(x=.18);ax.text(.04,.94,'Same '+('728' if sample=='advanced' else '403')+' observations',transform=ax.transAxes,va='top',fontsize=9,color=GRAY)
    axes[0].set_ylabel('Price refinancing interaction (log points)')
    handles,labels=axes[0].get_legend_handles_labels();fig.legend(handles,labels,loc='upper center',ncol=3,frameon=False,fontsize=9)
    fig.tight_layout(rect=[0,0,1,.89],w_pad=2)
    finish(fig,'external_mechanism_checks')


def main():
    research_design();ownership_contrast();coverage();matched_propagation();fiscal_external();external_mechanisms()
    from exhibit_style import table, number, pv
    data=pd.read_csv(R/'mechanism_contrasts.csv')
    labels={'matched baseline gamma':r'Baseline $\gamma_P$',
            'augmented gamma':r'Augmented $\gamma_P$',
            'change in gamma':r'Change in $\gamma_P$',
            'FX denomination slope':'FX-denomination slope',
            'external deficit slope':'CA-deficit slope',
            'baseline AE minus EM':'Baseline',
            'augmented AE minus EM':'FX + external balance'}
    for sample,name in [('advanced','advanced'),('emerging','emerging'),('advanced minus emerging','difference')]:
        rows=[]
        for item in data[data['sample'].eq(sample)].itertuples():
            rows.append([item.horizon,labels[item.term],number(item.estimate),number(item.se),pv(item.p_value),pv(item.p_maxT)])
        table('mechanisms_'+name,['$h$','Contrast','Estimate','SE','$p$',r'$p_{\max}$'],rows,'rlrrrr')
    instruments=pd.read_csv(ROOT/'data/monetary_instruments.csv')
    table('official_instruments',['Issuer','Swap maturity','Floating reference in source Table A.1'],
          instruments[['issuer','swap_maturity','floating_reference']].values.tolist(),'lll')
    print('Research diagrams, coverage and coefficient figures generated.',flush=True)


if __name__=='__main__':main()
