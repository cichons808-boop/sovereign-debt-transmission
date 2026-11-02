"""Public OECD, US Treasury, NBP and monetary-event sources."""
from __future__ import annotations

import csv
import json
import re
from dataclasses import replace
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

import openpyxl

from .model import Job, compact, frame, number, observation
from .normalize import json_body
from .storage import Lake


def plan_oecd(lake, dl, profile="broad"):
    flows = [
        ("OECD.SDD.NAD", "DSD_PSD_D1D4@DF_PSD_D1D4", "1.0", "Debt by instrument coverage"),
        ("OECD.SDD.NAD", "DSD_NASEC20@DF_T7PSD_Q", "1.1", "Consolidated quarterly public-sector debt"),
        ("OECD.SDD.NAD", "DSD_FIN_DASH@DF_FIN_DASH_S13", "", "General-government financial indicators"),
    ]
    return [Job("OECD", fid.replace("@", "_"), "sdmx_csv",
                f"https://sdmx.oecd.org/public/rest/v1/data/{agency},{fid},{version}/all?format=csvfile",
                {"title": title}, 24) for agency, fid, version, title in flows]


TREASURY_ENDPOINTS = {
    "average_interest_rates": ("v2/accounting/od/avg_interest_rates", "M", ["avg_interest_rate_amt"]),
    "debt_to_penny": ("v2/accounting/od/debt_to_penny", "D", ["tot_pub_debt_out_amt", "debt_held_public_amt", "intragov_hold_amt"]),
    "mspd_market": ("v1/debt/mspd/mspd_table_3_market", "M", ["interest_rate_pct", "yield_pct", "issued_amt", "inflation_adj_amt", "redeemed_amt", "outstanding_amt"]),
    "mspd_nonmarket": ("v1/debt/mspd/mspd_table_3_nonmarket", "M", ["interest_rate_pct", "issued_amt", "redeemed_amt", "outstanding_amt"]),
    "interest_expense": ("v2/accounting/od/interest_expense", "M", ["month_expense_amt", "fytd_expense_amt"]),
}


def plan_treasury(lake, dl, profile="broad"):
    jobs=[]
    for name,(endpoint,freq,measures) in TREASURY_ENDPOINTS.items():
        jobs.append(Job("US_TREASURY", name, "treasury_json",
            "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/"+endpoint+"?"+urlencode({"page[size]":10000,"page[number]":1,"sort":"record_date"}),
            {"frequency":freq,"measures":measures},24))
    return jobs


def treasury_json(job, raw, path, lake):
    obj=json_body(path)
    if "data" not in obj or "meta" not in obj:raise ValueError("Treasury response is not a data envelope")
    meta=obj["meta"]; u=urlsplit(job.url); q=parse_qs(u.query)
    page=int(q.get("page[number]",[1])[0]); pages=int(meta.get("total-pages",1))
    if page==1 and pages>1:
        jobs=[]
        for i in range(2,pages+1):
            q["page[number]"]=[str(i)]
            jobs.append(replace(job,url=urlunsplit((u.scheme,u.netloc,u.path,urlencode(q,doseq=True),u.fragment))))
        lake.add(jobs)
    types=meta.get("dataTypes",{}); labels=meta.get("labels",{})
    fields=job.options["measures"]
    missing=[k for k in fields if k not in types]
    if missing:raise ValueError(f"Treasury fields absent from provider metadata: {missing}")
    rows=[]
    for rec in obj["data"]:
        period=rec["record_date"][:7] if job.options["frequency"]=="M" else rec["record_date"]
        dims={k:v for k,v in rec.items() if k.endswith("_desc") or k in {"cusip","series_cd","issue_date","maturity_date","interest_pay_date_1","interest_pay_date_2","interest_pay_date_3","interest_pay_date_4"}}
        # Rows without a security identifier still have a provider line identity.
        dims.update(REF_AREA="US",FREQ=job.options["frequency"],SOURCE_LINE=rec.get("src_line_nbr"))
        for measure in fields:
            typ=types.get(measure,""); label=labels.get(measure,measure)
            unit="Percent" if typ=="PERCENTAGE" else ("USD" if typ.startswith("CURRENCY") else None)
            # The Treasury labels explicitly say when amounts are in millions.
            mult=6 if "in millions" in label.lower() else 0
            rows.append(observation(job,raw,period=period,value=rec.get(measure),dims={**dims,"MEASURE":measure},indicator=measure,
                label=label,ref_area="US",unit=unit,multiplier=mult,currency="USD" if unit=="USD" else None,
                attrs={"record_date":rec["record_date"],"provider_type":typ,"provider_format":meta.get("dataFormats",{}).get(measure),"page":page}))
        if len(rows)>=50000:yield frame(rows);rows=[]
    if rows:yield frame(rows)


