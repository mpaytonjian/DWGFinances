"""
config.py — Central configuration for the DWG Financial Overview pipeline.

Everything that a controller or CPA might want to tune lives here:
  * File locations
  * Entity identification (account last-four -> legal entity)
  * Materiality / review thresholds
  * Chart of accounts
  * Workbook formatting palette

NOTHING in this file mutates source workbooks. Source files are read-only.
"""
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
SOURCE_DIR = ROOT / "source_workbooks"          # read-only source copies
OUTPUT_DIR = ROOT / "DWG_Financial_Overview_2025_2026"
MAPPING_DIR = ROOT / "mappings"
LOG_DIR = ROOT / "logs"

for _d in (OUTPUT_DIR, MAPPING_DIR, LOG_DIR):
    _d.mkdir(exist_ok=True)

WORKBOOK_NAME = "DWG_Financial_Overview_2025_2026.xlsx"

# ---------------------------------------------------------------------------
# Reporting period
# ---------------------------------------------------------------------------
FY_2025 = 2025
FY_2026 = 2026
YTD_2026_THROUGH = "2026-06-30"   # 2026 data currently runs through June

DISCLAIMER = (
    "Preliminary management reporting compiled from available transaction-level "
    "source data. The information remains subject to bank reconciliation, entity "
    "allocation, accrual adjustments, balance-sheet substantiation, management "
    "review, and CPA approval."
)
REPORT_TITLE = ("Preliminary Management Financial Overview Based Primarily on "
                "Available Cash Activity")

# ---------------------------------------------------------------------------
# Entity master.  Canonical entity names used everywhere downstream.
# ---------------------------------------------------------------------------
ENTITY_DWGCP = "DWG Capital Partners"
ENTITY_DWGCG = "DWG Capital Group"
ENTITY_POS_PARTNERS = "Poseidon Partners"
ENTITY_POS_ASSET = "Poseidon Asset Group"
ENTITY_JOHN = "John/Judd Dunning (Personal)"
ENTITY_ANGELA = "Angela (Personal)"
ENTITY_FAMILY = "Family / Household"
ENTITY_VENMO = "Venmo (Personal)"
ENTITY_UNASSIGNED = "Unassigned / Allocation Required"

ALL_ENTITIES = [
    ENTITY_DWGCP, ENTITY_DWGCG, ENTITY_POS_PARTNERS, ENTITY_POS_ASSET,
    ENTITY_JOHN, ENTITY_ANGELA, ENTITY_FAMILY, ENTITY_VENMO, ENTITY_UNASSIGNED,
]

# The DWG operating group (consolidated operating results are built from these).
DWG_OPERATING_ENTITIES = [ENTITY_DWGCP, ENTITY_DWGCG]

# Account last-four -> canonical entity.  Extend as new statements arrive.
# NOTE: account number is the most deterministic entity signal and overrides
# filename. Confirmed from each workbook's Entity/header block.
ACCOUNT_LAST4_TO_ENTITY = {
    "1004": ENTITY_DWGCP,   # XXXX-XXXXXX-01004  Amex Business Platinum (DWGCP)
    "01004": ENTITY_DWGCP,
    "1005": ENTITY_DWGCG,   # XXXX-XXXXXX-81005  Amex Business Platinum (DWGCG)
    "81005": ENTITY_DWGCG,
    "2000": ENTITY_POS_PARTNERS,   # XXXX-XXXXXX-02000  Poseidon Partners Amex
    "02000": ENTITY_POS_PARTNERS,
    "7008": ENTITY_DWGCP,   # XXXX-XXXXXX-27008  The Plum Card (Entity = DWG Capital Partners per statement)
    "27008": ENTITY_DWGCP,
    "27000": ENTITY_JOHN,   # XXXX-XXXXXX-27000  Amex Platinum — John L Dunning personal
    "1168": ENTITY_DWGCG,   # Chase 1168 — DWG Capital Group operating bank
    "9335": ENTITY_POS_ASSET,  # Chase 9335 — Poseidon Asset Group bank
    "1117": ENTITY_ANGELA,  # Chase 1117 — Angela personal bank
}

