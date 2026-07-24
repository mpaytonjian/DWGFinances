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

# Sheet-name hints, most-granular first. We pick the transaction-level sheet(s).
TXN_SHEET_PRIORITY = [
    "transaction details", "transaction detail", "raw data", "transactions",
    "transaction overview", "details", "commission",
]
# Sheets that are reference-only (never imported as transactions).
# Transfer/Wire/Commission tabs are SUBSETS of Transaction Overview in the
# bank workbooks — importing them as transactions would double-count.
REFERENCE_SHEETS = {
    "transaction summary", "category summary", "monthly breakdown",
    "monthly", "monthly detail", "mapping", "category rules", "summary",
    "transfer in", "transfer out", "wire in", "wire out", "commission",
    "transfers",
}

# Header tokens we recognise per column role.
HEADER_ROLES = {
    "date": ["date", "transaction date", "trans date", "posting date"],
    "post_date": ["posting date", "post date"],
    "description": ["description", "merchant / description", "merchant", "name",
                    "payee"],
    "merchant": ["merchant"],
    "amount": ["amount", "amount (usd)", "debit/credit"],
    "category": ["category", "categories"],
    "bp": ["b/p", "business/personal", "b / p"],
    "reimb": ["reimb.", "reimb", "reimbursable", "reimbursement"],
    "notes": ["notes", "memo", "note"],
    "extended": ["extended details", "extended detail"],
    "statement_as": ["appears on your statement as", "appears on statement as",
                     "appears on your statem"],
    "debit": ["debit"],
    "credit": ["credit"],
    # bank-export columns (Chase style)
    "dc_flag": ["details"],       # DEBIT / CREDIT / DSLIP indicator
    "bank_type": ["type"],        # ACH_DEBIT, WIRE_OUTGOING, ...
    "balance": ["balance"],
    "card_member": ["card member"],
    "acct_col": ["account #", "account#"],
}


def _norm(s):
    return "" if s is None else str(s).strip().lower()


def _find_header_row(rows, max_scan=15):
    """Return (row_index, {role: col_index}) for the first row containing a date header."""
    for i, row in enumerate(rows[:max_scan]):
        cells = [_norm(c) for c in row]
        if any(c in ("date", "transaction date", "trans date", "posting date")
               for c in cells):
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


def _scan_summary_meta(wb, sheet_names):
    """Scan a Summary sheet for identity fields (account, entity, holder, period)."""
    meta = {"entity_text": "", "account_raw": "", "account_last4": "",
            "statement_period": "", "card_name": "", "account_holder": ""}
    for name in sheet_names:
        if "summary" not in name.lower():
            continue
        ws = wb[name]
        block = [list(r) for r in ws.iter_rows(values_only=True)][:12]
        m = _scan_header_meta(block, len(block))
        for k, v in m.items():
            if v and not meta.get(k):
                meta[k] = v
        # Title rows: card name / entity often on the first two lines
        for r in block[:3]:
            cells = [c for c in r if c is not None and str(c).strip()]
            if cells:
                low = str(cells[0]).lower()
                if not meta["card_name"] and ("amex" in low or "plum" in low
                                              or "platinum" in low or "express" in low):
                    meta["card_name"] = str(cells[0]).strip()
                if not meta["entity_text"] and any(k in low for k in
                        ("dwg", "poseidon", "capital", "plum card", "family")):
                    meta["entity_text"] = str(cells[0]).strip()
        break
    return meta


def _select_txn_sheets(sheet_names):
    """
    Return the list of transaction-level sheets to import for a workbook.

    Rules (prevent double-counting the same data twice inside one file):
      1. All 'Transaction Details*' sheets (multi-year files carry one per year).
      2. Else 'Transaction Overview' (bank workbooks). The trailing raw
         account-activity sheet (e.g. 'Chase1168_2025', '2025_DWG_Activity',
         'Angela_2026_Chase1117_Activity') is the SAME data re-exported and is
         skipped whenever an Overview/Details sheet exists.
      3. Else 'Raw Data'; else any non-reference sheet.
    """
    low = {s: s.lower() for s in sheet_names}
    details = [s for s in sheet_names if "transaction detail" in low[s]]
    if details:
        return details
    overview = [s for s in sheet_names if "transaction overview" in low[s]]
    if overview:
        return overview
    raw = [s for s in sheet_names if "raw data" in low[s]]
    if raw:
        return raw
    rest = [s for s in sheet_names if low[s] not in REFERENCE_SHEETS]
    return rest[:1] if rest else sheet_names[:1]


