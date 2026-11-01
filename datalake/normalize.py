"""Format adapters. Every published partition has a checked, common schema."""
from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import os
import re
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import replace
from functools import lru_cache
from pathlib import Path

import polars as pl
import pyarrow as pa
import pyarrow.parquet as pq

from .model import Job, SCHEMA, compact, digest, frame, geography, number, observation, period_bounds, reported_unit
from .storage import Lake, utcnow


@lru_cache(maxsize=4096)
def bounds(p: str):
    return period_bounds(p)


def json_body(path: Path):
    with path.open("rb") as f:
        sig = f.read(2)
    if sig == b"\x1f\x8b":
        with gzip.open(path, "rt", encoding="utf-8-sig") as f: return json.load(f)
    with path.open(encoding="utf-8-sig") as f: return json.load(f)


def worldbank(job: Job, raw: dict, path: Path, lake: Lake):
    obj = json_body(path)
    if not isinstance(obj, list) or len(obj) != 2 or not isinstance(obj[0], dict) or "message" in obj[0]:
        raise ValueError(f"World Bank returned a data error: {compact(obj)[:500]}")
    meta, records = obj
    if records is None: records = []
    if not isinstance(records, list): raise ValueError("Invalid World Bank observations")
    # Pagination is scheduled dynamically, including the last, partial page.
    pages, page = int(meta.get("pages", 1)), int(meta.get("page", 1))
    if page == 1 and pages > 1:
        from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit
        u = urlsplit(job.url); q = parse_qs(u.query)
        pending = []
        for i in range(2, pages + 1):
            q["page"] = [str(i)]
            pending.append(replace(job, url=urlunsplit((u.scheme, u.netloc, u.path, urlencode(q, doseq=True), u.fragment))))
        lake.add(pending)
    countries_file = lake.root / "metadata/worldbank_countries.json"
    countries = json.loads(countries_file.read_text()) if countries_file.exists() else {}
    indicators_file = lake.root / "metadata" / f"worldbank_indicators_{job.options['source_id']}.json"
    indicators = json.loads(indicators_file.read_text()) if indicators_file.exists() else {}
    rows = []
    for rec in records:
        indicator = rec["indicator"]["id"]; detail = indicators.get(indicator, {})
        area = rec.get("countryiso3code") or rec.get("country", {}).get("id", "")
        dims = {"REF_AREA": area, "INDICATOR": indicator, "WB_SOURCE": str(job.options["source_id"])}
        status = rec.get("obs_status", "")
        rows.append(observation(job, raw, period=rec["date"], value=rec.get("value"), dims=dims,
            indicator=indicator, label=rec["indicator"].get("value", detail.get("name", "")),
            ref_area=area, unit=rec.get("unit") or detail.get("unit") or reported_unit(detail.get("name", "")),
            multiplier=0, status=status, forecast=True if status == "F" else None,
            attrs={"decimal": rec.get("decimal"), "footnote": rec.get("footnote"),
                   "provider_total": meta.get("total"), "provider_page": page},
            source_updated=meta.get("lastupdated"), countries=countries))
    yield frame(rows)


def eurostat_json(job: Job, raw: dict, path: Path, lake: Lake):
    obj = json_body(path)
    if "error" in obj: raise ValueError(compact(obj["error"]))
    if obj.get("class") != "dataset" and "dimension" not in obj:
        raise ValueError("Response is not a JSON-stat dataset")
    ids, sizes = obj["id"], obj["size"]
    codes = []
    for dim in ids:
        ix = obj["dimension"][dim]["category"]["index"]
        codes.append(sorted(ix, key=ix.get) if isinstance(ix, dict) else ix)
    values = obj.get("value", {})
    items = enumerate(values) if isinstance(values, list) else values.items()
    statuses = obj.get("status", {})
    rows = []
    for pos, value in items:
        # Structural absent cells are kept in raw; explicit missing cells can be null in silver.
        if value is None: continue
        idx = int(pos); coords = [0] * len(sizes)
        for j in range(len(sizes) - 1, -1, -1): coords[j], idx = idx % sizes[j], idx // sizes[j]
        ds = {k: codes[j][coords[j]] for j, k in enumerate(ids)}
        period = ds.pop("time", ds.pop("TIME_PERIOD", None))
        if period is None: raise ValueError("JSON-stat has no time dimension")
        status = statuses.get(str(pos), "") if isinstance(statuses, dict) else (statuses[int(pos)] or "")
        area = ds.get("geo", ds.get("REF_AREA", ""))
        rows.append(observation(job, raw, period=period, value=value, dims=ds,
                               indicator=ds.get("na_item", ds.get("coicop", job.dataset)),
                               label=obj.get("label", ""), ref_area=area,
                               unit=ds.get("unit"), currency=ds.get("currency"),
                               status=status, multiplier=None, attrs={}, source_updated=obj.get("updated")))
        if len(rows) >= 50000:
            yield frame(rows); rows = []
    if rows: yield frame(rows)


