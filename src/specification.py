"""Fiscal structure and monetary transmission at observed data frequency."""
from pathlib import Path
import gzip,hashlib,json
import numpy as np
import pandas as pd
from scipy.linalg import lstsq
from local_projection import prepared,fit
from international_data import shocks,external_controls
from creditor_sectors import prepare as sector_prepare
from macro_data import EA_ENTRY

P=Path(__file__).resolve().parents[1];D=P/'data/processed';R=P/'results'
EM=set('BR CL CN HU IN MX PL TH'.split())
STATES=['reer_state','ca_state','wti_state','spy_state']

def dump(name,obj):(R/('fiscal_'+name+'.json')).write_text(json.dumps(obj,indent=2,allow_nan=False)+'\n')
def flat(name,fits):
    rows=[]
    for f in fits:
        for e in f.get('estimates',[]):
            rows.append({**{k:f.get(k) for k in ['sample','model','outcome','horizon','n','countries','time_periods','p','variant','pair_sha256']},**e})
    pd.DataFrame(rows).to_csv(R/('fiscal_'+name+'.csv'),index=False)

def macro_controls(d,extra):
    cols={}
    for name in STATES:
        a=d[name];cols['macro_'+name]=a
        for sh in ['mp','info']:
            prod=a*d[sh];key='macro_'+name+'_'+sh;cols[key]=prod
            for lag in [1,2]:cols[key+f'_l{lag}']=prod.groupby(d.country).shift(lag)
    return pd.concat([d,pd.DataFrame(cols,index=d.index)],axis=1),list(extra)+list(cols)

def setup(data,model,external,accumulation=False):
    d,names=prepared(data,model)
    if accumulation:
        name='debt_accumulation';names=names+[name]
        d['a_'+name]=d[name];d['f_'+name]=d.mp*d[name];d['i_'+name]=d['info']*d[name]
        for lag in [1,2]:
            for pre in ['f','i']:d[f'{pre}_{name}_lag{lag}']=d.groupby('country')[pre+'_'+name].shift(lag)
    extra=[]
    if external:d,extra=external_controls(d,names)
    return (*macro_controls(d,extra),names)

