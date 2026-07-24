# Configuration & Review Thresholds

These thresholds live in `pipeline/config.py` (`THRESHOLDS`) and are surfaced
here and on the workbook's Source Control sheet.

| Rule | Threshold |
|---|--:|
| Individual review (any txn) | $10,000 |
| Uncategorized review | $1,000 |
| Owner / personal review | $500 |
| Deal-specific cost review | $5,000 |
| Unmatched transfers | any amount |
| Loan proceeds / payments | any amount |
| Cash withdrawals | any amount |

Confidence bands: ≥95 deterministic · 80–94 strong · 60–79 review · <60 suspense.
