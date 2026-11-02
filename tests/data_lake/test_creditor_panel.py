"""Small structural fixtures; no fixture values count as acquired coverage."""
import polars as pl
from datalake.model import Job, observation, frame
from datalake.storage import Lake
from datalake.creditor_panel import build_creditor_panel


def test_creditor_view_preserves_zero_missing_and_future_classification(tmp_path):
    lake = Lake(tmp_path / 'lake')
    job = Job('WORLDBANK', 'IDS_CREDITOR', 'worldbank_advanced', 'https://example.invalid/fixture')
    raw = {'retrieved_at':'2026-11-02T00:00:00+00:00', 'snapshot_id':'fixture', 'sha256':'0'*64}
    rows = []
    for code, year, value in [('001','2020',0), ('002','2020',None), ('WLD','2032',5)]:
        rows.append(observation(job, raw, period=year, value=value,
            dims={'REF_AREA':'AGO', 'COUNTERPART_AREA':code, 'FREQ':'A'},
            ref_area='AGO', indicator='fixture', label='Fixture', unit='USD', multiplier=0,
            attrs={'native_labels':{'counterpart_area':code, 'country':'Angola'}}))
    frame(rows).write_parquet(lake.root / 'silver/fixture.parquet')
    lake.register_download({'snapshot_id':'fixture', 'job_id':job.id, 'retrieved_at':raw['retrieved_at']})
    lake.register_partition({'id':'fixture', 'job_id':job.id, 'snapshot_id':'fixture',
        'path':'silver/fixture.parquet', 'source':job.source, 'dataset':job.dataset})
    result = build_creditor_panel(lake)
    view = pl.read_parquet(lake.root / 'gold/ids_observed_creditor_panel.parquet')
    assert result['normalized_rows'] == 3 and result['observed_rows'] == 2 and result['missing_rows'] == 1
    assert result['reported_zeroes'] == 1 and result['after_retrieval_year_rows'] == 1
    assert view['creditor_code'].to_list() == ['001','WLD']
    assert view['is_world_total'].to_list() == [False,True]
    assert view['is_forecast'].null_count() == 2 and view['currency'].null_count() == 2
