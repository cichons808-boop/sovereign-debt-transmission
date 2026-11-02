import json
from datalake.extra_sources import nbp_json
from datalake.model import Job
from datalake.storage import Lake


def test_historical_union_currencies_keep_native_country_and_symbol(tmp_path):
    # Structural fixture: historical APIs may repeat a currency/symbol across countries.
    obj=[{'table':'B','no':'fixture','effectiveDate':'2003-04-01','rates':[
        {'country':'Mikronezja, Federacja','symbol':'787','currency':'dolar','code':'USD','mid':4},
        {'country':'Palau','symbol':'787','currency':'dolar','code':'USD','mid':4}]}]
    p=tmp_path/'raw.json';p.write_text(json.dumps(obj))
    raw={'snapshot_id':'fixture','sha256':'0'*64,'retrieved_at':'2026-11-02'}
    out=next(nbp_json(Job('NBP','exchange_rates_B','nbp_json','https://example.invalid'),raw,p,Lake(tmp_path/'lake')))
    assert out.height==2 and out['series_id'].n_unique()==2
    assert out['country_iso3'].to_list()==['POL','POL']
    assert out['value'].to_list()==[4,4]
    dims=[json.loads(x) for x in out['dimensions']]
    assert [x['CURRENCY_COUNTRY_NATIVE'] for x in dims]==['Mikronezja, Federacja','Palau']
    assert all(x['CURRENCY_SYMBOL_NATIVE']=='787' for x in dims)
