# Monetary and fiscal research database

This subsystem expands the project into a multi-source research database. The
original `run.py`, article estimators, frozen input files and processed article
panels keep their existing behavior. All new dataframe transformations use
Polars. Large files live outside Git.

## Run

Reference platform: Linux, Python 3.12. Use a separate environment so that the
article's frozen dependencies are preserved.

```bash
python3 -m venv .venv-data
.venv-data/bin/python -m pip install -r requirements-data.txt
.venv-data/bin/python -m pytest -q tests/data_lake

# Choose a persistent filesystem with sufficient free space.
.venv-data/bin/python -m datalake --root /data/monetary-fiscal plan --profile broad
.venv-data/bin/python -m datalake --root /data/monetary-fiscal import-existing --repository .
.venv-data/bin/python -u -m datalake --root /data/monetary-fiscal \
  --max-gb 40 --min-free-gb 8 run --workers 1 --hours 7

.venv-data/bin/python -m datalake --root /data/monetary-fiscal report
.venv-data/bin/python -m datalake --root /data/monetary-fiscal build-panels
.venv-data/bin/python -m datalake --root /data/monetary-fiscal research-readiness
.venv-data/bin/python -m datalake --root /data/monetary-fiscal verify --hashes
```

`plan` performs real catalog discovery. It queues requests and reports provider
failures. `run` downloads and normalizes them, adds every required API page,
retains successful work, and records failed requests separately. A `full`
profile selects all WDI indicators, all BIS bulk topics listed by the current
catalog, additional fiscal Eurostat tables, and IMF vintages exposed by its
current catalog. It requires more time and storage. Public API availability
and provider coverage set the actual attainable sample.

Queue control:

```bash
# Small, network-connected smoke run.
.venv-data/bin/python -m datalake --root /data/smoke plan \
  --providers BIS WORLDBANK IMF FRBSF --profile smoke
.venv-data/bin/python -m datalake --root /data/smoke run --max-jobs 12

# Resume pending work, or retry failed requests after resolving their cause.
.venv-data/bin/python -m datalake --root /data/monetary-fiscal run --hours 7
.venv-data/bin/python -m datalake --root /data/monetary-fiscal retry --sources IMF
.venv-data/bin/python -m datalake --root /data/monetary-fiscal run --sources IMF

# Revalidate completed requests to collect a new retrieval vintage.
.venv-data/bin/python -m datalake --root /data/monetary-fiscal \
  retry --sources WORLDBANK --include-done
.venv-data/bin/python -m datalake --root /data/monetary-fiscal \
  run --sources WORLDBANK --refresh

# Graceful stop: active jobs finish before the runner stops.
.venv-data/bin/python -m datalake --root /data/monetary-fiscal stop
```

The hours limit controls admission of new jobs. An active large download or
normalization can finish after that limit. Interruptions leave original
objects available for the next normalization attempt. On restart, the runner
recovers interrupted queue entries under its exclusive filesystem lock.

## Provider coverage

These are implemented acquisition routes. Successful downloads, countries,
dates and failures are measured by the generated reports, rather than assumed
from a provider's advertised maximum coverage.

| Provider | Implemented datasets or route | Research purpose |
|---|---|---|
| World Bank | WDI, IDS, QPSD, QEDS SDDS/GDDS, GEM, JEDH, GFDD, WGI, IDS DSSI; ESG in full profile | Global macro controls; fiscal stocks, external debt, creditors, maturities, institutions and financial development |
| IMF | WEO, FM, GDD, HPD, ICSD, PSBS, FD, monetary and financial statistics, GFS/QGFS, BOP, IIP/IIPCC, PIP/DIP, FSI, FAS, FX intervention | Fiscal outcomes and balance sheets, government/bank links, external positions, forecasts and available historical releases |
| BIS | Policy rates, CPI, central-bank assets, credit, debt-service ratios, credit gaps, exchange rates, debt securities, GLI, international banking, property and derivatives | Repricing, refinancing, financial cycles, currency exposure and international spillovers |
| Eurostat | Discovered government debt/currency/remaining-maturity/guarantee tables, government accounts, sector balance sheets, GDP, HICP, rates, BOP and activity | Comparable European fiscal and monetary panels |
| ECB | Discovered EXR, YC, MIR, BSI, GFS, CISS, CLIFS and selected financial-account flows; policy-rate series | Yield curves, deposit/credit pass-through, bank balance sheets and financial stress |
| OECD | Public-sector debt, instrument-coverage definitions, government financial indicators | Debt-definition checks and broader advanced-economy comparisons |
| US Treasury | Debt to the penny, average interest rates, interest expense, monthly security-level debt tables | Security maturity schedules, interest costs, inflation-indexed and floating-rate debt |
| NBP | A/B/C exchange-rate tables from 2002, in bounded date windows | Polish currency conditions, bid/ask and original currency conventions |
| FRBSF | USMPD workbook and original policy-surprise bundle | Separate FOMC statements, press conferences, combined events and minutes |
| ECB event database | EA-MPD workbook with original Notes | Event-window rate, equity and exchange-rate changes |
| Bolhuis–Das–Yao | Workbook discovered in the author's publicly linked folder; separate release datasets | Updated or revised global monetary surprises, with actual coverage checked after retrieval |
| Existing article | All original file checksums and explicit processed-table bridges | Creditor ownership, native maturity observations, currency shares and existing monetary shocks |

