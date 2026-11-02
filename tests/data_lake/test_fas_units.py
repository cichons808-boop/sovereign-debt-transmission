import json
from datalake.model import Job
from datalake.storage import Lake
from datalake.normalize import sdmx_xml


def test_fas_units_use_supplied_dsd_labels_without_guessing_or_scaling(tmp_path):
    lake=Lake(tmp_path/'lake')
    lake.atomic_json('metadata/imf_FAS_structure.json',{'codes':{'TYPE_OF_TRANSFORMATION':{
        'PHTADLT_NUM':{'label':'Per 100,000 adults'},'XDC':{'label':'Domestic currency'}}}})
    p=tmp_path/'raw.xml';p.write_text('<Data><DataSet>'
        '<Series COUNTRY="POL" INDICATOR="A" FREQUENCY="A" TYPE_OF_TRANSFORMATION="PHTADLT_NUM" SCALE="6"><Obs TIME_PERIOD="2024" OBS_VALUE="25"/></Series>'
        '<Series COUNTRY="POL" INDICATOR="A" FREQUENCY="A" TYPE_OF_TRANSFORMATION="XDC" UNIT="Explicit native unit"><Obs TIME_PERIOD="2024" OBS_VALUE="0"/></Series>'
        '<Series COUNTRY="POL" INDICATOR="A" FREQUENCY="A" TYPE_OF_TRANSFORMATION="UNKNOWN"><Obs TIME_PERIOD="2024"/></Series>'
        '</DataSet></Data>')
    job=Job('IMF','FAS','sdmx_xml','https://example.invalid',{'dimensions':['COUNTRY','INDICATOR','FREQUENCY','TYPE_OF_TRANSFORMATION']})
    raw={'snapshot_id':'fixture','sha256':'0'*64,'retrieved_at':'2026-11-02'}
    out=next(sdmx_xml(job,raw,p,lake))
    assert out['unit'].to_list()==['Per 100,000 adults','Explicit native unit',None]
    assert out['value'].to_list()==[25,0,None] and out['unit_multiplier'].to_list()==[0,0,0]
    assert out['currency'].null_count()==3
    assert json.loads(out['attributes'][0])['unit_provenance']['code']=='PHTADLT_NUM'
    assert 'unit_provenance' not in json.loads(out['attributes'][1])
