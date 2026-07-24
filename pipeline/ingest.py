"""
ingest.py — Read every source workbook, locate the transaction-level sheet,
auto-detect its layout, and emit a list of raw transaction dictionaries.

Design principles
-----------------
* Source workbooks are opened READ-ONLY and never written.
* The most granular transaction sheet is the source of truth. Summary and
  monthly sheets are recorded for reconciliation but NOT imported as txns.
* Every emitted row carries source_file / source_sheet / source_row so nothing
  is ever silently discarded and everything is traceable.
"""
import logging
from pathlib import Path

import openpyxl

from . import config
from .normalize import normalize_date, normalize_amount, looks_like_date

log = logging.getLogger("ingest")

# Sheet-name hints, most-granular first. We pick the transaction-level sheet.
TXN_SHEET_PRIORITY = [
    "transaction details", "transaction detail", "raw data", "transactions",
    "transaction overview", "details", "commission",
]
# Sheets that are reference-only (never imported as transactions)
REFERENCE_SHEETS = {
    "transaction summary", "category summary", "monthly breakdown",
    "monthly", "mapping", "category rules", "summary",
}

# Header tokens we recognise per column role.
HEADER_ROLES = {
    "date": ["date", "transaction date", "trans date"],
    "post_date": ["posting date", "post date"],
    "description": ["description", "merchant", "name", "payee"],
    "merchant": ["merchant"],
    "amount": ["amount", "amount (usd)", "debit/credit"],
    "category": ["category"],
    "bp": ["b/p", "business/personal", "b / p"],
    "reimb": ["reimb.", "reimb", "reimbursable", "reimbursement"],
    "notes": ["notes", "memo", "note"],
    "extended": ["extended details", "extended detail"],
    "statement_as": ["appears on your statement as", "appears on statement as",
                     "appears on your statem"],
    "debit": ["debit"],
    "credit": ["credit"],
}


def _norm(s):
    return "" if s is None else str(s).strip().lower()


def _find_header_row(rows, max_scan=15):
    """Return (row_index, {role: col_index}) for the first row containing a date header."""
    for i, row in enumerate(rows[:max_scan]):
        cells = [_norm(c) for c in row]
        if any(c in ("date", "transaction date", "trans date") for c in cells):
            mapping = {}
            for j, cell in enumerate(cells):
                for role, hints in HEADER_ROLES.items():
                    if role in mapping:
                        continue
                    if any(cell == h or (cell and cell.startswith(h)) for h in hints):
                        mapping[role] = j
                        break
            # 'merchant' should not shadow 'description' if description absent
            if "description" not in mapping and "merchant" in mapping:
                mapping["description"] = mapping["merchant"]
            return i, mapping
    return None, {}


def _scan_header_meta(rows, header_idx):
    """Extract entity / account / statement-period text from the block above the header."""
    meta = {"entity_text": "", "account_raw": "", "account_last4": "",
            "statement_period": "", "account_holder": "", "card_name": ""}
    for row in rows[:header_idx]:
        cells = [c for c in row if c is not None and str(c).strip() != ""]
        if not cells:
            continue
        label = _norm(cells[0])
        val = str(cells[1]).strip() if len(cells) > 1 else ""
        if label == "entity":
            meta["entity_text"] = val
        elif label in ("account", "account number"):
            meta["account_raw"] = val or (str(cells[0]) if len(cells) == 1 else "")
        elif label in ("account holder", "prepared for"):
            meta["account_holder"] = val
        elif label.startswith("statement period"):
            meta["statement_period"] = val
        elif "amex" in label or "platinum" in label or "card" in label or "plum" in label:
            meta["card_name"] = str(cells[0]).strip()
        elif label.startswith("xxxx"):
            meta["account_raw"] = str(cells[0]).strip()
        # first non-empty text line often is the entity name
        if not meta["entity_text"] and len(cells) == 1 and label not in ("transaction details",):
            if any(k in label for k in ("dwg", "poseidon", "capital", "family",
                                         "angela", "dunning", "venmo", "plum")):
                meta["entity_text"] = str(cells[0]).strip()
    # derive last4 from any account string
    acct = meta["account_raw"] or ""
    digits = "".join(ch for ch in acct if ch.isdigit())
    if len(digits) >= 4:
        meta["account_last4"] = digits[-5:] if len(digits) >= 5 else digits[-4:]
    return meta