IMF structures, dimension ordering and country codes are discovered from the
current SDMX definitions. Large flows are split into country groups. Country
groups and territories are retained in the source layer and identified
separately in research views. A country with no observed value does not count
toward reported country coverage.

## Storage and retrieval vintages

```
raw/objects/<sha-prefix>/<sha256>    immutable original response bodies
metadata/catalog.sqlite            queue, source objects, partitions, events
metadata/jobs/                     reproducible request specifications
metadata/downloads/                immutable download manifests
metadata/partitions/               normalized-file manifests and checksums
metadata/*                         provider catalogs, DSDs and series metadata
silver/<provider>/<dataset>/<id>/   native-frequency Parquet observations
gold/                              explicitly constructed research views
reports/                           coverage, failures, provenance and validation
logs/                              execution output
```

The raw SHA256 is tied to every normalized observation. Retrieval vintages are
retained. A successful refresh creates a new snapshot, while the research
scan selects the latest successful partition for each exact request. Archived
provider releases remain separate datasets. Retrieval date and historical
publication date have different meanings; see [the data contract](data_contract.md).

SQLite uses short, serialized connections and a rollback journal to support
managed filesystems without relying on mmap-backed WAL behavior. Immutable
JSON sidecars retain request and file provenance. SQLite's backup API creates
portable checkpoints; an active database file is never copied directly.

## Large storage and Google Drive

The lake can reside on a larger local disk, a server, or a suitably mounted
persistent filesystem. Increase `--max-gb` and the free-space reserve for a
larger installation. The default 40 GiB budget fits the initial environment;
it does not claim terabyte capacity.

For an already configured and authorized rclone remote:

```bash
rclone about gdrive:
.venv-data/bin/python -m datalake --root /data/monetary-fiscal \
  cloud-copy --remote gdrive:MonetaryFiscalLake --dry-run
.venv-data/bin/python -m datalake --root /data/monetary-fiscal \
  cloud-copy --remote gdrive:MonetaryFiscalLake
```

The command creates a SQLite backup, copies completed objects and datasets,
and verifies provider-supported checksums with `rclone check --one-way`.
It performs no deletion. Credentials stay in the local rclone configuration
or the normal authorization system, outside Git. Connecting a Google Drive
app in ChatGPT does not automatically authorize rclone on a server. A copy is
reported as complete only after the actual transfer and check succeed.

Drive storage capacity must be checked on the selected account. Google
documents a 750 GB/day upload/copy limit for Workspace and resumable large
uploads, so large initial archives need staged transfer. Source:
[Drive API limits](https://developers.google.com/workspace/drive/api/guides/limits).

For a portable checkpoint containing newly acquired source data:

```bash
.venv-data/bin/python -m datalake --root /data/monetary-fiscal \
  snapshot --output /backups/monetary_fiscal_lake_checkpoint.tar.gz
mkdir -p /data/restored-lake
tar -xzf /backups/monetary_fiscal_lake_checkpoint.tar.gz -C /data/restored-lake
.venv-data/bin/python -m datalake --root /data/restored-lake verify --hashes
```

Code and the original article's Git-backed files are excluded from this
checkpoint. Reattach those sources with `import-existing` if wanted. Transfer
the archive only after generation completes and retain its SHA256. Restoring
an externally supplied archive requires the usual path/symlink inspection.

## Research interfaces

```python
import polars as pl
from datalake.storage import Lake
from datalake.research import scan

lake = Lake("/data/monetary-fiscal")
debt = (
    scan(lake, source="IMF", dataset="GDD")
    .filter(pl.col("country_iso3").is_not_null())
    .select("country_iso3", "indicator", "label", "period", "value", "unit", "dimensions")
    .collect(engine="streaming")
)
```

`build-panels` creates a native annual WDI country panel and a separate
observation-level lineage file. It does not substitute general-government
debt for a central-government measure. `research-readiness` builds observed
BIS refinancing ratios only for a fixed, compatible security portfolio and
reports monetary-event coverage. Missing components remain missing.

The [research directions](research_directions.md) describe questions supported
by this expanded scope and the additional checks needed before estimation.
The initial live-run evidence is recorded separately in `run_summary.json`.

## Attribution and use

Keep every original provider identifier, source URL and citation. Public
downloadability does not imply unrestricted redistribution of all underlying
series: this particularly affects FRED series from third parties, BIS
vendor-derived data and author-provided research workbooks. The Bolhuis–Das–Yao
author page permits academic research use and requests citation. The lake
does not download Bloomberg or other paid-vendor microdata without a separately
authorized source and appropriate rights.
