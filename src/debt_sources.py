"""Normalize the official data expansion without consulting LP estimates.

Raw annual and quarterly IMF observations are exported separately. Main LP
ownership states keep the previously declared previous-calendar-year rule.
Remaining-maturity states retain their actual observation date/frequency.
"""
from pathlib import Path
import json, gzip, re, zipfile, hashlib, io
import numpy as np
import pandas as pd
from macro_data import ISO2, ISO3, EA_ENTRY

P=Path(__file__).resolve().parents[1]; RAW=P/'data/raw'/'official_expansion'; OUT=P/'data/processed'
NAMES=dict(x.split(':') for x in '''Australia:AU|Austria:AT|Belgium:BE|Bulgaria:BG|Canada:CA|Chile:CL|China:CN|Croatia:HR|Cyprus:CY|Czech Republic:CZ|Denmark:DK|Estonia:EE|Finland:FI|France:FR|Germany:DE|Greece:GR|Hungary:HU|Iceland:IS|India:IN|Ireland:IE|Israel:IL|Italy:IT|Japan:JP|Korea:KR|Latvia:LV|Lithuania:LT|Luxembourg:LU|Malta:MT|Mexico:MX|Netherlands:NL|New Zealand:NZ|Norway:NO|Poland:PL|Portugal:PT|Romania:RO|Slovak Republic:SK|Slovenia:SI|Spain:ES|Sweden:SE|Switzerland:CH|Thailand:TH|United Kingdom:GB|United States:US|Brazil:BR|South Africa:ZA|Turkey:TR|Albania:AL'''.split('|'))

def save(d,name):
    path=OUT/name
    body=d.to_csv(index=False).encode()
    path.write_bytes(gzip.compress(body,mtime=0) if name.endswith('.gz') else body)

def numeric(x):
    return pd.to_numeric(x,errors='coerce')

