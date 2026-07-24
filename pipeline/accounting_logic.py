"""
accounting_logic.py — Turn raw ingested records into fully-classified master
transaction rows.

For each record we derive:
  * source_entity / proposed_reporting_entity
  * gl_account / financial_statement_group / combined_category
  * direction (cash_in / cash_out), debit / credit
  * boolean classification flags (cc_payment, personal, deal, loan, interest,
    intercompany, owner_activity, reimbursement, revenue/expense/balance sheet)
  * review_status / review_reason / proposed_treatment / confidence
  * management_notes

Sign convention: source is Amex-style (positive = charge/outflow,
negative = payment/credit/inflow).
"""
from . import config
from . import entity_rules
from . import category_rules
from .normalize import (normalize_merchant, normalize_description, fingerprint,
                        month_key)

CC_PAYMENT_ACCOUNT = "Credit Cards Payable"


_PERSONAL_ENTITIES = {config.ENTITY_JOHN, config.ENTITY_ANGELA,
                      config.ENTITY_FAMILY, config.ENTITY_VENMO}
_BUSINESS_HINTS = ("dwg", "costar", "sponsorcloud", "sponsor cloud", "crexi",
                   "listing platform", "loopnet", "e&o", "notary", "underwriting",
                   "deal", "investor", "conference", "commission", "brokerage",
                   "payroll", "office reimb")


def _business_personal(rec, gl_account, source_entity):
    """Return ('Business'|'Personal', reason) from B/P flag, category, and the
    nature of the source account. Personal-account activity defaults to
    Personal; business-account activity defaults to Business."""
    flag = str(rec.get("bp_flag") or "").strip().upper()
    cat = str(rec.get("category") or "").strip().lower()
    desc = str(rec.get("description") or "").strip().lower()
    if flag in ("P", "P?", "PERSONAL"):
        return "Personal", "B/P flag = personal"
    if "personal" in cat:
        return "Personal", "category marked personal"
    if "family" in cat:
        return "Personal", "category marked family/household"
    if flag == "B":
        return "Business", "B/P flag = business"
    if source_entity in _PERSONAL_ENTITIES:
        text = cat + " " + desc
        if any(h in text for h in _BUSINESS_HINTS):
            return "Business", "business indicator on personal account (review)"
        return "Personal", "assumed personal (personal account, no business indicator)"
    return "Business", "assumed business (business account)"


