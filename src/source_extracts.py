"""Select published government-security observations from the BIS bulk file."""
from pathlib import Path
import zipfile,gzip
import pandas as pd
P=Path(__file__).resolve().parents[1];RAW=P/'data/raw';D=P/'data/processed'

def main():
    D.mkdir(exist_ok=True,parents=True)
    with zipfile.ZipFile(RAW/'bis_national_debt_securities.zip') as z:
        member=next(n for n in z.namelist() if n.endswith('.csv'))
        currency=[]
        for c in pd.read_csv(z.open(member),chunksize=2000,dtype=str,keep_default_na=False):
            a=c[c.REF_AREA.isin('AU BR CA CH CL GB HU IN IL JP KR MX NO NZ PL SE US'.split())&c.REF_SECTOR.isin(['S13','S1311'])&c.STO.eq('LE')&c.ACCOUNTING_ENTRY.eq('L')]
            if len(a):currency.append(a)
        (D/'bis_currency_extract.csv.gz').write_bytes(gzip.compress(pd.concat(currency,ignore_index=True).to_csv(index=False).encode(),mtime=0))
        maturity=[]
        filters={'FREQ':['Q'],'ADJUSTMENT':['N'],'REF_SECTOR':['S13','S1311'],'COUNTERPART_AREA':['XW'],'COUNTERPART_SECTOR':['S1'],'CONSOLIDATION':['N'],'INSTR_ASSET':['F3'],'EXPENDITURE':['_Z'],'CURRENCY_DENOM':['_T'],'VALUATION':['F','M','N'],'PRICES':['V'],'TRANSFORMATION':['N'],'CUST_BREAKDOWN':['_T']}
        for c in pd.read_csv(z.open(member),chunksize=10000,low_memory=False):
            for col,values in filters.items():c=c[c[col].isin(values)]
            if len(c):maturity.append(c)
        (D/'bis_maturity_extract.csv.gz').write_bytes(gzip.compress(pd.concat(maturity,ignore_index=True).to_csv(index=False).encode(),mtime=0))
    print('BIS government security extracts rebuilt',flush=True)

if __name__=='__main__':main()
