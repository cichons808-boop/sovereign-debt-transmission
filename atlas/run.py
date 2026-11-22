"""Sequential, checkpointed research entry point (no background continuation)."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
from datetime import datetime,timezone
from pathlib import Path

import pandas as pd

from .data import AUDIT, BASE, PROCESSED, build_audit, save_csv
from .estimation import RESULTS, fit_record, pooled_heterogeneity, write_run


def panels():
    return [pd.read_csv(path,low_memory=False) for path in sorted(PROCESSED.glob('*.csv.gz'))
            if path.name.startswith(('W_','H_','T_'))]


def checkpoint(stage,status,**details):
    event=dict(stage=stage,status=status,utc=datetime.now(timezone.utc).isoformat(),**details)
    with (BASE/'checkpoints.jsonl').open('a') as handle:handle.write(json.dumps(event)+'\n')
    print(json.dumps(event),flush=True)


def horizons(d):return range(6) if d.frequency.iloc[0]=='A' else range(13)


def scopes(d):
    result=['global','AE','EMDE','euro_area']
    if 'external'not in d.universe.iloc[0]:result+=['independent']
    # Regional groups are the source's exact current World Bank labels.
    result+=['region:'+str(x) for x in sorted(d.region.dropna().unique())
             if d.loc[d.region.eq(x)&d.shock.notna(),'country'].nunique()>=5]
    return result


def baseline(force=False):
    all_records=[]
    for d in panels():
        name=d.universe.iloc[0];directory=RESULTS/'baseline'/name
        existing=directory/'specifications.jsonl.gz'
        fingerprint=hashlib.sha256((PROCESSED/(name+'.csv.gz')).read_bytes()+
            (BASE/'estimation.py').read_bytes()+(BASE/'run.py').read_bytes()).hexdigest()
        manifest=directory/'run_manifest.json'
        same=manifest.exists() and json.loads(manifest.read_text()).get('fingerprint')==fingerprint
        if existing.exists() and not force and same:
            with gzip.open(existing,'rt') as handle:records=[json.loads(line) for line in handle]
            all_records+=records
            checkpoint('baseline','reused_verified_checkpoint',universe=name,specifications=len(records))
            continue
        if directory.exists() and existing.exists():
            previous=json.loads(manifest.read_text()).get('fingerprint','initial_unfingerprinted') if manifest.exists() else 'initial_unfingerprinted'
            archive=RESULTS/'baseline_archive'/name/previous[:20]
            archive.parent.mkdir(parents=True,exist_ok=True)
            if not archive.exists():directory.rename(archive)
            else:
                archive=archive.with_name(archive.name+'_'+datetime.now(timezone.utc).strftime('%H%M%S'))
                directory.rename(archive)
            checkpoint('baseline','archived_prior_run',universe=name,path=str(archive.relative_to(BASE)))
        records=[]
        country_list=sorted(d.loc[d.shock.notna(),'country'].unique())
        checkpoint('baseline','running',universe=name,countries=len(country_list))
        for outcome in ['gdp','cpi']:
            for horizon in horizons(d):
                for country in country_list:
                    for variant in ['all','exclude_largest_shock']:
                        records.append(fit_record(d,outcome,horizon,scope='country',country=country,
                                                  variant=variant,use_influence=variant=='all'))
                for scope in scopes(d):
                    records.append(fit_record(d,outcome,horizon,scope=scope))
                variants=['domestic_only','stable_source_only'] if name=='W_CWY_annual' else ['exclude_covid_windows']
                for variant in variants:
                    records.append(fit_record(d,outcome,horizon,scope='global',variant=variant))
        write_run(records,directory);all_records+=records
        manifest.write_text(json.dumps(dict(fingerprint=fingerprint,universe=name,
            source_file=str((PROCESSED/(name+'.csv.gz')).relative_to(BASE)),
            estimated_utc=datetime.now(timezone.utc).isoformat()),indent=2))
        checkpoint('baseline','estimated',universe=name,specifications=len(records),
                   ok=sum(r['status']=='ok' for r in records),
                   failed=sum(r['status']=='failed' for r in records))
    distribution=pooled_heterogeneity(all_records)
    save_csv(distribution,RESULTS/'baseline'/'response_distribution.csv')
    write_run(all_records,RESULTS/'baseline')
    checkpoint('baseline','completed',specifications=len(all_records),
               successful=sum(x['status']=='ok' for x in all_records))
    return all_records


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage',choices=['macro','audit','fresh','external','reconstruct','baseline','chunk','report','validate','all'])
    parser.add_argument('--moderator',default='F01')
    parser.add_argument('--force',action='store_true')
    args=parser.parse_args()
    if args.stage in ['macro','all']:
        from .macro_expansion import run
        run();checkpoint('native_macro_expansion','completed')
    if args.stage in ['audit','all']:build_audit();checkpoint('audit','completed')
    if args.stage in ['fresh','all']:
        from .fresh_shocks import run
        run();checkpoint('fresh_shocks','completed')
    if args.stage in ['external','all']:
        from .external import run
        run();checkpoint('external_spillover_panels','completed')
    if args.stage in ['reconstruct','all']:
        from .reconstruct import run
        run();checkpoint('global_reconstruction','completed')
    if args.stage in ['baseline','all']:baseline(force=args.force)
    if args.stage in ['chunk','all']:
        from .moderators import run_chunk
        # Each chunk is estimated, documented and committed before advancing.
        queue=[args.moderator] if args.stage=='chunk' else ['F01','F04','R01','E01']
        for moderator in queue:run_chunk(moderator,force=args.force)
    if args.stage in ['validate','all']:
        from .validate import run
        run()
    if args.stage in ['report','all']:
        from .reporting import run
        run()


if __name__=='__main__':main()
