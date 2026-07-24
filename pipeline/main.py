"""
main.py — Orchestrate the full DWG Financial Overview pipeline.

Run:  python -m pipeline.main
Outputs land in DWG_Financial_Overview_2025_2026/ plus mappings/.
Source workbooks are never modified (verified by SHA-256 before/after).
"""
import csv
import hashlib
import json
import logging
import sys
from pathlib import Path

from . import config
from . import ingest
from . import accounting_logic
from . import duplicate_detection
from . import transfer_matching
from . import controls as controls_mod
from . import reporting
from . import adjusting
from . import category_rules
from . import workbook_output

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s %(name)-10s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout),
              logging.FileHandler(config.LOG_DIR / "pipeline.log", mode="w")],
)
log = logging.getLogger("main")


def _hash_sources():
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(config.SOURCE_DIR.glob("*.xlsx"))}


def run():
    log.info("=== DWG Financial Overview pipeline start ===")
    src_hashes_before = _hash_sources()

    # 1. Ingest
    records, reports = ingest.ingest_all()
    log.info("Ingested %d transaction rows from %d files", len(records), len(reports))

    # 2. Classify -> master
    overrides = category_rules.load_overrides()
    master = accounting_logic.build_master(records, overrides)

    # 3. Duplicate detection
    ndup = duplicate_detection.detect_duplicates(master)
    log.info("Duplicate groups: %d", ndup)

    # 4. Transfer matching
    transfers = transfer_matching.match_transfers(master)
    log.info("Transfer candidates: %d", len(transfers))

    # 5. Adjusting entries + missing items
    adj = adjusting.build_adjusting_entries(master, transfers)
    missing = adjusting.MISSING_ITEMS

    # 6. Controls
    control_results = controls_mod.run_controls(master, records, reports, transfers)
    critical_fail = [c for c in control_results if c["critical"] and not c["passed"]]
    for c in control_results:
        log.info("CONTROL [%s] %s — %s",
                 "PASS" if c["passed"] else "FAIL", c["control"], c["detail"])

    # 7. Verify sources unmodified
    src_hashes_after = _hash_sources()
    if src_hashes_before != src_hashes_after:
        critical_fail.append({"control": "Source workbooks unmodified",
                              "detail": "hash changed!"})
        log.error("SOURCE FILES CHANGED — aborting")

    if critical_fail:
        _write_control_failure(control_results, critical_fail)
        log.error("CRITICAL CONTROL FAILURE — final workbook NOT written. See control_failure_report.txt")
        return {"status": "control_failure", "controls": control_results}

    # 8. Outputs
    out = config.OUTPUT_DIR
    workbook_output.build_workbook(out / config.WORKBOOK_NAME, master, reports,
                                   transfers, control_results, adj, missing)
    log.info("Workbook written: %s", out / config.WORKBOOK_NAME)

    _write_master_csv(master, out / "master_transactions.csv")
    _write_review_csv(master, out / "review_items.csv")
    _write_adjusting_csv(adj, out / "adjusting_entries.csv")
    _write_source_recon_csv(master, reports, out / "source_reconciliation.csv")
    _write_executive_md(master, transfers, control_results, out / "executive_summary.md")
    _write_methodology_md(out / "methodology.md")
    _write_config_readme(out / "config_thresholds.md")
    _seed_override_file()

    # persist a machine-readable run summary
    (out / "run_summary.json").write_text(json.dumps({
        "files": len(reports), "transactions": len(master),
        "duplicate_groups": ndup, "transfers": len(transfers),
        "controls_passed": sum(1 for c in control_results if c["passed"]),
        "controls_total": len(control_results),
    }, indent=2))

    log.info("=== pipeline complete ===")
    return {"status": "ok", "master": master, "transfers": transfers,
            "controls": control_results, "adjusting": adj, "reports": reports}


# ---------------------------------------------------------------------------
# CSV / MD writers
# ---------------------------------------------------------------------------
def _write_master_csv(master, path):
    cols = [k for k, _, _ in workbook_output.MASTER_COLUMNS]
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in master:
            w.writerow({c: r.get(c, "") for c in cols})


def _write_review_csv(master, path):
    rows = reporting.review_items(master)
    cols = ["transaction_date", "source_file", "source_entity", "description_raw",
            "amount_raw", "original_category", "combined_category",
            "proposed_reporting_entity", "review_reason",
            "proposed_accounting_treatment", "confidence_score"]
    headers = ["transaction_date", "source", "entity", "description", "amount",
               "current_category", "proposed_category", "proposed_entity",
               "review_reason", "suggested_decision", "confidence_score"]
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(headers)
        for r in rows:
            w.writerow([r.get(c, "") for c in cols])


