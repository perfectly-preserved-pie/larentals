from __future__ import annotations
from typing import Optional
import json
import re
import sqlite3

# This normalizes lease terms into canonical codes so we don't get redundant terms for the same thing
TERM_SYNONYMS: dict[str, str] = {
    # -----------------
    # Month-to-month
    # -----------------
    "MO": "MO",
    "M2M": "MO",
    "MONTH TO MONTH": "MO",
    "MONTH TO MONTH LEASE": "MO",
    "MONTHLY": "MO",

    # -----------------
    # Daily / Weekly
    # -----------------
    "DL": "DL",
    "DAILY": "DL",
    "DAY TO DAY": "DL",
    "DAY-TO-DAY": "DL",

    "WK": "WK",
    "WEEKLY": "WK",
    "WEEK TO WEEK": "WK",
    "WEEK-TO-WEEK": "WK",

    # -----------------
    # 6 months
    # -----------------
    "6M": "6M",
    "6 MONTH": "6M",
    "6 MONTHS": "6M",
    "SIX MONTH": "6M",
    "SIX MONTHS": "6M",

    # -----------------
    # 12 months / 1 year
    # -----------------
    "12M": "12M",
    "12 MONTH": "12M",
    "12 MONTHS": "12M",
    "1 YEAR": "12M",
    "ONE YEAR": "12M",
    "ANNUAL": "12M",
    "YEARLY": "12M",

    # -----------------
    # 24 months / 2 year
    # -----------------
    "24M": "24M",
    "24 MONTH": "24M",
    "24 MONTHS": "24M",
    "2 YEAR": "24M",
    "TWO YEAR": "24M",

    # -----------------
    # Short term
    # -----------------
    "STL": "STL",
    "SHORT TERM": "STL",
    "SHORT TERM LEASE": "STL",
    "SHORT-TERM": "STL",

    # -----------------
    # Seasonal / vacation
    # -----------------
    "SN": "SN",
    "SEASON": "SN",
    "SEASONAL": "SN",

    "VR": "VR",
    "VACATION": "VR",
    "VACATION RENTAL": "VR",

    # -----------------
    # Negotiable
    # -----------------
    "NG": "NG",
    "NEGOTIABLE": "NG",

    # -----------------
    # Special conditions
    # -----------------
    "RO": "RO",
    "RENEWAL OPTIONS": "RO",

    "DR": "DR",
    "DEPOSIT REQUIRED": "DR",

    # -----------------
    # Other / unknown
    # -----------------
    "OTHER": "Other",
    "NONE": "Unknown",
    "N/A": "Unknown",
    "NA": "Unknown",
    "UNKNOWN": "Unknown",
    "": "Unknown",
}

CANONICAL_ORDER: list[str] = [
    "DL",
    "WK",
    "MO",
    "6M",
    "12M",
    "24M",
    "STL",
    "SN",
    "VR",
    "NG",
    "RO",
    "DR",
    "Other",
    "Unknown",
]

def normalize_token(token: str) -> str:
    """
    Normalize a single rental term token for dictionary lookup.

    This is designed to collapse common punctuation variants like:
      - "1-Year" -> "1 YEAR"
      - "1+Year" -> "1 YEAR"
      - "Month-to-Month" -> "MONTH TO MONTH"
    """
    return (
        token.upper()
        .replace("–", "-")
        .replace("—", "-")
        .replace("+", " ")
        .replace("-", " ")
        .strip()
    )


def _tokenize_terms(raw: str) -> list[str]:
    """
    Split raw terms string into tokens.

    Handles commas, semicolons, slashes, pipes, and repeated whitespace.
    Does not upper-case here; normalization happens in normalize_token().
    """
    parts = re.split(r"[,\;/|]+", raw)
    tokens: list[str] = []
    for p in parts:
        t = re.sub(r"\s+", " ", p.strip())
        if t:
            tokens.append(t)
    return tokens


def normalize_terms(raw: Optional[str]) -> list[str]:
    """
    Normalize a raw lease terms field into canonical codes.

    Returns a deduped list ordered by CANONICAL_ORDER.
    Unknown / empty / NULL -> ["Unknown"].
    """
    if raw is None:
        return ["Unknown"]

    raw_str = str(raw).strip()
    if not raw_str:
        return ["Unknown"]

    tokens = _tokenize_terms(raw_str)

    canon: list[str] = []
    for token in tokens:
        key = normalize_token(token)
        mapped = TERM_SYNONYMS.get(key)
        if mapped is None:
            continue
        canon.append(mapped)

    if not canon:
        canon = ["Unknown"]

    canon_set = set(canon)
    ordered = [c for c in CANONICAL_ORDER if c in canon_set]
    extras = sorted(canon_set.difference(CANONICAL_ORDER))
    return ordered + extras


def backfill_lease_terms(db_path: str) -> None:
    """
    Backfill lease.terms and lease.terms_norm with canonical values.

    - lease.terms: a comma-joined canonical string (for simple filtering / display)
    - lease.terms_norm: JSON list of canonical codes (structured)
    """
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT rowid, terms FROM lease")
        rows = cur.fetchall()

        updates: list[tuple[str, str, int]] = []
        for rowid, terms in rows:
            canon_list = normalize_terms(terms)
            canon_string = ", ".join(canon_list) if canon_list != ["Unknown"] else ""
            canon_json = json.dumps(canon_list, separators=(",", ":"))

            updates.append((canon_string, canon_json, rowid))

        cur.executemany(
            "UPDATE lease SET terms = ?, terms_norm = ? WHERE rowid = ?",
            updates,
        )
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    backfill_lease_terms("/assets/datasets/larentals.db")