# Observation/series attributes must not become economic dimensions. Unknown
# non-label columns remain dimensions, preventing accidental many-to-one merges.
ATTRIBUTES = {"OBS_STATUS", "OBS_CONF", "CONF_STATUS", "DECIMALS", "UNIT_MULT", "UNIT_MULTIPLIER",
              "TIME_FORMAT", "TIME_PER_COLLECT", "TITLE", "TITLE_COMPL", "SERIES_NAME", "SERIES",
              "BREAKS", "COMPILING_ORG", "COMMENT_TS", "COMMENT_OBS", "SOURCE_AGENCY",
              "PUBL_PUBLIC", "PUBL_MU", "SOURCE_PUB", "SOURCE_REF", "COVERAGE", "LAST_UPDATE",
              "TIME_PERIOD_START", "TIME_PERIOD_END", "OBS_PRE_BREAK", "OBS_COM", "PRE_BREAK_VALUE",
              "OBS_CONFIDENCE", "BASE_PER", "BASE_PER_OBS", "ACTION", "STRUCTURE", "STRUCTURE_ID",
              "DATAFLOW", "STRUCTURE_NAME", "FREQ_LABEL", "UNIT_INDEX_BASE", "KEY",
              "COMPILATION", "SUPP_INFO_BREAKS", "DISS_ORG", "DOM_SER_IDS", "FM_CONTRACT_TIME",
              "FM_COUPON_RATE", "FM_IDENTIFIER", "FM_LOT_SIZE", "FM_MATURITY", "FM_OUTS_AMOUNT",
              "FM_PUT_CALL", "FM_STRIKE_PRICE", "ORG_SPS", "CURRENCY_SUFFIX"}


def _column_name(s: str) -> str:
    return s.lstrip("\ufeff").strip().split(":", 1)[0].strip().upper().replace(" ", "_")


