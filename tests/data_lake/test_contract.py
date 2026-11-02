import json
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

import polars as pl
import pytest

from datalake.model import Job, SCHEMA, geography, number, period_bounds
from datalake.normalize import worldbank, sdmx_csv, sdmx_xml, normalize
from datalake.storage import Lake
from datalake.research import scan


def raw():
    return {"retrieved_at": "2026-11-01T00:00:00+00:00", "snapshot_id": "fixture", "sha256": "0"*64}


@pytest.mark.parametrize("period,start,end,freq", [
    ("2024", "2024-01-01", "2024-12-31", "A"),
    ("2024Q1", "2024-01-01", "2024-03-31", "Q"),
    ("2024-Q4", "2024-10-01", "2024-12-31", "Q"),
    ("2024-M02", "2024-02-01", "2024-02-29", "M"),
    ("2024M02", "2024-02-01", "2024-02-29", "M"),
    ("2024-02", "2024-02-01", "2024-02-29", "M"),
    ("2024-02-01", "2024-02-01", "2024-02-01", "D"),
])
def test_native_periods_are_not_broadcast(period, start, end, freq):
    a,b,f = period_bounds(period)
    assert (a.isoformat(), b.isoformat(), f) == (start,end,freq)


def test_aggregate_territory_alias_and_unknown_are_distinct():
    assert geography("PL") == ("POL", False)
    assert geography("EL") == ("GRC", False)
    assert geography("XKX") == ("XKX", False)
    assert geography("EU27_2020") == (None, True)
    assert geography("UNRECOGNISED") == (None, None)


def test_zero_is_not_missing():
    assert number("0") == 0
    assert number(":") is None
    assert number(float("inf")) is None


def test_bis_labeled_codes_units_and_frequency(tmp_path):
    p=tmp_path/"data.csv"
    p.write_text('STRUCTURE,FREQ:Frequency,REF_AREA:Reference area,UNIT_MEASURE:Unit,TIME_PERIOD:Time period,OBS_VALUE:Value,UNIT_MULT:Multiplier,OBS_STATUS:Status\n'
                 'dataflow,M: Monthly,PL: Poland,368: Percent per year,2024-01,0,0: Units,A: Normal\n'
                 'dataflow,M: Monthly,PL: Poland,368: Percent per year,2024-02,,0: Units,M: Missing\n')
    d=next(sdmx_csv(Job("BIS","rate","sdmx_csv","https://data.bis.org"),raw(),p,Lake(tmp_path/"lake")))
    assert d["country_iso3"].to_list()==["POL","POL"]
    assert d["frequency"].to_list()==["M","M"]
    assert d["unit_multiplier"].to_list()==[0,0]
    assert d["value"].to_list()==[0,None]
    assert d["series_id"].n_unique()==1
    assert json.loads(d["dimensions"][0])["UNIT_MEASURE"]=="368"


def test_ecb_provider_id_is_a_separate_dimension(tmp_path):
    p=tmp_path/"data.csv"
    p.write_text('FREQ,REF_AREA,PROVIDER_FM,PROVIDER_FM_ID,TIME_PERIOD,OBS_VALUE,UNIT,UNIT_MULT\nB,U2,4F,MRR_FR,2024-01-01,4.5,PCPA,0\n')
    d=next(sdmx_csv(Job("ECB","FM","sdmx_csv","https://data-api.ecb.europa.eu"),raw(),p,Lake(tmp_path/"lake")))
    dims=json.loads(d["dimensions"][0])
    assert dims["PROVIDER_FM"]=="4F" and dims["PROVIDER_FM_ID"]=="MRR_FR"
    assert d["country_iso3"][0] is None and d["is_aggregate"][0] is True


