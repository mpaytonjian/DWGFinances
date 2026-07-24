"""
reporting.py — Aggregate the classified master table into the numbers the
workbook and markdown/CSV deliverables need.

Golden rule for every rollup: exclude rows where
    potential_duplicate == 'Duplicate'  (excluded dup leg)
    credit_card_payment == 'Yes'        (balance-sheet)
    intercompany == 'Yes'               (eliminates on consolidation)
    financial_statement_group in (Balance Sheet, Suspense)  -> not in P&L EBITDA
Personal items are routed OUT of operating EBITDA into their own schedule.
"""
from collections import defaultdict

from . import config


def _pl_eligible(r):
    """Rows eligible for the operating P&L (EBITDA)."""
    if r["potential_duplicate"] == "Duplicate":
        return False
    if r["credit_card_payment"] == "Yes":
        return False
    if r["intercompany"] == "Yes":
        return False
    if r["financial_statement_group"] in (config.FSG_BALANCE, config.FSG_SUSPENSE,
                                          config.FSG_NONOP):
        return False
    if r["business_or_personal"] == "Personal":
        return False   # routed to Personal-Paid-by-Business schedule
    return True


def _signed_pl(r):
    """P&L contribution: revenue positive, expense negative (net income view)."""
    if r["financial_statement_group"] == config.FSG_REVENUE:
        return r["cash_inflow"] - r["cash_outflow"]
    # expense: outflow reduces income; refunds/credits (inflow) add back
    return -(r["cash_outflow"] - r["cash_inflow"])


def pl_summary(master, year=None, entities=None):
    """Return dict: fsg -> gl_account -> net amount (expense positive)."""
    out = defaultdict(lambda: defaultdict(float))
    for r in master:
        if not _pl_eligible(r):
            continue
        if year and r["year"] != year:
            continue
        if entities and r["source_entity"] not in entities:
            continue
        fsg = r["financial_statement_group"]
        gl = r["combined_category"]
        if fsg == config.FSG_REVENUE:
            out[fsg][gl] += (r["cash_inflow"] - r["cash_outflow"])
        else:
            out[fsg][gl] += (r["cash_outflow"] - r["cash_inflow"])
    return out


def pl_totals(master, year=None, entities=None):
    s = pl_summary(master, year, entities)
    revenue = sum(s.get(config.FSG_REVENUE, {}).values())
    comp = sum(s.get(config.FSG_COMP, {}).values())
    opex = sum(s.get(config.FSG_OPEX, {}).values())
    deal = sum(s.get(config.FSG_DEAL, {}).values())
    total_exp = comp + opex + deal
    return {
        "revenue": revenue, "compensation": comp, "opex": opex, "deal": deal,
        "total_expense": total_exp, "operating_income": revenue - total_exp,
    }


def monthly_pl(master, year, entities=None):
    """month -> {revenue, expense, net}"""
    buckets = defaultdict(lambda: {"revenue": 0.0, "expense": 0.0})
    for r in master:
        if not _pl_eligible(r) or r["year"] != year:
            continue
        if entities and r["source_entity"] not in entities:
            continue
        mo = r["month"]
        if r["financial_statement_group"] == config.FSG_REVENUE:
            buckets[mo]["revenue"] += (r["cash_inflow"] - r["cash_outflow"])
        else:
            buckets[mo]["expense"] += (r["cash_outflow"] - r["cash_inflow"])
    out = {}
    for mo, v in sorted(buckets.items()):
        out[mo] = {"revenue": v["revenue"], "expense": v["expense"],
                   "net": v["revenue"] - v["expense"]}
    return out


def entity_comparison(master, year=None):
    out = {}
    for ent in config.ALL_ENTITIES:
        t = pl_totals(master, year, entities=[ent])
        if t["revenue"] or t["total_expense"]:
            out[ent] = t
    return out