def _detect_sign_convention(records_amounts, colmap):
    """
    Return 'bank' if negative amounts represent outflows (Chase exports),
    'amex' if positive amounts represent charges (Amex exports).

    Deterministic rules, in order:
      * a Details DEBIT/CREDIT indicator column exists -> 'bank'
      * a running Balance column exists                -> 'bank'
      * majority of nonzero amounts are negative       -> 'bank'
      * otherwise                                      -> 'amex'
    """
    if "dc_flag" in colmap or "balance" in colmap:
        return "bank"
    nz = [a for a in records_amounts if a]
    if nz and sum(1 for a in nz if a < 0) > len(nz) * 0.6:
        return "bank"
    return "amex"


def ingest_workbook(path: Path):
    """Return (records, sheet_report). records = list of raw txn dicts."""
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    sheet_names = wb.sheetnames
    txn_sheets = _select_txn_sheets(sheet_names)
    summ_meta = _scan_summary_meta(wb, sheet_names)

    records = []
    per_sheet = []
    for txn_sheet in txn_sheets:
        ws = wb[txn_sheet]
        rows = [list(r) for r in ws.iter_rows(values_only=True)]
        header_idx, colmap = _find_header_row(rows)
        meta = _scan_header_meta(rows, header_idx if header_idx is not None else 0)
        # Backfill identity fields from the Summary sheet when the details block
        # doesn't carry them.
        for k in ("entity_text", "account_raw", "account_last4",
                  "statement_period", "card_name", "account_holder"):
            if not meta.get(k) and summ_meta.get(k):
                meta[k] = summ_meta[k]

        if header_idx is None or "date" not in colmap or "amount" not in colmap:
            log.warning("No usable transaction header in %s :: %s",
                        path.name, txn_sheet)
            per_sheet.append({"sheet": txn_sheet, "imported": 0,
                              "sign_convention": "n/a"})
            continue

        # First pass: collect raw amounts to detect the sign convention.
        raw_amts = []
        for row in rows[header_idx + 1:]:
            ai = colmap["amount"]
            di = colmap["date"]
            if di < len(row) and looks_like_date(row[di]) and ai < len(row):
                a = normalize_amount(row[ai])
                if a is not None:
                    raw_amts.append(a)
        convention = _detect_sign_convention(raw_amts, colmap)

        n_before = len(records)
        for r_off, row in enumerate(rows[header_idx + 1:], start=header_idx + 2):
            di = colmap["date"]
            ai = colmap["amount"]
            date_val = row[di] if di < len(row) else None
            amt_val = row[ai] if ai < len(row) else None
            # Skip rows that are not real transactions (summary tails, blanks)
            if not looks_like_date(date_val):
                continue
            amt = normalize_amount(amt_val)
            if amt is None:
                continue

            def g(role):
                j = colmap.get(role)
                return row[j] if (j is not None and j < len(row)) else None

            # Canonical sign: positive = charge / cash outflow.
            dc = str(g("dc_flag") or "").strip().upper()
            if convention == "bank":
                if dc.startswith("DEBIT"):
                    amt_canon = abs(amt)
                elif dc.startswith(("CREDIT", "DSLIP")):
                    amt_canon = -abs(amt)
                else:
                    amt_canon = -amt   # negative bank amount -> positive outflow
            else:
                amt_canon = amt

            # Per-row account (Family Amex carries Card Member / Account # cols)
            row_acct = str(g("acct_col") or "").strip()
            acct_last = meta["account_last4"]
            if row_acct:
                digits = "".join(ch for ch in row_acct if ch.isdigit())
                if len(digits) >= 4:
                    acct_last = digits[-5:]

            records.append({
                "source_file": path.name,
                "source_sheet": txn_sheet,
                "source_row": r_off,
                "raw_date": date_val,
                "date": normalize_date(date_val),
                "raw_amount": amt_val,
                "amount_raw": amt_canon,
                "sign_convention": convention,
                "bank_type": g("bank_type"),
                "dc_flag": dc,
                "card_member": g("card_member"),
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
                "meta_account_last4": acct_last,
                "meta_statement_period": meta["statement_period"],
                "meta_card_name": meta["card_name"],
                "meta_account_holder": meta["account_holder"],
            })
        per_sheet.append({"sheet": txn_sheet, "imported": len(records) - n_before,
                          "sign_convention": convention})

    ref_totals = _extract_reference_totals(wb, sheet_names)
    wb.close()

    sheet_report = {
        "file": path.name,
        "sheets": sheet_names,
        "txn_sheet": ", ".join(txn_sheets),
        "per_sheet": per_sheet,
        "imported": len(records),
        "meta": summ_meta if not records else {
            "entity_text": records[0]["meta_entity_text"],
            "account_raw": records[0]["meta_account_raw"],
            "account_last4": records[0]["meta_account_last4"],
            "statement_period": records[0]["meta_statement_period"],
            "card_name": records[0]["meta_card_name"],
            "account_holder": records[0]["meta_account_holder"],
        },
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
