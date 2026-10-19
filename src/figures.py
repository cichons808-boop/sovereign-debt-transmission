from plot_io import save_pdf
from pathlib import Path
import os,json
os.environ['MPLBACKEND']='Agg'
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.stats import t
ROOT=Path(__file__).resolve().parents[1];R=ROOT/'results';D=ROOT/'data/processed';P1=ROOT/'output'
BLUE='#243F57';GOLD='#AE7B35';RED='#995345'
plt.rcParams.update({'font.family':'serif','font.size':10,'axes.spines.top':False,'axes.spines.right':False,'axes.labelsize':10,'axes.titlesize':11,'legend.frameon':False,'pdf.fonttype':42,'ps.fonttype':42})
def style(ax):
 ax.axhline(0,color='#777777',lw=.7,zorder=0)
 ax.grid(axis='y',color='#E5E5E5',lw=.6);ax.set_axisbelow(True)
def save(fig,p):
 save_pdf(fig,p,bbox_inches='tight',pad_inches=.12)
 plt.close(fig)

means=pd.read_csv(ROOT/'results/mean_responses_gdp_prices.csv')
fig,axs=plt.subplots(2,2,figsize=(7.0,4.7),sharex=True)
for i,(group,label) in enumerate([('advanced','Advanced own-policy'),('emerging','Emerging own-policy')]):
 for j,(outcome,title) in enumerate([('log_gdp','Real GDP'),('log_prices','Consumer prices')]):
  ax=axs[i,j];z=means[(means['sample']==group)&(means.outcome==outcome)].sort_values('horizon')
  ax.fill_between(z.horizon,z.ci_low,z.ci_high,color=BLUE,alpha=.14,lw=0)
  ax.plot(z.horizon,z.estimate,'o-',color=BLUE,ms=3.4,lw=1.4)
  style(ax);ax.set_title(label+'\n'+title,loc='left',fontweight='bold')
  ax.set_xticks([1,2,4,8,12]);ax.set_ylabel('Log percentage points')
  if i==1:ax.set_xlabel('Quarters after the surprise')
fig.tight_layout(h_pad=1.6,w_pad=1.7);save(fig,P1/'figures/average_responses.pdf')

