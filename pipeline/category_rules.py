"""
category_rules.py — Map a source category + merchant + description onto the
proposed management Chart of Accounts.

The engine is an ordered list of rules. Each rule is:
    (matcher, gl_account_name, confidence)
where `matcher` tests the combined lower-cased text of
(category, merchant, description). First match wins. Rules are ordered from
most-specific to most-general so deterministic categories short-circuit early.

Deal names are parsed separately (parse_deal) and preserved regardless of the
GL mapping so nothing about a deal is lost.

Persisted overrides (mappings/category_overrides.csv) always win — this lets
management decisions survive re-runs.
"""
import csv
import re
from pathlib import Path

from . import config

# ---------------------------------------------------------------------------
# Persisted management overrides: source_category (lower) -> gl_account_name
# ---------------------------------------------------------------------------
_OVERRIDE_PATH = config.MAPPING_DIR / "category_overrides.csv"


def load_overrides():
    overrides = {}
    if _OVERRIDE_PATH.exists():
        with open(_OVERRIDE_PATH, newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                key = (row.get("source_category") or "").strip().lower()
                gl = (row.get("gl_account") or "").strip()
                if key and gl in config.COA_BY_NAME:
                    overrides[key] = gl
    return overrides


def _kw(*words):
    pat = re.compile("|".join(re.escape(w) for w in words))
    return lambda text: bool(pat.search(text))


# Ordered rule table. (predicate, gl_account, confidence)
RULES = [
    # ---- Credit-card payments (balance sheet) -------------------------------
    (_kw("online amex pmt", "online amex payment", "online payment - thank",
         "autopay", "auto pay", "payment - thank", "mobile payment",
         "amex credit card payment", "american express credit card",
         "credit card pmt", "credit card payment", "amex epayment",
         "amex payment"),
     "Credit Cards Payable", config.CONF_DETERMINISTIC),
    (lambda t: t.strip() in ("payment", "credit"), "Credit Cards Payable", 92),

    # ---- Revenue (bank inflows) ---------------------------------------------
    (_kw("incoming commission", "dwg commission", "commissions sta"),
     "Brokerage Commissions", 95),
    # Pass-through wires: inbound wire creates a due-to; outbound "Due to X –
    # Pass-Through" legs settle it. Only the retained split is revenue — the
    # gross flows are balance sheet, never P&L. All flagged for review.
    (_kw("pass-through", "pass through"), "Due To Related Parties", 62),
    (_kw("incoming crystal asset management"), "Suspense & Review", 55),
    (_kw("mortgage coverage"), "Suspense & Review", 55),

    # ---- Owner / related-person transfers -----------------------------------
    (_kw("transfer to angela", "transfer from angela", "angela dunning"),
     "Owner Distributions", 75),   # flipped to Contributions on inflow

    # ---- Intercompany / account transfers (balance sheet) -------------------
    (_kw("transfer to dwg", "transfer from dwg", "transfer to poseidon",
         "transfer from poseidon", "poseidon asset group (incoming",
         "transfer to ecomm", "transfer from ecomm"),
     "Intercompany Transfers", 92),
    (_kw("transfer to", "transfer from"),   # third-party transfers: review
     "Intercompany Transfers", 62),
    (lambda t: t.strip() == "venmo" or "venmo funding" in t,
     "Intercompany Transfers", 62),   # match against Venmo ledger when loaded

    # ---- Loan / bridge servicing --------------------------------------------
    (_kw("forward bridge payment", "bridge payment"), "Loan Principal", 72),

    # ---- Points / refunds / credits (contra) --------------------------------
    (_kw("points redemption", "pay with points", "amex travel pay with points",
         "platinum hotel credit", "membership reward"),
     "Other Operating Expense", 85),   # contra handled by sign; flagged review
    (_kw("refund"), "Other Operating Expense", 80),

    # ---- Deal-specific costs (preserve into Deal & Asset group) --------------
    # Distinctive "deal specific" prefix routes to the Deal group; sub-account by
    # keyword. Deal/asset name is parsed separately and always preserved.
    (_kw("deal specific"), "Deal - Pursuit Costs", config.CONF_REASONABLE),
    (_kw("due diligence", "dead deal", "earnest money", "deal deposit"),
     "Deal - Due Diligence", config.CONF_REASONABLE),

    # ---- Loan / debt --------------------------------------------------------
    (_kw("bridge loan", "member loan", "loan proceed"),
     "Loan Proceeds", config.CONF_REASONABLE),
    (_kw("interest expense", "loan interest"), "Interest Expense", 85),
    (_kw("sba", "eidl"), "Loan Principal", config.CONF_REASONABLE),

    # ---- Compensation -------------------------------------------------------
    (_kw("payroll tax"), "Payroll Taxes", 90),
    (_kw("payroll", "gusto", "adp", "wages", "salary"), "Payroll", 88),
    (_kw("employee bonus", "bonus"), "Payroll", 82),
    (_kw("recruiting", "recruit", "indeed", "linkedin recruiter"),
     "Recruiting", 88),
    (_kw("contractor", "1099", "notary services", "notary", "upwork",
         "zelle -", "zelle-"),
     "Contractor Compensation", 72),
    (_kw("commission"), "Commissions Paid", 80),
    (_kw("employee tech onboarding", "tech onboarding"), "Software & Technology", 80),
    (_kw("employee benefit", "health insurance", "benefits"),
     "Employee Benefits", 80),

    # ---- Insurance ----------------------------------------------------------
    (_kw("e&o insurance", "e & o insurance", "realcare", "errors and omissions"),
     "Insurance", 90),
    (_kw("insurance"), "Insurance", 78),

    # ---- Data & listing platforms -------------------------------------------
    (_kw("costar", "crexi", "listing platform", "loopnet", "reonomy",
         "sponsorcloud", "sponsor cloud"),
     "Data & Listing Platforms", 90),

    # ---- Software & technology ----------------------------------------------
    (_kw("ai subscription", "anthropic", "openai", "chatgpt", "software & subscription",
         "software and subscription", "software", "subscription", "intuit",
         "quickbooks", "adobe", "google", "microsoft", "socialpilot", "zoom",
         "slack", "dropbox", "bestbuy", "best buy", "apple.com", "operational subscription"),
     "Software & Technology", 86),
    (_kw("godaddy", "go daddy"), "Software & Technology", 90),

    # ---- Marketing / IR -----------------------------------------------------
    (_kw("marketing", "advertis", "mailchimp", "canva"), "Marketing", 80),
    (_kw("investor meeting", "investor dinner", "investor relations"),
     "Investor Relations", 82),

    # ---- Professional / accounting / legal ----------------------------------
    (_kw("accounting", "bookkeep", "cpa"), "Accounting & Bookkeeping", 85),
    (_kw("legal case", "attorney", "law firm", "legal"), "Legal", 80),
    (_kw("professional training", "training", "hr", "professional service"),
     "Professional Services", 75),

    # ---- Travel / meals / conferences ---------------------------------------
    (_kw("team travel", "dwgcp team travel", "airline", "american airlines",
         "delta", "united", "hotel", "marriott", "hilton", "lodging", "airbnb",
         "uber", "lyft", "transportation", "rental car", "flight", "travel"),
     "Travel", 84),
    (_kw("team lunch", "team dinner", "travel meal", "meal", "restaurant",
         "dining", "team outing", "coffee", "starbucks"),
     "Meals & Entertainment", 82),
    (_kw("conference", "summit", "expo"), "Conferences", 82),

    # ---- Auto ---------------------------------------------------------------
    (_kw("auto", "car", "fuel", "gas station", "parking", "toll"),
     "Auto", 76),

    # ---- Office / telecom ---------------------------------------------------
    (_kw("office", "staples", "amazon"), "Office", 70),
    (_kw("telephone", "internet", "verizon", "at&t", "comcast", "mobile"),
     "Telephone & Internet", 80),

    # ---- Banking / fees / dues ----------------------------------------------
    (_kw("annual amex fee", "amex fee", "wire fee", "bank fee", "membership fee"),
     "Banking & Wire Fees", 85),
    (_kw("license", "dues", "membership"), "Licenses & Dues", 75),

    # ---- Personal / family --------------------------------------------------
    (_kw("family trip", "family travel"), "Travel", 60),
    (_kw("family", "household"), "General & Administrative", 55),
    (_kw("personal health"), "General & Administrative", 55),
    (lambda t: t.strip() == "personal" or "personal" in t, "Suspense & Review", 50),

    # ---- Misc / review ------------------------------------------------------
    (_kw("tbd review", "review", "misc", "employee misc"),
     "General & Administrative", 55),
]


def parse_deal(*texts):
    """
    Extract a deal / asset name from any of the given texts.
    Handles patterns like 'Deal Specific - Austin Iron', 'JAL Legal Case',
    'Bridge Loan (JC Whitner)', 'DWG Team Travel (Austin, TX)'.
    Returns "" if none.
    """
    for text in texts:
        if not text:
            continue
        s = str(text).strip()
        low = s.lower()
        m = re.search(r"deal specific\s*[-:]\s*(.+)", low)
        if m:
            return m.group(1).strip().title()
        m = re.search(r"bridge loan\s*\(([^)]+)\)", low)
        if m:
            return m.group(1).strip()
        m = re.search(r"\(([A-Za-z][^)]*(?:,\s*[A-Z]{2})?)\)", s)  # (Austin, TX)
        if m and any(city in m.group(1).lower() for city in
                     ("tx", "ga", "va", "austin", "atlanta", "roanoke")):
            return m.group(1).strip()
        if "jal" in low:
            return "JAL"
        if "mrm" in low or "cmg" in low:
            return "MRM/CMG"
    return ""


def map_category(category, merchant, description, overrides=None):
    """Return (gl_account_name, fsg, confidence, basis)."""
    overrides = overrides or {}
    cat = (category or "").strip()
    cat_low = cat.lower()
    if cat_low in overrides:
        gl = overrides[cat_low]
        return gl, config.COA_BY_NAME[gl][1], config.CONF_DETERMINISTIC, "override"
    text = " ".join(x for x in (cat_low, str(merchant or "").lower(),
                                str(description or "").lower()) if x)
    for pred, gl, conf in RULES:
        try:
            if pred(text):
                return gl, config.COA_BY_NAME[gl][1], conf, f"rule:{gl}"
        except Exception:
            continue
    return "Suspense & Review", config.FSG_SUSPENSE, config.CONF_UNRESOLVED, "no rule matched"
