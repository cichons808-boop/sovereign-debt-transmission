"""Matched-support fiscal extension and a fixed-spillover PDS sensitivity."""
import gc,json,hashlib
import numpy as np
import selection as ml
from local_projection import fit
from specification import setup

def main():
    data=ml.populations();fits=[]
    for sample in ['ea','advanced','emerging','own','pooled']:
        d,ex,names=setup(data[sample],'rollover',sample!='ea',True)
        for out in ['log_gdp','log_prices']:
            for h in [4,8,12]:
                _,v=fit(d,names,'rollover',out,h,additional_nuisance=ex,return_validation=True)
                for method in ['full','pds']:
                    f=ml.estimate(v,names,ex,method)
                    f.update(sample=sample,outcome=out,horizon=h,model='debt_accumulation',variant='debt accumulation')
                    fits.append(f)
                del v;gc.collect()
        print('accumulation',sample,flush=True)
        ml.dump(fits,'ml_accumulation')
    default=ml.mandatory
    # Source-specific external slopes are forced, while external-state products
    # remain optional. Reconstruct the six baseline state names explicitly.
    forced=[]
    for sample in ['ea','advanced','emerging']:
        d,ex,names=setup(data[sample],'rollover',sample!='ea')
        ml.mandatory=lambda s:default(s) or (s.startswith('external_') and not any(s.endswith('_'+n) for n in names))
        for out in ['log_gdp','log_prices']:
            for h in [4,8,12]:
                _,v=fit(d,names,'rollover',out,h,additional_nuisance=ex,return_validation=True)
                f=ml.estimate(v,names,ex,'pds');f.update(sample=sample,outcome=out,horizon=h,model='rollover',variant='forced external source slopes')
                forced.append(f);del v;gc.collect()
        print('fixed foreign slopes',sample,flush=True)
        ml.dump(forced,'ml_forced_spillover_sensitivity')
    ml.mandatory=default
    (ml.P/'config/foreign_policy.json').write_text(json.dumps(dict(method='same quarterly-HAC PDS penalty as the primary estimator',forced='all source-specific Fed/ECB monetary and information slopes',selected='external-state and other optional interactions',matched_support=True),indent=2)+'\n')
if __name__=='__main__':main()
