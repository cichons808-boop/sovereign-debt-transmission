from pathlib import Path
import sys, json, gzip
import pandas as pd
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
P=ROOT
sys.path.insert(0,str(ROOT/'src'))
(ROOT/'data/processed').mkdir(parents=True,exist_ok=True)
(ROOT/'results').mkdir(exist_ok=True)
f=pd.read_excel(ROOT/'data/raw/fhl.xlsx')
for parts,total in [(['Domestic_Total','Foreign_Total'],'Total_Debt'),(['Domestic_CentralBank','Domestic_Bank','Domestic_NonBank'],'Domestic_Total'),(['Foreign_Official','Foreign_Bank','Foreign_NonBank'],'Foreign_Total')]:
    assert ((f[parts].sum(axis=1)-f[total]).abs()/f.Total_Debt).max()<1e-10
for c in [c for c in f if c.startswith(('Domestic_','Foreign_'))]:
    neg=f[c]<0
    assert (f.loc[neg,c].abs()/f.loc[neg,'Total_Debt']<1e-10).all()
    f.loc[neg,c]=0.
cols={'total_gdp':'Total_Debt','domestic_gdp':'Domestic_Total','foreign_gdp':'Foreign_Total','central_bank_gdp':'Domestic_CentralBank','domestic_bank_gdp':'Domestic_Bank','domestic_nonbank_gdp':'Domestic_NonBank','foreign_official_gdp':'Foreign_Official','foreign_bank_gdp':'Foreign_Bank','foreign_nonbank_gdp':'Foreign_NonBank'}
for k,v in cols.items():f[k]=100*f[v]/f.GDP
f['domestic_private_gdp']=f.domestic_bank_gdp+f.domestic_nonbank_gdp
f.to_csv(ROOT/'data/processed/fhl_holdings.csv',index=False)
import source_extracts
source_extracts.main()
import macro_data as bp
h,ee,ff,j=bp.annual_holdings();dg,rm=bp.maturity();m,q=bp.shocks()
a=bp.attach(bp.macro_quarterly(),h,j,dg,rm,q,'Q')
(P/'data/processed/panel_quarterly.csv.gz').write_bytes(gzip.compress(a.to_csv(index=False).encode(),mtime=0))
print('Quarterly macro panel built',len(a),flush=True)
import international_data
international_data.build()
print('Own-policy macro panel built',flush=True)
import debt_sources as ex
for name in ['imf','bis','qpsd','poland','chile','eurostat','hungary','brazil','india','slovenia','estonia','luxembourg','latvia']:
    print('Normalizing',name,flush=True);getattr(ex,name)()
import currency_states
currency_states.build_states()
import debt_panel
debt_panel.main()
import fiscal_data
fiscal_data.main()
import retail_episodes
retail_episodes.main()
print('DATA REBUILT',flush=True)
