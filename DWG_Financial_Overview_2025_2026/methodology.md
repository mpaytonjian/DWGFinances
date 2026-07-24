# Methodology — DWG Financial Overview Pipeline

Preliminary management reporting compiled from available transaction-level source data. The information remains subject to bank reconciliation, entity allocation, accrual adjustments, balance-sheet substantiation, management review, and CPA approval.

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
and matched on equal amount within a 5-day window. Matched
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
Individual review ≥ $10,000;
uncategorized ≥ $1,000;
owner/personal ≥ $500;
deal cost ≥ $5,000; all unmatched transfers,
loan proceeds/payments, and cash withdrawals reviewed regardless of amount.

## Known limitations
Cash/charge basis only; no bank reconciliations, accruals, balance sheet, or
equity roll-forward. Not GAAP/tax/reviewed/audited. Results are preliminary and
subject to CPA approval.