def plan_nbp(lake, dl, profile="broad"):
    # The documented API permits at most 93 days in a date-range request.
    end=date.today();start=date(2002,1,2);jobs=[]
    while start<=end:
        last=min(end,start+timedelta(days=89))
        for table in (["A"] if profile=="smoke" else ["A","B","C"]):
            jobs.append(Job("NBP",f"exchange_rates_{table}","nbp_json",
                f"https://api.nbp.pl/api/exchangerates/tables/{table.lower()}/{start.isoformat()}/{last.isoformat()}/?format=json",{},31))
        start=last+timedelta(days=1)
    return jobs


def nbp_json(job,raw,path,lake):
    obj=json_body(path)
    if not isinstance(obj,list):raise ValueError("NBP response must be a table list")
    rows=[]
    for table in obj:
        for rate in table["rates"]:
            for field in ["mid","bid","ask"]:
                if field not in rate:continue
                dims={"REF_AREA":"PL","CURRENCY":rate["code"],"QUOTE_CURRENCY":"PLN","TABLE":table["table"],"RATE_TYPE":field,"FREQ":"D"}
                rows.append(observation(job,raw,period=table["effectiveDate"],value=rate[field],dims=dims,
                    indicator=rate["code"]+"_"+field,label=rate.get("currency",""),ref_area="PL",unit="PLN per foreign-currency unit",
                    currency=rate["code"],multiplier=0,publication_date=table.get("tradingDate",table["effectiveDate"]),
                    attrs={"table_number":table.get("no"),"trading_date":table.get("tradingDate"),"quote_convention":"Original NBP convention; inspect historical redenominations and currency code changes"}))
    yield frame(rows)


def plan_events(lake,dl,profile="broad"):
    return [Job("FRBSF","USMPD","usmpd_xlsx","https://www.frbsf.org/wp-content/uploads/USMPD.xlsx",{},5),
            Job("FRBSF","USMPD_surprises_original","raw","https://www.frbsf.org/wp-content/uploads/monetary-policy-surprises.zip",{},5)]


def plan_ecb_events(lake,dl,profile="broad"):
    return [Job("ECB_EVENTS","EA_MPD","ea_mpd_xlsx","https://www.ecb.europa.eu/pub/pdf/annex/Dataset_EA-MPD.xlsx",{},5)]


def plan_bdy(lake,dl,profile="broad"):
    from .providers import metadata
    metadata(lake,dl,"AUTHOR_META","bolhuis_data_page","https://sites.google.com/site/mabolhuis/data",True)
    path=metadata(lake,dl,"AUTHOR_META","bolhuis_public_folder","https://drive.google.com/drive/folders/1wrQ1O5XsPQDGSCKa058lOym-H_DYR0a9",True)
    html=path.read_text(); files={}
    for m in re.finditer(r'data-id="([A-Za-z0-9_-]+)"',html):
        tail=html[m.end():m.end()+900]
        name=re.search(r'\b(MP_shocks_(\d{8})\.xlsx)\b',tail)
        if name:
            try:stamp=datetime.strptime(name[2],"%m%d%Y")
            except ValueError:continue
            files[name[1]]=(stamp,m[1])
    if not files:raise ValueError("No public BDY workbook found in the author's linked folder")
    selected=sorted(files.items(),key=lambda x:x[1][0],reverse=True)
    if profile!="full":selected=selected[:1]
    return [Job("BDY_AUTHOR","HF_"+stamp.strftime("%Y%m%d"),"bdy_xlsx",
                "https://drive.google.com/uc?export=download&id="+fileid,
                {"release_filename":name,"provider_release_date_from_filename":stamp.date().isoformat(),
                 "conditions":"Academic research free of charge; cite Bolhuis, Das and Yao (2024). Other use requires author permission."},5)
            for name,(stamp,fileid) in selected]