def imf():
    all_annual=[];all_quarterly=[];all_currency=[]
    for typ in ['AM','EM']:
        f=RAW/f'Database_For_Posting_{typ}_Frozen.xlsx'
        sh=pd.read_excel(f,sheet_name='ExtendedDataset',header=None)
        starts=[i for i,v in enumerate(sh.iloc[:,0]) if isinstance(v,str) and ('(Billion' in v or v.startswith(('Exchange Rate','Debt to GDP')))]
        annual=None
        labels={'Total':'debt_amount','Foreign':'foreign_amount','Foreign Official':'foreign_official_amount',
            'Foreign Banks':'foreign_bank_amount','Foreign Nonbanks':'foreign_nonbank_amount',
            'Domestic Central Bank':'cb_amount','Domestic Banks':'domestic_bank_amount','Domestic Nonbanks':'domestic_nonbank_amount',
            'Debt to GDP':'debt','Exchange Rate':'exchange_rate','Foreign Official Loans':'foreign_official_loans_amount'}
        for start,end in zip(starts,starts[1:]+[len(sh)]):
            title=sh.iloc[start,0]
            label=next((v for k,v in sorted(labels.items(),key=lambda x:-len(x[0])) if title.startswith(k)),None)
            if label is None:continue
            cols=[i for i,v in enumerate(sh.iloc[start,:37]) if i and pd.notna(v) and str(v).strip().isdigit()]
            block=sh.iloc[start+1:end,[0]+cols].copy()
            block.columns=['country_name']+[int(sh.iloc[start,i]) for i in cols]
            block=block[block.country_name.notna()]
            assert not block.country_name.duplicated().any()
            block=block.melt(id_vars='country_name',var_name='year',value_name=label)
            block[label]=numeric(block[label])
            annual=block if annual is None else annual.merge(block,on=['country_name','year'],how='outer',validate='one_to_one')
        annual['country']=annual.country_name.map(NAMES);annual['imf_group']=typ
        annual['source']='IMF_AT_'+typ+'_2025v';annual['date']=annual.year.astype(str)+'-12-31'
        denom=annual.debt_amount
        for name in ['foreign','foreign_official','foreign_bank','foreign_nonbank','cb','domestic_bank','domestic_nonbank','foreign_official_loans']:
            annual[name]=annual[name+'_amount']/denom*annual.debt
        annual['domestic_noncb']=annual.domestic_bank+annual.domestic_nonbank
        annual['domestic']=annual.domestic_noncb+annual.cb
        complete=annual[['debt','cb','domestic_noncb','foreign']].notna().all(axis=1)
        annual['identity_error']=annual.cb+annual.domestic_noncb+annual.foreign-annual.debt
        # Inputs rounded to three decimals in original currency amounts.
        relative=(annual.cb_amount+annual.domestic_bank_amount+annual.domestic_nonbank_amount+annual.foreign_amount-annual.debt_amount).abs()/denom
        bad=complete & (relative>0.001) & (annual.identity_error.abs()>.03)
        assert not bad.any(),annual.loc[bad,['country_name','year','identity_error']].to_dict('records')[:10]
        all_annual.append(annual)
        # Quarterly data: first (all-instrument) block only. Later worksheet
        # blocks are securities/currency subsets and are not new countries.
        qmap={'Table 1. Total':'debt_amount','Table 2. Foreign':'foreign_amount',
            'Table 2.1 ForeignOfficial':'foreign_official_amount','Table 2.2 ForeignBank':'foreign_bank_amount',
            'Table 2.3 ForeignNonbank':'foreign_nonbank_amount','Table 3.1 DomesticCentralBank':'cb_amount',
            'Table 3.2 DomesticBank':'domestic_bank_amount','Table 3.3 DomesticNonbank':'domestic_nonbank_amount'}
        quarterly=None
        for sheet,label in qmap.items():
            a=pd.read_excel(f,sheet_name=sheet,header=None)
            end=next((i for i,v in enumerate(a.iloc[1:,0],1) if pd.isna(v) or (isinstance(v,str) and v.startswith('o/w'))),len(a))
            b=a.iloc[1:end].copy();b.columns=['country_name']+a.iloc[0,1:].astype(str).to_list()
            b=b.melt(id_vars='country_name',var_name='period',value_name=label);b[label]=numeric(b[label])
            quarterly=b if quarterly is None else quarterly.merge(b,on=['country_name','period'],how='outer',validate='one_to_one')
        a=pd.read_excel(f,sheet_name='FX',header=None)
        start=a.index[a.iloc[:,0].eq('Total Debt/GDP')][0]
        end=next((i for i,v in enumerate(a.iloc[start+1:,0],start+1) if pd.isna(v)),len(a))
        b=a.iloc[start+1:end].copy();b.columns=['country_name']+a.iloc[start,1:].astype(str).to_list()
        b=b.melt(id_vars='country_name',var_name='period',value_name='debt');b['debt']=numeric(b.debt)
        quarterly=quarterly.merge(b,on=['country_name','period'],how='left',validate='one_to_one')
        for name in ['foreign','foreign_official','foreign_bank','foreign_nonbank','cb','domestic_bank','domestic_nonbank']:
            quarterly[name]=quarterly[name+'_amount']/quarterly.debt_amount*quarterly.debt
        quarterly['domestic_noncb']=quarterly.domestic_bank+quarterly.domestic_nonbank
        quarterly['country']=quarterly.country_name.map(NAMES);quarterly['imf_group']=typ
        quarterly['source']='IMF_AT_'+typ+'_2025v';all_quarterly.append(quarterly)
        a=pd.read_excel(f,sheet_name='ExtendedDataset_Currency',header=None)
        for start,label in [(0,'local_currency_share'),(next(i for i,v in enumerate(a.iloc[:,0]) if isinstance(v,str) and v.startswith('Foreign holdings')),'foreign_local_currency_share')]:
            end=next((i for i,v in enumerate(a.iloc[start+1:,0],start+1) if pd.isna(v)),len(a))
            b=a.iloc[start+1:end].copy();b.columns=['country_name']+[int(v) for v in a.iloc[start,1:]]
            b=b.melt(id_vars='country_name',var_name='year',value_name='share');b['share']=numeric(b.share)
            b['measure']=label;b['country']=b.country_name.map(NAMES);b['imf_group']=typ
            b['portfolio']='general-government debt securities' if typ=='AM' else 'general-government gross debt'
            assert b.share.dropna().between(0,1.000001).all()
            all_currency.append(b)
    aa=pd.concat(all_annual,ignore_index=True);qq=pd.concat(all_quarterly,ignore_index=True);cc=pd.concat(all_currency,ignore_index=True)
    save(aa,'official_imf_annual_all.csv.gz');save(qq,'official_imf_quarterly_all.csv.gz');save(cc,'official_imf_currency_annual_all.csv.gz')
    a=aa[aa.country.notna()].dropna(subset=['debt','cb','foreign','domestic_noncb']).copy()
    assert not a.duplicated(['country','year']).any()
    save(a,'official_imf_annual_selected.csv.gz')
    print('IMF annual country-years',len(a),'countries',a.country.nunique(),'max identity error',a.identity_error.abs().max(),flush=True)
    return a

def bis():
    d=pd.read_csv(OUT/'bis_maturity_extract.csv.gz',low_memory=False)
    filters=dict(FREQ='Q',ADJUSTMENT='N',COUNTERPART_AREA='XW',COUNTERPART_SECTOR='S1',
        CONSOLIDATION='N',ACCOUNTING_ENTRY='L',STO='LE',INSTR_ASSET='F3',EXPENDITURE='_Z',
        UNIT_MEASURE='USD',CURRENCY_DENOM='_T',PRICES='V',TRANSFORMATION='N',CUST_BREAKDOWN='_T')
    for key,val in filters.items():d=d[d[key].eq(val)]
    d=d[d.MATURITY.isin(['S','LS','T']) & d.VALUATION.isin(['N','F','M']) & d.REF_SECTOR.isin(['S13','S1311'])].copy()
    times=[c for c in d if re.fullmatch(r'\d{4}-Q[1-4]',c)]
    keys=list(filters)+['REF_AREA','REF_SECTOR','VALUATION','MATURITY']
    assert not d.duplicated(keys).any(),d.loc[d.duplicated(keys,keep=False),'Series'].to_list()
    dd=d[keys+['Series']+times].melt(id_vars=keys+['Series'],var_name='period',value_name='value').dropna(subset=['value'])
    dd['period']=dd.period.str.replace('-','',regex=False)
    idx=['REF_AREA','REF_SECTOR','VALUATION','period']
    w=dd.pivot(index=idx,columns='MATURITY',values='value').reset_index()
    w['refinance_share']=(w.S+w.LS)/w['T']
    w=w.dropna(subset=['refinance_share']);w=w[w['T'].ne(0)]
    assert w.refinance_share.between(0,1.002).all(),w.loc[~w.refinance_share.between(0,1.002),idx+['refinance_share']].to_dict('records')
    w=w.rename(columns={'REF_AREA':'country','REF_SECTOR':'sector','VALUATION':'valuation'})
    w['frequency']='Q';w['source']='BIS_NA_SEC';w['portfolio']='debt securities';w['unit']='share'
    save(w,'official_bis_maturity_all.csv.gz')
    print('BIS maturity observed',len(w),'countries',w.country.nunique(),flush=True)
    return w

