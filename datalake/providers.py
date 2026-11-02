"""Discover provider catalogs first; queue reproducible requests second."""
from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from urllib.parse import urlencode

from .http import Downloader
from .model import Job, geography
from .normalize import json_body
from .storage import Lake

WB_SOURCES = {
    "20": ("QPSD", 10), "2": ("WDI", 12), "6": ("IDS", 15),
    "22": ("QEDS_SDDS", 16), "23": ("QEDS_GDDS", 17),
    "15": ("GEM", 18), "54": ("JEDH", 19), "32": ("GFDD", 20),
    "3": ("WGI", 21), "81": ("IDS_DSSI", 22), "75": ("ESG", 60),
}
WDI_CORE = re.compile(r"^(?:NY\.|NE\.|BN\.|BM\.|BX\.|DT\.|FI\.|FS\.|FD\.|FM\.|FR\.|FP\.|GC\.|PA\.|PX\.|GF\.|IC\.FRM\.BNK|SP\.POP\.TOTL|SL\.UEM\.|SL\.TLF\.TOTL|SI\.POV\.GINI|EG\.IMP\.|EG\.USE\.|TX\.|TM\.|NV\.)")

BIS_TOPICS = {
    "WS_CBPOL": ("Central-bank policy rates", 1), "WS_LONG_CPI": ("Consumer prices", 2),
    "WS_TC": ("Credit to the non-financial sector", 3), "WS_DSR": ("Debt-service ratios", 4),
    "WS_CREDIT_GAP": ("Credit-to-GDP gaps", 5), "WS_NA_SEC_DSS": ("Debt securities, issuer/currency/maturity", 7),
    "WS_CBTA": ("Central-bank total assets", 6), "WS_EER": ("Effective exchange rates", 8),
    "WS_XRU": ("Bilateral exchange rates", 9), "WS_GLI": ("Global liquidity", 9),
    "WS_LBS_D_PUB": ("Locational international banking", 35),
    "WS_CBS_PUB": ("Consolidated international banking", 36),
    "WS_DEBT_SEC2_PUB": ("International debt securities", 34),
    "WS_SPP": ("Residential property prices", 25), "WS_DPP": ("Detailed residential property prices", 45),
    "WS_CPP": ("Commercial property prices", 45), "WS_OTC_DERIV2": ("OTC derivatives", 47),
    "WS_XTD_DERIV": ("Exchange-traded derivatives", 48),
    "WS_DER_OTC_TOV": ("Triennial derivatives turnover", 49),
}

EUROSTAT_DATASETS = {
    "gov_10dd_ggd": "Debt by creditor and original maturity",
    "gov_10dd_rmd": "Debt by remaining maturity",
    "gov_10dd_dcur": "Debt by currency of issuance",
    "gov_10dd_acd": "Average debt costs",
    "gov_10q_ggdebt": "Quarterly government debt",
    "gov_10q_ggnfa": "Quarterly government nonfinancial accounts",
    "gov_10q_ggfa": "Quarterly government financial accounts",
    "gov_10a_main": "Annual government finance main aggregates",
    "gov_10a_exp": "Government expenditure by function",
    "gov_10a_taxag": "Tax aggregates",
    "gov_10dd_edpt1": "Excessive deficit procedure notification",
    "gov_10dd_slgd": "Government guarantees",
    "gov_10dd_guar": "Contingent government guarantees",
    "nasa_10_f_bs": "Annual sector financial balance sheets",
    "nasq_10_f_bs": "Quarterly sector financial balance sheets",
    "nasa_10_nf_tr": "Annual nonfinancial sector transactions",
    "nasq_10_nf_tr": "Quarterly nonfinancial sector transactions",
    "namq_10_gdp": "Quarterly GDP and components",
    "nama_10_gdp": "Annual GDP and components",
    "prc_hicp_midx": "Monthly harmonised consumer price indices",
    "prc_hicp_manr": "HICP annual inflation rates",
    "irt_lt_mcby_m": "Long-term government bond yields",
    "irt_st_m": "Short-term money-market rates",
    "bop_6_q": "Quarterly balance of payments",
    "bop_iip6_q": "Quarterly international investment positions",
    "ei_bsin_q_r2": "Quarterly business sentiment",
    "une_rt_m": "Monthly unemployment",
    "sts_inpr_m": "Monthly industrial production",
    "ilc_di12": "Disposable-income inequality",
}

