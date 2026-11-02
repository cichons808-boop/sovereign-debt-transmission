"""Whole-lake reporting with bounded Parquet batches and disk-backed series keys."""
from __future__ import annotations

import json
import os
import sqlite3
import shutil
import tempfile
from contextlib import closing
from pathlib import Path

import polars as pl
import pyarrow.parquet as pq

from .model import SCHEMA
from .storage import utcnow

DICTIONARY = ["source", "dataset", "series_id", "ref_area", "country_iso3", "indicator", "label",
              "frequency", "unit", "unit_multiplier", "currency", "dimensions"]
COUNTERS = ["rows", "nonmissing_observations", "aggregate_rows", "unmapped_or_aggregate_rows",
            "missing_unit_rows", "estimated_rows"]


def _merge(target, key, row):
    old = target.setdefault(key, {k: 0 for k in COUNTERS} | {"first_period": None, "last_period": None})
    for name in COUNTERS:
        old[name] += row.get(name, 0)
    for name, operation in [("first_period", min), ("last_period", max)]:
        value = row.get(name)
        if value is not None:
            old[name] = value if old[name] is None else operation(old[name], value)


def report(lake, *, batch_rows=8192):
    from .research import current_partitions
    if batch_rows < 1:
        raise ValueError("batch_rows must be positive")
    # Freeze the same latest-successful-request selection as research.scan.
    parts = current_partitions(lake)
    totals, countries = {}, {}
    columns = DICTIONARY + ["value", "period_start", "period_end", "is_aggregate", "is_estimate"]
    aggregations = [pl.len().alias("rows"), pl.col("value").is_not_null().sum().alias("nonmissing_observations"),
        pl.col("period_start").filter(pl.col("value").is_not_null()).min().alias("first_period"),
        pl.col("period_end").filter(pl.col("value").is_not_null()).max().alias("last_period"),
        pl.col("is_aggregate").fill_null(False).sum().alias("aggregate_rows"),
        pl.col("country_iso3").is_null().sum().alias("unmapped_or_aggregate_rows"),
        pl.col("unit").is_null().sum().alias("missing_unit_rows"),
        pl.col("is_estimate").fill_null(False).sum().alias("estimated_rows")]
    with tempfile.TemporaryDirectory(prefix="report-", dir=lake.root / "raw/tmp") as temporary:
        stage = Path(temporary)
        with closing(sqlite3.connect(stage / "series.sqlite")) as db:
            db.execute("PRAGMA cache_size=-8192")
            db.execute("PRAGMA temp_store=FILE")
            db.execute("CREATE TABLE series(source TEXT,dataset TEXT,id TEXT,country TEXT,frequency TEXT,payload TEXT,PRIMARY KEY(source,dataset,id)) WITHOUT ROWID")
            for part in parts:
                if shutil.disk_usage(lake.root).free < 8 * 1024**3:
                    raise OSError("Free-space reserve reached during report")
                for batch in pq.ParquetFile(lake.root / part["path"]).iter_batches(batch_size=batch_rows, columns=columns):
                    data = pl.from_arrow(batch)
                    for row in data.group_by("source", "dataset").agg(aggregations).to_dicts():
                        _merge(totals, (row["source"], row["dataset"]), row)
                    for row in data.filter(pl.col("country_iso3").is_not_null()).group_by(
                            "source", "dataset", "country_iso3", "frequency").agg(aggregations).to_dicts():
                        _merge(countries, tuple(row[k] for k in ["source", "dataset", "country_iso3", "frequency"]), row)
                    # Only this bounded batch is deduplicated in memory. SQLite
                    # resolves overlap across batches/requests in acquisition order.
                    metadata = data.select(DICTIONARY).unique(subset=["source", "dataset", "series_id"], keep="last")
                    db.executemany("INSERT OR REPLACE INTO series VALUES(?,?,?,?,?,?)", (
                        (r[0], r[1], r[2], r[4], r[7], json.dumps(r, ensure_ascii=False, separators=(",", ":")))
                        for r in metadata.iter_rows()))
                db.commit()
            series_counts = {(s, d): n for s, d, n in db.execute("SELECT source,dataset,COUNT(*) FROM series GROUP BY source,dataset")}
            country_series = {(s, d, c, f): n for s, d, c, f, n in db.execute(
                "SELECT source,dataset,country,frequency,COUNT(*) FROM series WHERE country IS NOT NULL GROUP BY source,dataset,country,frequency")}
            dictionary_path = stage / "series_dictionary.parquet"
            dictionary_schema = {k: SCHEMA[k] for k in DICTIONARY}
            with pq.ParquetWriter(dictionary_path, pl.DataFrame(schema=dictionary_schema).to_arrow().schema, compression="zstd") as writer:
                cursor = db.execute("SELECT payload FROM series ORDER BY source,dataset,id")
                while records := cursor.fetchmany(batch_rows):
                    frame = pl.DataFrame([json.loads(r[0]) for r in records], schema=dictionary_schema, orient="row")
                    writer.write_table(frame.to_arrow())
            summary_rows = []
            for (source, dataset), row in sorted(totals.items()):
                # A country with multiple native frequencies counts once.
                count = len({c for (s,d,c,f),r in countries.items()
                             if (s,d)==(source,dataset) and r["nonmissing_observations"]>0})
                summary_rows.append({"source":source, "dataset":dataset, **row,
                                     "countries":count, "series":series_counts[(source,dataset)]})
            country_rows = [{"source":s,"dataset":d,"country_iso3":c,"frequency":f,
                             "rows":r["rows"],"nonmissing_observations":r["nonmissing_observations"],
                             "series":country_series[(s,d,c,f)],"first_observed_period":r["first_period"],
                             "last_observed_period":r["last_period"]}
                            for (s,d,c,f),r in sorted(countries.items(),key=lambda x:tuple(str(v) for v in x[0]))]
            summary_schema = {"source":pl.String,"dataset":pl.String,**{k:pl.Int64 for k in COUNTERS},
                              "first_period":pl.Date,"last_period":pl.Date,"countries":pl.Int64,"series":pl.Int64}
            country_schema = {"source":pl.String,"dataset":pl.String,"country_iso3":pl.String,"frequency":pl.String,
                              "rows":pl.Int64,"nonmissing_observations":pl.Int64,"series":pl.Int64,
                              "first_observed_period":pl.Date,"last_observed_period":pl.Date}
            pl.DataFrame(summary_rows, schema=summary_schema).write_csv(stage / "source_coverage.csv")
            pl.DataFrame(country_rows, schema=country_schema).write_csv(stage / "country_coverage.csv")
            for name in ["source_coverage.csv", "country_coverage.csv"]:
                os.replace(stage / name, lake.root / "reports" / name)
            os.replace(dictionary_path, lake.root / "metadata/series_dictionary.parquet")
    with lake.db() as db:
        downloads = [dict(r) for r in db.execute("SELECT * FROM downloads ORDER BY retrieved_at,snapshot_id")]
        failures = [dict(r) for r in db.execute("SELECT id,source,dataset,error,spec FROM jobs WHERE state='failed'")]
        pending = [dict(r) for r in db.execute("SELECT source,dataset,state,COUNT(*) jobs FROM jobs GROUP BY source,dataset,state")]
    lake.atomic_json("reports/download_manifest.json", downloads)
    lake.atomic_json("reports/failures.json", failures)
    lake.atomic_json("reports/queue.json", pending)
    country_ids = sorted({c for (s,d,c,f),r in countries.items() if r["nonmissing_observations"]>0})
    result = {"generated_at":utcnow(),"current_dataset_count":len(totals),
              "current_rows":sum(r["rows"] for r in totals.values()),
              "current_nonmissing_observations":sum(r["nonmissing_observations"] for r in totals.values()),
              "country_count_with_data":len(country_ids),"country_iso3_with_data":country_ids,
              "immutable_downloads":len(downloads),"bytes_on_disk":lake.usage(),"failed_jobs":len(failures),
              "series_dictionary_rows":sum(series_counts.values()),"report_batch_rows":batch_rows,
              "notes":["Latest successful partition per exact request; overlapping requests are not economically deduplicated.",
                       "Country coverage requires a nonmissing provider value; future-dated entries are not necessarily realized history.",
                       "Native units, dimensions and provider identities stay separate. Missing units require research review.",
                       "Series keys deduplicated on disk; bounded Parquet batches. Retrieval is not historical publication."]}
    lake.atomic_json("reports/coverage_summary.json", result)
    return result