def test_worldbank_pagination_and_aggregates(tmp_path):
    lake=Lake(tmp_path/"lake")
    lake.atomic_json("metadata/worldbank_countries.json",{"WLD":{"iso3":None,"is_aggregate":True}})
    p=tmp_path/"wb.json"
    p.write_text(json.dumps([{"pages":3,"page":1,"lastupdated":"2026-10-01"},[
        {"indicator":{"id":"X","value":"Test"},"countryiso3code":"WLD","date":"2024","value":0,"obs_status":""}]]))
    job=Job("WORLDBANK","WDI","worldbank","https://api.worldbank.org/v2/country/all/indicator/X?format=json&page=1",{"source_id":"2"})
    d=next(worldbank(job,raw(),p,lake))
    assert d["is_aggregate"][0] is True
    assert d["value"][0]==0
    with lake.db() as db: assert db.execute("SELECT count(*) FROM jobs").fetchone()[0]==2
    d2=next(worldbank(job,raw(),p,lake))
    with lake.db() as db: assert db.execute("SELECT count(*) FROM jobs").fetchone()[0]==2


def test_imf_actual_units_display_scale_and_estimates(tmp_path):
    p=tmp_path/"data.xml"
    p.write_text('<Data><DataSet PUBLICATION_DATE="2026-10-01">'
                 '<Series COUNTRY="POL" INDICATOR="GDP" FREQUENCY="A" SCALE="9" LATEST_ACTUAL_ANNUAL_DATA="2024">'
                 '<Obs TIME_PERIOD="2024" OBS_VALUE="1000000000"/>'
                 '<Obs TIME_PERIOD="2025" OBS_VALUE="1100000000"/>'
                 '<Obs TIME_PERIOD="2026"/>'
                 '</Series></DataSet></Data>')
    job=Job("IMF","WEO","sdmx_xml","https://api.imf.org",{"dimensions":["COUNTRY","INDICATOR","FREQUENCY"]})
    d=next(sdmx_xml(job,raw(),p,Lake(tmp_path/"lake")))
    assert d["value"].to_list()==[1e9,1.1e9,None]
    assert d["unit_multiplier"].to_list()==[0,0,0]
    assert d["is_estimate"].to_list()==[False,True,True]
    assert d["is_forecast"].to_list()==[None,None,None]
    assert json.loads(d["attributes"][0])["SCALE"]=="9"


def test_duplicate_observations_cannot_be_published(tmp_path):
    lake=Lake(tmp_path/"lake"); p=lake.root/"raw/objects/fixture"
    p.write_text('FREQ,REF_AREA,TIME_PERIOD,OBS_VALUE\nM,PL,2024-01,1\nM,PL,2024-01,2\n')
    r={**raw(),"path":"raw/objects/fixture"}
    j=Job("ECB","test","sdmx_csv","https://data-api.ecb.europa.eu")
    with pytest.raises(ValueError,match="duplicate"):
        normalize(lake,j,r)
    with lake.db() as db:assert db.execute("SELECT count(*) FROM partitions").fetchone()[0]==0
    assert not list((lake.root/"silver").rglob("*.parquet"))


def test_parallel_queue_writes_are_idempotent_and_integral(tmp_path):
    lake=Lake(tmp_path/"lake")
    def add(i):lake.add([Job("BIS",f"dataset{i%5}","raw",f"https://data.bis.org/{i%5}")])
    with ThreadPoolExecutor(max_workers=4) as ex:list(ex.map(add,range(40)))
    with lake.db() as db:
        assert db.execute("SELECT count(*) FROM jobs").fetchone()[0]==5
        assert db.execute("PRAGMA integrity_check").fetchone()[0]=="ok"


def test_metadata_only_sdmx_rows_and_nan_are_not_observed_values(tmp_path):
    p=tmp_path/"data.csv"
    p.write_text('FREQ,REF_AREA,TIME_PERIOD,OBS_VALUE\nM,PL,,\nM,PL,2024-01,NaN\nM,PL,2024-02,0\n')
    d=next(sdmx_csv(Job("BIS","test","sdmx_csv","https://data.bis.org"),raw(),p,Lake(tmp_path/"lake")))
    assert d.height==2 and d["value"].to_list()==[None,0]