def classify(rec, overrides):
    """Return a fully-populated master row dict."""
    d = rec["date"]
    amt_raw = rec["amount_raw"]
    desc_raw = normalize_description(rec.get("description") or rec.get("merchant"))
    merch_raw = rec.get("merchant") or rec.get("description")
    merchant_norm = normalize_merchant(merch_raw)
    desc_norm = normalize_description(desc_raw).upper()
    category = rec.get("category") or ""

    # --- entity ---
    source_entity, ent_conf, ent_basis = entity_rules.resolve_entity(rec)

    # --- GL mapping ---
    gl, fsg, cat_conf, cat_basis = category_rules.map_category(
        category, merch_raw, desc_raw, overrides)
    deal = category_rules.parse_deal(category, rec.get("notes"), desc_raw)

    # Owner transfers: direction decides contribution vs distribution.
    if gl == "Owner Distributions" and amt_raw < 0:
        gl = "Owner Contributions"
    fsg = config.COA_BY_NAME[gl][1]

    # Cash withdrawals always require review (mapped to suspense/owner).
    _txt = f"{category} {desc_raw}".lower()
    is_cash_withdrawal = any(k in _txt for k in
                             ("atm", "cash withdrawal", "withdrawal", "cash advance"))

    # Material deal-related INFLOWS (closing proceeds, recoveries, escrow
    # returns) must not net against deal costs — they need a revenue vs
    # reimbursement vs pass-through determination.
    if fsg == config.FSG_DEAL and amt_raw < -1000:
        gl = "Suspense & Review"
        fsg = config.FSG_SUSPENSE
        cat_conf = min(cat_conf, 58)
        cat_basis = "deal inflow -> revenue/reimbursement review"

    # --- direction ---
    is_inflow = amt_raw < 0
    cash_in = -amt_raw if is_inflow else 0.0
    cash_out = amt_raw if amt_raw > 0 else 0.0
    # Accounting debit/credit (expense debit / payment credit) — expense positive
    debit = amt_raw if amt_raw > 0 else 0.0
    credit = -amt_raw if amt_raw < 0 else 0.0

    # --- classification flags ---
    is_cc_payment = (gl == CC_PAYMENT_ACCOUNT)
    is_loan = fsg == config.FSG_BALANCE and gl in ("Loan Proceeds", "Loan Principal",
                                                   "Member Loans")
    is_interest = gl == "Interest Expense"
    bp, bp_reason = _business_personal(rec, gl, source_entity)
    is_personal = (bp == "Personal")
    is_refund = (amt_raw < 0 and not is_cc_payment and gl not in
                 ("Loan Proceeds",))
    is_revenue = (fsg == config.FSG_REVENUE)
    is_balance_sheet = fsg in (config.FSG_BALANCE,)
    # Reimbursement flag
    reimb = str(rec.get("reimb_flag") or "").strip()
    is_reimbursement = bool(reimb) and reimb.lower() not in ("nan", "none")

    # operating vs nonoperating
    if fsg in (config.FSG_REVENUE, config.FSG_COMP, config.FSG_OPEX):
        op = "Operating"
    elif fsg == config.FSG_DEAL:
        op = "Operating"   # deal costs are operating unless capitalized (flagged)
    else:
        op = "Nonoperating"

    # revenue/expense label
    if is_revenue:
        rev_exp = "Revenue"
    elif fsg in (config.FSG_COMP, config.FSG_OPEX, config.FSG_DEAL) and not is_inflow:
        rev_exp = "Expense"
    elif is_inflow and not is_cc_payment and not is_balance_sheet:
        rev_exp = "Contra/Inflow"
    else:
        rev_exp = "Balance Sheet" if is_balance_sheet else "Expense"

    # --- proposed reporting entity ---
    reporting_entity = source_entity

    # --- confidence (blend entity + category, penalise suspense) ---
    confidence = min(ent_conf, cat_conf)
    if gl == "Suspense & Review":
        confidence = min(confidence, config.CONF_UNRESOLVED)

    # --- proposed accounting treatment ---
    treatment, review_status, review_reason = _propose_treatment(
        gl, fsg, is_cc_payment, is_personal, is_loan, is_refund, deal,
        amt_raw, confidence, source_entity, bp_reason)
    if is_cash_withdrawal and review_status != "Review":
        review_status = "Review"
        review_reason = (review_reason + "; " if review_reason else "") + \
            "Cash withdrawal — review regardless of amount"
    if gl == "Intercompany Transfers" and review_status != "Review":
        review_status = "Review"
        review_reason = (review_reason + "; " if review_reason else "") + \
            "Transfer — verify counterparty and matching"

    row = {
        # identity / source
        "transaction_id": fingerprint(rec["source_file"], rec["source_sheet"],
                                      rec["source_row"], d, amt_raw, merchant_norm),
        "source_file": rec["source_file"],
        "source_sheet": rec["source_sheet"],
        "source_row": rec["source_row"],
        "source_entity": source_entity,
        "proposed_reporting_entity": reporting_entity,
        "account_name": rec.get("meta_card_name") or "",
        "account_last4": rec.get("meta_account_last4") or "",
        "account_type": "Credit Card"
            if "amex" in str(rec.get("meta_card_name") or "").lower()
            or "plum" in str(rec.get("source_file") or "").lower() else "Account",
        # dates
        "transaction_date": d.isoformat() if d else "",
        "posting_date": "",
        "year": d.year if d else "",
        "month": month_key(d) or "",
        # description / category
        "description_raw": desc_raw,
        "description_normalized": desc_norm,
        "merchant_normalized": merchant_norm,
        "original_category": category,
        "combined_category": gl,
        "financial_statement_group": fsg,
        "proposed_gl_account": f"{config.COA_BY_NAME[gl][0]} {gl}",
        "deal_or_asset": deal,
        # amounts
        "amount_raw": round(amt_raw, 2),
        "debit": round(debit, 2),
        "credit": round(credit, 2),
        "cash_inflow": round(cash_in, 2),
        "cash_outflow": round(cash_out, 2),
        # flags
        "business_or_personal": bp,
        "operating_or_nonoperating": op,
        "revenue_or_expense": rev_exp,
        "balance_sheet_activity": "Yes" if is_balance_sheet else "No",
        "intercompany": "No",           # set by transfer_matching
        "owner_activity": "Yes" if (is_personal or gl in
                                    ("Owner Contributions", "Owner Distributions",
                                     "Due From Owner", "Due To Owner")) else "No",
        "reimbursement": "Yes" if is_reimbursement else "No",
        "credit_card_payment": "Yes" if is_cc_payment else "No",
        "loan_principal": "Yes" if gl == "Loan Principal" else "No",
        "interest": "Yes" if is_interest else "No",
        # dedup / transfer (filled later)
        "potential_duplicate": "No",
        "duplicate_group_id": "",
        "transfer_match_id": "",
        # review
        "confidence_score": confidence,
        "review_status": review_status,
        "review_reason": review_reason,
        "proposed_accounting_treatment": treatment,
        "management_notes": "",
        # raw carry for audit
        "_bp_flag": rec.get("bp_flag"),
        "_notes": rec.get("notes"),
        "_is_inflow": is_inflow,
        "_is_personal": is_personal,
        "_is_cc_payment": is_cc_payment,
        "_is_loan": is_loan,
        "_is_deal": bool(deal) or fsg == config.FSG_DEAL,
        "_is_revenue": is_revenue,
        "_ent_basis": ent_basis,
        "_cat_basis": cat_basis,
    }
    return row