def sdmx_frame(df: pl.DataFrame, job: Job, raw: dict) -> pl.DataFrame:
    labelled_columns = {_column_name(c) for c in df.columns if ":" in c}
    df = df.rename({k: _column_name(k) for k in df.columns})
    if "TIME_PERIOD" not in df.columns or "OBS_VALUE" not in df.columns:
        raise ValueError(f"No SDMX time/value columns: {df.columns[:15]}")
    no_time = pl.col("TIME_PERIOD").is_null() | (pl.col("TIME_PERIOD").str.strip_chars() == "")
    # BIS includes metadata-only series rows without a period/value. They are
    # preserved in the original, but are not observations. A value without a
    # period is an actual error and must not disappear.
    if df.filter(no_time & pl.col("OBS_VALUE").fill_null("").str.strip_chars().is_not_null() & (pl.col("OBS_VALUE").fill_null("").str.strip_chars() != "")).height:
        raise ValueError("SDMX value has no time period")
    df = df.filter(~no_time)
    if df.height == 0: return frame([])
    labels = {c for c in df.columns if c.endswith("_LABEL") or c in {"SERIES_DESCRIPTION", "SERIES_KEY"}}
    dim_cols = [c for c in df.columns if c not in ATTRIBUTES | labels | {"TIME_PERIOD", "OBS_VALUE", "OBS_STATUS", "SERIES_ID"}]
    # BIS CSV-flat explicitly labels both headers and code values ("PL: Poland").
    # Strip the appended label only for coded columns, never for free text.
    coded = labelled_columns.intersection(set(dim_cols) | {"UNIT_MULT", "UNIT_MULTIPLIER", "OBS_STATUS", "OBS_CONF", "DECIMALS"})
    if coded:
        df = df.with_columns([pl.col(c).str.split(": ").list.first().alias(c) for c in coded])
    if not dim_cols: raise ValueError("No dimensions discovered in SDMX CSV")
    # Compute geography, JSON keys, and identifiers once per series in each batch.
    series = df.select(dim_cols).unique(maintain_order=True)
    ds = series.to_dicts()
    area_col = next((k for k in ("REF_AREA", "BORROWER_CTY", "L_REP_CTY", "REPORTING_COUNTRY", "GEO", "COUNTRY") if k in dim_cols), None)
    if not area_col:
        area_col = job.options.get("ref_area_column")
    areas = [str(r.get(area_col) or "") for r in ds]
    geos = [geography(a) for a in areas]
    extra = dict(
        dimensions=[compact(r) for r in ds],
        series_id=[digest([job.source, job.dataset, r])[:32] for r in ds],
        ref_area=areas, country_iso3=[x[0] for x in geos], is_aggregate=[x[1] for x in geos])
    series = series.with_columns([pl.Series(k, v, dtype=SCHEMA[k]) for k, v in extra.items()])
    df = df.join(series, on=dim_cols, how="left", nulls_equal=True)
    periods = df["TIME_PERIOD"].unique().to_list()
    bb = [bounds(p) for p in periods]
    pmap = pl.DataFrame({"TIME_PERIOD": periods, "period_start": [x[0] for x in bb],
                         "period_end": [x[1] for x in bb], "_parsed_frequency": [x[2] for x in bb]})
    df = df.join(pmap, on="TIME_PERIOD", how="left")
    def col(*names, default=None):
        name = next((x for x in names if x in df.columns), None)
        return pl.col(name) if name else pl.lit(default)
    attrs = [c for c in df.columns if c in ATTRIBUTES and c not in {"ACTION", "STRUCTURE", "STRUCTURE_ID", "DATAFLOW"}]
    att = pl.struct(attrs).map_elements(compact, return_dtype=pl.String) if attrs else pl.lit("{}")
    return df.select(
        pl.lit(job.source).alias("source"), pl.lit(job.dataset).alias("dataset"),
        "series_id", "ref_area", "country_iso3", "is_aggregate",
        col("INDICATOR", "MEASURE", "NA_ITEM", "SERIES_KEY", "KEY", default=job.dataset).alias("indicator"),
        col("TITLE_COMPL", "TITLE", "SERIES_DESCRIPTION", "SERIES_NAME").alias("label"),
        col("FREQ", default=None).fill_null(pl.col("_parsed_frequency")).replace({"Y": "A", "S": "H"}).alias("frequency"),
        pl.col("TIME_PERIOD").alias("period"), "period_start", "period_end",
        pl.col("OBS_VALUE").str.replace_all(",", "").cast(pl.Float64, strict=False).fill_nan(None).alias("value"),
        col("UNIT_MEASURE", "UNIT").alias("unit"),
        col("UNIT_MULT", "UNIT_MULTIPLIER").cast(pl.Int16, strict=False).alias("unit_multiplier"),
        col("CURRENCY_DENOM", "CURRENCY", "CURRENCY_TRANS").alias("currency"),
        col("OBS_STATUS").alias("obs_status"), pl.lit(None, dtype=pl.Boolean).alias("is_forecast"),
        pl.lit(None, dtype=pl.Boolean).alias("is_estimate"), pl.lit(None, dtype=pl.String).alias("publication_date"),
        "dimensions", att.alias("attributes"), col("LAST_UPDATE").alias("source_updated"),
        pl.lit(raw["retrieved_at"]).alias("retrieved_at"), pl.lit(raw["snapshot_id"]).alias("vintage_id"),
        pl.lit(raw["sha256"]).alias("raw_sha256"), pl.lit(job.url).alias("source_url"),
    ).cast(SCHEMA)