def ea_mpd_xlsx(job,raw,path,lake):
    with path.open("rb") as stream:
        workbook=openpyxl.load_workbook(stream,read_only=True,data_only=True)
        if "Notes" not in workbook:raise ValueError("EA-MPD workbook has no Notes sheet")
        notes=[list(r) for r in workbook["Notes"].iter_rows(values_only=True)]
        lake.atomic_json("metadata/ea_mpd_notes.json",notes)
        for sheet in workbook:
            if sheet.title=="Notes":continue
            iterator=sheet.iter_rows(values_only=True);headers=list(next(iterator))
            if not headers or str(headers[0]).lower()!="date":raise ValueError("Unrecognised EA-MPD header")
            active=[(i,str(x)) for i,x in enumerate(headers) if i and x is not None]
            rows=[]
            for values in iterator:
                dt=values[0]
                if dt is None:continue
                if isinstance(dt,str):
                    try:dt=datetime.strptime(dt.strip(),"%d/%m/%Y")
                    except ValueError:raise ValueError(f"Unrecognised EA-MPD date text: {dt!r}")
                if not isinstance(dt,(datetime,date)):raise ValueError("Unrecognised EA-MPD event date")
                for i,instrument in active:
                    value=values[i] if i<len(values) else None
                    # Workbook Notes specify bps for yield changes and percentage
                    # points for equity-index/exchange-rate changes.
                    rate=instrument.startswith(("OIS","DE","FR","IT","ES"))
                    dims={"REF_AREA":"U2","FREQ":"D","ISSUER":"ECB","EVENT_WINDOW":sheet.title,"INSTRUMENT":instrument}
                    rows.append(observation(job,raw,period=dt.strftime("%Y-%m-%d"),value=value,dims=dims,
                        indicator=instrument,label=f"EA-MPD {sheet.title}: {instrument}",ref_area="U2",
                        unit="basis points" if rate else "percentage-point change",multiplier=0,
                        attrs={"window_definition":"See authoritative ea_mpd_notes.json","identification_note":"Observed event-window changes, not automatically exogenous monetary shocks"}))
                if len(rows)>=25000:yield frame(rows);rows=[]
            if rows:yield frame(rows)
        workbook.close()


def bdy_xlsx(job,raw,path,lake):
    with path.open("rb") as stream:
        workbook=openpyxl.load_workbook(stream,read_only=True,data_only=True)
        if "data" not in workbook:raise ValueError("BDY workbook has no data sheet")
        if "variables" in workbook:
            lake.atomic_json("metadata/bdy_"+job.dataset+"_variables.json",[list(r) for r in workbook["variables"].iter_rows(values_only=True)])
        iterator=workbook["data"].iter_rows(values_only=True);headers=list(next(iterator));rows=[]
        required={"market_Date","iso3","mps","orth","orth_MP1","orth_CBI1"}
        if not required.issubset(headers):raise ValueError("BDY workbook columns have changed")
        for values in iterator:
            rec=dict(zip(headers,values));dt=rec["market_Date"]
            if dt is None:continue
            if not isinstance(dt,(datetime,date)):raise ValueError("Unrecognised BDY date")
            original_area=rec["iso3"];area="U2" if original_area=="DEU" else original_area
            for measure in ["mps","orth","orth_MP1","orth_CBI1"]:
                dims={"REF_AREA":area,"ISSUER":"ECB" if original_area=="DEU" else original_area,"FREQ":"D","MEASURE":measure}
                rows.append(observation(job,raw,period=dt.strftime("%Y-%m-%d"),value=rec.get(measure),dims=dims,
                    indicator=measure,label="Bolhuis-Das-Yao: "+measure,ref_area=area,unit="basis points",multiplier=0,
                    publication_date=job.options.get("provider_release_date_from_filename"),
                    attrs={"original_iso3":original_area,"measurement_date_definition":"First date following the meeting during which market is open",
                           "emergency_meeting":rec.get("emergency_meeting"),"meeting":rec.get("meeting"),
                           "release_filename":job.options.get("release_filename"),"conditions":job.options.get("conditions"),
                           "scope_note":"DEU in this source denotes the euro area policy issuer, not an independent German monetary policy"}))
            if len(rows)>=25000:yield frame(rows);rows=[]
        if rows:yield frame(rows)
        workbook.close()