def qpsd():
    rows=[]
    for f in sorted(RAW.glob('qpsd_*.json.gz')):
        obj=json.loads(gzip.decompress(f.read_bytes()))
        assert int(obj[0]['pages'])==1
        for r in obj[1]:
            if r.get('value') is None:continue
            iso=r.get('countryiso3code') or r['country']['id']
            rows.append(dict(country=ISO2.get(iso),iso3=iso,period=r['date'],
                indicator=r['indicator']['id'],value=r['value'],source_file=f.name))
    long=pd.DataFrame(rows);long=long[long.country.notna()]
    save(long,'official_qpsd_observed.csv.gz')
    out=[]
    for sec in ['GG','CG','BC']:
        indicators={'DP.DOD.DECT.CR.'+sec:'total','DP.DOD.DSTC.CR.'+sec:'short_original',
            'DP.DOD.DLTC.CR.L1.'+sec:'long_due_1yr','DP.DOD.DLTC.CR.M1.'+sec:'long_due_later'}
        a=long[long.indicator.isin(indicators)].copy();a['measure']=a.indicator.map(indicators)
        a=a.pivot(index=['country','period'],columns='measure',values='value').reset_index()
        a['refinance_share']=(a.short_original+a.long_due_1yr)/a.total
        a=a.dropna(subset=['refinance_share']);a=a[a.total>0]
        assert a.refinance_share.between(0,1.000001).all()
        a['sector']={'GG':'S13','CG':'S1311','BC':'budgetary central government'}[sec]
        a['source']='QPSD_'+sec;a['valuation']='nominal';a['portfolio']='all reported debt instruments'
        a['frequency']='Q';a['date']=pd.PeriodIndex(a.period,freq='Q').to_timestamp(how='end').normalize()
        a['numerator']=a.short_original+a.long_due_1yr;a['denominator']=a.total
        out.append(a)
    d=pd.concat(out,ignore_index=True);save(d,'official_qpsd_maturity_all.csv.gz')
    return d

def poland():
    f=RAW/'poland_state_treasury.xlsx';out=[]
    for sheet,totalrow,shortrow,portfolio in [('debt by maturity',2,3,'State Treasury gross debt'),
        ('debt by maturity TS',2,3,'domestic-market Treasury securities')]:
        a=pd.read_excel(f,sheet_name=sheet,header=None)
        for col in range(1,a.shape[1]):
            dt=pd.to_datetime(a.iloc[1,col],errors='coerce')
            if pd.isna(dt):continue
            den=pd.to_numeric(a.iloc[totalrow,col],errors='coerce');num=pd.to_numeric(a.iloc[shortrow,col],errors='coerce')
            if pd.isna(den) or den<=0 or pd.isna(num):continue
            bins=pd.to_numeric(a.iloc[3:8 if sheet=='debt by maturity' else 7,col],errors='coerce')
            assert np.isclose(bins.sum(),den,atol=.15,rtol=1e-6),(sheet,dt,den,bins.to_list())
            out.append(dict(country='PL',date=dt,period=str(pd.Period(dt,'Q')),frequency='M',
                refinance_share=float(num/den),numerator=float(num),denominator=float(den),
                source='PL_MF_'+('all' if sheet=='debt by maturity' else 'domestic_securities'),
                sector='S1311',valuation='nominal',portfolio=portfolio,source_file=f.name,source_detail=sheet))
    d=pd.DataFrame(out);assert d.refinance_share.between(0,1).all();save(d,'official_poland_maturity_monthly.csv.gz')
    return d