def csv_stream(path: Path, separator=","):
    """Stream a CSV member; never extract untrusted ZIP paths to the filesystem."""
    f = path.open("rb"); sig = f.read(4); f.seek(0)
    if sig[:2] == b"PK":
        z = zipfile.ZipFile(f)
        members = [n for n in z.namelist() if n.lower().endswith((".csv", ".tsv")) and not n.startswith("__MACOSX")]
        if not members: z.close(); f.close(); raise ValueError("ZIP contains no CSV/TSV data")
        for member in members:
            if "metadata" in member.lower(): continue
            with z.open(member) as data:
                yield io.TextIOWrapper(data, encoding="utf-8-sig", newline="")
        z.close()
    elif sig[:2] == b"\x1f\x8b":
        with gzip.GzipFile(fileobj=f) as data:
            yield io.TextIOWrapper(data, encoding="utf-8-sig", newline="")
    else:
        yield io.TextIOWrapper(f, encoding="utf-8-sig", newline="")
    f.close()


def sdmx_csv(job: Job, raw: dict, path: Path, lake: Lake):
    sep = job.options.get("separator", ",")
    for stream in csv_stream(path, sep):
        reader = csv.DictReader(stream, delimiter=sep)
        rows = []
        for row in reader:
            if None in row or any(v is None for v in row.values()):
                raise ValueError("Malformed CSV row: header/data field counts differ")
            rows.append(row)
            if len(rows) >= 50000:
                yield sdmx_frame(pl.DataFrame(rows, schema={k: pl.String for k in rows[0]}, strict=False), job, raw); rows = []
        if rows: yield sdmx_frame(pl.DataFrame(rows, schema={k: pl.String for k in rows[0]}, strict=False), job, raw)


def bis_wide(job:Job,raw:dict,path:Path,lake:Lake):
    """BIS column CSV avoids malformed comma-containing flat-header labels."""
    time_pattern=re.compile(r"\d{4}(?:-?Q[1-4]|-?[HS][12]|-?W\d{2}|-?M\d{2}|-\d{2}(?:-\d{2})?)?$")
    for stream in csv_stream(path):
        reader=csv.reader(stream);header=next(reader)
        times=[(i,c.strip()) for i,c in enumerate(header) if time_pattern.fullmatch(c.strip())]
        if not times:raise ValueError("BIS column CSV has no period columns")
        metadata=[(i,c) for i,c in enumerate(header) if re.fullmatch(r"[A-Z][A-Z0-9_]*",c) or c=="Series"]
        rows=[]
        for values in reader:
            if len(values)!=len(header):raise ValueError("Malformed BIS column CSV row")
            fixed={c:values[i] for i,c in metadata}
            for i,period in times:
                value=values[i]
                if value is None or not value.strip():continue
                rows.append({**fixed,"TIME_PERIOD":period,"OBS_VALUE":value})
                if len(rows)>=25000:
                    yield sdmx_frame(pl.DataFrame(rows,schema={k:pl.String for k in rows[0]},strict=False),job,raw);rows=[]
        if rows:yield sdmx_frame(pl.DataFrame(rows,schema={k:pl.String for k in rows[0]},strict=False),job,raw)


def eurostat_tsv(job: Job, raw: dict, path: Path, lake: Lake):
    for stream in csv_stream(path, "\t"):
        reader = csv.reader(stream, delimiter="\t")
        header = next(reader)
        dimnames = header[0].split("\\", 1)[0].split(",")
        periods = [x.strip() for x in header[1:]]
        rows = []
        for record in reader:
            if len(record) != len(header): raise ValueError("Malformed Eurostat TSV row")
            dims = dict(zip(dimnames, (x.strip() for x in record[0].split(",")), strict=True))
            for period, cell in zip(periods, record[1:]):
                m = re.fullmatch(r"\s*([^\s]+)(?:\s+(.*))?\s*", cell)
                value, status = (m[1], m[2] or "") if m else (None, "")
                if value in {":", "", None}: continue
                rows.append(observation(job, raw, period=period, value=value, dims=dims,
                    indicator=dims.get("na_item", dims.get("coicop", job.dataset)), ref_area=dims.get("geo", ""),
                    unit=dims.get("unit"), currency=dims.get("currency"), status=status))
                if len(rows) >= 50000: yield frame(rows); rows = []
        if rows: yield frame(rows)


