"""
transfer_matching.py — Match intercompany / credit-card transfers between a
sending account (outflow) and a receiving account (inflow).

Because the current data set is credit-card charge data, the dominant "transfer"
pattern is a credit-card PAYMENT: an outflow from a bank account paying down an
Amex balance (the negative "Online AMEX Payment" rows). Until bank statements
arrive we can only see the card side; those are flagged credit_card_payment and
recorded here as unmatched (awaiting the bank-side leg).

When both legs exist (a sending entity outflow and a receiving entity inflow of
the same amount within a tolerance window) we assign a shared Transfer Match ID
and mark both intercompany = Yes so they eliminate on consolidation.
"""
from datetime import date, timedelta

DATE_TOLERANCE_DAYS = 5


def _parse(dstr):
    try:
        y, m, d = (int(x) for x in dstr.split("-"))
        return date(y, m, d)
    except Exception:
        return None


def match_transfers(master):
    """
    Identify transfer candidates and assign Transfer Match IDs where an
    outflow leg and an inflow leg reconcile. Returns list of transfer records.
    """
    # Candidate legs: credit-card payments and any explicitly-transfer rows.
    out_legs, in_legs = [], []
    for r in master:
        if r["potential_duplicate"] == "Duplicate":
            continue
        is_cc = r["credit_card_payment"] == "Yes"
        is_xfer_cat = "transfer" in (r["combined_category"] or "").lower()
        if not (is_cc or is_xfer_cat):
            continue
        if r["cash_outflow"] and r["cash_outflow"] > 0:
            out_legs.append(r)
        elif r["cash_inflow"] and r["cash_inflow"] > 0:
            in_legs.append(r)

    transfers = []
    seq = 0
    used_in = set()
    for o in out_legs:
        od = _parse(o["transaction_date"])
        amt = round(o["cash_outflow"], 2)
        match = None
        for idx, i in enumerate(in_legs):
            if idx in used_in:
                continue
            if round(i["cash_inflow"], 2) != amt:
                continue
            idd = _parse(i["transaction_date"])
            if od and idd and abs((od - idd).days) <= DATE_TOLERANCE_DAYS:
                match = (idx, i)
                break
        seq += 1
        tid = f"XFER-{seq:04d}"
        o["transfer_match_id"] = tid
        if match:
            idx, i = match
            used_in.add(idx)
            i["transfer_match_id"] = tid
            o["intercompany"] = i["intercompany"] = "Yes"
            transfers.append({
                "transfer_match_id": tid,
                "status": "Matched",
                "sending_entity": o["source_entity"],
                "receiving_entity": i["source_entity"],
                "send_date": o["transaction_date"], "send_amount": amt,
                "recv_date": i["transaction_date"], "recv_amount": round(i["cash_inflow"], 2),
                "timing_diff_days": abs((od - _parse(i["transaction_date"])).days),
                "proposed_treatment": "Eliminate on consolidation (Due To/Due From).",
            })
        else:
            transfers.append({
                "transfer_match_id": tid,
                "status": "Unmatched (card side only)",
                "sending_entity": "(bank account — not yet imported)",
                "receiving_entity": o["source_entity"],
                "send_date": "", "send_amount": "",
                "recv_date": o["transaction_date"], "recv_amount": amt,
                "timing_diff_days": "",
                "proposed_treatment": ("Credit-card payment; awaiting bank-side leg. "
                                       "Balance-sheet — excluded from P&L."),
            })

    # Inflow legs never matched to an outflow (e.g. Amex payments credited to the
    # card whose paying bank account is not yet loaded). Surface them too so the
    # Intercompany sheet shows every card-payment/transfer leg.
    for idx, i in enumerate(in_legs):
        if idx in used_in or i.get("transfer_match_id"):
            continue
        seq += 1
        tid = f"XFER-{seq:04d}"
        i["transfer_match_id"] = tid
        transfers.append({
            "transfer_match_id": tid,
            "status": "Unmatched (card side only)",
            "sending_entity": "(bank account — not yet imported)",
            "receiving_entity": i["source_entity"],
            "send_date": "", "send_amount": "",
            "recv_date": i["transaction_date"],
            "recv_amount": round(i["cash_inflow"], 2),
            "timing_diff_days": "",
            "proposed_treatment": ("Credit-card payment received on card; awaiting "
                                   "bank-side leg. Balance-sheet — excluded from P&L."),
        })
    return transfers