# Free-text entity strings found in workbook headers -> canonical entity.
ENTITY_TEXT_MAP = {
    "dwg capital partners": ENTITY_DWGCP,
    "dwgcp": ENTITY_DWGCP,
    "dwg capital group": ENTITY_DWGCG,
    "dwgcg": ENTITY_DWGCG,
    "dwgre": ENTITY_DWGCG,          # "DWG-RE" statements resolve to Capital Group per content
    "dwg-re": ENTITY_DWGCG,
    "dwg real estate": ENTITY_DWGCG,
    "poseidon partners": ENTITY_POS_PARTNERS,
    "poseidon asset group": ENTITY_POS_ASSET,
    "poseidon asset": ENTITY_POS_ASSET,
    "plum card": ENTITY_DWGCP,      # Plum Card statements carry Entity = DWG Capital Partners
    "family": ENTITY_FAMILY,
    "angela": ENTITY_ANGELA,
    "john l dunning": ENTITY_JOHN,
    "john dunning": ENTITY_JOHN,
    "judd": ENTITY_JOHN,
    "venmo": ENTITY_VENMO,
}

# ---------------------------------------------------------------------------
# Materiality / review thresholds (see workbook "Missing Information" & README)
# ---------------------------------------------------------------------------
THRESHOLDS = {
    "individual_review": 10_000,       # any txn >= this amount
    "uncategorized_review": 1_000,     # uncategorized txn >= this amount
    "owner_personal_review": 500,      # owner/personal txn >= this amount
    "deal_cost_review": 5_000,         # deal-specific cost >= this amount
    # unmatched transfers, loan proceeds/payments, cash withdrawals: review regardless
}

# ---------------------------------------------------------------------------
# Confidence scoring bands
# ---------------------------------------------------------------------------
CONF_DETERMINISTIC = 97   # account+merchant+mapping deterministic
CONF_STRONG = 88          # strong evidence, not fully deterministic
CONF_REASONABLE = 70      # reasonable proposal, needs review
CONF_UNRESOLVED = 45      # -> Suspense & Review

# ---------------------------------------------------------------------------
# Financial-statement groups
# ---------------------------------------------------------------------------
FSG_REVENUE = "Revenue"
FSG_COMP = "Compensation"
FSG_OPEX = "Operating Expense"
FSG_DEAL = "Deal & Asset Cost"
FSG_NONOP = "Nonoperating"
FSG_BALANCE = "Balance Sheet"
FSG_SUSPENSE = "Suspense & Review"

