from exhibit_style import *
def allocation():
    d=pd.read_csv(R/'original_informed_allocation_bounds.csv');fig,axs=plt.subplots(1,2,figsize=(6.9,3.15))
    ax=axs[0];ax.scatter(d.marginal_width,d.original_informed_width,s=17,alpha=.65,color=INK,edgecolors='none');lim=max(d.marginal_width.max(),d.original_informed_width.max())*1.05
    ax.plot([0,lim],[0,lim],ls='--',color=GRAY,lw=.8);ax.set_xlim(0,lim);ax.set_ylim(0,lim);ax.set_xlabel('Width from marginal tables (pp GDP)');ax.set_ylabel('Width with original-maturity cells');ax.set_title('109 matched country-years')
    a=d.groupby('country').proportional_width_reduction.median().sort_values();ax=axs[1];ax.barh(a.index,a.values*100,color=TEAL,height=.65);ax.set_xlabel('Median reduction in interval width (%)');ax.set_title('Information gained, by reporting country');ax.tick_params(axis='y',labelsize=7);ax.set_xlim(0,100)
    fig.tight_layout(w_pad=2);save(fig,'panel_allocation_bounds')


if __name__=='__main__':allocation()
