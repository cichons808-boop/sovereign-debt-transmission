"""Exact reporting across batch boundaries, request overlap and frequencies."""
import polars as pl
from datalake.model import Job, observation, frame
from datalake.storage import Lake
from datalake.bounded_report import report


def test_disk_dictionary_and_coverage_across_single_row_batches(tmp_path):
    lake = Lake(tmp_path / 'lake')
    for n in range(2):
        job = Job('FIXTURE','sample','fixture',f'https://example.invalid/{n}')
        raw = {'snapshot_id':str(n),'sha256':'0'*64,'retrieved_at':f'2026-11-0{n+1}T00:00:00+00:00'}
        rows = []
        for area, period, value in [('PL','2020',0),('PL','2021',None),('PL','2020-01',2),('WLD','2020',None)]:
            rows.append(observation(job,raw,period=period,value=value,
                dims={'REF_AREA':area,'FREQ':'M' if '-' in period else 'A'}, ref_area=area,
                indicator='fixture',label=f'Label {n}',unit=None,multiplier=None))
        path=f'silver/fixture{n}.parquet';frame(rows).write_parquet(lake.root/path)
        lake.register_download({'snapshot_id':str(n),'job_id':job.id,'retrieved_at':raw['retrieved_at']})
        lake.register_partition({'id':str(n),'job_id':job.id,'snapshot_id':str(n),'path':path,
                                 'source':job.source,'dataset':job.dataset})
    result = report(lake,batch_rows=1)
    dictionary=pl.read_parquet(lake.root/'metadata/series_dictionary.parquet')
    source=pl.read_csv(lake.root/'reports/source_coverage.csv')
    country=pl.read_csv(lake.root/'reports/country_coverage.csv')
    assert result['current_rows']==8 and result['current_nonmissing_observations']==4
    assert result['country_iso3_with_data']==['POL']
    assert result['series_dictionary_rows']==3 and dictionary.height==3
    assert dictionary['label'].unique().to_list()==['Label 1']
    assert source['countries'].item()==1 and source['series'].item()==3
    assert source['missing_unit_rows'].item()==8
    assert country.sort('frequency')['series'].to_list()==[1,1]
    assert country['rows'].sum()==6 and country['nonmissing_observations'].sum()==4


def test_empty_lake_report_has_typed_outputs(tmp_path):
    lake=Lake(tmp_path/'lake')
    result=report(lake,batch_rows=1)
    assert result['current_rows']==0 and result['current_dataset_count']==0
    assert pl.read_parquet(lake.root/'metadata/series_dictionary.parquet').height==0
    assert pl.read_csv(lake.root/'reports/source_coverage.csv').height==0
