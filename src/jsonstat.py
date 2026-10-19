"""Read sparse JSON-stat with source status flags and exact dimensions."""
from pathlib import Path
import json
import numpy as np
import pandas as pd

P=Path(__file__).resolve().parents[1]

def decode(path):
    obj=json.loads(Path(path).read_text())
    ids,sizes=obj['id'],obj['size']
    values=obj.get('value',{})
    if isinstance(values,list):values={str(i):x for i,x in enumerate(values) if x is not None}
    if not values:return pd.DataFrame(columns=ids+['value','status'])
    keys=np.asarray(list(values),int)
    coords=np.asarray(np.unravel_index(keys,sizes)).T
    data={}
    for j,name in enumerate(ids):
        cat=obj['dimension'][name]['category']['index']
        codes=sorted(cat,key=cat.get) if isinstance(cat,dict) else cat
        data[name]=np.asarray(codes)[coords[:,j]]
    data['value']=[values[str(i)] for i in keys]
    statuses=obj.get('status',{})
    if isinstance(statuses,list):data['status']=[statuses[i] if i<len(statuses) else '' for i in keys]
    else:data['status']=[statuses.get(str(i),'') for i in keys]
    return pd.DataFrame(data)


