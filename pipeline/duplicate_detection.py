"""
duplicate_detection.py — Deterministic duplicate flagging.

A duplicate GROUP is a set of master rows sharing the same fingerprint on:
    (source_entity, account_last4, transaction_date, rounded amount,
     normalized merchant)
across DIFFERENT source files/rows (overlapping exports).

We NEVER delete. The first occurrence (by source file name, then row) keeps
disposition 'Primary'; the rest are marked 'Duplicate — excluded from totals'.
Rows flagged as duplicates are excluded from financial rollups but retained in
the master table with a Duplicate Group ID for full traceability.
"""
from collections import defaultdict

from .normalize import fingerprint


def _dup_key(row):
    return fingerprint(
        row["source_entity"],
        row["account_last4"],
        row["transaction_date"],
        f'{row["amount_raw"]:.2f}',
        row["merchant_normalized"],
    )


def detect_duplicates(master):
    groups = defaultdict(list)
    for row in master:
        groups[_dup_key(row)].append(row)

    dup_group_seq = 0
    for key, rows in groups.items():
        if len(rows) < 2:
            continue
        # Are they actually from different source files/rows? (true overlap)
        distinct_sources = {(r["source_file"], r["source_row"]) for r in rows}
        if len(distinct_sources) < 2:
            continue
        dup_group_seq += 1
        gid = f"DUP-{dup_group_seq:04d}"
        ordered = sorted(rows, key=lambda r: (r["source_file"], r["source_row"]))
        for i, r in enumerate(ordered):
            r["duplicate_group_id"] = gid
            if i == 0:
                r["potential_duplicate"] = "Primary"
            else:
                r["potential_duplicate"] = "Duplicate"
                r["review_status"] = "Duplicate-Excluded"
                if "Duplicate" not in (r["review_reason"] or ""):
                    r["review_reason"] = (r["review_reason"] + "; " if r["review_reason"]
                                          else "") + "Duplicate of " + gid
    return dup_group_seq


def is_excluded_duplicate(row):
    return row.get("potential_duplicate") == "Duplicate"
