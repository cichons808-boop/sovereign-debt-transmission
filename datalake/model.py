"""Provider-independent observation contract, without erasing source dimensions."""
from __future__ import annotations

import calendar
import math
import re
from datetime import date

import polars as pl
import pycountry

from .identity import Job, compact, digest

SCHEMA_VERSION = "1.0"
SCHEMA = {
    "source": pl.String, "dataset": pl.String, "series_id": pl.String,
    "ref_area": pl.String, "country_iso3": pl.String, "is_aggregate": pl.Boolean,
    "indicator": pl.String, "label": pl.String, "frequency": pl.String,
    "period": pl.String, "period_start": pl.Date, "period_end": pl.Date,
    "value": pl.Float64, "unit": pl.String, "unit_multiplier": pl.Int16,
    "currency": pl.String, "obs_status": pl.String, "is_forecast": pl.Boolean,
    "is_estimate": pl.Boolean, "publication_date": pl.String,
    "dimensions": pl.String, "attributes": pl.String, "source_updated": pl.String,
    "retrieved_at": pl.String, "vintage_id": pl.String,
    "raw_sha256": pl.String, "source_url": pl.String,
}
ALIASES = {"EL": "GR", "UK": "GB", "XK": "XKX", "XKX": "XKX"}
# Unknown geography is not automatically asserted to be an aggregate.
KNOWN_AGGREGATES = {"XW", "XM", "U2", "I8", "I9", "EA", "EU", "EA19", "EA20", "EA21",
                    "EU27_2020", "EU28", "WLD", "OECD", "G20", "G7", "_T", "ALL", "TOTAL"}


def geography(code: str | None, countries: dict | None = None) -> tuple[str | None, bool | None]:
    if not code:
        return None, None
    code = str(code).strip()
    if countries and code in countries:
        row = countries[code]
        return row.get("iso3"), row.get("is_aggregate")
    code = ALIASES.get(code, code)
    if code == "XKX":
        return "XKX", False
    item = pycountry.countries.get(**({"alpha_2": code} if len(code) == 2 else {"alpha_3": code}))
    if item:
        return item.alpha_3, False
    if code in KNOWN_AGGREGATES or re.fullmatch(r"(?:EA|EU)\d+.*", code):
        return None, True
    return None, None


def period_bounds(period: str, frequency: str = "") -> tuple[date, date, str]:
    """Parse dates explicitly; never broadcast annual values to four quarters."""
    p = str(period).strip()
    m = re.fullmatch(r"(\d{4})", p)
    if m:
        y = int(m[1]); return date(y, 1, 1), date(y, 12, 31), "A"
    m = re.fullmatch(r"(\d{4})-?Q([1-4])", p, re.I)
    if m:
        y, q = int(m[1]), int(m[2]); a, b = 3*q-2, 3*q
        return date(y, a, 1), date(y, b, calendar.monthrange(y, b)[1]), "Q"
    m = re.fullmatch(r"(\d{4})(?:-?M|-)(\d{2})", p)
    if m:
        y, mo = int(m[1]), int(m[2])
        return date(y, mo, 1), date(y, mo, calendar.monthrange(y, mo)[1]), "M"
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", p)
    if m:
        d = date(*map(int, m.groups()))
        return d, d, "D"
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})T\d{2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:\d{2})?", p)
    if m:
        d = date(*map(int, m.groups()))
        return d, d, "E"
    m = re.fullmatch(r"(\d{4})-?[HS]([12])", p)
    if m:
        y, h = int(m[1]), int(m[2]); a, b = 6*h-5, 6*h
        return date(y, a, 1), date(y, b, calendar.monthrange(y, b)[1]), "H"
    m = re.fullmatch(r"(\d{4})-?W(\d{2})", p)
    if m:
        return date.fromisocalendar(int(m[1]), int(m[2]), 1), date.fromisocalendar(int(m[1]), int(m[2]), 7), "W"
    raise ValueError(f"Unsupported native period {p!r} (declared frequency {frequency!r})")


def number(value: object) -> float | None:
    if value is None or str(value).strip() in {"", ":", "..", "...", "NA", "N/A", "nan", ".", "NaN", "null"}:
        return None
    try:
        n = float(str(value).replace(",", ""))
        return n if math.isfinite(n) else None
    except (ValueError, TypeError):
        return None


def reported_unit(label: str) -> str | None:
    """Read explicit unit wording; do not infer an economic definition from a code."""
    text = label or ""
    for pattern, unit in [
        (r"(?:percent(?:age)?|%)\s+of\s+(?:nominal\s+)?GDP", "Percent of GDP"),
        (r"(?:percent(?:age)?|%)\s+of\s+GNI", "Percent of GNI"),
        (r"(?:percent(?:age)?|%)\s+(?:annual\s+)?change", "Percent change"),
    ]:
        if re.search(pattern, text, re.I): return unit
    m = re.search(r"\(([^()]*)\)\s*$", text)
    if m and re.search(r"%|US\$|LCU|currency|index|years|persons|per\s", m[1], re.I):
        return m[1]
    if re.search(r"(?:national|domestic|local) currency\s*$", text, re.I): return "National currency"
    if re.search(r"(?:,|\()\s*(?:USD|US\$)\)?\s*$", text): return "USD"
    if re.search(r"(?:,|\()\s*(?:percent|percentage)\)?\s*$", text, re.I): return "Percent"
    return None


def observation(job: Job, raw: dict, *, period: str, value: object, dims: dict,
                indicator: str = "", label: str = "", ref_area: str = "",
                unit: str | None = None, multiplier: object = None, currency: str | None = None,
                status: str = "", forecast: bool | None = None, estimate: bool | None = None,
                publication_date: str | None = None, attrs: dict | None = None,
                source_updated: str | None = None, countries: dict | None = None) -> dict:
    start, end, freq = period_bounds(period, str(dims.get("FREQ", "")))
    iso, aggregate = geography(ref_area, countries)
    declared_freq = dims.get("FREQ", dims.get("freq"))
    # A daily date can be a weekly/monthly observation label: keep provider frequency.
    if declared_freq:
        freq = {"Y": "A", "S": "H"}.get(str(declared_freq), str(declared_freq))
    try:
        mult = int(multiplier) if multiplier is not None and str(multiplier).strip() else None
    except (TypeError, ValueError):
        mult = None
    return dict(source=job.source, dataset=job.dataset,
                series_id=digest([job.source, job.dataset, dims])[:32],
                ref_area=ref_area or None, country_iso3=iso, is_aggregate=aggregate,
                indicator=indicator or None, label=label or None, frequency=freq,
                period=str(period).strip(), period_start=start, period_end=end,
                value=number(value), unit=unit or None, unit_multiplier=mult,
                currency=currency or None, obs_status=status or None, is_forecast=forecast,
                is_estimate=estimate, publication_date=publication_date,
                dimensions=compact(dims), attributes=compact(attrs or {}),
                source_updated=source_updated or None, retrieved_at=raw["retrieved_at"],
                vintage_id=raw["snapshot_id"], raw_sha256=raw["sha256"], source_url=job.url)


def frame(rows: list[dict]) -> pl.DataFrame:
    return pl.DataFrame(rows, schema=SCHEMA, strict=False)