def chile():
    import fitz
    out=[];witness=[]
    for f in sorted(RAW.glob('chile_debt_20*.pdf')):
        year=int(f.stem[-4:]);doc=fitz.open(f)
        pages=[(i,g.get_text()) for i,g in enumerate(doc) if 'Resto' in g.get_text() and 'Amortizaciones de Deuda' in g.get_text()]
        assert len(pages)==1,(f.name,len(pages))
        i,t=pages[0];t=t[t.index('Amortizaciones de Deuda'):]
        matches=list(re.finditer(r'(?m)^(20\d{2}|Resto)\s*$',t));values=[]
        for j,m in enumerate(matches):
            if m.group(1)!='Resto' and int(m.group(1))<=year:continue
            block=t[m.end():matches[j+1].start() if j+1<len(matches) else len(t)]
            ns=[]
            for line in block.splitlines():
                if re.fullmatch(r'\s*-?\d[\d.,]*(?:\s+-?\d[\d.,]*)*\s*',line):ns.extend(line.split())
                if len(ns)>=11:break
            numbers=[]
            for n in ns[:11]:
                if ',' in n and ('.' in n or re.search(r',\d{1,2}$',n)):n=n.replace('.','').replace(',','.')
                elif ',' in n:n=n.replace(',','')
                else:n=n.replace('.','')
                numbers.append(float(n))
            assert len(numbers)==11,(f.name,m.group(1),numbers)
            assert np.isclose(numbers[0]+numbers[5],numbers[10],atol=2,rtol=2e-6),(f.name,m.group(1),numbers)
            values.append((m.group(1),numbers))
            witness.append(dict(report_year=year,page=i+1,redemption_year=m.group(1),
                central_government=numbers[0],central_bank=numbers[5],consolidated=numbers[10],
                source_file=f.name,raw_numeric_cells=json.dumps(ns[:11])))
        assert values[0][0]==str(year+1) and values[-1][0]=='Resto'
        num=values[0][1][0];den=sum(v[0] for _,v in values)
        out.append(dict(country='CL',date=f'{year}-12-31',period=f'{year}Q4',frequency='A',
            refinance_share=num/den,numerator=num,denominator=den,source='CL_Hacienda_schedule',
            sector='S1311',valuation='principal repayment schedule',
            portfolio='central-government scheduled principal excluding Treasury bonds held by Corfo; older reports also exclude fiscal promissory notes to the central bank',
            source_file=f.name,source_detail=f'Amortizaciones de Deuda, p. {i+1}; central-government TOTAL, next calendar year / all future years including Resto'))
    d=pd.DataFrame(out);assert d.refinance_share.between(0,1).all()
    save(d,'official_chile_maturity_annual.csv.gz');save(pd.DataFrame(witness),'official_chile_schedule_cells.csv.gz')
    return d

def eurostat():
    # JSON-stat decoding, retaining original status flags, without writing a
    # second temporary source or discarding source dimensions.
    obj=json.loads(gzip.decompress((RAW/'eurostat_rmd_all_sectors.json.gz').read_bytes()))
    ids,sizes=obj['id'],obj['size'];v=obj['value'];keys=np.asarray(list(v),int)
    coords=np.asarray(np.unravel_index(keys,sizes)).T;cols={}
    for j,k in enumerate(ids):
        ind=obj['dimension'][k]['category']['index'];codes=sorted(ind,key=ind.get) if isinstance(ind,dict) else ind
        cols[k]=np.asarray(codes)[coords[:,j]]
    cols['value']=[v[str(i)] for i in keys]
    d=pd.DataFrame(cols);d['country']=d.geo.replace({'EL':'GR','UK':'GB'});d['year']=d.time.astype(int)
    d=d[d.country.isin(ISO3)&d.na_item.eq('GD')]
    w=d.pivot(index=['country','sector','year'],columns='maturity',values='value').reset_index()
    w['denominator']=w.TOTAL.fillna(w.Y_LE1+w.Y_GT1)
    # Complete disjoint remaining-maturity bins are another valid total.
    bins=['Y_LE1','Y1-5','Y5-10','Y10-30','Y_GT30']
    w['denominator']=w.denominator.fillna(w[bins].sum(axis=1,min_count=len(bins)))
    e=pd.read_csv(OUT/'holdings_annual_eurostat.csv')[['country','year','debt']]
    w=w.merge(e,on=['country','year'],how='left',validate='many_to_one')
    w['denominator_from_same_S13_Maastricht_total']=w.denominator.isna() & w.sector.eq('S13') & w.debt.notna()
    w.loc[w.denominator_from_same_S13_Maastricht_total,'denominator']=w.loc[w.denominator_from_same_S13_Maastricht_total,'debt']
    w['numerator']=w.Y_LE1;w['refinance_share']=w.numerator/w.denominator
    w=w.dropna(subset=['refinance_share']);w=w[w.denominator>0]
    assert w.refinance_share.between(0,1.01).all()
    w['source']='EurostatRMD';w['frequency']='A';w['date']=w.year.astype(str)+'-12-31';w['period']=w.year.astype(str)+'Q4'
    w['valuation']='nominal';w['portfolio']='Maastricht gross debt';w['source_file']='eurostat_rmd_all_sectors.json.gz'
    save(w,'official_eurostat_maturity_annual.csv.gz');return w

