"""
normalize.py — Date, sign, merchant, and description normalization helpers.

Sign convention (canonical across the whole pipeline):
    cash_outflow  -> stored as a POSITIVE expense magnitude in `amount`,
                     cash_out column populated.
    cash_inflow   -> populated in cash_in column.

Source workbooks are American-Express-style: a POSITIVE amount is a charge
(money leaving the business / an expense), a NEGATIVE amount is a payment or
credit (money returning). We preserve the raw amount and derive direction.
"""
import re
import hashlib
from datetime import datetime, date

import pandas as pd


# ---------------------------------------------------------------------------
# Dates
# ---------------------------------------------------------------------------
def normalize_date(value):
    """Return a datetime.date or None. Handles Excel serials, datetimes, strings."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)):
        # Excel serial date (1900 system). Guard against amounts mis-fed here.
        try:
            if 20000 < float(value) < 80000:
                return (pd.Timestamp("1899-12-30") + pd.to_timedelta(int(value), "D")).date()
        except Exception:
            return None
        return None
    s = str(value).strip()
    if not s:
        return None
    for fmt in ("%m/%d/%Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%m/%d/%y",
                "%m-%d-%Y", "%B %d, %Y", "%b %d, %Y", "%m/%d/%Y %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    try:
        ts = pd.to_datetime(s, errors="coerce")
        return None if pd.isna(ts) else ts.date()
    except Exception:
        return None


def looks_like_date(value):
    return normalize_date(value) is not None


# ---------------------------------------------------------------------------
# Amounts
# ---------------------------------------------------------------------------
def normalize_amount(value):
    """Parse a currency-ish value to float. Returns None if not numeric."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        f = float(value)
        return None if pd.isna(f) else f
    s = str(value).strip()
    if not s:
        return None
    neg = False
    if s.startswith("(") and s.endswith(")"):
        neg = True
        s = s[1:-1]
    s = s.replace("$", "").replace(",", "").replace("USD", "").strip()
    if s in ("-", "--", ""):
        return None
    try:
        f = float(s)
        return -f if neg else f
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Merchant / description normalization
# ---------------------------------------------------------------------------
_WS = re.compile(r"\s+")
_TRAILING_REF = re.compile(r"\b[A-Z0-9]{6,}\b")   # long ref tokens
_NONALNUM = re.compile(r"[^A-Za-z0-9&' ]+")


def normalize_description(value):
    if value is None:
        return ""
    return _WS.sub(" ", str(value).strip())


def normalize_merchant(value):
    """
    Collapse an Amex merchant/description into a stable, comparable token.
    e.g. 'ANTHROPIC           SA'   -> 'ANTHROPIC'
         'AMAZON MARKEPLACE NA P'   -> 'AMAZON MARKEPLACE NA P' -> 'AMAZON'
    We keep it deterministic: uppercase, strip trailing state/ref noise,
    collapse whitespace, drop long alphanumeric reference codes.
    """
    if value is None:
        return ""
    s = str(value).upper().strip()
    s = _WS.sub(" ", s)
    # Drop obvious trailing reference codes (transaction ids etc.)
    tokens = s.split(" ")
    kept = [t for t in tokens if not (len(t) >= 8 and any(c.isdigit() for c in t)
                                      and any(c.isalpha() for c in t))]
    s = " ".join(kept) if kept else s
    s = _NONALNUM.sub(" ", s)
    s = _WS.sub(" ", s).strip()
    # Collapse well-known multi-word merchants to a canonical head token set
    canon = {
        "AMAZON MARKEPLACE NA P": "AMAZON", "AMAZON MARKETPLACE": "AMAZON",
        "AMAZON MKTPL": "AMAZON", "AMZN MKTP": "AMAZON",
    }
    for k, v in canon.items():
        if s.startswith(k):
            return v
    # Keep first up-to-4 meaningful tokens
    return " ".join(s.split(" ")[:4]).strip()


def fingerprint(*parts):
    """Deterministic SHA1 fingerprint for duplicate detection / transaction ids."""
    raw = "|".join("" if p is None else str(p) for p in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def month_key(d):
    return None if d is None else f"{d.year:04d}-{d.month:02d}"