def usmpd_xlsx(job,raw,path,lake):
    with path.open("rb") as stream:
        workbook=openpyxl.load_workbook(stream,read_only=True,data_only=True)
        readme=[]
        if "README" in workbook:
            readme=[list(r) for r in workbook["README"].iter_rows(values_only=True)]
            lake.atomic_json("metadata/usmpd_readme.json",readme)
        for sheet in workbook:
            if sheet.title=="README":continue
            iterator=sheet.iter_rows(values_only=True);headers=list(next(iterator))
            if "Date" not in headers or "date_time" not in headers:raise ValueError(f"Unrecognised USMPD worksheet {sheet.title}")
            rows=[]
            for values in iterator:
                rec=dict(zip(headers,values));dt=rec["Date"]
                if dt is None:continue
                if not isinstance(dt,(datetime,date)):raise ValueError("USMPD event date is not an Excel date")
                attrs={k:str(rec[k]) if k=="date_time" else rec[k] for k in ["date_time","SEP","Unscheduled","PC"] if k in rec}
                for key,value in rec.items():
                    if key in {"Date","date_time","SEP","Unscheduled","PC"} or key is None:continue
                    # Rate changes and asset returns have different units; preserve
                    # the workbook documentation rather than assuming all are bps.
                    rate=key.startswith(("MP","FF","ED","OIS","UST","TIPS"))
                    unit="percentage-point change" if rate else None
                    dims={"REF_AREA":"US","FREQ":"E","EVENT_TYPE":sheet.title,"INSTRUMENT":key}
                    event_time=rec["date_time"]
                    if not isinstance(event_time,datetime):raise ValueError("USMPD event has no precise event timestamp")
                    rows.append(observation(job,raw,period=event_time.isoformat(timespec="seconds"),value=value,dims=dims,
                        indicator=key,label=f"USMPD {sheet.title}: {key}",ref_area="US",unit=unit,multiplier=0,
                        attrs={**attrs,"event_time_zone":"America/New_York","identification_note":"Observed event-window change, not automatically an exogenous monetary shock"}))
            if rows:yield frame(rows)
        workbook.close()


def plan_catalog_extensions(lake, dl, profile="broad"):
    """Reviewed official links; raw archival jobs never count as silver coverage."""
    path = Path(__file__).resolve().parents[1] / "docs/data_lake/source_extensions_20261102.json"
    catalog = json.loads(path.read_text())
    lake.atomic_json("metadata/source_extensions_20261102.json", catalog)
    entries = catalog["entries"][:1] if profile == "smoke" else catalog["entries"]
    return [Job(**entry["job"]) for entry in entries]


PLANNERS={"OECD":plan_oecd,"US_TREASURY":plan_treasury,"NBP":plan_nbp,"FRBSF":plan_events,"ECB_EVENTS":plan_ecb_events,"BDY_AUTHOR":plan_bdy,"CATALOG_EXTENSIONS":plan_catalog_extensions}
ADAPTERS={"treasury_json":treasury_json,"nbp_json":nbp_json,"usmpd_xlsx":usmpd_xlsx,"ea_mpd_xlsx":ea_mpd_xlsx,"bdy_xlsx":bdy_xlsx}