def _propose_treatment(gl, fsg, is_cc_payment, is_personal, is_loan, is_refund,
                       deal, amt_raw, confidence, source_entity, bp_reason):
    """Return (treatment_text, review_status, review_reason)."""
    T = THRESH = config.THRESHOLDS
    amt = abs(amt_raw)
    status = "OK"
    reason = ""

    if is_cc_payment:
        treatment = ("Balance-sheet credit-card payment — exclude from operating "
                     "expense (underlying charges captured separately).")
        return treatment, "Auto-Excluded", "Credit-card payment"

    if is_loan:
        return ("Financing activity — record to loan account, not P&L. Principal/"
                "interest split unknown without amortization schedule."), \
               "Review", "Loan/debt activity — review regardless of amount"

    if is_personal:
        status = "Review" if amt >= THRESH["owner_personal_review"] else "Review"
        treatment = ("Personal expense paid from business account — propose Due "
                     "From Owner / Owner Distribution pending substantiation.")
        reason = f"Personal item ({bp_reason})"
        return treatment, status, reason

    if is_refund:
        return ("Credit / refund / points — contra to original expense; confirm "
                "matching original charge."), "Review", "Refund/credit/points"

    if gl == "Suspense & Review":
        return ("Unmapped — assign to Suspense & Review pending classification."), \
               "Review", "Unmapped category"

    if source_entity == config.ENTITY_UNASSIGNED:
        return ("Entity could not be determined from source — allocate before "
                "consolidation."), "Review", "Entity unassigned"

    if fsg == config.FSG_DEAL:
        treatment = (f"Deal/asset cost{' — ' + deal if deal else ''}. Evaluate "
                     "whether expensable, reimbursable, or capitalizable.")
        status = "Review" if amt >= THRESH["deal_cost_review"] else "OK"
        reason = "Deal-specific cost >= $5,000" if status == "Review" else ""
        return treatment, status, reason

    # generic materiality
    if amt >= THRESH["individual_review"]:
        return ("Booked to " + gl + " — material item, confirm."), "Review", \
               "Amount >= $10,000"

    treatment = f"Book to {gl}."
    if confidence < config.CONF_REASONABLE:
        return treatment, "Review", "Low confidence"
    return treatment, "OK", ""


def build_master(records, overrides=None):
    overrides = overrides or category_rules.load_overrides()
    return [classify(r, overrides) for r in records]
