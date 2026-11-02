"""World Bank's four-dimensional IDS JSON and native location dictionaries.

Parsing helpers deliberately have no dataframe dependency. Numerical research
coverage still requires successful acquisition and checked silver partitions.
"""
from __future__ import annotations

import csv
import io
import re
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit


def concept_key(value: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("World Bank concept must have a name")
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def native_id(value) -> str:
    # Numeric coercion would turn creditor 001 into 1 and destroy its identity.
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Native World Bank identifiers must be nonempty strings")
    return value.strip()


def page_info(obj: dict) -> tuple[int, int]:
    if not isinstance(obj, dict) or "message" in obj or "error" in obj:
        raise ValueError("World Bank returned an error, not an advanced data envelope")
    try:
        page, pages = int(obj.get("page", 1)), int(obj.get("pages", 1))
    except (ValueError, TypeError) as exc:
        raise ValueError("Invalid World Bank pagination") from exc
    if page < 1 or pages < 0 or (pages and page > pages):
        raise ValueError("Invalid World Bank page range")
    return page, pages


def later_pages(url: str, obj: dict) -> list[str]:
    page, pages = page_info(obj)
    if page != 1:
        return []
    parsed = urlsplit(url); query = parse_qs(parsed.query, keep_blank_values=True)
    result = []
    for number in range(2, pages + 1):
        query["page"] = [str(number)]
        result.append(urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query, doseq=True), parsed.fragment)))
    return result


def metadata_codes(obj: dict, concept: str) -> dict:
    """Parse the provider's source/concept/variable catalog, including lists."""
    page_info(obj)
    sources = obj.get("source")
    if isinstance(sources, dict):
        sources = [sources]
    if not isinstance(sources, list) or not sources:
        raise ValueError("Missing World Bank source catalog")
    wanted = concept_key(concept); found = False; result = {}
    for source in sources:
        if str(source.get("id")) != "6":
            raise ValueError("Expected IDS source 6")
        concepts = source.get("concept", [])
        if not isinstance(concepts, list):
            raise ValueError("Invalid concept catalog")
        for item in concepts:
            if concept_key(item.get("id", item.get("name", ""))) != wanted:
                continue
            found = True
            variables = item.get("variable")
            if not isinstance(variables, list):
                raise ValueError("Invalid variable catalog")
            for variable in variables:
                code = native_id(variable.get("id")); label = variable.get("value")
                if code in result and result[code] != label:
                    raise ValueError("Conflicting native World Bank code labels")
                result[code] = label
    if not found:
        raise ValueError(f"Missing IDS concept {concept}")
    return result


def data_records(obj: dict):
    """Read concepts by name, never by their ordering in a response."""
    page_info(obj)
    source = obj.get("source")
    if not isinstance(source, dict) or str(source.get("id")) != "6":
        raise ValueError("Expected an IDS source-6 data envelope")
    data = source.get("data")
    if data is None and str(obj.get("total")) == "0":
        data = []
    if not isinstance(data, list):
        raise ValueError("Missing IDS data list; an error is not an empty result")
    for record in data:
        variables = record.get("variable")
        if not isinstance(variables, list):
            raise ValueError("Missing IDS observation dimensions")
        dims = {}; labels = {}
        for variable in variables:
            key = concept_key(variable.get("concept"))
            if key in dims:
                raise ValueError("Repeated IDS concept within one observation")
            dims[key] = native_id(variable.get("id")); labels[key] = variable.get("value")
        required = {"country", "series", "time", "counterpart_area"}
        if not required.issubset(dims):
            raise ValueError("IDS observation is missing one of its four dimensions")
        match = re.fullmatch(r"(?:YR)?(\d{4})", dims["time"])
        if not match:
            raise ValueError("Expected native annual IDS time code")
        period = match[1]
        if labels.get("time") and str(labels["time"]) not in {period, "YR" + period}:
            raise ValueError("IDS time code and label disagree")
        if "value" not in record or isinstance(record["value"], bool):
            raise ValueError("Invalid IDS observation value")
        yield {"dimensions": dims, "labels": labels, "period": period,
               "value": record["value"],
               "attributes": {k: v for k, v in record.items() if k not in {"variable", "value"}}}


def reference_locations(raw: bytes, *, encoding="cp1252") -> dict:
    """Read the official tutorial snapshot without coercing either namespace.

    The published Git blob uses Windows-1252 and nonbreaking label padding.
    Keep raw labels, with an additional display label, and no inferred ISO map.
    """
    reader = csv.DictReader(io.StringIO(raw.decode(encoding)))
    if reader.fieldnames != ["locationName", "debtorCode", "creditorCode"]:
        raise ValueError("Unexpected official IDS location CSV columns")
    debtors = {}; creditors = {}; rows = []
    for row in reader:
        if None in row or not row["locationName"]:
            raise ValueError("Malformed IDS location row")
        row = {**row, "display_label": row["locationName"].strip()}
        for field, target in [("debtorCode", debtors), ("creditorCode", creditors)]:
            if row[field]:
                code = native_id(row[field])
                if code in target:
                    raise ValueError("Duplicate native code in IDS reference snapshot")
                target[code] = row
        rows.append(row)
    return {"rows": rows, "debtors": debtors, "creditors": creditors,
            "scope": "Official tutorial snapshot; not a freshly queried IDS catalog",
            "encoding": encoding, "country_mapping": "No name-based or numeric ISO inference"}


def select_indicators(catalog: dict, *, full=False) -> list[str]:
    """Select only identifiers actually present in a source-6 indicator catalog."""
    preferred = ["DT.DOD.BLAT.CD", "DT.DOD.MLAT.CD", "DT.DOD.DPPG.CD",
                 "DT.TDS.BLAT.CD", "DT.DIS.BLAT.CD", "DT.INT.BLAT.CD"]
    if full:
        preferred = sorted(code for code in catalog if re.fullmatch(
            r"DT\.(?:DOD|TDS|DIS|INT|AMT)\.(?:BLAT|MLAT|DPPG|PRVS|PBND|PCBK|PNFB)\.CD", code))
    return [code for code in preferred if code in catalog]