def hungary():
    out=[];audit=[]
    for f in sorted(RAW.glob('hungary_maturity_*.xls')):
        dt=pd.Timestamp(f.stem[-8:]);q=pd.Period(dt,'Q');book=pd.ExcelFile(f)
        a=pd.read_excel(book,sheet_name=0,header=None)
        # The standard subtotal excludes the separately listed other
        # obligations. Before that subtotal was introduced, the numeric
        # instrument rows are disjoint (HUF/FX section headings are blank).
        inds=[i for i,s in enumerate(a.iloc[:,0]) if isinstance(s,str) and s.strip().lower()=='összesen']
        if inds: row=pd.to_numeric(a.iloc[inds[0],1:],errors='coerce')
        else:
            body=a.iloc[4:,1:].apply(pd.to_numeric,errors='coerce')
            row=body[body.iloc[:,0].notna()].sum(axis=0,min_count=1)
        den=float(row.iloc[0]);flow=row.iloc[1:]
        assert den>0 and np.isclose(flow.sum(),den,atol=.3,rtol=.001),(f.name,den,float(flow.sum()))
        source='HU_AKK_CG';detail='Central-government HUF and FX debt; excludes separately listed other obligations'
        if len(book.sheet_names)>1:
            b=pd.read_excel(book,sheet_name=1,header=None)
            inds=[i for i,s in enumerate(b.iloc[:,0]) if isinstance(s,str) and s.strip().lower()=='összesen']
            assert len(inds)==1,f.name
            cols=[i for i,s in enumerate(b.iloc[3]) if isinstance(s,str) and re.fullmatch(r'\d{4}\.Q[1-4]',s)]
            periods=[pd.Period(b.iloc[3,j].replace('.',''),'Q') for j in cols]
            assert periods[:4]==list(pd.period_range(q+1,q+4,freq='Q')),f.name
            v=pd.to_numeric(b.iloc[inds[0],cols],errors='coerce')
            assert v.iloc[:4].notna().all()
            assert np.isclose(v.sum(),den,atol=.4,rtol=.001),(f.name,den,float(v.sum()))
            num=float(v.iloc[:4].sum());freq='Q';witness='Quarterly schedule: sum of the next four quarters / reported stock'
        elif q.quarter==4:
            assert int(a.iloc[3,2])==dt.year+1,f.name
            num=float(flow.iloc[0]);freq='A';witness='Year-end annual schedule: following calendar-year principal / reported stock'
        else:
            audit.append(dict(source_file=f.name,date=str(dt.date()),status='not_used_for_one_year_share',reason='Only calendar-year buckets; next 12 months not point identified at an intra-year date'))
            continue
        out.append(dict(country='HU',date=dt,period=str(q),frequency=freq,refinance_share=num/den,
            numerator=num,denominator=den,source=source,sector='S1311',valuation='scheduled principal at reported exchange rates',
            portfolio=detail,source_file=f.name,source_detail=witness))
        audit.append(dict(source_file=f.name,date=str(dt.date()),status='valid',frequency=freq,numerator=num,denominator=den,
            published_schedule_minus_stock=float(flow.sum()-den),relative_schedule_gap=float((flow.sum()-den)/den)))
    d=pd.DataFrame(out);assert d.refinance_share.between(0,1).all()
    save(d,'official_hungary_maturity.csv.gz');save(pd.DataFrame(audit),'official_hungary_schedule_audit.csv')
    return d

def brazil():
    f=RAW/'brazil_rmd_annex.zip';z=zipfile.ZipFile(f)
    member=next(n for n in z.namelist() if n.endswith('.xlsx'))
    book=pd.ExcelFile(io.BytesIO(z.read(member)))
    a=pd.read_excel(book,sheet_name='3.1',header=None);out=[]
    labels=[(i,str(v).strip()) for i,v in enumerate(a.iloc[:,0]) if str(v).strip() in ['DPF','DPMFi','DPFe']]
    for pos,(start,label) in enumerate(labels):
        end=labels[pos+1][0] if pos+1<len(labels) else len(a)
        for i in range(start+1,end):
            if not isinstance(a.iloc[i,0],(pd.Timestamp,__import__('datetime').datetime)):continue
            dt=pd.Timestamp(a.iloc[i,0])+pd.offsets.MonthEnd(0)
            num=pd.to_numeric(a.iloc[i,1],errors='coerce');den=pd.to_numeric(a.iloc[i,13],errors='coerce')
            if pd.isna(num) or pd.isna(den) or den<=0:continue
            bins=pd.to_numeric(a.iloc[i,[1,3,5,7,9,11]],errors='coerce')
            assert bins.notna().all() and np.isclose(bins.sum(),den,rtol=2e-6,atol=.05),(dt,label)
            published=pd.to_numeric(a.iloc[i,2],errors='coerce')
            assert np.isclose(num/den,published,atol=.00005),(dt,label,num/den,published)
            portfolio={'DPMFi':'federal domestic marketable debt','DPF':'federal public debt; external flows at present value from 2010',
                'DPFe':'federal external debt; flows at present value from 2010'}[label]
            out.append(dict(country='BR',date=dt,period=str(pd.Period(dt,'Q')),frequency='M',
                refinance_share=float(num/den),numerator=float(num),denominator=float(den),
                source='BR_Tesouro_'+label,sector='S1311',valuation='source debt-accounting value',portfolio=portfolio,
                source_file=f.name,source_detail=f'{member}; worksheet 3.1, {label}; Até 12 meses / Total'))
    d=pd.DataFrame(out);assert d.refinance_share.between(0,1).all();save(d,'official_brazil_maturity_monthly.csv.gz');return d

def india():
    # Published Table 5.3 values, precision and source URLs.
    f=RAW/'india_dea_table53_transcription.json';obj=json.loads(f.read_text());out=[]
    for block in obj['tables']:
        for year,amount,share,gdp in block['rows']:
            out.append(dict(country='IN',date=f'{year}-03-31',period=f'{year}Q1',frequency='A',
                refinance_share=share/100,numerator=amount,denominator=np.nan,published_percent=share,
                short_debt_percent_gdp=gdp,source='IN_DEA_GG_'+('revised2023' if block['vintage']>='2022-23' else 'earlier'),
                sector='S13',valuation='reported public-debt value',portfolio='consolidated general-government public debt, published Table 5.3 denominator',
                source_file=f.name,source_detail=block['url']+'; Table 5.3; '+block['vintage'],
                vintage=block['vintage'],retrieval_method=obj['retrieval_method']))
    allrows=pd.DataFrame(out);save(allrows,'official_india_maturity_all_vintages.csv.gz')
    d=allrows.sort_values(['date','vintage']).drop_duplicates(['country','date'],keep='last')
    assert d.refinance_share.between(0,1).all();save(d,'official_india_maturity_annual.csv.gz');return d

