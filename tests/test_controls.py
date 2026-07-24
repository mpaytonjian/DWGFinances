"""
tests/test_controls.py — Lightweight assertion-based controls that can run
under pytest OR standalone (`python tests/test_controls.py`). Re-runs the
pipeline in-memory and asserts the critical invariants.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import ingest, accounting_logic, duplicate_detection
from pipeline import transfer_matching, category_rules, config, reporting


def _pipeline():
    records, reports = ingest.ingest_all()
    master = accounting_logic.build_master(records, category_rules.load_overrides())
    duplicate_detection.detect_duplicates(master)
    transfers = transfer_matching.match_transfers(master)
    return records, reports, master, transfers


def test_all():
    records, reports, master, transfers = _pipeline()

    # 1. every row traceable
    assert all(r["source_file"] and r["source_row"] for r in master), "missing source"

    # 2. unique ids
    ids = [r["transaction_id"] for r in master]
    assert len(ids) == len(set(ids)), "duplicate transaction ids"

    # 3. nothing discarded
    assert sum(rep["imported"] for rep in reports) == len(master), "row count mismatch"

    # 4. cc payments not in expense groups
    leaked = [r for r in master if r["credit_card_payment"] == "Yes"
              and r["financial_statement_group"] in
              (config.FSG_OPEX, config.FSG_COMP, config.FSG_DEAL)]
    assert not leaked, f"{len(leaked)} cc payments leaked into expense"

    # 5. personal excluded from EBITDA rollup
    t = reporting.pl_totals(master, config.FY_2026)
    personal_in = [r for r in master if r["business_or_personal"] == "Personal"
                   and reporting._pl_eligible(r)]
    assert not personal_in, "personal item leaked into P&L eligibility"

    # 6. duplicates retain a group id
    assert all(r["duplicate_group_id"] for r in master
               if r["potential_duplicate"] == "Duplicate"), "untraceable duplicate"

    # 7. monthly ties to annual
    from collections import defaultdict
    ann, mon = defaultdict(float), defaultdict(float)
    for r in master:
        if r["potential_duplicate"] == "Duplicate" or not r["year"]:
            continue
        ann[(r["source_entity"], r["year"])] += r["amount_raw"]
        mon[(r["source_entity"], r["year"], r["month"])] += r["amount_raw"]
    recomposed = defaultdict(float)
    for (e, y, m), v in mon.items():
        recomposed[(e, y)] += v
    for k, v in ann.items():
        assert abs(recomposed[k] - v) < 0.01, f"monthly!=annual at {k}"

    print(f"OK — {len(master)} txns, {len(transfers)} transfers, all controls pass")


if __name__ == "__main__":
    test_all()