def fred_csv(job: Job, raw: dict, path: Path, lake: Lake):
    with path.open(encoding="utf-8-sig") as f:
        reader = csv.DictReader(f); rows = []
        for rec in reader:
            dt = rec.get("DATE", rec.get("observation_date"))
            if not dt: raise ValueError("FRED response has no observation_date")
            for indicator, value in rec.items():
                if indicator in {"DATE", "observation_date"}: continue
                meta = job.options.get("series", {}).get(indicator, {})
                frequency = meta.get("frequency", "D")
                native_period = dt[:4] if frequency == "A" else (dt[:7] if frequency == "M" else dt)
                if frequency == "Q": native_period = f"{dt[:4]}-Q{(int(dt[5:7])-1)//3+1}"
                dims = {"REF_AREA": meta.get("country", "US"), "INDICATOR": indicator, "FREQ": frequency}
                rows.append(observation(job, raw, period=native_period, value=value, dims=dims,
                    indicator=indicator, label=meta.get("label", indicator), ref_area=dims["REF_AREA"],
                    unit=meta.get("unit"), multiplier=meta.get("multiplier"), currency=meta.get("currency"),
                    attrs={"original_date": dt, "rights": "Underlying series may have third-party restrictions; retain attribution."}))
        yield frame(rows)


def sdmx_xml(job: Job, raw: dict, path: Path, lake: Lake):
    """Structure-specific SDMX 2.1, including IMF series/observation attributes.

    IMF SCALE is a display attribute: API OBS_VALUE is in actual units. It must
    not be multiplied by 10**SCALE. Preserve SCALE separately in attributes.
    """
    dimnames = set(job.options.get("dimensions", []))
    if not dimnames: raise ValueError("An SDMX XML adapter requires discovered DSD dimensions")
    labels = job.options.get("indicator_labels", {})
    label_file = lake.root / "metadata" / f"imf_{job.dataset}_indicators.json"
    if label_file.exists(): labels = json.loads(label_file.read_text())
    series = {}; dataset = {}; rows = []; found = False
    for event, elem in ET.iterparse(path, events=("start", "end")):
        tag = elem.tag.rsplit("}", 1)[-1]
        if event == "start" and tag == "DataSet":
            dataset = {k: v for k, v in elem.attrib.items() if "}" not in k}
        elif event == "start" and tag == "Series":
            series = dict(elem.attrib)
        elif event == "end" and tag == "Obs":
            found = True
            obs = dict(elem.attrib); merged = {**dataset, **series, **obs}
            period = obs.get("TIME_PERIOD")
            if period is None: raise ValueError("No TIME_PERIOD in SDMX observation")
            dims = {k: merged.get(k) for k in sorted(dimnames) if k != "TIME_PERIOD"}
            indicator = str(dims.get("INDICATOR", dims.get("MEASURE", "")) or "")
            detail = labels.get(indicator, {})
            if isinstance(detail, str): detail = {"label": detail}
            area = merged.get("COUNTRY", merged.get("REF_AREA", ""))
            latest = number(merged.get("LATEST_ACTUAL_ANNUAL_DATA"))
            estimate = int(str(period)[:4]) > latest if latest is not None else None
            status = merged.get("OBS_STATUS", "")
            attrs = {k: v for k, v in merged.items() if k not in dimnames | {"OBS_VALUE", "TIME_PERIOD"}}
            attrs["scale_semantics"] = "SCALE is display scaling; OBS_VALUE retained in actual API units"
            rows.append(observation(job, raw, period=period, value=obs.get("OBS_VALUE"), dims=dims,
                indicator=indicator, label=merged.get("SERIES_NAME", detail.get("label", "")),
                ref_area=area, unit=merged.get("UNIT_MEASURE", merged.get("UNIT", detail.get("unit"))) or reported_unit(detail.get("label", "")),
                multiplier=0, currency=merged.get("PRIMARY_DOMESTIC_CURRENCY", merged.get("CURRENCY")),
                status=status, forecast=True if status == "F" else None, estimate=estimate,
                publication_date=dataset.get("PUBLICATION_DATE"), attrs=attrs,
                source_updated=dataset.get("UPDATE_DATE")))
            if len(rows) >= 25000: yield frame(rows); rows = []
            elem.clear()
        elif event == "end" and tag == "Series":
            elem.clear()
    if rows: yield frame(rows)
    if not found: raise ValueError("No structure-specific SDMX observations found")


