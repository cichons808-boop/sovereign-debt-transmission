"""Read-only bridge to the article's frozen evidence and derived observations."""
from __future__ import annotations

import csv
import gzip
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

from .model import Job, digest, frame, observation
from .normalize import ADAPTERS, normalize
from .storage import Lake, utcnow

OWNERSHIP = {k: "percentage points of GDP" for k in ["debt", "foreign", "cb", "domestic_noncb", "domestic", "foreign_official", "foreign_bank", "foreign_nonbank", "domestic_bank", "domestic_nonbank", "foreign_official_loans"]}
BRIDGES = {
    "official_imf_annual_all.csv.gz": {"dataset":"IMF_investor_annual","period":"year","frequency":"A","values":OWNERSHIP},
    "official_imf_quarterly_all.csv.gz": {"dataset":"IMF_investor_quarterly","period":"period","frequency":"Q","values":OWNERSHIP},
    "official_imf_currency_annual_all.csv.gz": {"dataset":"IMF_debt_currency","period":"year","frequency":"A","values":{"share":"fraction"},"indicator_column":"measure"},
    "fhl_holdings.csv": {"dataset":"FHL_investors","period":"Year","frequency":"A","country":"Country_Code", "values":{k:"percentage points of GDP" for k in ["total_gdp","domestic_gdp","foreign_gdp","central_bank_gdp","domestic_bank_gdp","domestic_nonbank_gdp","foreign_official_gdp","foreign_bank_gdp","foreign_nonbank_gdp","domestic_private_gdp"]}},
    "official_bis_maturity_all.csv.gz": {"dataset":"BIS_refinancing_derived","period":"period","frequency":"Q","values":{"refinance_share":"fraction"}},
    "maturity_quarterly_DGM.csv": {"dataset":"DGM_maturity","period":"quarter","frequency":"Q","values":{"refinance_share":"fraction","floating_share":"fraction","maturity_years":"years","short_yield":"percent per year","long_yield":"percent per year"}},
    "official_poland_maturity_monthly.csv.gz": {"dataset":"PL_MF_maturity_derived","period":"date","frequency":"M","values":{"refinance_share":"fraction","numerator":"PLN million","denominator":"PLN million"}},
    "shocks_monthly.csv": {"dataset":"JK_ECB_shocks","period":"period","frequency":"M","area":"U2","values":{k:"10 basis points" for k in ["MP_pm","CBI_pm","MP_median","CBI_median"]}},
}


def legacy_csv(job,raw,path,lake):
    opts=job.options;opener=gzip.open if opts.get("gzip") else open
    with opener(path,"rt",encoding="utf-8-sig",newline="") as f:
        rows=[]
        for rec in csv.DictReader(f):
            period=rec[opts["period"]]
            if opts["frequency"]=="M":period=period[:7]
            area=rec.get(opts.get("country","country")) or opts.get("area") or rec.get("country_name","")
            ds={k:rec[k] for k in ["source","imf_group","portfolio","sector","valuation","source_detail","measure"] if k in rec}
            ds.update(REF_AREA=area,FREQ=opts["frequency"])
            for variable,unit in opts["values"].items():
                if variable not in rec:continue
                indicator=rec.get(opts.get("indicator_column","")) or variable
                rows.append(observation(job,raw,period=period,value=rec[variable],dims={**ds,"INDICATOR":indicator},
                    indicator=indicator,label=indicator,ref_area=area,unit=unit,multiplier=0,
                    attrs={"derived_in_frozen_project":True,"original_processed_file":opts["original_path"],
                           "country_name":rec.get("country_name",rec.get("Country")),
                           "repository_commit":opts.get("repository_commit"),
                           "timing_note":"Observation at native date; no new lags, interpolation, or source substitution"}))
            if len(rows)>=50000:yield frame(rows);rows=[]
        if rows:yield frame(rows)


ADAPTERS["legacy_csv"]=legacy_csv


def copy_original(lake,path,job):
    with path.open("rb") as f:sha=hashlib.file_digest(f,"sha256").hexdigest()
    target=lake.root/"raw/objects"/sha[:2]/sha;target.parent.mkdir(exist_ok=True)
    if not target.exists():
        try:os.link(path,target)
        except OSError:shutil.copyfile(path,target)
    row=dict(snapshot_id=digest([job.id,sha])[:32],job_id=job.id,url=job.url,sha256=sha,bytes=path.stat().st_size,
             retrieved_at=utcnow(),source_last_modified=None,etag=None,content_type="application/octet-stream",
             path=str(target.relative_to(lake.root)),http_status=None)
    old=lake.latest_download(job)
    if old and old["sha256"]==sha:return old
    lake.register_download(row)
    return row


def import_existing(lake:Lake,repository:Path):
    manifest=repository/"data/sources.csv"
    if not manifest.is_file():raise FileNotFoundError(f"No frozen source catalog at {manifest}")
    commit=subprocess.check_output(["git","rev-parse","HEAD"],cwd=repository,text=True).strip()
    inventory=[];mismatches=[]
    for rec in csv.DictReader(manifest.open()):
        file=(repository/rec["file"]).resolve()
        if not file.is_relative_to(repository):raise ValueError("Legacy source path escapes repository")
        if not file.is_file():
            mismatches.append({"file":rec["file"],"error":"missing source file"});continue
        with file.open("rb") as f:actual=hashlib.file_digest(f,"sha256").hexdigest()
        if actual!=rec["sha256"]:
            mismatches.append({"file":rec["file"],"error":"frozen checksum mismatch","actual":actual,"expected":rec["sha256"]});continue
        job=Job("PROJECT_LEGACY_RAW","frozen_sources","raw",rec["url"] or "https://github.com/cichons808-boop/sovereign-debt-transmission",
                {"original_path":rec["file"],"dataset":rec["dataset"],"series":rec["series"],"repository_commit":commit},99)
        lake.add([job]);raw=copy_original(lake,file,job);lake.finish(job)
        inventory.append({**rec,"raw_object":raw["path"],"snapshot_id":raw["snapshot_id"],"verified":True})
    lake.atomic_json("metadata/legacy_source_inventory.json",inventory)
    lake.atomic_json("reports/legacy_checksum_mismatches.json",mismatches)
    processed=[]
    for name,options in BRIDGES.items():
        file=repository/"data/processed"/name
        if not file.is_file():continue
        opts={**options,"gzip":name.endswith(".gz"),"original_path":"data/processed/"+name,"repository_commit":commit}
        job=Job("PROJECT_LEGACY",opts["dataset"],"legacy_csv","https://github.com/cichons808-boop/sovereign-debt-transmission/blob/"+commit+"/"+opts["original_path"],opts,4)
        lake.add([job]);raw=copy_original(lake,file,job)
        try:
            part=normalize(lake,job,raw);lake.finish(job);processed.append({"file":name,"rows":part.get("rows",0)})
        except Exception as e:lake.finish(job,f"{type(e).__name__}: {e}");processed.append({"file":name,"error":str(e)})
    result={"verified_frozen_sources":len(inventory),"mismatches":mismatches,"processed_bridges":processed,"repository_commit":commit}
    lake.atomic_json("reports/legacy_import.json",result)
    return result