def _write_adjusting_csv(adj, path):
    cols = ["entry_id", "entry_date", "entity", "debit_account", "credit_account",
            "amount", "explanation", "source_transaction_ids", "support_status",
            "approval_status"]
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for e in adj:
            w.writerow(e)


def _write_source_recon_csv(master, reports, path):
    recon = reporting.source_reconciliation(master, reports)
    cols = ["file", "entity", "account", "period", "imported", "gross_inflows",
            "gross_outflows", "net", "duplicates", "transfers", "cc_payments",
            "personal", "review", "control_total", "reconciled"]
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for x in recon:
            w.writerow(x)


def _money(v):
    v = round(v, 2)
    return f"(${abs(v):,.2f})" if v < 0 else f"${v:,.2f}"


def _write_executive_md(master, transfers, controls_results, path):
    DWG = config.DWG_OPERATING_ENTITIES
    POS = [config.ENTITY_POS_PARTNERS, config.ENTITY_POS_ASSET]
    t25 = reporting.pl_totals(master, config.FY_2025, DWG)
    t26 = reporting.pl_totals(master, config.FY_2026, DWG)
    p25 = reporting.pl_totals(master, config.FY_2025, POS)
    p26 = reporting.pl_totals(master, config.FY_2026, POS)
    m25 = reporting.monthly_pl(master, config.FY_2025, DWG)
    m26 = reporting.monthly_pl(master, config.FY_2026, DWG)
    burn26 = (sum(v["expense"] for v in m26.values()) / len(m26)) if m26 else 0
    payroll = sum(reporting.pl_summary(master, entities=DWG).get(config.FSG_COMP, {}).values())
    pers = reporting.personal_paid_by_business(master)
    bp = reporting.business_paid_personally(master)
    reviews = reporting.review_items(master)
    top_reviews = reviews[:20]
    top_cat = reporting.top_categories(master, n=10)
    top_vend = reporting.top_vendors(master, n=10)
    top_deal = reporting.top_deals(master, n=10)
    unmatched = [t for t in transfers if t["status"].startswith("Unmatched")]
    files = sorted({r["source_file"] for r in master})

    L = []
    L.append("# DWG — Preliminary Management Financial Overview")
    L.append(f"### {config.REPORT_TITLE}")
    L.append(f"\n> {config.DISCLAIMER}\n")
    L.append(f"**Scope of this draft:** {len(master):,} transactions from "
             f"{len(files)} source workbook(s). Additional source files listed in "
             "the assignment are not yet loaded — figures will change materially "
             "as they arrive.\n")
    L.append("## Headline Numbers — DWG Operating (Capital Group + Capital Partners)\n")
    L.append("Poseidon and personal entities are reported separately below, NOT consolidated.\n")
    L.append("| Metric | 2025 (FY) | 2026 (YTD) |")
    L.append("|---|--:|--:|")
    L.append(f"| Revenue | {_money(t25['revenue'])} | {_money(t26['revenue'])} |")
    L.append(f"| Operating Expenses | {_money(t25['opex']+t25['compensation'])} | "
             f"{_money(t26['opex']+t26['compensation'])} |")
    L.append(f"| Deal & Asset Costs | {_money(t25['deal'])} | {_money(t26['deal'])} |")
    L.append(f"| Total Expenses | {_money(t25['total_expense'])} | {_money(t26['total_expense'])} |")
    L.append(f"| **Preliminary Operating Income / EBITDA** | **{_money(t25['operating_income'])}** | "
             f"**{_money(t26['operating_income'])}** |")
    L.append("")
    L.append("## Related Entities — Poseidon (separate, not consolidated)\n")
    L.append("| Metric | 2025 (FY) | 2026 (YTD) |")
    L.append("|---|--:|--:|")
    L.append(f"| Revenue | {_money(p25['revenue'])} | {_money(p26['revenue'])} |")
    L.append(f"| Total Expenses | {_money(p25['total_expense'])} | {_money(p26['total_expense'])} |")
    L.append(f"| Preliminary Operating Income | {_money(p25['operating_income'])} | {_money(p26['operating_income'])} |")
    L.append("")
    L.append("## Cash & Run-Rate\n")
    L.append(f"- **2026 average monthly operating spend (burn):** {_money(burn26)}")
    L.append(f"- **Compensation / contractor total (all periods loaded):** {_money(payroll)}")
    L.append(f"- **Personal expenses paid by business:** {_money(sum(abs(r['amount_raw']) for r in pers))} "
             f"across {len(pers)} items → propose Due From Owner / Distribution")
    L.append(f"- **Business expenses paid personally:** {_money(sum(abs(r['amount_raw']) for r in bp))} "
             f"across {len(bp)} items → propose Due To Owner / reimbursable")
    L.append(f"- **Unmatched intercompany / card-payment legs:** {len(unmatched)} "
             "(bank side not yet loaded)")
    L.append("")
    L.append("## Largest Expense Categories\n")
    L.append("| GL Account | Amount |")
    L.append("|---|--:|")
    for cat, amt in top_cat:
        L.append(f"| {cat} | {_money(amt)} |")
    L.append("\n## Top Vendors\n")
    L.append("| Vendor | Amount |")
    L.append("|---|--:|")
    for v, amt in top_vend:
        L.append(f"| {v} | {_money(amt)} |")
    if top_deal:
        L.append("\n## Deal-Specific Spending\n")
        L.append("| Deal / Asset | Amount |")
        L.append("|---|--:|")
        for d, amt in top_deal:
            L.append(f"| {d} | {_money(amt)} |")
    L.append("\n## Twenty Largest Unresolved / Review Items\n")
    L.append("| Date | Entity | Description | Amount | Reason |")
    L.append("|---|---|---|--:|---|")
    for r in top_reviews:
        L.append(f"| {r['transaction_date']} | {r['source_entity']} | "
                 f"{(r['description_raw'] or '')[:38]} | {_money(r['amount_raw'])} | "
                 f"{r['review_reason']} |")
    L.append("\n## Reliability Limitations\n")
    L.append("- Cash/charge-basis only; not GAAP, tax-basis, reviewed, or audited.")
    L.append("- Bank statements, card ending balances, payroll registers, loan "
             "schedules, A/R, A/P, and equity are **not yet loaded**.")
    L.append("- Only the card side of credit-card payments and transfers is visible.")
    L.append("- Entity allocation for any 'Unassigned' rows is preliminary.")
    L.append("\n## Immediate Accounting Cleanup Priorities\n")
    L.append("1. Load remaining source workbooks (Group, Partners full-year, "
             "Poseidon, Plum, Family, Angela, Venmo).")
    L.append("2. Provide bank & card statements to confirm balances and the paying side of transfers.")
    L.append("3. Confirm personal-vs-business dispositions to clear Due To/From Owner.")
    L.append("4. Supply payroll registers and loan amortization schedules.")
    L.append("5. Approve or revise the proposed adjusting entries.")
    npass = sum(1 for c in controls_results if c['passed'])
    L.append(f"\n---\n*Automated controls: {npass}/{len(controls_results)} passed. "
             "See the Source Control sheet for detail.*")
    path.write_text("\n".join(L), encoding="utf-8")