def slovenia():
    import fitz
    out=[]
    for f in sorted(RAW.glob('slovenia_debt_20*.pdf')):
        vintage=int(f.stem[-4:]);doc=fitz.open(f)
        for i,pg in enumerate(doc):
            t=pg.get_text();m=re.search(r'(?:pod\s+1\s+letom|Do\s+1\s+leta)\s*',t,re.I)
            if m is None:continue
            # Take only the table whose title explicitly denotes time to
            # maturity, not maturity at issuance or an issuance-flow table.
            before=t[:m.start()];starts=list(re.finditer(r'Tabela\s+\d+[-.]\d+\s*:',before))
            assert starts,(f.name,i)
            head=before[starts[-1].start():]
            assert ('do dospetja' in head or 'do zapadlosti' in head),(f.name,i,head[:150])
            # Report 2012 prints the column year 2010 as "20010". The raw
            # PDF is retained; this unambiguous header typo is not a data fill.
            if vintage==2012:head=head.replace('20010','2010')
            years=[int(v) for v in re.findall(r'\b(?:19|20)\d{2}\b',head)]
            # The year range is also printed in the title; actual columns are
            # the final uninterrupted annual sequence ending at report year.
            unique=[]
            for y in reversed(years):
                if y in unique:break
                unique.append(y)
            years=list(reversed(unique))
            if not years or years[-1]!=vintage:continue
            assert years==list(range(years[0],years[-1]+1)),(f.name,years)
            after=t[m.end():];ns=re.findall(r'(?m)^\s*(\d{1,3}(?:[,.]\d+)?)\s*%?\s*$',after)
            vals=[float(v.replace(',','.')) for v in ns[:len(years)]]
            assert len(vals)==len(years) and all(0<=v<=100 for v in vals)
            for year,val in zip(years,vals):
                out.append(dict(country='SI',date=f'{year}-12-31',period=f'{year}Q4',frequency='A',
                    refinance_share=val/100,published_percent=val,numerator=np.nan,denominator=np.nan,
                    source='SI_MF_budget_debt',sector='S1311',valuation='reported principal stock',
                    portfolio='state-budget debt; actual remaining time to maturity',source_file=f.name,
                    source_detail=f'{head.splitlines()[0]}; p. {i+1}; below one year, published percentage',vintage=vintage))
    a=pd.DataFrame(out);assert not a.empty
    save(a,'official_slovenia_maturity_all_vintages.csv.gz')
    d=a.sort_values(['date','vintage']).drop_duplicates(['country','date'],keep='last')
    save(d,'official_slovenia_maturity_annual.csv.gz');return d

def estonia():
    import fitz
    out=[]
    files=sorted(RAW.glob('estonia_consolidated_*.pdf'))+sorted(RAW.glob('estonia_et_consolidated_*.pdf'))
    for f in files:
        vintage=int(f.stem[-4:]);doc=fitz.open(f)
        original_pages=[pg.get_text() for pg in doc];pages=original_pages
        if f.name.startswith('estonia_et_'):
            translations={'Lisa c14':'Note c14','Lisa c15':'Note c15','Laenukohustised':'Loan liabilities','Laenukohustused':'Loan liabilities',
                'Valitsussektor':'General government','Jääk seisuga':'Balance as of','Kuni 1 aasta':'Up to 1 year',
                '1 kuni 5 aastat':'1 to 5 years','Üle 5 aasta':'More than 5 years',
                'Laenukohustiste liikumine':'Movements in loan liabilities','Laenukohustiste muutused':'Movements in loan liabilities'}
            pages=[]
            for text in original_pages:
                for a,b in translations.items():text=text.replace(a,b)
                lines=[]
                for line in text.splitlines():
                    if re.fullmatch(r'\s*[-−–]?[\d ]+(?:,\d+)?\s*',line):line=re.sub(r'\s','',line).replace(',','.')
                    lines.append(line)
                pages.append('\n'.join(lines))
        text='\n'.join(pages)
        starts=list(re.finditer(r'Note\s+c14\s+Loan liabilities',text))
        if not starts:continue
        chunk=text[starts[-1].end():];chunk=chunk[:re.search(r'Note\s+c15',chunk).start()] if re.search(r'Note\s+c15',chunk) else chunk[:14000]
        marker=re.search(r'B\.\s+General government',chunk,re.I)
        assert marker,(f.name,chunk[:120])
        gg=chunk[marker.end():]
        if 'Movements in loan liabilities' in gg:gg=gg[:gg.index('Movements in loan liabilities')]
        pat=r'Balance as of\s+31[./]12[./](\d{4})\s+((?:[\d,.]+\s+){4})Up to 1 year\s+((?:[\d,.]+\s+){4})1 to 5 years\s+((?:[\d,.]+\s+){4})More than 5 years\s+((?:[\d,.]+\s+){3}[\d,.]+)'
        found=list(re.finditer(pat,gg));assert found,(f.name,gg[:400])
        page_candidates=[i+1 for i,t in enumerate(pages) if re.search(r'Note\s+c14\s+Loan liabilities',t)]
        page=page_candidates[-1] if page_candidates else next(i+1 for i,t in enumerate(pages) if 'Note c14' in t)
        for m in found:
            year=int(m.group(1));values=[[float(v.replace(',','')) for v in m.group(j).split()] for j in range(2,6)]
            den,num,mid,long=[v[-1] for v in values]
            rounding_tolerance=2.1 if vintage<=2010 else .21
            assert np.isclose(num+mid+long,den,atol=rounding_tolerance),(f.name,year,values)
            component_errors=[sum(v[:3])-v[3] for v in values]
            # Published 2020 note c14 has an inconsistent 2018 lease cell in
            # the instrument breakdown. The TOTAL column independently sums
            # across residual-maturity bins and is the column used here.
            out.append(dict(country='EE',date=f'{year}-12-31',period=f'{year}Q4',frequency='A',
                refinance_share=num/den,numerator=num,denominator=den,source='EE_MF_GG_accounts',sector='S13',
                valuation='financial-statement carrying value',portfolio='consolidated general-government bonds, loans and finance leases',
                source_file=f.name,source_detail=f'Note c14 / Lisa c14, B. General government / Valitsussektor; residual maturity up to 1 year; note starts p. {page}',vintage=vintage,
                source_language='Estonian' if f.name.startswith('estonia_et_') else 'English',
                published_component_sum_errors=json.dumps(component_errors)))
    a=pd.DataFrame(out);assert not a.empty;save(a,'official_estonia_maturity_all_vintages.csv.gz')
    d=a.sort_values(['date','vintage']).drop_duplicates(['country','date'],keep='last')
    save(d,'official_estonia_maturity_annual.csv.gz');return d

