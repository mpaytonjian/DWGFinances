"""
adjusting.py — Generate PROPOSED adjusting journal entries and the
missing-information schedule. Nothing here is posted or final.
"""
from collections import defaultdict

from . import config
from . import reporting


def build_adjusting_entries(master, transfers):
    entries = []
    seq = 0

    def add(entity, dr, cr, amount, expl, txn_ids, support):
        nonlocal seq
        seq += 1
        entries.append({
            "entry_id": f"AJE-{seq:03d}",
            "entry_date": config.YTD_2026_THROUGH,
            "entity": entity,
            "debit_account": dr,
            "credit_account": cr,
            "amount": round(amount, 2),
            "explanation": expl,
            "source_transaction_ids": txn_ids,
            "support_status": support,
            "approval_status": "Proposed — Pending Approval",
        })

    # 1. Reclass personal-paid-by-business -> Due From Owner
    pers = reporting.personal_paid_by_business(master)
    by_ent = defaultdict(list)
    for r in pers:
        by_ent[r["source_entity"]].append(r)
    for ent, rows in by_ent.items():
        amt = sum(r["cash_outflow"] - r["cash_inflow"] for r in rows)
        if abs(amt) < 0.01:
            continue
        ids = ", ".join(r["transaction_id"] for r in rows[:8]) + \
            (" …" if len(rows) > 8 else "")
        add(ent, "Due From Owner", "Operating Expenses (various)", amt,
            f"Reclass {len(rows)} personal charges paid on the business card to "
            "Due From Owner (or Owner Distribution) pending substantiation.",
            ids, "Needs owner confirmation")

    # 2. Business-paid-personally -> Due To Owner
    bp = reporting.business_paid_personally(master)
    by_ent = defaultdict(list)
    for r in bp:
        by_ent[r["source_entity"]].append(r)
    for ent, rows in by_ent.items():
        amt = sum(r["cash_outflow"] - r["cash_inflow"] for r in rows)
        if abs(amt) < 0.01:
            continue
        ids = ", ".join(r["transaction_id"] for r in rows[:8])
        add(config.ENTITY_DWGCP, "Operating Expenses (various)", "Due To Owner", amt,
            f"Record {len(rows)} business charges paid on personal accounts as "
            "Due To Owner / reimbursable, pending approval.", ids,
            "Needs receipt substantiation")

    # 3. Reclass credit-card payments out of expense (already excluded; documents the control)
    ccp = [r for r in master if r["credit_card_payment"] == "Yes"
           and r["potential_duplicate"] != "Duplicate"]
    amt = sum(r["cash_outflow"] for r in ccp)
    if amt > 0.01:
        add("Consolidated", "Credit Cards Payable", "Cash (bank — pending)", amt,
            f"{len(ccp)} Amex payment(s) recorded as balance-sheet paydown of card "
            "liability, not operating expense (control confirmation).",
            "see Debt and Credit Cards sheet", "Confirmed from card data")

    # 4. Suspense clearing placeholder
    susp = [r for r in master if r["combined_category"] == "Suspense & Review"
            and r["potential_duplicate"] != "Duplicate"]
    amt = sum(r["cash_outflow"] - r["cash_inflow"] for r in susp)
    if abs(amt) > 0.01:
        add("Consolidated", "Suspense & Review", "(to be determined)", amt,
            f"{len(susp)} unclassified item(s) parked in Suspense pending "
            "classification. Do not include in operating results.",
            "see Uncategorized Review", "Needs classification")

    # 5. Deal costs potentially capitalizable
    deals = [r for r in master if r["financial_statement_group"] == config.FSG_DEAL
             and r["potential_duplicate"] != "Duplicate"
             and abs(r["amount_raw"]) >= config.THRESHOLDS["deal_cost_review"]]
    for r in deals:
        add(r["source_entity"], "Deal Cost (capitalize?)", "Deal Expense", abs(r["amount_raw"]),
            f"Deal-specific cost for {r['deal_or_asset'] or 'unnamed deal'} — evaluate "
            "whether to capitalize, reimburse, or expense.", r["transaction_id"],
            "Needs CPA determination")

    return entries


MISSING_ITEMS = [
    ("Beginning & ending bank reconciliations",
     "No bank statements loaded; cash balances and completeness of activity unverified.", "High"),
    ("Credit-card statement balances (Amex, Plum)",
     "Only charge-level detail present; ending liability balances not confirmed.", "High"),
    ("Accounts receivable / unbilled fees",
     "Revenue is cash-view only; earned-but-uncollected fees not captured.", "High"),
    ("Accounts payable / unpaid bills",
     "Accrued obligations not reflected; expenses are cash/charge basis.", "High"),
    ("Payroll registers & payroll-tax filings",
     "Payroll only visible if charged to a card; gross wages/taxes/benefits incomplete.", "High"),
    ("Loan agreements & amortization schedules",
     "Principal/interest split unknown; loan balances not stated.", "High"),
    ("Equity / owner contribution & distribution ledgers",
     "Owner activity inferred from personal charges only.", "High"),
    ("Accrued professional fees (legal, accounting)",
     "Only paid amounts captured; accruals missing.", "Medium"),
    ("Fixed-asset register & depreciation/amortization",
     "No capital assets or depreciation recorded.", "Medium"),
    ("Security deposits & prepaid expenses",
     "Balance-sheet timing items not identified.", "Medium"),
    ("Deferred revenue",
     "Advance fees, if any, not separated from earned revenue.", "Medium"),
    ("Property-level operating statements",
     "Asset/property carry, taxes, insurance, utilities not fully captured.", "Medium"),
    ("Intercompany / related-party bank statements",
     "Only the card side of transfers is visible; matching legs missing.", "High"),
    ("Prior-year trial balance & filed tax returns",
     "No opening balances to anchor 2025; equity roll-forward impossible.", "High"),
    ("Missing source workbooks (per assignment list)",
     "Group, Partners full-year, Poseidon, Plum, Family, Angela, Venmo files not yet loaded.", "High"),
]