def _write_methodology_md(path):
    txt = f"""# Methodology — DWG Financial Overview Pipeline

{config.DISCLAIMER}

## Import logic
Every `.xlsx` in `source_workbooks/` is opened **read-only** (SHA-256 verified
unchanged before and after the run). For each workbook the most granular
transaction sheet is selected by priority: Transaction Details → Raw Data →
Transactions → Transaction Overview → Commission. Summary / Monthly / Mapping
sheets are **reference only** and never imported as transactions; their control
totals are captured for reconciliation.

## Sheet-selection & header detection
The header row is the first row (scanning the top 15) that contains a `Date`
column. Columns are mapped by fuzzy header tokens to roles (date, description,
merchant, amount, category, B/P, reimbursement, notes, extended details). Two
layouts are handled automatically: raw Amex exports
(`Date | Description | Amount | Extended Details | Category`) and cleaned
exports (`Date | Merchant | Category | Amount | B/P | Reimb. | Notes`).

## Date normalization
Excel serials, datetimes, and many string formats (`mm/dd/yyyy`,
`yyyy-mm-dd`, `Month d, yyyy`, …) are coerced to ISO dates. Rows whose date
cell is not a real date are treated as summary/junk and skipped (never counted).

## Sign convention
Source data is American-Express style: **positive = charge (cash outflow /
expense)**, **negative = payment or credit (cash inflow)**. The pipeline stores
`amount_raw`, and derives `cash_inflow`, `cash_outflow`, `debit`, `credit`.

## Entity assignment
Resolution order (highest confidence first): (1) account last-four →
entity map; (2) explicit `Entity` header text; (3) card name / account holder /
filename hint; (4) fallback `Unassigned / Allocation Required`. Filenames are
treated as hints only — e.g. a "DWGRE" file resolves to **DWG Capital Group**
from its internal Entity field.

## Duplicate detection
Deterministic fingerprint over (entity, account last-four, date, rounded amount,
normalized merchant). A group with ≥2 rows from **different source files/rows**
is a real overlap (e.g. the May 29 boundary between the Mar-May and June DWGCP
exports). The first occurrence is `Primary` and stays in totals; the rest are
`Duplicate`, excluded from rollups but **retained** with a Duplicate Group ID.

## Transfer matching
Credit-card payments and explicit transfers are split into outflow/inflow legs
and matched on equal amount within a {{transfer_matching_days}}-day window. Matched
legs share a Transfer Match ID and are marked intercompany (eliminate on
consolidation). Card payments whose bank-side leg is not yet loaded are recorded
as `Unmatched (card side only)`.

## Credit-card payment treatment
Amex/Plum/autopay payments are mapped to **Credit Cards Payable** (balance
sheet) and **excluded from operating expense** — the underlying charges are
already captured, so counting the payment too would double-count.

## Personal vs business allocation
The `B/P` flag and any "Personal" category route an item to Personal. Personal
items paid from a business account are **excluded from operating EBITDA** and
proposed as Due From Owner / Owner Distribution. Business items paid from
personal/family/Angela/Venmo accounts are reported separately and proposed as
Due To Owner / reimbursable.

## Category mapping
An ordered rule table maps (category + merchant + description) to the management
Chart of Accounts, most-specific first. Management overrides in
`mappings/category_overrides.csv` always win and survive re-runs. Deal/asset
names are parsed and preserved independently of the GL mapping.

## Confidence scoring
95–100 deterministic (account+merchant+mapping); 80–94 strong; 60–79 reasonable
(review); <60 unresolved → Suspense & Review. The row score is the min of the
entity and category confidences, floored to Suspense when unmapped.

## Materiality thresholds
Individual review ≥ ${config.THRESHOLDS['individual_review']:,};
uncategorized ≥ ${config.THRESHOLDS['uncategorized_review']:,};
owner/personal ≥ ${config.THRESHOLDS['owner_personal_review']:,};
deal cost ≥ ${config.THRESHOLDS['deal_cost_review']:,}; all unmatched transfers,
loan proceeds/payments, and cash withdrawals reviewed regardless of amount.

## Known limitations
Cash/charge basis only; no bank reconciliations, accruals, balance sheet, or
equity roll-forward. Not GAAP/tax/reviewed/audited. Results are preliminary and
subject to CPA approval.
""".replace("{transfer_matching_days}", str(transfer_matching.DATE_TOLERANCE_DAYS))
    path.write_text(txt, encoding="utf-8")


