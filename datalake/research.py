"""Coverage-first research views. No automatic causal claims or source splicing."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import polars as pl

from .model import SCHEMA
from .storage import Lake, utcnow


def current_partitions(lake: Lake) -> list[dict]:
    # Latest successfully normalized retrieval for each exact request. A failed
    # refresh does not hide its last valid dataset. Vintage history stays intact.
    with lake.db() as db:
        return [dict(r) for r in db.execute("""
        SELECT * FROM (
          SELECT p.*, d.retrieved_at AS acquired_at, ROW_NUMBER() OVER (PARTITION BY p.job_id ORDER BY d.retrieved_at DESC,p.created_at DESC,p.snapshot_id DESC) AS rn
          FROM partitions p JOIN downloads d ON d.snapshot_id=p.snapshot_id
        ) WHERE rn=1 ORDER BY acquired_at,created_at,snapshot_id,path
        """)]


def scan(lake: Lake, *, source=None, dataset=None, deduplicate=False) -> pl.LazyFrame:
    rows = [p for p in current_partitions(lake) if (source is None or p["source"] == source) and (dataset is None or p["dataset"] == dataset)]
    if not rows: return pl.DataFrame(schema=SCHEMA).lazy()
    data=pl.scan_parquet([str(lake.root / p["path"]) for p in rows])
    # Large scans stay streaming. Optional revision resolution should be used
    # on a country/time/indicator slice, not on an entire multi-terabyte lake.
    if deduplicate:
        data=data.unique(subset=["source","dataset","series_id","period"],keep="last")
    return data


def report(lake: Lake) -> dict:
    from .bounded_report import report as bounded_report
    return bounded_report(lake)


WDI_ANNUAL = {
    "NY.GDP.MKTP.CD": "gdp_current_usd", "NY.GDP.MKTP.KD.ZG": "real_gdp_growth_pct",
    "NY.GDP.PCAP.KD": "real_gdp_per_capita_constant2015usd",
    "FP.CPI.TOTL.ZG": "cpi_inflation_pct", "FP.CPI.TOTL": "cpi_index_2010",
    "BN.CAB.XOKA.GD.ZS": "current_account_pct_gdp", "NE.TRD.GNFS.ZS": "trade_pct_gdp",
    "GC.DOD.TOTL.GD.ZS": "central_government_debt_pct_gdp",
    "GC.BAL.CASH.GD.ZS": "central_government_cash_balance_pct_gdp",
    "GC.REV.XGRT.GD.ZS": "government_revenue_ex_grants_pct_gdp",
    "GC.TAX.TOTL.GD.ZS": "tax_revenue_pct_gdp", "GC.XPN.INTP.RV.ZS": "interest_pct_revenue",
    "GC.XPN.INTP.ZS": "interest_pct_expense", "GC.XPN.TOTL.GD.ZS": "government_expense_pct_gdp",
    "FR.INR.RINR": "real_interest_rate_pct", "FR.INR.LEND": "lending_interest_rate_pct",
    "FM.LBL.BMNY.GD.ZS": "broad_money_pct_gdp", "FS.AST.PRVT.GD.ZS": "private_credit_pct_gdp",
    "FD.AST.PRVT.GD.ZS": "bank_private_credit_pct_gdp",
    "DT.DOD.DECT.GN.ZS": "external_debt_pct_gni", "DT.TDS.DECT.EX.ZS": "external_debt_service_pct_exports",
    "DT.DOD.DSTC.IR.ZS": "short_external_debt_pct_reserves", "FI.RES.TOTL.CD": "reserves_incl_gold_usd",
    "PA.NUS.FCRF": "official_fx_lcu_per_usd", "SL.UEM.TOTL.ZS": "unemployment_pct_labor_force",
    "BX.KLT.DINV.WD.GD.ZS": "fdi_inflows_pct_gdp", "SP.POP.TOTL": "population",
}


def build_panels(lake: Lake) -> dict:
    wdi = (scan(lake, source="WORLDBANK", dataset="WDI")
           .filter(pl.col("country_iso3").is_not_null() & (pl.col("frequency") == "A") & pl.col("indicator").is_in(list(WDI_ANNUAL))))
    d = wdi.select("country_iso3", "period", "indicator", "value", "vintage_id", "raw_sha256","retrieved_at").collect(engine="streaming")
    if d.height == 0: return {"wdi_annual_rows": 0, "message": "No curated WDI series have been downloaded yet"}
    dup = d.group_by("country_iso3", "period", "indicator").len().filter(pl.col("len") > 1)
    if dup.height:
        dup.write_csv(lake.root / "reports/panel_key_conflicts.csv")
        # Catalog growth can regroup requests. Resolve the same WDI definition
        # by its latest retrieval; source/dataset/indicator are unchanged.
        d=d.sort("retrieved_at","vintage_id").unique(subset=["country_iso3","period","indicator"],keep="last")
    d = d.with_columns(pl.col("indicator").replace_strict(WDI_ANNUAL).alias("variable"))
    panel = d.pivot(on="variable", index=["country_iso3", "period"], values="value").sort("country_iso3", "period")
    target = lake.root / "gold/wdi_annual_country_panel.parquet"
    panel.write_parquet(target, compression="zstd")
    panel.write_csv(lake.root / "gold/wdi_annual_country_panel.csv")
    d.write_parquet(lake.root / "gold/wdi_annual_lineage.parquet", compression="zstd")
    lake.atomic_json("gold/wdi_annual_definitions.json", {
        "indicators": WDI_ANNUAL, "source": "World Bank WDI", "frequency": "native annual",
        "missing": "No interpolation, carry-forward, or zero-filling", "debt_scope": "GC.DOD.TOTL.GD.ZS is central government, not automatically general government",
        "time_information": "Current revised values; not a point-in-time backtest dataset",
        "series_lineage": "wdi_annual_lineage.parquet", "created_at": utcnow()})
    complete = panel.select([pl.col(c).is_not_null().sum().alias(c) for c in panel.columns if c not in {"country_iso3", "period"}]).to_dicts()[0]
    result = {"wdi_annual_rows": panel.height, "countries": panel["country_iso3"].n_unique(),
              "variables": len(panel.columns)-2, "nonmissing_by_variable": complete}
    lake.atomic_json("reports/research_panel_coverage.json", result)
    return result


def build_refinancing(lake:Lake) -> dict:
    """Observed short-original plus long-due-within-year over the same stock."""
    d=scan(lake,source="BIS",dataset="WS_NA_SEC_DSS")
    filters={"FREQ":"Q","ADJUSTMENT":"N","COUNTERPART_AREA":"XW","COUNTERPART_SECTOR":"S1",
             "CONSOLIDATION":"N","ACCOUNTING_ENTRY":"L","STO":"LE","INSTR_ASSET":"F3","EXPENDITURE":"_Z",
             "UNIT_MEASURE":"USD","CURRENCY_DENOM":"_T","PRICES":"V","TRANSFORMATION":"N","CUST_BREAKDOWN":"_T","VALUATION":"N"}
    for key,value in filters.items():d=d.filter(pl.col("dimensions").str.json_path_match("$."+key)==value)
    d=(d.with_columns(pl.col("dimensions").str.json_path_match("$.MATURITY").alias("maturity"),
                      pl.col("dimensions").str.json_path_match("$.REF_SECTOR").alias("sector"))
       .filter(pl.col("maturity").is_in(["S","LS","T"]) & pl.col("sector").is_in(["S13","S1311"]))
       .select("country_iso3","ref_area","period","sector","maturity","value","unit_multiplier","raw_sha256","vintage_id")
       .collect(engine="streaming"))
    if d.height==0:return {"bis_refinancing_rows":0,"message":"BIS debt-security partitions not available yet"}
    if d["unit_multiplier"].null_count():raise ValueError("Cannot combine BIS maturity stocks with unknown scale")
    d=d.with_columns((pl.col("value")*(pl.lit(10.0).pow(pl.col("unit_multiplier")))).alias("stock_usd"))
    keys=["country_iso3","ref_area","period","sector"]
    dup=d.group_by(keys+["maturity"]).len().filter(pl.col("len")>1)
    if dup.height:
        dup.write_csv(lake.root/"reports/bis_maturity_key_conflicts.csv")
        raise ValueError("BIS maturity candidates have extra economic dimensions; resolve before ratio calculation")
    wide=d.pivot(on="maturity",index=keys,values="stock_usd")
    for col in ["S","LS","T"]:
        if col not in wide.columns:wide=wide.with_columns(pl.lit(None,dtype=pl.Float64).alias(col))
    result=(wide.with_columns(((pl.col("S")+pl.col("LS"))/pl.col("T")).alias("refinance_share"))
            .filter(pl.col("T")>0).with_columns(pl.lit("debt securities").alias("portfolio"),pl.lit("nominal").alias("valuation")))
    bad=result.filter((pl.col("refinance_share")<0)|(pl.col("refinance_share")>1.002))
    if bad.height:
        bad.write_csv(lake.root/"reports/bis_maturity_ratio_flags.csv")
        raise ValueError("BIS maturity shares outside [0,1.002]; flagged observations require review")
    result=result.sort(keys);result.write_parquet(lake.root/"gold/bis_government_refinancing_quarterly.parquet",compression="zstd")
    d.write_parquet(lake.root/"gold/bis_government_refinancing_lineage.parquet",compression="zstd")
    return {"bis_refinancing_rows":result.height,"observed_shares":result["refinance_share"].drop_nulls().len(),
            "countries":result.filter(pl.col("refinance_share").is_not_null())["country_iso3"].drop_nulls().n_unique(),
            "candidate_countries":result["country_iso3"].drop_nulls().n_unique()}


def research_readiness(lake:Lake) -> dict:
    """Report source/date coverage that can motivate subsequent research designs."""
    events=(scan(lake).filter(pl.col("source").is_in(["FRBSF","ECB_EVENTS","BDY_AUTHOR"]))
            .filter(pl.col("value").is_not_null()).group_by("source","dataset","ref_area","indicator")
            .agg(pl.len().alias("observations"),pl.col("period_start").min().alias("first"),pl.col("period_end").max().alias("last"))
            .sort("source","dataset","ref_area","indicator").collect(engine="streaming"))
    events.write_csv(lake.root/"reports/monetary_event_coverage.csv")
    return {"event_series_with_data":events.height,"event_sources":events["source"].n_unique(),
            "refinancing":build_refinancing(lake)}


def verify(lake: Lake, hashes=False) -> dict:
    errors = []; checked = 0
    with lake.db() as db:
        integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok": errors.append({"catalog_integrity": integrity})
        downloads = [dict(r) for r in db.execute("SELECT * FROM downloads")]
        parts = [dict(r) for r in db.execute("SELECT * FROM partitions")]
    raw_ids = {r["snapshot_id"] for r in downloads}
    for row in downloads + parts:
        p = lake.root / row["path"]; checked += 1
        if not p.exists(): errors.append({"path": row["path"], "error": "missing file"}); continue
        if hashes:
            with p.open("rb") as f: sha = hashlib.file_digest(f, "sha256").hexdigest()
            if sha != row["sha256"]: errors.append({"path": row["path"], "error": "SHA256 mismatch"})
    for row in parts:
        if row["snapshot_id"] not in raw_ids: errors.append({"path": row["path"], "error": "missing raw lineage"})
        p = lake.root / row["path"]
        if not p.exists(): continue
        try:
            lf = pl.scan_parquet(p)
            if dict(lf.collect_schema()) != SCHEMA: errors.append({"path": row["path"], "error": "schema differs"})
            actual = lf.select(pl.len()).collect().item()
            if actual != row["rows"]: errors.append({"path": row["path"], "error": "row count mismatch"})
        except Exception as exc: errors.append({"path": row["path"], "error": str(exc)})
    result = {"verified_at": utcnow(), "checked_files": checked, "checked_partitions": len(parts),
              "raw_hashes_recomputed": hashes, "catalog_integrity": integrity, "errors": errors}
    lake.atomic_json("reports/verification.json", result)
    return result