# Bounded high-value flows first. Full large financial flows can be country-sharded.
ECB_FLOWS = {"EXR": 24, "YC": 24, "MIR": 26, "BSI": 32, "GFS": 28,
             "CISS": 24, "CLIFS": 25, "IVF": 50, "ICB": 51, "BOP": 52, "QSA": 53, "SEC": 54}

IMF_SMALL = {"GDD", "HPD", "FM", "WEO", "ICSD", "PSBS", "FD", "WPFXI", "MFS_IR", "MFS_MA", "FAS", "CPI_WCA"}
IMF_LARGE = {"QGFS", "GFS_BS", "GFS_SOEF", "GFS_COFOG", "GFS_SFCP", "GFS_SSUC",
             "MFS_CBS", "MFS_DC", "MFS_ODC", "MFS_FC", "MFS_OFC", "MFS_FMP", "MFS_NSRF",
             "CPI", "BOP", "IIP", "IIPCC", "PIP", "DIP", "FSICDM", "FSIBSIS"}


def metadata(lake: Lake, dl: Downloader, source: str, dataset: str, url: str, allow_html=False):
    job = Job(source, dataset, "raw", url, {"allow_html": allow_html})
    raw = dl.fetch(job)
    return lake.root / raw["path"]


def plan_worldbank(lake: Lake, dl: Downloader, profile="broad", source_ids=None) -> list[Job]:
    countries_path = metadata(lake, dl, "WB_META", "countries", "https://api.worldbank.org/v2/country?format=json&per_page=1000")
    countries = {}
    for r in json_body(countries_path)[1]:
        aggregate = r["region"]["value"] == "Aggregates"
        iso = geography(r["id"])[0] if not aggregate else None
        if r["id"] == "XKX": iso = "XKX"
        item = {"iso3": iso, "is_aggregate": aggregate, "name": r["name"], "iso2": r["iso2Code"],
                "region": r["region"], "income_level": r["incomeLevel"], "lending_type": r["lendingType"],
                "classification_note": "Current provider classification; not historical country-year classifications"}
        countries[r["id"]] = item; countries[r["iso2Code"]] = item
    lake.atomic_json("metadata/worldbank_countries.json", countries)
    metadata(lake, dl, "WB_META", "sources", "https://api.worldbank.org/v2/source?format=json&per_page=1000")
    jobs = []; selection = []
    for source_id in source_ids or WB_SOURCES:
        dataset, priority = WB_SOURCES[source_id]
        if dataset == "ESG" and profile != "full": continue
        path = metadata(lake, dl, "WB_META", dataset + "_indicators",
                        f"https://api.worldbank.org/v2/indicator?source={source_id}&format=json&per_page=20000")
        obj = json_body(path)
        if not isinstance(obj, list) or len(obj) < 2: raise ValueError(f"Bad indicator catalog for WB {source_id}")
        if int(obj[0]["pages"]) != 1: raise ValueError("World Bank metadata catalog is paginated; increase metadata pagination support")
        indicators = {r["id"]: r for r in obj[1]}
        lake.atomic_json(f"metadata/worldbank_indicators_{source_id}.json", indicators)
        codes = sorted(indicators)
        if source_id == "2" and profile != "full": codes = [k for k in codes if WDI_CORE.search(k)]
        if profile == "smoke":
            preferred = {"2": ["NY.GDP.MKTP.CD", "GC.DOD.TOTL.GD.ZS", "FP.CPI.TOTL.ZG", "BN.CAB.XOKA.GD.ZS"],
                         "20": ["DP.DOD.DECT.CR.GG.Z1", "DP.DOD.DECT.CR.GG.CD"], "6": ["DT.DOD.DECT.CD"]}
            codes = [k for k in preferred.get(source_id, codes[:1]) if k in indicators]
        selection.append({"dataset": dataset, "source_id": source_id, "available_indicators": len(indicators), "selected_indicators": len(codes)})
        # Code-length bound leaves ample space below the provider's 1500-character path limit.
        groups = []; group = []
        for code in codes:
            if group and (len(group) >= 10 or len(";".join(group + [code])) > 1200): groups.append(group); group = []
            group.append(code)
        if group: groups.append(group)
        for group in groups:
            query = urlencode({"source": source_id, "format": "json", "per_page": 20000, "page": 1, "footnote": "y"})
            url = "https://api.worldbank.org/v2/country/all/indicator/" + ";".join(group) + "?" + query
            core={"NY.GDP.MKTP.CD","NY.GDP.MKTP.KD.ZG","FP.CPI.TOTL.ZG","GC.DOD.TOTL.GD.ZS","BN.CAB.XOKA.GD.ZS","NE.TRD.GNFS.ZS","GC.XPN.INTP.RV.ZS"}
            job_priority=9 if source_id=="2" and core.intersection(group) else priority
            jobs.append(Job("WORLDBANK", dataset, "worldbank", url, {"source_id": source_id}, job_priority))
    lake.atomic_json("metadata/worldbank_selection.json", selection)
    return jobs