ADAPTERS = {"worldbank": worldbank, "sdmx_csv": sdmx_csv, "eurostat_tsv": eurostat_tsv,
            "eurostat_json": eurostat_json, "fred_csv": fred_csv, "sdmx_xml": sdmx_xml,"bis_wide":bis_wide}


def normalize(lake: Lake, job: Job, raw: dict, *, max_gb=40.0, min_free_gb=8.0) -> dict:
    if job.adapter == "raw":
        return {"rows": 0, "raw_only": True}
    if job.adapter not in ADAPTERS: raise ValueError(f"No adapter for {job.adapter}")
    out = lake.root / "silver" / job.source / job.dataset / raw["snapshot_id"]
    # Atomic visibility: catalog registration follows the completed parquet file.
    out.mkdir(parents=True, exist_ok=True)
    target = out / f"{job.id}.parquet"; tmp = target.with_suffix(".parquet.part")
    writer = None; rows = missing = 0; checked_bytes=0
    countries: set[str] = set(); series: set[str] = set(); first = last = None
    try:
        for df in ADAPTERS[job.adapter](job, raw, lake.root / raw["path"], lake):
            if df.height == 0: continue
            if df.select(pl.col("series_id").is_null().any()).item(): raise ValueError("Null series identifier")
            if df.select(pl.col("value").is_infinite().any()).item(): raise ValueError("Infinite observation")
            duplicated = df.select(pl.struct("series_id", "period").is_duplicated().sum()).item()
            if duplicated: raise ValueError(f"{duplicated} duplicate series/period rows inside batch")
            countries.update(df["country_iso3"].drop_nulls().unique().to_list())
            series.update(df["series_id"].unique().to_list())
            a, b = df["period_start"].min(), df["period_end"].max()
            first = min(first, a) if first else a; last = max(last, b) if last else b
            missing += df["value"].null_count(); rows += df.height
            arrow = df.to_arrow()
            if writer is None: writer = pq.ParquetWriter(tmp, arrow.schema, compression="zstd", compression_level=6)
            writer.write_table(arrow, row_group_size=50000)
            written=tmp.stat().st_size
            if written-checked_bytes>=64*1024**2:
                lake.check_space(max_gb,min_free_gb)
                checked_bytes=written
            if rows%500000==0:
                lake.event(job.id,"normalizing",f"{rows} rows written; not yet committed")
                print(compact({"at":utcnow(),"event":"normalizing","dataset":job.dataset,"rows":rows}),flush=True)
        if writer is not None: writer.close(); writer = None
        if rows == 0:
            tmp.unlink(missing_ok=True)
            lake.event(job.id, "empty", "Provider returned no observations; not a successful data partition")
            return {"rows": 0, "empty": True}
        # Across-batch duplicate validation is external-memory capable via Polars.
        dup = (pl.scan_parquet(tmp).group_by("series_id", "period").len()
               .filter(pl.col("len") > 1).select(pl.len()).collect(engine="streaming").item())
        if dup: raise ValueError(f"{dup} duplicate series/period keys across batches")
        os.replace(tmp, target)
        sha = hashlib.file_digest(target.open("rb"), "sha256").hexdigest()
        row = dict(id=digest([job.id, raw["snapshot_id"]]), job_id=job.id,
                   snapshot_id=raw["snapshot_id"], path=str(target.relative_to(lake.root)),
                   source=job.source, dataset=job.dataset, rows=rows, missing_values=missing,
                   duplicates=0, countries=len(countries), series=len(series), first_period=str(first),
                   last_period=str(last), sha256=sha, created_at=utcnow())
        lake.register_partition(row)
        return row
    except BaseException:
        if writer: writer.close()
        tmp.unlink(missing_ok=True)
        raise