def latvia():
    import fitz
    out=[];audit=[]
    files=sorted(RAW.glob('latvia_debt_*.pdf'))+sorted(RAW.glob('latvia_annual_*.pdf'))
    for f in files:
        doc=fitz.open(f);rows=[]
        for page,pg in enumerate(doc,1):
            text=pg.get_text()
            if not re.search(r'Maturity\s+profile',text,re.I):continue
            tables=[]
            for tab in pg.find_tables().tables:
                cells=tab.extract()
                if any(re.search(r'Maturity\s+profile',str(v),re.I) for r in cells for v in r):tables.append(cells)
            if not tables:continue
            cells=min(tables,key=lambda t:len(t)*max(len(r) for r in t))
            headers=[]
            for i,row in enumerate(cells):
                dates=[(j,re.search(r'\b(\d{1,2}[./]\d{1,2}[./]\d{4})\b',str(v))) for j,v in enumerate(row)]
                dates=[(j,m.group(1)) for j,m in dates if m]
                if dates:headers.append((i,row,dates))
            if not headers:continue
            hi,head,dates=headers[0]
            mi=next(i for i,r in enumerate(cells) if any(re.search(r'Maturity\s+profile',str(v),re.I) for v in r))
            end=mi+1
            while end<len(cells) and (not cells[end][0] or re.search(r'^\s*(?:<|≤|[\d%., ]+)',str(cells[end][0]))):end+=1
            segment=cells[mi:end]
            boundaries=sorted(set([j for j,v in dates]+[j for j,v in enumerate(head) if v and 'STRATEGY' in str(v).upper()]+[len(head)]))
            for col,dt in dates:
                stop=next(j for j in boundaries if j>col)
                content=' '.join(str(v) for r in segment for v in r[col:stop] if v)
                values=re.findall(r'(?<!\d)(\d+(?:[.,]\d+)?)\s*%',content)
                if not values:continue
                # An explicit bound is not treated as a point observation.
                first=re.search(r'([<≤]?\s*\d+(?:[.,]\d+)?)\s*%',content)
                if first and first.group(1).lstrip().startswith(('<','≤')):
                    audit.append(dict(source_file=f.name,date=dt,status='interval_only',witness=content));continue
                share=float(values[0].replace(',','.'))/100
                day,month,year=map(int,re.split(r'[./]',dt))
                if day==31 and month in [4,6,9,11]:
                    date=pd.Timestamp(year,month,1)+pd.offsets.MonthEnd(0)
                    audit.append(dict(source_file=f.name,status='invalid_end_month_day_corrected',date_label=dt,corrected_date=str(date.date()),reason='Published table says day 31 in a 30-day month; retain the same month-end reference'))
                else:date=pd.Timestamp(year,month,day)
                assert 0<=share<=1,(f.name,dt,content)
                rows.append(dict(country='LV',date=date,period=str(pd.Period(date,'Q')),
                    frequency='M' if re.search(r'M\d\d',f.stem) else ('A' if 'annual' in f.name else 'Q'),
                    refinance_share=share,published_percent=share*100,numerator=np.nan,denominator=np.nan,
                    source='LV_Treasury_CG',sector='S1311',valuation='source central-government debt stock',
                    portfolio='central-government debt portfolio, residual maturity',source_file=f.name,
                    source_detail=f'Parameters of the Central Government Debt Portfolio Structure; p. {page}; maturity profile <=1 year; date column {dt}',
                    numeric_witness=content,original_date_label=dt))
        if rows:
            vintage=max(r['date'] for r in rows)
            for r in rows:r['vintage']=vintage
            out.extend(rows)
        audit.append(dict(source_file=f.name,status='valid' if rows else 'not_extracted',observations=len(rows)))
    a=pd.DataFrame(out);assert not a.empty
    save(a,'official_latvia_maturity_all_vintages.csv.gz')
    # A few early bulletins print date headings more than one year before
    # their reporting period. Retain those published cells in the raw export,
    # but do not let an anomalous heading replace a contemporaneous reading.
    valid=a[(a.vintage-a.date).dt.days.between(0,370)].copy()
    d=valid.sort_values(['date','vintage','source_file']).drop_duplicates(['country','date'],keep='last')
    save(d,'official_latvia_maturity.csv.gz');save(pd.DataFrame(audit),'official_latvia_extraction_audit.csv')
    return d