def _write_config_readme(path):
    t = config.THRESHOLDS
    path.write_text(f"""# Configuration & Review Thresholds

These thresholds live in `pipeline/config.py` (`THRESHOLDS`) and are surfaced
here and on the workbook's Source Control sheet.

| Rule | Threshold |
|---|--:|
| Individual review (any txn) | ${t['individual_review']:,} |
| Uncategorized review | ${t['uncategorized_review']:,} |
| Owner / personal review | ${t['owner_personal_review']:,} |
| Deal-specific cost review | ${t['deal_cost_review']:,} |
| Unmatched transfers | any amount |
| Loan proceeds / payments | any amount |
| Cash withdrawals | any amount |

Confidence bands: ≥95 deterministic · 80–94 strong · 60–79 review · <60 suspense.
""", encoding="utf-8")


def _seed_override_file():
    p = config.MAPPING_DIR / "category_overrides.csv"
    if not p.exists():
        p.write_text("source_category,gl_account\n"
                     "# Add rows to lock management decisions, e.g.:\n"
                     "# Employee MISC,General & Administrative\n", encoding="utf-8")


def _write_control_failure(control_results, critical_fail):
    lines = ["DWG PIPELINE — CONTROL FAILURE REPORT", "=" * 40, ""]
    for c in control_results:
        lines.append(f"[{'PASS' if c['passed'] else 'FAIL'}] {c['control']} — {c['detail']}")
    lines.append("")
    lines.append("CRITICAL FAILURES (final workbook withheld):")
    for c in critical_fail:
        lines.append(f"  - {c['control']}: {c.get('detail','')}")
    (config.OUTPUT_DIR / "control_failure_report.txt").write_text("\n".join(lines))


from . import transfer_matching  # noqa: E402  (used in methodology text)

if __name__ == "__main__":
    run()
