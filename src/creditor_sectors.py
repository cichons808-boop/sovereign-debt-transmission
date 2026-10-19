"""Exploratory holder-sector diagnostics using actual FHL sector stocks.

Foreign official creditors are separated from non-resident banks/nonbanks.
Domestic banks are then separated from domestic nonbanks. The latter are
not equated with households or assumed to have a common consumption MPC.
"""
import json
from datetime import datetime,timezone
import numpy as np
import pandas as pd
from local_projection import DATA,RES,P,fit,prepared
from international_data import external_controls

def prepare(data,kind,rollover):
    d=data.copy();d['mp']=d.MP_median;d['info']=d.CBI_median
    names=['total','domestic_noncb','central_bank','foreign_official']
    states=[d.debt/10,d.domestic_noncb/10,d.cb/10,d.foreign_official_gdp/10]
    if kind=='banks_nonbanks':
        names=['total','domestic_nonbank','central_bank','foreign_official','domestic_bank']
        states=[d.debt/10,d.domestic_nonbank_gdp/10,d.cb/10,d.foreign_official_gdp/10,d.domestic_bank_gdp/10]
    if rollover:
        names=names+[n+'_x_refinancing' for n in names]
        states=states+[a*d.rollover_centered for a in states]
    for name,a in zip(names,states):
        d['a_'+name]=a;d['f_'+name]=d.mp*a;d['i_'+name]=d['info']*a
        for lag in [1,2]:
            d[f'f_{name}_lag{lag}']=d.groupby('country')['f_'+name].shift(lag);d[f'i_{name}_lag{lag}']=d.groupby('country')['i_'+name].shift(lag)
    d['est_group']=d.roll_group if rollover else d.hold_group
    return external_controls(d,names)+(names,)