def test_snapshot_contains_new_downloads_and_excludes_frozen_git_files(tmp_path):
    import tarfile
    from datalake.snapshot import snapshot
    lake=Lake(tmp_path/"lake")
    source=lake.root/"raw/objects/new";source.write_text("new observations")
    row={"snapshot_id":"new","job_id":"j","url":"https://api.worldbank.org","sha256":"test","bytes":16,
         "retrieved_at":"2026-11-01","source_last_modified":None,"etag":None,"content_type":"text/plain",
         "path":"raw/objects/new","http_status":200}
    lake.register_download(row)
    output=tmp_path/"checkpoint.tar.gz";result=snapshot(lake,output)
    assert result["download_count"]==1
    with tarfile.open(output) as tf:
        assert "metadata/catalog.sqlite" in tf.getnames()
        assert "raw/objects/new" in tf.getnames()
        assert all(not x.startswith("datalake/") for x in tf.getnames())


def test_malformed_provider_headers_are_rejected(tmp_path):
    p=tmp_path/"bad.csv"
    p.write_text('FREQ,REF_AREA,TIME_PERIOD,OBS_VALUE,unexpected_header\nM,PL,2024-01,1\n')
    with pytest.raises(ValueError,match="field counts"):
        next(sdmx_csv(Job("BIS","test","sdmx_csv","https://data.bis.org"),raw(),p,Lake(tmp_path/"lake")))


def test_average_and_end_of_period_are_distinct_series(tmp_path):
    p=tmp_path/"rates.csv"
    p.write_text('FREQ:Frequency,REF_AREA:Area,COLLECTION:Collection,TIME_PERIOD:Period,OBS_VALUE:Value\n'
                 'A: Annual,PL: Poland,A: Average,2024,4.2\nA: Annual,PL: Poland,E: End of period,2024,4.4\n')
    d=next(sdmx_csv(Job("BIS","WS_XRU","sdmx_csv","https://data.bis.org"),raw(),p,Lake(tmp_path/"lake")))
    assert d["series_id"].n_unique()==2
    assert {json.loads(x)["COLLECTION"] for x in d["dimensions"]}=={"A","E"}


def test_valid_empty_sdmx_dataset_differs_from_an_invalid_response(tmp_path):
    l=Lake(tmp_path/"lake");p=tmp_path/"empty.xml"
    job=Job("IMF","test","sdmx_xml","https://api.imf.org",{"dimensions":["COUNTRY","INDICATOR","FREQUENCY"]})
    p.write_text('<StructureSpecificData><DataSet/></StructureSpecificData>')
    assert list(sdmx_xml(job,raw(),p,l))==[]
    p.write_text('<Error>temporarily unavailable</Error>')
    with pytest.raises(ValueError,match="dataset"):
        list(sdmx_xml(job,raw(),p,l))


def test_observed_refinancing_share_does_not_fill_a_missing_component(tmp_path,monkeypatch):
    from datalake.model import observation,frame
    import datalake.research as research
    filters={"FREQ":"Q","ADJUSTMENT":"N","COUNTERPART_AREA":"XW","COUNTERPART_SECTOR":"S1",
             "CONSOLIDATION":"N","ACCOUNTING_ENTRY":"L","STO":"LE","INSTR_ASSET":"F3","EXPENDITURE":"_Z",
             "UNIT_MEASURE":"USD","CURRENCY_DENOM":"_T","PRICES":"V","TRANSFORMATION":"N","CUST_BREAKDOWN":"_T","VALUATION":"N","REF_SECTOR":"S13"}
    j=Job("BIS","WS_NA_SEC_DSS","bis_wide","https://data.bis.org")
    rows=[]
    for area,values in [("PL",[20,30,100]),("DE",[20,None,100])]:
        for maturity,value in zip(["S","LS","T"],values):
            rows.append(observation(j,raw(),period="2024-Q1",value=value,ref_area=area,
                dims={**filters,"REF_AREA":area,"MATURITY":maturity},unit="USD",multiplier=6))
    monkeypatch.setattr(research,"scan",lambda *a,**kw:frame(rows).lazy())
    lake=Lake(tmp_path/"lake");result=research.build_refinancing(lake)
    assert result["observed_shares"]==1
    out=pl.read_parquet(lake.root/"gold/bis_government_refinancing_quarterly.parquet")
    assert out.filter(pl.col("country_iso3")=="POL")["refinance_share"][0]==0.5
    assert out.filter(pl.col("country_iso3")=="DEU")["refinance_share"][0] is None
    assert out.filter(pl.col("country_iso3")=="POL")["T"][0]==100e6