def plan_worldbank_creditors(lake: Lake, dl: Downloader, profile="broad") -> list[Job]:
    """Resolve both native location namespaces before constructing IDS requests."""
    from .wb_advanced import metadata_codes, later_pages, select_indicators
    # Reuse ordinary discovery for countries, sources and the complete indicator
    # dictionary, without adding its ordinary aggregate-creditor data requests.
    plan_worldbank(lake, dl, profile="smoke", source_ids=["6"])
    locations = {}
    for concept in ["country", "counterpart-area"]:
        first = f"https://api.worldbank.org/v2/sources/6/{concept}?format=json&per_page=20000&page=1"
        path = metadata(lake, dl, "WB_META", "IDS_"+concept+"_catalog", first)
        obj = json_body(path); codes = metadata_codes(obj, concept)
        for index, url in enumerate(later_pages(first, obj), 2):
            path = metadata(lake, dl, "WB_META", "IDS_"+concept+f"_catalog_page_{index}", url)
            more = metadata_codes(json_body(path), concept)
            for key, value in more.items():
                if key in codes and codes[key] != value:
                    raise ValueError("Conflicting IDS metadata across pages")
                codes[key] = value
        if not codes:
            raise ValueError(f"No IDS {concept} identifiers returned")
        locations[concept] = codes
    indicators = json.loads((lake.root / "metadata/worldbank_indicators_6.json").read_text())
    selected = select_indicators(indicators, full=profile == "full")
    if not selected:
        raise ValueError("No selected creditor indicators in the official IDS catalog")
    debtors = sorted(locations["country"])
    counterpart = "all"
    if profile == "smoke":
        debtors = ["AGO"] if "AGO" in locations["country"] else debtors[:1]
        counterpart = "701" if "701" in locations["counterpart-area"] else sorted(locations["counterpart-area"])[0]
        selected = selected[:1]
    lake.atomic_json("metadata/ids_creditor_catalog.json", {
        "source_id":"6", "native_namespaces":locations, "selected_indicators":selected,
        "status":"Provider metadata discovery; successful country/value coverage is measured after normalization",
        "reference_snapshot_note":"The separately archived Git tutorial CSV is not substituted for this live API catalog"})
    jobs = []
    for debtor in debtors:
        for indicator in selected:
            url = f"https://api.worldbank.org/v2/sources/6/country/{debtor}/series/{indicator}/counterpart-area/{counterpart}/time/all?format=json&per_page=20000&page=1"
            jobs.append(Job("WORLDBANK", "IDS_CREDITOR", "worldbank_advanced", url,
                            {"source_id":"6", "native_dimensions":["country","series","counterpart-area","time"]}, 16))
    return jobs


def plan_bis(lake: Lake, dl: Downloader, profile="broad") -> list[Job]:
    path = metadata(lake, dl, "BIS_META", "bulk_catalog", "https://data.bis.org/bulkdownload", True)
    available = set(re.findall(r"/static/bulk/([^\"<> ]+)_csv_flat\.zip", path.read_text()))
    wanted = ["WS_CBPOL", "WS_TC", "WS_LONG_CPI"] if profile == "smoke" else list(BIS_TOPICS)
    if profile == "full": wanted = sorted(available)
    jobs = []
    for flow in wanted:
        if flow not in available:
            lake.event("plan", "unavailable", f"BIS flow {flow} absent from current provider catalog"); continue
        title, priority = BIS_TOPICS.get(flow, (flow, 65))
        wide=flow in {"WS_NA_SEC_DSS","WS_LBS_D_PUB","WS_CBS_PUB","WS_DEBT_SEC2_PUB","WS_OTC_DERIV2","WS_XTD_DERIV","WS_DER_OTC_TOV"} or flow.startswith("WS_CPMI_")
        new=Job("BIS",flow,"bis_wide" if wide else "sdmx_csv",
                f"https://data.bis.org/static/bulk/{flow}_csv_{'col' if wide else 'flat'}.zip",{"title":title},priority)
        if wide:
            old=Job("BIS",flow,"sdmx_csv",f"https://data.bis.org/static/bulk/{flow}_csv_flat.zip",{"title":title},priority)
            with lake.db() as db:
                db.execute("UPDATE jobs SET state='superseded',error='Use the provider column CSV for bounded processing' WHERE id=? AND state='pending'",(old.id,))
        jobs.append(new)
    lake.atomic_json("metadata/bis_topics.json", {k: {"title": v[0], "priority": v[1], "available": k in available} for k, v in BIS_TOPICS.items()})
    return jobs


