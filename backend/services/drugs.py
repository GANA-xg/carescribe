"""Drug price / generic lookup — CDSCO + Jan Aushadhi CSV. OC-09.

CSV loaded once at import; fuzzy match via difflib on both brand and
generic names (case-insensitive). Prices are per-unit INR.
"""
import csv
import os
from difflib import SequenceMatcher, get_close_matches

from pydantic import BaseModel, Field

CSV_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "drugs.csv")

_rows: list[dict] = []
_lookup: dict[str, dict] = {}

FUZZY_THRESHOLD = 0.72


def load_csv() -> list[dict]:
    """Parse drugs.csv (brand, generic, brand price, JA price)."""
    global _rows, _lookup
    _rows = []
    _lookup = {}
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            entry = {
                "brand_name": row["brand_name"].strip(),
                "generic_name": row["generic_name"].strip(),
                "brand_price": float(row["brand_price"]),
                "generic_name_price": float(row["jaan_aushadhi_price"]),
                "formulation": row["formulation"].strip(),
            }
            _rows.append(entry)
            _lookup[entry["brand_name"].lower()] = entry
    return _rows


def _norm(s: str) -> str:
    return s.strip().lower()


def match_drug(name: str) -> dict | None:
    """Find the best CSV row for a drug name (exact, then fuzzy)."""
    if not _rows:
        load_csv()
    key = _norm(name)
    if key in _lookup:
        return _lookup[key]

    # exact generic-name match
    for row in _rows:
        if _norm(row["generic_name"]) == key:
            return row

    # fuzzy: try brand names first, then generic names
    candidates = [r["brand_name"] for r in _rows] + [r["generic_name"] for r in _rows]
    close = get_close_matches(name, candidates, n=1, cutoff=FUZZY_THRESHOLD)
    if close:
        target = _norm(close[0])
        for row in _rows:
            if target in (_norm(row["brand_name"]), _norm(row["generic_name"])):
                return row
    return None


def compare(drug_names: list[str]) -> list[dict]:
    """Compare brand vs generic for each name -> savings info."""
    out = []
    for name in drug_names:
        row = match_drug(name)
        if row is None:
            out.append({"name": name, "found": False})
            continue
        saving = round(row["brand_price"] - row["generic_name_price"], 2)
        out.append(
            {
                "name": name,
                "found": True,
                "brand_name": row["brand_name"],
                "brand_price": row["brand_price"],
                "generic_name": row["generic_name"],
                "generic_price": row["generic_name_price"],
                "saving": saving,
                "saving_pct": round(100 * saving / row["brand_price"], 1) if row["brand_price"] else 0,
                "formulation": row["formulation"],
            }
        )
    return out


def generics_for(drug_name: str) -> list[dict]:
    """All generic alternatives containing the same molecule."""
    row = match_drug(drug_name)
    if row is None:
        return []
    molecule = _norm(row["generic_name"])
    seen = set()
    matches = []
    for r in _rows:
        if _norm(r["generic_name"]) == molecule:
            key = (r["generic_name"], r["generic_name_price"], r["formulation"])
            if key not in seen:
                seen.add(key)
                matches.append(
                    {
                        "generic_name": r["generic_name"],
                        "price": r["generic_name_price"],
                        "formulation": r["formulation"],
                        "brand_name": r["brand_name"],
                    }
                )
    return matches


# Load on import (startup rule from the task spec).
load_csv()
