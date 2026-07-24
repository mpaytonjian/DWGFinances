# DWG Financial Overview — 2025 & 2026 YTD

Preliminary management financial overview compiled from transaction-level source
workbooks. **Not** GAAP, tax-basis, reviewed, or audited books.

> Preliminary management reporting compiled from available transaction-level
> source data. The information remains subject to bank reconciliation, entity
> allocation, accrual adjustments, balance-sheet substantiation, management
> review, and CPA approval.

## Layout

```
source_workbooks/                 read-only source copies (never modified)
pipeline/                         modular Python pipeline
  config.py                       entities, COA, thresholds, formatting
  ingest.py                       read workbooks, pick txn sheet, detect layout
  normalize.py                    dates, signs, merchant/description normalization
  entity_rules.py                 legal-entity resolution
  category_rules.py               source category -> Chart of Accounts
  accounting_logic.py             per-transaction classification -> master row
  duplicate_detection.py          deterministic duplicate fingerprints
  transfer_matching.py            intercompany / card-payment leg matching
  adjusting.py                    proposed adjusting entries + missing-info schedule
  controls.py                     automated control checks
  reporting.py                    rollups / aggregations
  workbook_output.py             23-sheet institutional workbook
  main.py                         orchestrator
mappings/
  category_overrides.csv          lock management decisions (survives re-runs)
tests/test_controls.py            assertion-based controls
DWG_Financial_Overview_2025_2026/ ALL deliverables (xlsx, csv, md)
logs/pipeline.log                 process log
```

## Deliverables (in `DWG_Financial_Overview_2025_2026/`)

- `DWG_Financial_Overview_2025_2026.xlsx` — 23 worksheets
- `executive_summary.md`
- `review_items.csv`
- `adjusting_entries.csv`
- `source_reconciliation.csv`
- `methodology.md`
- `master_transactions.csv` (full audit trail)
- `config_thresholds.md`, `run_summary.json`

## Rerun after adding new files

1. Copy any new `.xlsx` source files into `source_workbooks/`.
   (Source workbooks are opened read-only and SHA-256-verified unchanged.)
2. Run:

   ```bash
   pip install pandas openpyxl xlsxwriter      # first time only
   python -m pipeline.main
   ```

3. Run the controls:

   ```bash
   python tests/test_controls.py
   ```

4. To lock a classification decision so it survives re-runs, add a row to
   `mappings/category_overrides.csv`:

   ```csv
   source_category,gl_account
   Employee MISC,General & Administrative
   ```

If any **critical** control fails, `main.py` stops before writing the final
workbook and writes `control_failure_report.txt` instead.

## Status of source data

Only the transaction-level Amex charge files currently loaded are reflected.
The remaining workbooks named in the assignment (DWG Capital Group/Partners
full-year bank activity, Poseidon entities, Plum Card, Family Amex, John L.
Dunning, Angela, Venmo) are **not yet loaded** — headline figures will change
materially as they arrive. See the workbook's *Missing Information* sheet.