def plan_eurostat(lake: Lake, dl: Downloader, profile="broad") -> list[Job]:
    path=metadata(lake,dl,"EUROSTAT_META","catalog","https://ec.europa.eu/eurostat/api/dissemination/catalogue/toc/xml")
    catalog={}
    for e in ET.parse(path).iter():
        if e.tag.rsplit("}",1)[-1]!="leaf":continue
        code=next((x.text for x in e if x.tag.rsplit("}",1)[-1]=="code"),None)
        if not code:continue
        catalog[code]={"title":next((x.text for x in e if x.tag.rsplit("}",1)[-1]=="title" and x.attrib.get("language")=="en"),""),
                       **{x.tag.rsplit("}",1)[-1]:x.text for x in e if x.tag.rsplit("}",1)[-1] in {"dataStart","dataEnd","values","lastUpdate"}}}
    lake.atomic_json("metadata/eurostat_catalog.json",catalog)
    names = ["gov_10q_ggdebt", "irt_lt_mcby_m"] if profile == "smoke" else list(EUROSTAT_DATASETS)
    if profile!="smoke":names=sorted(set(names)|{k for k in catalog if k.startswith(("gov_10dd_","gov_cl_"))})
    if profile=="full":names=sorted(set(names)|{k for k in catalog if k.startswith(("gov_10a_","gov_10q_","nasa_10_f_","nasq_10_f_"))})
    jobs = []
    for name in names:
        if name not in catalog:
            lake.event("plan","unavailable",f"Eurostat {name} absent from current catalog")
            with lake.db() as db:
                db.execute("UPDATE jobs SET state='unavailable',error='Not listed in current Eurostat catalog' WHERE source='EUROSTAT' AND dataset=? AND state IN ('pending','failed')",(name,))
            continue
        priority = 11 if name.startswith("gov_10dd") else 23
        url = f"https://ec.europa.eu/eurostat/api/dissemination/sdmx/3.0/data/dataflow/ESTAT/{name.upper()}/1.0?format=TSV&compress=true"
        jobs.append(Job("EUROSTAT", name, "eurostat_tsv", url, {"title":EUROSTAT_DATASETS.get(name,catalog[name]["title"])}, priority))
    return jobs


def dataflows(path: Path) -> list[dict]:
    root = ET.parse(path)
    return [{"agency": x.attrib.get("agencyID"), "id": x.attrib["id"], "version": x.attrib.get("version"),
             "title": next((n.text for n in x if n.tag.rsplit("}", 1)[-1] == "Name"), "")}
            for x in root.iter() if x.tag.rsplit("}", 1)[-1] == "Dataflow"]


def english_text(element, tag="Name"):
    items=[x for x in element if x.tag.rsplit("}",1)[-1]==tag]
    return next((x.text for x in items if x.attrib.get("{http://www.w3.org/XML/1998/namespace}lang")=="en"), items[0].text if items else "")


def plan_ecb(lake: Lake, dl: Downloader, profile="broad") -> list[Job]:
    path = metadata(lake, dl, "ECB_META", "dataflows", "https://data-api.ecb.europa.eu/service/dataflow")
    flows = {r["id"]: r for r in dataflows(path)}
    lake.atomic_json("metadata/ecb_dataflows.json", flows)
    small = {"EXR": "M..EUR.SP00.A", "YC": "B.U2.EUR.4F.G_N_A.SV_C_YM..", "MIR": "M..B..R.A.2250.EUR.N", "CISS": "", "CLIFS": ""}
    selected = {"EXR": 24, "CISS": 24} if profile == "smoke" else ECB_FLOWS
    jobs = []
    for flow, priority in selected.items():
        if flow not in flows: continue
        # Preserve full native coverage in broad/full; splitting is possible by a documented series key.
        key = small.get(flow, "") if profile == "smoke" else ""
        jobs.append(Job("ECB", flow, "sdmx_csv", f"https://data-api.ecb.europa.eu/service/data/{flow}/{key}?format=csvdata", {}, priority))
    for key in ["B.U2.EUR.4F.KR.MRR_FR.LEV", "B.U2.EUR.4F.KR.DFR.LEV", "B.U2.EUR.4F.KR.MLFR.LEV"]:
        jobs.append(Job("ECB", "FM_policy", "sdmx_csv", f"https://data-api.ecb.europa.eu/service/data/FM/{key}?format=csvdata", {}, 6))
    return jobs