def top_categories(master, year=None, n=10):
    agg = defaultdict(float)
    for r in master:
        if not _pl_eligible(r):
            continue
        if r["financial_statement_group"] == config.FSG_REVENUE:
            continue
        if year and r["year"] != year:
            continue
        agg[r["combined_category"]] += (r["cash_outflow"] - r["cash_inflow"])
    return sorted(agg.items(), key=lambda kv: -kv[1])[:n]


def top_vendors(master, year=None, n=10):
    agg = defaultdict(float)
    for r in master:
        if not _pl_eligible(r):
            continue
        if year and r["year"] != year:
            continue
        agg[r["merchant_normalized"] or "(unknown)"] += (r["cash_outflow"] - r["cash_inflow"])
    return sorted(agg.items(), key=lambda kv: -kv[1])[:n]


def top_deals(master, n=10):
    agg = defaultdict(float)
    for r in master:
        if r["potential_duplicate"] == "Duplicate":
            continue
        if r["deal_or_asset"]:
            agg[r["deal_or_asset"]] += (r["cash_outflow"] - r["cash_inflow"])
    return sorted(agg.items(), key=lambda kv: -kv[1])[:n]


def personal_paid_by_business(master):
    return [r for r in master if r["business_or_personal"] == "Personal"
            and r["source_entity"] in config.DWG_OPERATING_ENTITIES
            and r["potential_duplicate"] != "Duplicate"]


def business_paid_personally(master):
    personal_entities = {config.ENTITY_JOHN, config.ENTITY_ANGELA,
                         config.ENTITY_FAMILY, config.ENTITY_VENMO}
    return [r for r in master if r["source_entity"] in personal_entities
            and r["business_or_personal"] == "Business"
            and r["potential_duplicate"] != "Duplicate"]


def review_items(master):
    out = []
    for r in master:
        if r["review_status"] in ("Review",) or (
                r["review_status"] == "OK" and r["confidence_score"] < config.CONF_REASONABLE):
            out.append(r)
    return sorted(out, key=lambda r: -abs(r["amount_raw"]))


def cash_flow(master, year=None):
    inflow = outflow = 0.0
    for r in master:
        if r["potential_duplicate"] == "Duplicate":
            continue
        if year and r["year"] != year:
            continue
        inflow += r["cash_inflow"]
        outflow += r["cash_outflow"]
    return {"inflow": inflow, "outflow": outflow, "net": inflow - outflow}


def source_reconciliation(master, reports):
    """Per source-file reconciliation rows."""
    by_file = defaultdict(list)
    for r in master:
        by_file[r["source_file"]].append(r)
    out = []
    rep_by_file = {rep["file"]: rep for rep in reports}
    for fname, rows in sorted(by_file.items()):
        rep = rep_by_file.get(fname, {})
        inflow = sum(x["cash_inflow"] for x in rows)
        outflow = sum(x["cash_outflow"] for x in rows)
        dup = sum(1 for x in rows if x["potential_duplicate"] == "Duplicate")
        xfer = sum(1 for x in rows if x["transfer_match_id"])
        ccp = sum(1 for x in rows if x["credit_card_payment"] == "Yes")
        pers = sum(1 for x in rows if x["business_or_personal"] == "Personal")
        rev = sum(1 for x in rows if x["review_status"] == "Review")
        ent = rows[0]["source_entity"] if rows else ""
        acct = rows[0]["account_last4"] if rows else ""
        ref = rep.get("reference_totals", {})
        # control: net of imported charges vs summary net
        net = outflow - inflow
        ref_net = ref.get("charges", 0) + ref.get("credits_payments", 0) \
            if ref else None
        reconciled = "n/a"
        if ref_net is not None:
            reconciled = "Tie" if abs(net - ref_net) < 1.0 else \
                f"Diff {net-ref_net:,.2f}"
        out.append({
            "file": fname, "entity": ent, "account": acct,
            "period": rep.get("meta", {}).get("statement_period", ""),
            "imported": len(rows), "gross_inflows": inflow,
            "gross_outflows": outflow, "net": net,
            "duplicates": dup, "transfers": xfer, "cc_payments": ccp,
            "personal": pers, "review": rev,
            "control_total": net, "reconciled": reconciled,
        })
    return out
