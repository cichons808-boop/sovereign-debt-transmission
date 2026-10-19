from pathlib import Path
import pandas as pd
P=Path(__file__).resolve().parents[1];R=P/'results';ROOT=P
P1=P/'output'
fits=pd.read_csv(R/'ml_lp.csv');sim=pd.read_csv(R/'ml_simultaneous.csv');var=pd.read_csv(R/'ml_var.csv');wild=pd.read_csv(ROOT/'results/primary_PDS_wild_bootstrap.csv')
var_sim=pd.read_csv(R/'ml_var_simultaneous.csv')
def fmt(x):return '$<0.001$' if x<.001 else f'{x:.3f}'
rows=[]
for h in [1,2,4]:
 a=fits[(fits['sample']=='advanced')&(fits.estimator=='pds')&(fits.outcome=='log_prices')&(fits.horizon==h)&(fits.term=='domestic_noncb_x_refinancing')].iloc[0]
 s=sim[(sim['sample']=='advanced')&(sim.outcome=='log_prices')&(sim.horizon==h)&(sim.term=='domestic_noncb_x_refinancing')&(sim.family=='full_curves')]
 if s.empty:s=sim[(sim['sample']=='advanced')&(sim.outcome=='log_prices')&(sim.horizon==h)&(sim.term=='domestic_noncb_x_refinancing')&(sim.family_size==168)]
 s=s.iloc[0]
 v=var[(var['sample']=='advanced')&(var.outcome=='log_prices')&(var.horizon==h)&(var.term=='domestic_noncb_x_refinancing')].iloc[0]
 vs=var_sim[(var_sim['sample']=='advanced')&(var_sim.outcome=='log_prices')&(var_sim.horizon==h)&(var_sim.term=='domestic_noncb_x_refinancing')].iloc[0]
 direct=r'\shortstack{'+f'{a.estimate:.3f}'+r'\\('+f'{a.se:.3f}'+')}'
 iterated=r'\shortstack{'+f'{v.estimate:.3f}'+r'\\('+f'{v.se:.3f}'+')}'
 rows.append(f"{h} & {direct} & {fmt(s.p_maxT)} & {iterated} & {fmt(vs.p_maxT)} \\\\")
(P1/'tables/primary_price_results.tex').write_text('\\begin{tabular}{rrrrr}\n\\toprule\n$h$ & PDS LP (SE) & LP $p_{\\mathrm{curve}}$ & VARX (SE) & VARX $p_{\\mathrm{curve}}$ \\\\\n\\midrule\n'+'\n'.join(rows)+'\n\\bottomrule\n\\end{tabular}\n')
wildrows=[]
for _,w in wild.sort_values('horizon').iterrows():
 wildrows.append(f'{int(w.horizon)} & {w.estimate:.3f} & {w.country_cluster_se:.3f} & {w.country_cluster_t:.3f} & {w.rademacher_p:.4f} & {w.webb_p:.4f} '+r'\\')
(P1/'tables/primary_wild.tex').write_text(r'\begin{tabular}{rrrrrr}'+'\n'+r'\toprule'+'\n'+r'$h$ & Estimate & Country CR1 SE & Country $t$ & Wild signs $p$ & Webb $p$ \\'+'\n'+r'\midrule'+'\n'+'\n'.join(wildrows)+'\n'+r'\bottomrule'+'\n'+r'\end{tabular}'+'\n')
means=pd.read_csv(ROOT/'results/mean_responses_gdp_prices.csv')
rows=[]
for sample,label in [('advanced','Advanced'),('emerging','Emerging')]:
 for h in [1,2,4,8,12]:
  a=means[(means['sample']==sample)&(means.horizon==h)&(means.outcome=='log_gdp')].iloc[0]
  b=means[(means['sample']==sample)&(means.horizon==h)&(means.outcome=='log_prices')].iloc[0]
  rows.append(f'{label} & {h} & {a.estimate:.3f} & ({a.se:.3f}) & {b.estimate:.3f} & ({b.se:.3f}) \\\\')
(P1/'tables/average_responses.tex').write_text('\\begin{tabular}{llrrrr}\n\\toprule\nSetting & $h$ & GDP & SE & Prices & SE \\\\\n\\midrule\n'+'\n'.join(rows)+'\n\\bottomrule\n\\end{tabular}\n')