# ---------------------------------------------------------------------------
# Chart of Accounts.  (code, name, financial_statement_group)
# Codes: 4xxx revenue, 5xxx compensation, 6xxx opex, 7xxx deal/asset,
#        8xxx nonoperating, 9xxx balance sheet / suspense.
# ---------------------------------------------------------------------------
CHART_OF_ACCOUNTS = [
    # Revenue
    ("4000", "Brokerage Commissions", FSG_REVENUE),
    ("4010", "Acquisition Fees", FSG_REVENUE),
    ("4020", "Asset Management Fees", FSG_REVENUE),
    ("4030", "Property Management Fees", FSG_REVENUE),
    ("4040", "Consulting & Other Fees", FSG_REVENUE),
    ("4050", "Reimbursements (Revenue)", FSG_REVENUE),
    ("4090", "Other Operating Revenue", FSG_REVENUE),
    # Compensation
    ("5000", "Payroll", FSG_COMP),
    ("5010", "Contractor Compensation", FSG_COMP),
    ("5020", "Commissions Paid", FSG_COMP),
    ("5030", "Payroll Taxes", FSG_COMP),
    ("5040", "Employee Benefits", FSG_COMP),
    ("5050", "Recruiting", FSG_COMP),
    # Operating Expenses
    ("6000", "Accounting & Bookkeeping", FSG_OPEX),
    ("6010", "Legal", FSG_OPEX),
    ("6020", "Insurance", FSG_OPEX),
    ("6030", "Software & Technology", FSG_OPEX),
    ("6040", "Data & Listing Platforms", FSG_OPEX),
    ("6050", "Marketing", FSG_OPEX),
    ("6060", "Investor Relations", FSG_OPEX),
    ("6070", "Office", FSG_OPEX),
    ("6080", "Telephone & Internet", FSG_OPEX),
    ("6090", "Travel", FSG_OPEX),
    ("6100", "Meals & Entertainment", FSG_OPEX),
    ("6110", "Conferences", FSG_OPEX),
    ("6120", "Banking & Wire Fees", FSG_OPEX),
    ("6130", "Licenses & Dues", FSG_OPEX),
    ("6140", "Auto", FSG_OPEX),
    ("6150", "Professional Services", FSG_OPEX),
    ("6160", "General & Administrative", FSG_OPEX),
    ("6900", "Other Operating Expense", FSG_OPEX),
    # Deal & Asset Costs
    ("7000", "Deal - Pursuit Costs", FSG_DEAL),
    ("7010", "Deal - Due Diligence", FSG_DEAL),
    ("7020", "Deal - Underwriting", FSG_DEAL),
    ("7030", "Deal - Legal", FSG_DEAL),
    ("7040", "Deal - Travel", FSG_DEAL),
    ("7050", "Deal - Deposits", FSG_DEAL),
    ("7060", "Property - Carry", FSG_DEAL),
    ("7070", "Property - Repairs & Maintenance", FSG_DEAL),
    ("7080", "Property - Taxes", FSG_DEAL),
    ("7090", "Property - Insurance", FSG_DEAL),
    ("7100", "Property - Utilities", FSG_DEAL),
    ("7110", "Leasing Costs", FSG_DEAL),
    ("7120", "Dead-Deal Costs", FSG_DEAL),
    ("7130", "Reimbursable Costs", FSG_DEAL),
    ("7140", "Potential Capitalized Costs", FSG_DEAL),
    # Nonoperating & Balance Sheet
    ("8000", "Interest Expense", FSG_NONOP),
    ("9000", "Loan Principal", FSG_BALANCE),
    ("9010", "Credit Cards Payable", FSG_BALANCE),
    ("9020", "Due From Related Parties", FSG_BALANCE),
    ("9030", "Due To Related Parties", FSG_BALANCE),
    ("9040", "Due From Owner", FSG_BALANCE),
    ("9050", "Due To Owner", FSG_BALANCE),
    ("9060", "Owner Contributions", FSG_BALANCE),
    ("9070", "Owner Distributions", FSG_BALANCE),
    ("9080", "Member Loans", FSG_BALANCE),
    ("9090", "Loan Proceeds", FSG_BALANCE),
    ("9100", "Intercompany Transfers", FSG_BALANCE),
    ("9900", "Suspense & Review", FSG_SUSPENSE),
]
COA_BY_NAME = {name: (code, fsg) for code, name, fsg in CHART_OF_ACCOUNTS}
COA_BY_CODE = {code: (name, fsg) for code, name, fsg in CHART_OF_ACCOUNTS}

# ---------------------------------------------------------------------------
# Institutional workbook formatting palette
# ---------------------------------------------------------------------------
FMT = {
    "navy": "1F2A44",          # dark navy section headers
    "navy_text": "FFFFFF",
    "subhdr": "34517A",        # secondary header blue
    "blue_input": "0000FF",    # hardcoded inputs
    "black_formula": "000000", # formulas
    "green_link": "008000",    # cross-sheet links
    "yellow_review": "FFF2CC", # review-cell fill
    "grey_band": "F2F2F2",
    "red": "C00000",
    "total_border": "808080",
}
NUM_FMT_ACCT = '#,##0.00;[Red](#,##0.00);"-"'   # $ w/ comma, red parens, dash zero
NUM_FMT_INT = '#,##0;[Red](#,##0);"-"'
NUM_FMT_PCT = '0.0%;[Red](0.0%);"-"'
