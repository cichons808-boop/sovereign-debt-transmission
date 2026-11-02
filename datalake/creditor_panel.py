"""Observed IDS creditor view; no sums across overlapping creditor aggregates."""
from __future__ import annotations

import polars as pl

from .research import scan
from .storage import Lake, utcnow


def build_creditor_panel(lake: Lake) -> dict:
    # Restrict revision resolution to this dataset, never the entire lake.
    data = scan(lake, source="WORLDBANK", dataset="IDS_CREDITOR", deduplicate=True)
    summary = data.select(pl.len().alias("normalized_rows"),
                          pl.col("value").is_null().sum().alias("missing_rows")).collect(engine="streaming").row(0, named=True)
    observed = (data.filter(pl.col("value").is_not_null()).with_columns(
        pl.col("dimensions").str.json_path_match("$.COUNTERPART_AREA").alias("creditor_code"),
        pl.col("attributes").str.json_path_match("$.native_labels.counterpart_area").alias("creditor_label"),
        pl.col("attributes").str.json_path_match("$.native_labels.country").alias("debtor_label"))
        .with_columns((pl.col("creditor_code") == "WLD").alias("is_world_total"),
                      (pl.col("period").cast(pl.Int32) > pl.col("retrieved_at").str.slice(0, 4).cast(pl.Int32)).alias("after_retrieval_year"))
        .select("ref_area", "country_iso3", "debtor_label", "creditor_code", "creditor_label", "is_world_total",
                "indicator", "label", "period", "after_retrieval_year", "is_estimate", "is_forecast", "value", "unit", "unit_multiplier", "currency",
                "series_id", "vintage_id", "raw_sha256", "retrieved_at", "source_url")
        .sort("ref_area", "indicator", "creditor_code", "period").collect(engine="streaming"))
    if observed["creditor_code"].null_count():
        raise ValueError("Observed IDS value without native creditor identity")
    if observed.select(pl.struct("ref_area", "indicator", "creditor_code", "period").is_duplicated().any()).item():
        raise ValueError("Additional IDS dimensions require a richer creditor-view key")
    target = lake.root / "gold/ids_observed_creditor_panel.parquet"
    observed.write_parquet(target, compression="zstd")
    coverage = observed.group_by("ref_area", "country_iso3", "indicator").agg(
        pl.len().alias("observations"), pl.col("creditor_code").n_unique().alias("native_creditor_entities"),
        (pl.col("value") == 0).sum().alias("reported_zeroes"),
        pl.col("period").min().alias("first_period"), pl.col("period").max().alias("last_period"))
    coverage.sort("ref_area", "indicator").write_csv(lake.root / "reports/ids_creditor_coverage.csv")
    result = {"generated_at": utcnow(), **summary, "observed_rows": observed.height,
              "debtor_entities": observed["ref_area"].n_unique(),
              "debtor_countries_with_values": observed["country_iso3"].drop_nulls().n_unique(),
              "native_creditor_entities_with_values": observed["creditor_code"].n_unique(),
              "indicators_with_values": observed["indicator"].unique().sort().to_list(),
              "reported_zeroes": observed.filter(pl.col("value") == 0).height,
              "world_total_rows": observed.filter(pl.col("is_world_total")).height,
              "after_retrieval_year_rows": observed.filter(pl.col("after_retrieval_year")).height,
              "first_period": observed["period"].min(), "last_period": observed["period"].max(),
              "semantics": "Nonmissing provider values, including reported zeroes and future-dated entries. These are not all realized historical observations; after_retrieval_year is a calendar flag, not a forecast classification. Native estimate/forecast fields remain unchanged. Missing source cells are retained in silver. Native creditor entities include institutions and historical entities; they are not a country count. WLD is flagged separately; other aggregate codes are not guessed. No creditor summation, interpolation, zero-filling or currency-denomination inference. Latest successful retrieval resolves overlapping requests."}
    lake.atomic_json("reports/ids_creditor_panel.json", result)
    return result