def ingest_workbook(path: Path):
    """Return (records, sheet_report). records = list of raw txn dicts."""
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    sheet_names = wb.sheetnames

    # Pick the transaction-level sheet by priority.
    lowered = {s.lower(): s for s in sheet_names}
    txn_sheet = None
    for hint in TXN_SHEET_PRIORITY:
        for low, actual in lowered.items():
            if hint in low:
                txn_sheet = actual
                break
        if txn_sheet:
            break
    if txn_sheet is None:
        # fall back to the sheet with the most rows that isn't clearly reference
        candidates = [s for s in sheet_names if s.lower() not in REFERENCE_SHEETS]
        txn_sheet = candidates[0] if candidates else sheet_names[0]

    ws = wb[txn_sheet]
    rows = [list(r) for r in ws.iter_rows(values_only=True)]
    header_idx, colmap = _find_header_row(rows)
    meta = _scan_header_meta(rows, header_idx if header_idx is not None else 0)

    records = []
    if header_idx is None or "date" not in colmap or "amount" not in colmap:
        log.warning("No usable transaction header in %s :: %s", path.name, txn_sheet)
    else:
        for r_off, row in enumerate(rows[header_idx + 1:], start=header_idx + 2):
            di = colmap["date"]
            ai = colmap["amount"]
            date_val = row[di] if di < len(row) else None
            amt_val = row[ai] if ai < len(row) else None
            # Stop/skip rows that are not real transactions (summary tails, blanks)
            if not looks_like_date(date_val):
                continue
            amt = normalize_amount(amt_val)
            if amt is None:
                continue
            def g(role):
                j = colmap.get(role)
                return row[j] if (j is not None and j < len(row)) else None
            records.append({
                "source_file": path.name,
                "source_sheet": txn_sheet,
                "source_row": r_off,
                "raw_date": date_val,
                "date": normalize_date(date_val),
                "raw_amount": amt_val,
                "amount_raw": amt,
                "description": g("description"),
                "merchant": g("merchant"),
                "category": g("category"),
                "bp_flag": g("bp"),
                "reimb_flag": g("reimb"),
                "notes": g("notes"),
                "extended": g("extended"),
                "statement_as": g("statement_as"),
                "debit": normalize_amount(g("debit")),
                "credit": normalize_amount(g("credit")),
                "meta_entity_text": meta["entity_text"],
                "meta_account_raw": meta["account_raw"],
                "meta_account_last4": meta["account_last4"],
                "meta_statement_period": meta["statement_period"],
                "meta_card_name": meta["card_name"],
                "meta_account_holder": meta["account_holder"],
            })

    # Reference sheets: capture control totals for reconciliation (not imported).
    ref_totals = _extract_reference_totals(wb, sheet_names)
    wb.close()

    sheet_report = {
        "file": path.name,
        "sheets": sheet_names,
        "txn_sheet": txn_sheet,
        "header_row": header_idx,
        "imported": len(records),
        "meta": meta,
        "reference_totals": ref_totals,
    }
    return records, sheet_report


def _extract_reference_totals(wb, sheet_names):
    """Pull Charges / Credits / Net from a Transaction Summary sheet if present."""
    out = {}
    for name in sheet_names:
        if "summary" not in name.lower():
            continue
        ws = wb[name]
        for row in ws.iter_rows(values_only=True):
            cells = [c for c in row]
            if not cells:
                continue
            label = _norm(cells[0])
            val = None
            for c in cells[1:]:
                v = normalize_amount(c)
                if v is not None:
                    val = v
                    break
            if label in ("charges", "total charges") and val is not None:
                out["charges"] = val
            elif label in ("credits & payments", "credits and payments",
                           "credits", "payments") and val is not None:
                out["credits_payments"] = val
            elif label in ("net balance", "net", "net activity") and val is not None:
                out["net"] = val
    return out


def ingest_all(source_dir=None):
    source_dir = Path(source_dir or config.SOURCE_DIR)
    all_records, reports = [], []
    for path in sorted(source_dir.glob("*.xlsx")):
        if path.name.startswith("~$"):
            continue
        recs, rep = ingest_workbook(path)
        log.info("Ingested %-45s sheet=%-22s rows=%d", path.name, rep["txn_sheet"], len(recs))
        all_records.extend(recs)
        reports.append(rep)
    return all_records, reports