def imf_structure(lake: Lake, dl: Downloader, flow: dict) -> dict:
    fid, agency, version = flow["id"], flow["agency"], flow["version"]
    path = metadata(lake, dl, "IMF_META", fid + "_structure",
                    f"https://api.imf.org/external/sdmx/2.1/dataflow/{agency}/{fid}/{version}?references=all")
    root = ET.parse(path)
    dsd = root.find(".//{*}DataStructure/{*}DataStructureComponents")
    if dsd is None: raise ValueError(f"No DSD returned for IMF {fid}")
    dimensions = sorted(dsd.findall("./{*}DimensionList/{*}Dimension"), key=lambda x: int(x.attrib.get("position", 0)))
    ids = [x.attrib["id"] for x in dimensions]
    codelists = {x.attrib["id"]: x for x in root.findall(".//{*}Codelists/{*}Codelist")}
    concepts = {(x.attrib.get("agencyID"), x.attrib["id"], x.attrib.get("version")): x
                for x in root.findall(".//{*}ConceptScheme")}
    enum = {}
    for dimension in dimensions:
        ref = dimension.find("./{*}LocalRepresentation/{*}Enumeration/Ref")
        if ref is None:
            identity = dimension.find("./{*}ConceptIdentity/Ref")
            if identity is not None:
                scheme = concepts.get((identity.attrib.get("agencyID"), identity.attrib.get("maintainableParentID"), identity.attrib.get("maintainableParentVersion")))
                if scheme is not None:
                    concept = scheme.find("./{*}Concept[@id='" + identity.attrib["id"] + "']")
                    if concept is not None:
                        ref = concept.find("./{*}CoreRepresentation/{*}Enumeration/Ref")
        if ref is None: continue
        codes = codelists.get(ref.attrib.get("id"))
        if codes is None: continue
        enum[dimension.attrib["id"]] = {x.attrib["id"]: {"label": english_text(x), "description": english_text(x,"Description")}
                                        for x in codes if x.tag.rsplit("}", 1)[-1] == "Code"}
    lake.atomic_json(f"metadata/imf_{fid}_indicators.json", enum.get("INDICATOR", {}))
    result = {**flow, "dimensions": ids, "codes": enum, "raw_metadata_object": str(path.relative_to(lake.root))}
    lake.atomic_json(f"metadata/imf_{fid}_structure.json", result)
    return result


def plan_imf(lake: Lake, dl: Downloader, profile="broad", flow_ids=None) -> list[Job]:
    path = metadata(lake, dl, "IMF_META", "dataflows", "https://api.imf.org/external/sdmx/2.1/dataflow")
    flows = dataflows(path); lake.atomic_json("metadata/imf_dataflows.json", flows)
    wanted = set(flow_ids or ({"GDD", "WEO", "MFS_IR"} if profile == "smoke" else IMF_SMALL | IMF_LARGE))
    if profile == "full":
        wanted |= {r["id"] for r in flows if re.match(r"(?:WEO|FM|MFS_IR|MFS_MA|CPI|BOP|IIP)_\d{4}_.*VINTAGE", r["id"])}
    jobs = []
    for flow in sorted(flows, key=lambda x: x["id"]):
        fid = flow["id"]
        if fid not in wanted: continue
        struct = imf_structure(lake, dl, flow)
        dims = struct["dimensions"]
        small = fid in IMF_SMALL or "VINTAGE" in fid
        areas = list(struct["codes"].get("COUNTRY", struct["codes"].get("REF_AREA", {})))
        keys = ["all"]
        if not small and areas:
            name = "COUNTRY" if "COUNTRY" in dims else "REF_AREA"
            # Keep territories and aggregates, tagged separately at normalization time.
            groups = [areas[i:i+10] for i in range(0, len(areas), 10)]
            keys = []
            for group in groups:
                key = [""] * len(dims); key[dims.index(name)] = "+".join(group); keys.append(".".join(key))
            old = Job("IMF", fid, "sdmx_xml", f"https://api.imf.org/external/sdmx/2.1/data/{flow['agency']},{fid},{flow['version']}/all",
                      {"dimensions": dims, "flow_version": flow["version"]}, 40)
            with lake.db() as db:
                db.execute("UPDATE jobs SET state='superseded',error='Replaced by country shards discovered from the DSD' WHERE id=? AND state='pending'", (old.id,))
        priority = 8 if fid in {"GDD", "WEO", "FM", "HPD", "MFS_IR"} else (29 if small else 40)
        for key in keys:
            jobs.append(Job("IMF", fid, "sdmx_xml",
                f"https://api.imf.org/external/sdmx/2.1/data/{flow['agency']},{fid},{flow['version']}/{key}",
                {"dimensions": dims, "flow_version": flow["version"]}, priority))
    return jobs