def luxembourg():
    import fitz
    out=[];cells=[];audit=[]
    for f in sorted(RAW.glob('luxembourg_account_*.pdf')):
        year=int(f.stem[-4:]);doc=fitz.open(f)
        text='\n'.join(g.get_text() for g in list(doc)[:16])
        tables=list(re.finditer(r'Tableau\s+\d+\s*[: ]\s*([^\n]*(?:\n[^\n]*){0,2})',text))
        selected=None
        for m in tables:
            title=m.group(1).lower()
            if ('encours' in title or ('existants' in title and 'obligataires' in title)) and ('obligataires' in title or 'dette' in title):
                selected=m;break
        if selected is None:
            audit.append(dict(source_file=f.name,year=year,status='no_complete_debt_stock_table',reason='New-issuance-only tables are not outstanding stocks'))
            continue
        chunk=text[selected.end():]
        stops=[m.start() for m in re.finditer(r'(?:Tableau\s+\d+\s*:|Graphique|Note\s*[: ]|A noter que|En ce qui concerne)',chunk)]
        if stops:chunk=chunk[:min(stops)]
        matches=list(re.finditer(r'(?:GRAND[- ]DUCHE|BEI|BCEE)\b',chunk));instruments=[]
        for j,m in enumerate(matches):
            block=chunk[m.start():matches[j+1].start() if j+1<len(matches) else len(chunk)]
            if not block.startswith(('GRAND-DUCHE','GRAND DUCHE')) or 'SUKUK' in block:continue
            dates=re.findall(r'\b(\d{1,2}[./]\d{1,2}[./]\d{4})\b',block)
            amounts=re.findall(r'(?m)^\s*([\d][\d. \u00a0\u2002\u2003\u2008\u202f]*(?:,\d+)?)\s*$',block)
            amounts=[v for v in amounts if not re.fullmatch(r'\s*\d{1,2}\.\d{1,2}\.\d{4}\s*',v)]
            amounts=[float(re.sub(r'[.\s\u00a0\u2002\u2003\u2008\u202f]','',v).replace(',','.')) for v in amounts]
            amounts=[v for v in amounts if v>=1_000_000]
            if not dates or len(amounts)!=1:
                raise ValueError((f.name,block[:350],dates,amounts))
            # The 2016 report explicitly includes a starred January-2017
            # issuance in a table labelled "current". It is excluded from
            # the 2016 stock. Existing bonds have no 2016 redemption.
            if year==2016 and '(*)' in block:continue
            date=pd.to_datetime(dates[-1].replace('.','/'),dayfirst=True)
            amount=amounts[0]
            assert date>pd.Timestamp(f'{year}-12-31'),(f.name,date)
            instruments.append((date,amount))
            cells.append(dict(country='LU',report_year=year,source_file=f.name,maturity_date=str(date.date()),amount_eur=amount,
                text_witness=block.strip(),definition='classical central-government bullet bonds; excludes bank loans and SUKUK'))
        if not instruments:continue
        den=sum(v for _,v in instruments);num=sum(v for date,v in instruments if date<=pd.Timestamp(f'{year+1}-12-31'))
        out.append(dict(country='LU',date=f'{year}-12-31',period=f'{year}Q4',frequency='A',refinance_share=num/den,
            numerator=num,denominator=den,source='LU_IGF_classical_bonds',sector='S1311',valuation='nominal',
            portfolio='classical central-government bullet bonds, including private placement; excludes bank loans and SUKUK',
            source_file=f.name,source_detail='Published outstanding-instrument table; nominal stock of bonds redeeming next calendar year / all listed classical bonds'))
        audit.append(dict(source_file=f.name,year=year,status='valid',bonds=len(instruments),numerator=num,denominator=den))
    a=pd.DataFrame(out);assert not a.empty
    save(a,'official_luxembourg_maturity_annual.csv.gz');save(pd.DataFrame(cells),'official_luxembourg_bond_cells.csv.gz');save(pd.DataFrame(audit),'official_luxembourg_schedule_audit.csv')
    return a

if __name__=='__main__':
    imf();bis();qpsd();poland();chile();eurostat();hungary();brazil();india();slovenia();estonia();luxembourg();latvia()