def main():
    ea=pd.read_csv(D/'fiscal_panel_ea.csv.gz',float_precision='round_trip')
    own=pd.read_csv(D/'fiscal_panel_external.csv.gz',float_precision='round_trip')
    for d in [ea,own]:d['ea_member']=d.ea_member.astype(bool)
    # Spillovers exclude the observation's own policy authority.
    own.loc[own.country.eq('US'),['Fed_MP','Fed_CBI']]=0.
    s=shocks();s['period']=s.period.astype(str)
    pool_ea=ea[ea.country.isin(EA_ENTRY)].copy();ecb=s[s.issuer.eq('DEU')].set_index('period');fed=s[s.issuer.eq('USA')].set_index('period')
    for col in ['MP_median','CBI_median','MP_pm','CBI_pm','pc1_hf']:pool_ea[col]=pool_ea.period.map(ecb[col])
    pool_ea['ECB_MP']=0.;pool_ea['ECB_CBI']=0.
    pool_ea['Fed_MP']=pool_ea.period.map(fed.MP_median);pool_ea['Fed_CBI']=pool_ea.period.map(fed.CBI_median)
    # Apply common fiscal-control availability in the pooled comparison.
    pool_ea=pool_ea.drop(columns=[c for c in ['primary_balance_lag','net_interest_lag'] if c in pool_ea])
    pooled=pd.concat([pool_ea,own],ignore_index=True,sort=False).sort_values(['country','time_index']).reset_index(drop=True)
    data={}
    for sample,base,mask in [('ea',ea,ea.ea_member),('own',own,own.ea_member),
            ('advanced',own,own.ea_member&~own.country.isin(EM)),('emerging',own,own.ea_member&own.country.isin(EM)),
            ('pooled',pooled,pooled.ea_member)]:
        d=base.copy();d['ea_member']=mask;data[sample]=d
    dump('provenance',dict(
        inputs={n:hashlib.sha256((D/n).read_bytes()).hexdigest() for n in ['fiscal_panel_ea.csv.gz','fiscal_panel_external.csv.gz']},
        script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        controls=STATES,inference='Time-score HAC(12); pointwise confidence intervals',
        policy_blocks='Euro-area countries share one ECB surprise; scores aggregate within quarter'))
    fits=[];keys=[];validation=[];coverage=[]
    for sample,d in data.items():
        dr,er,nr=setup(d,'rollover',sample!='ea');dm,em,nm=setup(d,'ownership_matched',sample!='ea')
        for out in ['log_gdp','log_prices']:
            for h in range(13):
                got=fit(dr,nr,'rollover',out,h,additional_nuisance=er,return_validation=True)
                if not isinstance(got,tuple):
                    fits.append(dict(got,sample=sample,model='rollover',outcome=out,horizon=h));continue
                fr,vr=got;matched=dm.copy();matched['ea_member']=matched.ea_member&matched.index.isin(vr['g'].index)
                fm,vm=fit(matched,nm,'ownership_matched',out,h,additional_nuisance=em,return_validation=True)
                assert np.array_equal(vr['g'].index,vm['g'].index) and np.array_equal(vr['g'].response,vm['g'].response)
                kk=vr['g'][['country','period','ownership_frequency','ownership_measurement_period','maturity_source']].copy()
                pair=hashlib.sha256(kk[['country','period']].to_csv(index=False).encode()).hexdigest()
                kk['sample']=sample;kk['outcome']=out;kk['horizon']=h;keys.append(kk)
                for f in [fr,fm]:f.update(sample=sample,variant='macro conditions',pair_sha256=pair);fits.append(f)
                if out=='log_gdp' and h==4:
                    direct=lstsq(np.column_stack([vr['X0'],vr['F']]),vr['Y'],lapack_driver='gelsd')[0][-len(nr):]
                    err=float(np.max(np.abs(direct-np.array(fr['beta']))));assert err<1e-7
                    validation.append(dict(sample=sample,n=fr['n'],countries=fr['countries'],independent_OLS_error=err))
                    for country,g in vr['g'].groupby('country'):
                        coverage.append(dict(sample=sample,country=country,n=len(g),first=g.period.min(),last=g.period.max(),
                            quarterly_owner_rows=int(g.ownership_frequency.eq('Q').sum()),annual_owner_rows=int(g.ownership_frequency.eq('A').sum()),
                            ca_quarterly_rows=int(g.ca_state_frequency.eq('Q').sum()),ca_annual_rows=int(g.ca_state_frequency.eq('A').sum())))
            print(sample,out,fr.get('n'),fr.get('countries'),flush=True)
        # Fiscal and exchange-rate channels use the same model and focal years.
        for out in ['debt_ratio_observed','log_reer']:
            for h in [4,8,12]:
                f=fit(dr,nr,'rollover',out,h,additional_nuisance=er)
                f.update(sample=sample,variant='fiscal and exchange-rate outcomes');fits.append(f)
        dump('main',fits);flat('main',fits)
    accum=[]
    for sample,d in data.items():
        dx,ex,nx=setup(d,'rollover',sample!='ea',True);db,eb,nb=setup(d,'rollover',sample!='ea')
        for out in ['log_gdp','log_prices']:
            for h in [4,8,12]:
                got=fit(dx,nx,'rollover',out,h,additional_nuisance=ex,return_validation=True)
                if not isinstance(got,tuple):accum.append(dict(got,sample=sample,model='debt_accumulation',outcome=out,horizon=h));continue
                f,v=got;matched=db.copy();matched['ea_member']=matched.ea_member&matched.index.isin(v['g'].index)
                b,vb=fit(matched,nb,'rollover',out,h,additional_nuisance=eb,return_validation=True)
                assert np.array_equal(v['g'].index,vb['g'].index)
                for ff,role in [(b,'matched baseline'),(f,'debt accumulation')]:ff.update(sample=sample,variant=role);accum.append(ff)
        print('fiscal state',sample,f.get('n'),f.get('countries'),flush=True)
    dump('accumulation',accum);flat('accumulation',accum)
    sector=[]
    for kind in ['foreign_official_control','banks_nonbanks']:
        dr,er,nr=sector_prepare(own,kind,True);dr,er=macro_controls(dr,er)
        dm,em,nm=sector_prepare(own,kind,False);dm['est_group']=dm.roll_group;dm,em=macro_controls(dm,em)
        for out in ['log_gdp','log_prices']:
            for h in [4,8,12]:
                got=fit(dr,nr,'rollover',out,h,additional_nuisance=er,return_validation=True)
                if not isinstance(got,tuple):continue
                fr,vr=got;matched=dm.copy();matched['ea_member']=matched.ea_member&matched.index.isin(vr['g'].index)
                fm,vm=fit(matched,nm,'ownership',out,h,additional_nuisance=em,return_validation=True)
                assert np.array_equal(vr['g'].index,vm['g'].index)
                for f,role in [(fr,'rollover'),(fm,'ownership')]:f.update(sample='own',model=kind+'_'+role,variant='creditor sectors');sector.append(f)
        print('sector',kind,fr.get('n'),fr.get('countries'),flush=True)
    dump('sectors',sector);flat('sectors',sector)
    pd.concat(keys).to_csv(R/'fiscal_sample_keys.csv.gz',index=False,compression={'method':'gzip','mtime':0})
    pd.DataFrame(coverage).to_csv(R/'fiscal_country_coverage.csv',index=False)
    dump('validation',dict(status='passed',matched_pairs=len(keys),independent_checks=validation,
        same_outcome_values=True,complete_calendars=True,pooled_ECB_is_one_policy_issuer=True))
    print('Fiscal transmission fits complete.',flush=True)

if __name__=='__main__':main()