FRED_SERIES = {
    "DGS1": ("D", "Percent", 0), "DGS2": ("D", "Percent", 0), "DGS5": ("D", "Percent", 0),
    "DGS10": ("D", "Percent", 0), "DGS30": ("D", "Percent", 0), "DGS3MO": ("D", "Percent", 0),
    "DFII5": ("D", "Percent", 0), "DFII10": ("D", "Percent", 0), "DFII30": ("D", "Percent", 0),
    "T5YIE": ("D", "Percent", 0), "T10YIE": ("D", "Percent", 0),
    "DFF": ("D", "Percent", 0), "SOFR": ("D", "Percent", 0), "EFFR": ("D", "Percent", 0),
    "WALCL": ("W", "USD", 6), "RRPONTSYD": ("D", "USD", 9), "WRESBAL": ("W", "USD", 6),
    "WTREGEN": ("W", "USD", 6), "TREAST": ("W", "USD", 6), "WSHOMCB": ("W", "USD", 6),
    "GFDEBTN": ("Q", "USD", 6), "GFDEGDQ188S": ("Q", "Percent of GDP", 0),
    "GDP": ("Q", "USD annual rate", 9), "GDPC1": ("Q", "Chained 2017 USD annual rate", 9),
    "CPIAUCSL": ("M", "Index 1982-1984=100", 0), "PCEPI": ("M", "Index 2017=100", 0),
    "UNRATE": ("M", "Percent", 0), "PAYEMS": ("M", "Persons", 3), "INDPRO": ("M", "Index 2017=100", 0),
    "M2SL": ("M", "USD", 9), "BUSLOANS": ("M", "USD", 9), "TOTLL": ("W", "USD", 9),
    "DTWEXBGS": ("D", "Index January 2006=100", 0), "DEXUSEU": ("D", "USD per EUR", 0),
    "DEXJPUS": ("D", "JPY per USD", 0), "DEXCHUS": ("D", "CNY per USD", 0),
    "TEDRATE": ("D", "Percent", 0), "STLFSI4": ("W", "Index", 0),
    "BAMLH0A0HYM2": ("D", "Percent", 0), "BAMLC0A0CM": ("D", "Percent", 0),
    "VIXCLS": ("D", "Index", 0), "DCOILWTICO": ("D", "USD per barrel", 0),
    "DCOILBRENTEU": ("D", "USD per barrel", 0), "USEPUINDXD": ("D", "Index", 0),
    "FYFSGDA188S": ("A", "Percent of GDP", 0), "FYFRGDA188S": ("A", "Percent of GDP", 0),
    "FYOIGDA188S": ("A", "Percent of GDP", 0), "FGEXPND": ("Q", "USD annual rate", 9),
    "FGRECPT": ("Q", "USD annual rate", 9), "A091RC1Q027SBEA": ("Q", "USD annual rate", 9),
}


def plan_fred(lake: Lake, dl: Downloader, profile="broad") -> list[Job]:
    codes = ["DGS10", "DFF", "GDP", "WALCL"] if profile == "smoke" else list(FRED_SERIES)
    return [Job("FRED", "macro_finance", "fred_csv", f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={code}",
                {"series": {code: {"country": "US", "frequency": FRED_SERIES[code][0], "unit": FRED_SERIES[code][1],
                                    "multiplier": FRED_SERIES[code][2]}}}, 27) for code in codes]


PLANNERS = {"BIS": plan_bis, "WORLDBANK": plan_worldbank, "WB_CREDITOR":plan_worldbank_creditors, "EUROSTAT": plan_eurostat,
            "ECB": plan_ecb, "IMF": plan_imf, "FRED": plan_fred}
