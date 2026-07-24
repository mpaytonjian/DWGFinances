"""
workbook_output.py — Build DWG_Financial_Overview_2025_2026.xlsx (23 sheets)
with institutional financial-model formatting using xlsxwriter.

Formatting conventions:
  * Dark-navy section headers, white text
  * Hardcoded inputs in blue, formulas black, cross-sheet links green
  * Review cells yellow fill
  * Negatives red in parentheses; zeros as dashes; comma thousands
  * Freeze panes + autofilter on transaction sheets
"""
import xlsxwriter

from . import config
from . import reporting

MASTER_COLUMNS = [
    ("transaction_id", "Transaction ID", 18),
    ("source_file", "Source File", 34),
    ("source_sheet", "Source Sheet", 18),
    ("source_row", "Source Row", 10),
    ("source_entity", "Source Entity", 22),
    ("proposed_reporting_entity", "Proposed Reporting Entity", 22),
    ("account_name", "Account Name", 20),
    ("account_last4", "Acct Last4", 10),
    ("account_type", "Account Type", 12),
    ("transaction_date", "Txn Date", 12),
    ("posting_date", "Posting Date", 12),
    ("year", "Year", 7),
    ("month", "Month", 9),
    ("description_raw", "Description Raw", 34),
    ("description_normalized", "Description Norm", 30),
    ("merchant_normalized", "Merchant Norm", 20),
    ("original_category", "Original Category", 26),
    ("combined_category", "Combined Category", 24),
    ("financial_statement_group", "FS Group", 18),
    ("proposed_gl_account", "Proposed GL Account", 26),
    ("deal_or_asset", "Deal / Asset", 18),
    ("amount_raw", "Amount Raw", 13),
    ("debit", "Debit", 13),
    ("credit", "Credit", 13),
    ("cash_inflow", "Cash Inflow", 13),
    ("cash_outflow", "Cash Outflow", 13),
    ("business_or_personal", "Bus/Pers", 11),
    ("operating_or_nonoperating", "Op/Nonop", 12),
    ("revenue_or_expense", "Rev/Exp", 13),
    ("balance_sheet_activity", "Bal Sheet", 10),
    ("intercompany", "Intercompany", 12),
    ("owner_activity", "Owner Activity", 12),
    ("reimbursement", "Reimb", 8),
    ("credit_card_payment", "CC Payment", 11),
    ("loan_principal", "Loan Prin", 10),
    ("interest", "Interest", 9),
    ("potential_duplicate", "Dup Status", 12),
    ("duplicate_group_id", "Dup Group", 11),
    ("transfer_match_id", "Transfer ID", 12),
    ("confidence_score", "Confidence", 11),
    ("review_status", "Review Status", 15),
    ("review_reason", "Review Reason", 30),
    ("proposed_accounting_treatment", "Proposed Treatment", 44),
    ("management_notes", "Mgmt Notes", 22),
]


class Book:
    def __init__(self, path):
        self.wb = xlsxwriter.Workbook(str(path), {"nan_inf_to_errors": True})
        self._make_formats()

    def _make_formats(self):
        F = config.FMT
        A = config.NUM_FMT_ACCT
        self.f_title = self.wb.add_format({"bold": True, "font_size": 16,
                                           "font_color": F["navy"]})
        self.f_sub = self.wb.add_format({"italic": True, "font_size": 9,
                                         "font_color": "595959"})
        self.f_hdr = self.wb.add_format({"bold": True, "bg_color": F["navy"],
                                         "font_color": F["navy_text"],
                                         "border": 1, "border_color": "FFFFFF",
                                         "align": "center", "valign": "vcenter",
                                         "text_wrap": True})
        self.f_sub_hdr = self.wb.add_format({"bold": True, "bg_color": F["subhdr"],
                                             "font_color": "FFFFFF", "border": 1})
        self.f_label = self.wb.add_format({"bold": True})
        self.f_text = self.wb.add_format({})
        self.f_text_wrap = self.wb.add_format({"text_wrap": True, "valign": "top"})
        self.f_num = self.wb.add_format({"num_format": A, "font_color": F["black_formula"]})
        self.f_num_input = self.wb.add_format({"num_format": A,
                                               "font_color": F["blue_input"]})
        self.f_num_link = self.wb.add_format({"num_format": A,
                                              "font_color": F["green_link"]})
        self.f_num_bold = self.wb.add_format({"num_format": A, "bold": True,
                                              "top": 1, "bottom": 6})
        self.f_total = self.wb.add_format({"num_format": A, "bold": True,
                                           "top": 1, "bottom": 6,
                                           "bg_color": F["grey_band"]})
        self.f_int = self.wb.add_format({"num_format": config.NUM_FMT_INT})
        self.f_pct = self.wb.add_format({"num_format": config.NUM_FMT_PCT})
        self.f_review = self.wb.add_format({"bg_color": F["yellow_review"]})
        self.f_review_num = self.wb.add_format({"bg_color": F["yellow_review"],
                                                "num_format": A})
        self.f_date = self.wb.add_format({"num_format": "yyyy-mm-dd"})
        self.f_disc = self.wb.add_format({"italic": True, "font_size": 9,
                                          "font_color": F["red"], "text_wrap": True})
        self.f_boxhdr = self.wb.add_format({"bold": True, "bg_color": F["red"],
                                            "font_color": "FFFFFF"})

    def sheet(self, name):
        return self.wb.add_worksheet(name[:31])

    def section(self, ws, row, text, span=8):
        ws.merge_range(row, 0, row, span, text, self.f_hdr)
        return row + 1

    def close(self):
        self.wb.close()


def _acct_num(name):
    code, _ = config.COA_BY_NAME.get(name, ("", ""))
    return f"{code} {name}"


def build_workbook(path, master, reports, transfers, controls_results,
                   adjusting_entries, missing_items):
    bk = Book(path)
    _sheet_exec(bk, master, transfers)
    _sheet_pl(bk, "2025 P&L", master, config.FY_2025)
    _sheet_pl(bk, "2026 YTD P&L", master, config.FY_2026)
    _sheet_monthly(bk, master)
    _sheet_entity(bk, master)
    _sheet_revenue(bk, master)
    _sheet_payroll(bk, master)
    _sheet_opex(bk, master)
    _sheet_deals(bk, master)
    _sheet_personal_biz(bk, master)
    _sheet_biz_personal(bk, master)
    _sheet_intercompany(bk, transfers)
    _sheet_owner(bk, master)
    _sheet_debt(bk, master)
    _sheet_cashflow(bk, master)
    _sheet_master(bk, master)
    _sheet_duplicates(bk, master)
    _sheet_uncategorized(bk, master)
    _sheet_adjusting(bk, adjusting_entries)
    _sheet_missing(bk, missing_items)
    _sheet_coa(bk)
    _sheet_mapping(bk, master)
    _sheet_source_control(bk, master, reports, controls_results)
    bk.close()


# ---------------------------------------------------------------------------
# Individual sheets
# ---------------------------------------------------------------------------
def _kpi_block(bk, ws, row, title, totals):
    ws.write(row, 0, title, bk.f_sub_hdr)
    ws.write(row, 1, "", bk.f_sub_hdr)
    row += 1
    for label, key in [("Revenue", "revenue"), ("Compensation", "compensation"),
                       ("Operating Expenses", "opex"), ("Deal & Asset Costs", "deal"),
                       ("Total Expenses", "total_expense"),
                       ("Preliminary Operating Income / EBITDA", "operating_income")]:
        f = bk.f_total if key in ("total_expense", "operating_income") else bk.f_num
        ws.write(row, 0, label, bk.f_label if "Prelim" in label else bk.f_text)
        ws.write_number(row, 1, round(totals[key], 2), f)
        row += 1
    return row + 1


def _sheet_exec(bk, master, transfers):
    ws = bk.sheet("Executive Overview")
    ws.set_column(0, 0, 42)
    ws.set_column(1, 6, 16)
    ws.hide_gridlines(2)
    ws.write(0, 0, "DWG — Preliminary Management Financial Overview", bk.f_title)
    ws.write(1, 0, config.REPORT_TITLE, bk.f_sub)
    ws.write(2, 0, f"2025 full year and 2026 YTD (through {config.YTD_2026_THROUGH})",
             bk.f_sub)

    DWG = config.DWG_OPERATING_ENTITIES
    t25 = reporting.pl_totals(master, config.FY_2025, DWG)
    t26 = reporting.pl_totals(master, config.FY_2026, DWG)
    row = 4
    row = _kpi_block(bk, ws, row, "2025 DWG Operating (CG+CP, Full Year — Preliminary)", t25)
    row = _kpi_block(bk, ws, row, f"2026 DWG Operating YTD (through {config.YTD_2026_THROUGH})", t26)
    # Related entities shown separately — NOT consolidated into DWG results
    row = _kpi_block(bk, ws, row, "Poseidon Entities (separate — not in DWG results) 2025",
                     reporting.pl_totals(master, config.FY_2025,
                                         [config.ENTITY_POS_PARTNERS, config.ENTITY_POS_ASSET]))
    row = _kpi_block(bk, ws, row, "Poseidon Entities (separate) 2026 YTD",
                     reporting.pl_totals(master, config.FY_2026,
                                         [config.ENTITY_POS_PARTNERS, config.ENTITY_POS_ASSET]))

    # Operating metrics
    ws.write(row, 0, "Key Operating Metrics", bk.f_sub_hdr)
    ws.write(row, 1, "", bk.f_sub_hdr); row += 1
    m25 = reporting.monthly_pl(master, config.FY_2025, DWG)
    m26 = reporting.monthly_pl(master, config.FY_2026, DWG)
    avg_opex_25 = (sum(v["expense"] for v in m25.values()) / len(m25)) if m25 else 0
    avg_opex_26 = (sum(v["expense"] for v in m26.values()) / len(m26)) if m26 else 0
    payroll = sum(reporting.pl_summary(master, entities=DWG).get(config.FSG_COMP, {}).values())
    personal_biz = sum(abs(r["amount_raw"]) for r in reporting.personal_paid_by_business(master))
    biz_personal = sum(abs(r["amount_raw"]) for r in reporting.business_paid_personally(master))
    unmatched_xfer = sum(1 for t in transfers if t["status"].startswith("Unmatched"))
    uncat = sum(r["cash_outflow"] for r in master
                if r["combined_category"] == "Suspense & Review"
                and r["potential_duplicate"] != "Duplicate")
    reviews = reporting.review_items(master)
    review_amt = sum(abs(r["amount_raw"]) for r in reviews)
    for label, val in [
        ("Avg Monthly Operating Expense — 2025", avg_opex_25),
        ("Avg Monthly Operating Expense — 2026 YTD", avg_opex_26),
        ("Compensation / Contractor Run-Rate (period total)", payroll),
        ("Personal Expenses Paid by Business", personal_biz),
        ("Business Expenses Paid Personally", biz_personal),
        ("Uncategorized (Suspense) Amount", uncat),
        ("Review Items — $ Amount", review_amt),
    ]:
        ws.write(row, 0, label, bk.f_text)
        ws.write_number(row, 1, round(val, 2), bk.f_num)
        row += 1
    ws.write(row, 0, "Unmatched Intercompany Transfers (count)", bk.f_text)
    ws.write_number(row, 1, unmatched_xfer, bk.f_int); row += 1
    ws.write(row, 0, "Review Items (count)", bk.f_text)
    ws.write_number(row, 1, len(reviews), bk.f_int); row += 2

    # Reliability box
    ws.write(row, 0, "RELIABILITY & MISSING BOOKS", bk.f_boxhdr)
    ws.write(row, 1, "", bk.f_boxhdr); row += 1
    ws.merge_range(row, 0, row + 4, 6, config.DISCLAIMER + "  "
                   "Bank statements, credit-card statement balances, payroll "
                   "registers, loan schedules, A/R, A/P, and equity balances are "
                   "not yet loaded — see the 'Missing Information' sheet.",
                   bk.f_disc)
    row += 6

    # Monthly chart data (write a small table then chart it)
    chart_start = row
    ws.write(row, 0, "Month", bk.f_sub_hdr)
    ws.write(row, 1, "Revenue", bk.f_sub_hdr)
    ws.write(row, 2, "Expense", bk.f_sub_hdr)
    row += 1
    all_months = sorted(set(list(m25) + list(m26)) |
                        set(f"2026-{i:02d}" for i in range(1, 7)))
    combined = {**m25, **m26}
    data_first = row
    for mo in all_months:
        v = combined.get(mo, {"revenue": 0, "expense": 0})
        ws.write(row, 0, mo, bk.f_text)
        ws.write_number(row, 1, round(v["revenue"], 2), bk.f_num)
        ws.write_number(row, 2, round(v["expense"], 2), bk.f_num)
        row += 1
    data_last = row - 1
    if data_last >= data_first:
        chart = bk.wb.add_chart({"type": "column"})
        for col, name, color in [(1, "Revenue", "#2E7D32"), (2, "Expense", "#C0392B")]:
            chart.add_series({
                "name": name,
                "categories": ["Executive Overview", data_first, 0, data_last, 0],
                "values": ["Executive Overview", data_first, col, data_last, col],
                "fill": {"color": color},
            })
        chart.set_title({"name": "Monthly Revenue vs Expense"})
        chart.set_size({"width": 640, "height": 320})
        ws.insert_chart(chart_start, 4, chart)

    # Expense composition pie
    top = reporting.top_categories(master, n=8, entities=DWG)
    if top:
        pie_start = data_last + 3
        ws.write(pie_start, 0, "Top Expense Categories", bk.f_sub_hdr)
        ws.write(pie_start, 1, "Amount", bk.f_sub_hdr)
        pr = pie_start + 1
        pf, pl = pr, pr + len(top) - 1
        for cat, amt in top:
            ws.write(pr, 0, cat, bk.f_text)
            ws.write_number(pr, 1, round(amt, 2), bk.f_num)
            pr += 1
        pie = bk.wb.add_chart({"type": "pie"})
        pie.add_series({
            "name": "Expense Composition",
            "categories": ["Executive Overview", pf, 0, pl, 0],
            "values": ["Executive Overview", pf, 1, pl, 1],
        })
        pie.set_title({"name": "Expense Composition"})
        pie.set_size({"width": 500, "height": 320})
        ws.insert_chart(pie_start, 4, pie)

    ws.freeze_panes(4, 0)


def _write_pl_body(bk, ws, master, year, entities=None, start=4):
    s = reporting.pl_summary(master, year, entities)
    row = start
    order = [(config.FSG_REVENUE, "REVENUE"), (config.FSG_COMP, "COMPENSATION"),
             (config.FSG_OPEX, "OPERATING EXPENSES"),
             (config.FSG_DEAL, "DEAL & ASSET COSTS")]
    subtotals = {}
    for fsg, title in order:
        ws.write(row, 0, title, bk.f_sub_hdr)
        ws.write(row, 1, "", bk.f_sub_hdr); row += 1
        accounts = s.get(fsg, {})
        sub = 0.0
        for gl in sorted(accounts, key=lambda g: config.COA_BY_NAME[g][0]):
            amt = accounts[gl]
            ws.write(row, 0, "   " + _acct_num(gl), bk.f_text)
            ws.write_number(row, 1, round(amt, 2), bk.f_num)
            sub += amt
            row += 1
        ws.write(row, 0, f"Total {title.title()}", bk.f_label)
        ws.write_number(row, 1, round(sub, 2), bk.f_total)
        subtotals[fsg] = sub
        row += 2
    rev = subtotals.get(config.FSG_REVENUE, 0)
    exp = (subtotals.get(config.FSG_COMP, 0) + subtotals.get(config.FSG_OPEX, 0)
           + subtotals.get(config.FSG_DEAL, 0))
    ws.write(row, 0, "PRELIMINARY OPERATING INCOME / EBITDA", bk.f_label)
    ws.write_number(row, 1, round(rev - exp, 2), bk.f_total)
    return row


def _sheet_pl(bk, name, master, year):
    ws = bk.sheet(name)
    ws.set_column(0, 0, 40); ws.set_column(1, 1, 18)
    ws.hide_gridlines(2)
    ws.write(0, 0, f"{name} — {config.ENTITY_DWGCP} + {config.ENTITY_DWGCG} (DWG Operating, Consolidated)",
             bk.f_title)
    ws.write(1, 0, config.REPORT_TITLE, bk.f_sub)
    ws.write(2, 0, "DWG operating entities only. Excludes Poseidon/personal entities, credit-card "
             "payments, intercompany transfers, personal items, duplicates.", bk.f_sub)
    _write_pl_body(bk, ws, master, year, entities=config.DWG_OPERATING_ENTITIES, start=4)
    ws.freeze_panes(4, 0)


def _sheet_monthly(bk, master):
    ws = bk.sheet("Monthly P&L")
    ws.hide_gridlines(2)
    ws.write(0, 0, "Monthly P&L — Consolidated DWG Operating (CG+CP only)", bk.f_title)
    ws.write(1, 0, config.REPORT_TITLE, bk.f_sub)
    col = 0
    ws.set_column(0, 0, 22)
    row0 = 3
    for year in (config.FY_2025, config.FY_2026):
        m = reporting.monthly_pl(master, year, config.DWG_OPERATING_ENTITIES)
        ws.write(row0, col, f"{year}", bk.f_hdr)
        ws.write(row0, col + 1, "Revenue", bk.f_hdr)
        ws.write(row0, col + 2, "Expense", bk.f_hdr)
        ws.write(row0, col + 3, "Net", bk.f_hdr)
        ws.set_column(col + 1, col + 3, 15)
        r = row0 + 1
        tr = te = 0.0
        for mo, v in sorted(m.items()):
            ws.write(r, col, mo, bk.f_text)
            ws.write_number(r, col + 1, round(v["revenue"], 2), bk.f_num)
            ws.write_number(r, col + 2, round(v["expense"], 2), bk.f_num)
            ws.write_number(r, col + 3, round(v["net"], 2), bk.f_num)
            tr += v["revenue"]; te += v["expense"]; r += 1
        ws.write(r, col, "Total", bk.f_label)
        ws.write_number(r, col + 1, round(tr, 2), bk.f_total)
        ws.write_number(r, col + 2, round(te, 2), bk.f_total)
        ws.write_number(r, col + 3, round(tr - te, 2), bk.f_total)
        col += 5
    ws.freeze_panes(row0 + 1, 1)


def _sheet_entity(bk, master):
    ws = bk.sheet("Entity Comparison")
    ws.hide_gridlines(2)
    ws.write(0, 0, "Entity Comparison (before eliminations)", bk.f_title)
    ws.write(1, 0, config.REPORT_TITLE, bk.f_sub)
    headers = ["Entity", "2025 Revenue", "2025 Expense", "2025 Op Income",
               "2026 Revenue", "2026 Expense", "2026 Op Income"]
    ws.set_column(0, 0, 30); ws.set_column(1, 6, 16)
    r = 3
    for c, h in enumerate(headers):
        ws.write(r, c, h, bk.f_hdr)
    r += 1
    for ent in config.ALL_ENTITIES:
        a = reporting.pl_totals(master, config.FY_2025, [ent])
        b = reporting.pl_totals(master, config.FY_2026, [ent])
        if not any([a["revenue"], a["total_expense"], b["revenue"], b["total_expense"]]):
            continue
        ws.write(r, 0, ent, bk.f_text)
        for c, v in enumerate([a["revenue"], a["total_expense"], a["operating_income"],
                               b["revenue"], b["total_expense"], b["operating_income"]], 1):
            ws.write_number(r, c, round(v, 2), bk.f_num)
        r += 1
    ws.freeze_panes(4, 1)
    ws.autofilter(3, 0, r - 1, 6)


def _detail_sheet(bk, name, title, rows, note=""):
    ws = bk.sheet(name)
    ws.hide_gridlines(2)
    ws.write(0, 0, title, bk.f_title)
    ws.write(1, 0, config.REPORT_TITLE, bk.f_sub)
    if note:
        ws.write(2, 0, note, bk.f_sub)
    cols = [("transaction_date", "Date", 12), ("source_entity", "Entity", 22),
            ("source_file", "Source File", 30), ("merchant_normalized", "Merchant", 20),
            ("description_raw", "Description", 32), ("original_category", "Orig Cat", 22),
            ("combined_category", "GL Account", 22), ("deal_or_asset", "Deal", 16),
            ("amount_raw", "Amount", 13), ("business_or_personal", "B/P", 9),
            ("confidence_score", "Conf", 8), ("review_status", "Review", 14),
            ("proposed_accounting_treatment", "Proposed Treatment", 42)]
    hr = 4
    for c, (_, h, w) in enumerate(cols):
        ws.write(hr, c, h, bk.f_hdr); ws.set_column(c, c, w)
    r = hr + 1
    total = 0.0
    for row in rows:
        for c, (key, _, _) in enumerate(cols):
            v = row.get(key, "")
            if key == "amount_raw":
                fmt = bk.f_review_num if row["review_status"] == "Review" else bk.f_num
                ws.write_number(r, c, round(v, 2), fmt)
                total += v
            elif key == "confidence_score":
                ws.write_number(r, c, v, bk.f_int)
            else:
                fmt = bk.f_review if row["review_status"] == "Review" else bk.f_text
                ws.write(r, c, str(v), fmt)
        r += 1
    ws.write(r, 0, "TOTAL", bk.f_label)
    ws.write_number(r, 8, round(total, 2), bk.f_total)
    ws.freeze_panes(hr + 1, 0)
    ws.autofilter(hr, 0, max(r - 1, hr), len(cols) - 1)
    return ws


def _sheet_revenue(bk, master):
    # Revenue-review table: every classified-revenue row PLUS every other
    # material inflow (>= $1,000) so no cash-in escapes the revenue decision.
    rows = [r for r in master if r["potential_duplicate"] != "Duplicate"
            and (r["financial_statement_group"] == config.FSG_REVENUE
                 or (r["cash_inflow"] >= 1000
                     and r["credit_card_payment"] != "Yes"))]
    rows.sort(key=lambda r: -r["cash_inflow"])
    _detail_sheet(bk, "Revenue Detail", "Revenue Detail & Material Inflow Review", rows,
                  "Every material inflow with proposed treatment (revenue vs transfer vs "
                  "contribution vs pass-through). Only confirmed revenue rows enter the P&L.")


def _sheet_payroll(bk, master):
    rows = [r for r in master if r["financial_statement_group"] == config.FSG_COMP
            and r["potential_duplicate"] != "Duplicate"]
    _detail_sheet(bk, "Payroll and Contractors", "Payroll & Contractor Compensation", rows)


def _sheet_opex(bk, master):
    rows = [r for r in master if r["financial_statement_group"] == config.FSG_OPEX
            and r["business_or_personal"] != "Personal"
            and r["potential_duplicate"] != "Duplicate"]
    rows.sort(key=lambda r: -abs(r["amount_raw"]))
    _detail_sheet(bk, "Operating Expenses", "Operating Expenses", rows)


def _sheet_deals(bk, master):
    rows = [r for r in master if (r["financial_statement_group"] == config.FSG_DEAL
            or r["deal_or_asset"]) and r["potential_duplicate"] != "Duplicate"]
    rows.sort(key=lambda r: (r["deal_or_asset"], -abs(r["amount_raw"])))
    _detail_sheet(bk, "Deal and Asset Costs", "Deal & Asset Costs", rows,
                  "Retain deal/asset name. Flag capitalizable / reimbursable for CPA review.")


def _sheet_personal_biz(bk, master):
    rows = reporting.personal_paid_by_business(master)
    rows.sort(key=lambda r: -abs(r["amount_raw"]))
    _detail_sheet(bk, "Personal Paid by Business", "Personal Expenses Paid by Business",
                  rows, "Propose Due From Owner / Owner Distribution — excluded from EBITDA.")


def _sheet_biz_personal(bk, master):
    rows = reporting.business_paid_personally(master)
    rows.sort(key=lambda r: -abs(r["amount_raw"]))
    _detail_sheet(bk, "Business Paid Personally", "Business Expenses Paid Personally",
                  rows, "Propose Due To Owner / reimbursable — reported separately until approved.")


def _sheet_intercompany(bk, transfers):
    ws = bk.sheet("Intercompany Reconciliation")
    ws.hide_gridlines(2)
    ws.write(0, 0, "Intercompany & Transfer Reconciliation", bk.f_title)
    ws.write(1, 0, config.REPORT_TITLE, bk.f_sub)
    cols = ["Transfer ID", "Status", "Sending Entity", "Receiving Entity",
            "Send Date", "Send Amt", "Recv Date", "Recv Amt", "Timing (days)",
            "Proposed Treatment"]
    widths = [12, 24, 26, 26, 12, 14, 12, 14, 12, 44]
    hr = 3
    for c, (h, w) in enumerate(zip(cols, widths)):
        ws.write(hr, c, h, bk.f_hdr); ws.set_column(c, c, w)
    r = hr + 1
    for t in transfers:
        ws.write(r, 0, t["transfer_match_id"], bk.f_text)
        fmt = bk.f_review if t["status"].startswith("Unmatched") else bk.f_text
        ws.write(r, 1, t["status"], fmt)
        ws.write(r, 2, t["sending_entity"], bk.f_text)
        ws.write(r, 3, t["receiving_entity"], bk.f_text)
        ws.write(r, 4, t["send_date"], bk.f_text)
        ws.write(r, 5, t["send_amount"] if t["send_amount"] != "" else "", bk.f_num if t["send_amount"] != "" else bk.f_text)
        ws.write(r, 6, t["recv_date"], bk.f_text)
        ws.write(r, 7, t["recv_amount"] if t["recv_amount"] != "" else "", bk.f_num if t["recv_amount"] != "" else bk.f_text)
        ws.write(r, 8, t["timing_diff_days"], bk.f_text)
        ws.write(r, 9, t["proposed_treatment"], bk.f_text_wrap)
        r += 1
    ws.freeze_panes(hr + 1, 0)
    if r > hr + 1:
        ws.autofilter(hr, 0, r - 1, len(cols) - 1)


def _sheet_owner(bk, master):
    rows = [r for r in master if r["owner_activity"] == "Yes"
            and r["potential_duplicate"] != "Duplicate"]
    rows.sort(key=lambda r: -abs(r["amount_raw"]))
    _detail_sheet(bk, "Owner Activity", "Owner Activity (Contributions / Distributions / Personal)",
                  rows)


def _sheet_debt(bk, master):
    rows = [r for r in master if (r["credit_card_payment"] == "Yes"
            or r["loan_principal"] == "Yes" or r["interest"] == "Yes"
            or r["combined_category"] in ("Loan Proceeds", "Credit Cards Payable",
                                          "Member Loans"))
            and r["potential_duplicate"] != "Duplicate"]
    rows.sort(key=lambda r: r["transaction_date"])
    _detail_sheet(bk, "Debt and Credit Cards", "Debt, Credit-Card Payments & Loan Activity",
                  rows, "Credit-card payments are balance-sheet; principal/interest split flagged where unknown.")


def _sheet_cashflow(bk, master):
    ws = bk.sheet("Cash Flow Overview")
    ws.hide_gridlines(2)
    ws.write(0, 0, "Cash Flow Overview (cash-basis, per available card activity)", bk.f_title)
    ws.write(1, 0, config.REPORT_TITLE, bk.f_sub)
    ws.set_column(0, 0, 34); ws.set_column(1, 3, 16)
    hr = 3
    for c, h in enumerate(["Period", "Inflows", "Outflows", "Net"]):
        ws.write(hr, c, h, bk.f_hdr)
    r = hr + 1
    for label, yr in [("2025", config.FY_2025), ("2026 YTD", config.FY_2026)]:
        cf = reporting.cash_flow(master, yr)
        ws.write(r, 0, label, bk.f_text)
        ws.write_number(r, 1, round(cf["inflow"], 2), bk.f_num)
        ws.write_number(r, 2, round(cf["outflow"], 2), bk.f_num)
        ws.write_number(r, 3, round(cf["net"], 2), bk.f_num)
        r += 1
    ws.write(r, 0, "Note", bk.f_label)
    ws.merge_range(r, 1, r + 2, 3,
                   "Cash flow reflects credit-card charge activity only until bank "
                   "statements are loaded. Not a statement of cash flows under GAAP.",
                   bk.f_disc)


def _sheet_master(bk, master):
    ws = bk.sheet("Master Transactions")
    ws.hide_gridlines(2)
    ws.write(0, 0, "Master Transactions (normalized, full audit trail)", bk.f_title)
    ws.write(1, 0, config.REPORT_TITLE, bk.f_sub)
    hr = 3
    for c, (_, h, w) in enumerate(MASTER_COLUMNS):
        ws.write(hr, c, h, bk.f_hdr); ws.set_column(c, c, w)
    r = hr + 1
    numeric = {"amount_raw", "debit", "credit", "cash_inflow", "cash_outflow"}
    for row in master:
        review = row["review_status"] == "Review"
        for c, (key, _, _) in enumerate(MASTER_COLUMNS):
            v = row.get(key, "")
            if key in numeric:
                ws.write_number(r, c, round(float(v or 0), 2),
                                bk.f_review_num if review else bk.f_num)
            elif key in ("confidence_score", "source_row", "year"):
                try:
                    ws.write_number(r, c, int(v), bk.f_int)
                except (ValueError, TypeError):
                    ws.write(r, c, str(v), bk.f_text)
            else:
                ws.write(r, c, "" if v is None else str(v),
                         bk.f_review if review else bk.f_text)
        r += 1
    ws.freeze_panes(hr + 1, 4)
    ws.autofilter(hr, 0, max(r - 1, hr), len(MASTER_COLUMNS) - 1)


def _sheet_duplicates(bk, master):
    rows = [r for r in master if r["duplicate_group_id"]]
    rows.sort(key=lambda r: (r["duplicate_group_id"], r["potential_duplicate"]))
    ws = _detail_sheet(bk, "Duplicate Review", "Duplicate Review (retained, not deleted)", rows,
                       "Primary rows kept in totals; Duplicate rows excluded but retained for audit.")


def _sheet_uncategorized(bk, master):
    rows = [r for r in master if r["combined_category"] == "Suspense & Review"
            or r["confidence_score"] < config.CONF_REASONABLE]
    rows = [r for r in rows if r["potential_duplicate"] != "Duplicate"]
    rows.sort(key=lambda r: -abs(r["amount_raw"]))
    _detail_sheet(bk, "Uncategorized Review", "Uncategorized / Low-Confidence Review", rows,
                  "Assigned to Suspense & Review until classified. Not in operating results.")


def _sheet_adjusting(bk, entries):
    ws = bk.sheet("Proposed Adjusting Entries")
    ws.hide_gridlines(2)
    ws.write(0, 0, "Proposed Adjusting Entries (ALL PROPOSED — not posted)", bk.f_title)
    ws.write(1, 0, config.REPORT_TITLE, bk.f_sub)
    cols = ["Entry ID", "Date", "Entity", "Debit Account", "Credit Account",
            "Amount", "Explanation", "Source Txn IDs", "Support", "Approval"]
    widths = [10, 12, 22, 24, 24, 14, 44, 26, 16, 12]
    hr = 3
    for c, (h, w) in enumerate(zip(cols, widths)):
        ws.write(hr, c, h, bk.f_hdr); ws.set_column(c, c, w)
    r = hr + 1
    for e in entries:
        ws.write(r, 0, e["entry_id"], bk.f_text)
        ws.write(r, 1, e["entry_date"], bk.f_text)
        ws.write(r, 2, e["entity"], bk.f_text)
        ws.write(r, 3, e["debit_account"], bk.f_text)
        ws.write(r, 4, e["credit_account"], bk.f_text)
        ws.write_number(r, 5, round(e["amount"], 2), bk.f_num)
        ws.write(r, 6, e["explanation"], bk.f_text_wrap)
        ws.write(r, 7, e["source_transaction_ids"], bk.f_text)
        ws.write(r, 8, e["support_status"], bk.f_review)
        ws.write(r, 9, e["approval_status"], bk.f_review)
        r += 1
    ws.freeze_panes(hr + 1, 0)
    if r > hr + 1:
        ws.autofilter(hr, 0, r - 1, len(cols) - 1)


def _sheet_missing(bk, items):
    ws = bk.sheet("Missing Information")
    ws.hide_gridlines(2)
    ws.write(0, 0, "Missing Information Schedule", bk.f_title)
    ws.write(1, 0, "Items required to move from preliminary cash view to complete books.",
             bk.f_sub)
    hr = 3
    for c, h in enumerate(["#", "Missing Item", "Why It Matters", "Priority"]):
        ws.write(hr, c, h, bk.f_hdr)
    ws.set_column(0, 0, 5); ws.set_column(1, 1, 40); ws.set_column(2, 2, 52)
    ws.set_column(3, 3, 12)
    r = hr + 1
    for i, (item, why, pri) in enumerate(items, 1):
        ws.write_number(r, 0, i, bk.f_int)
        ws.write(r, 1, item, bk.f_text)
        ws.write(r, 2, why, bk.f_text_wrap)
        ws.write(r, 3, pri, bk.f_review if pri == "High" else bk.f_text)
        r += 1
    ws.freeze_panes(hr + 1, 0)


def _sheet_coa(bk):
    ws = bk.sheet("Chart of Accounts")
    ws.hide_gridlines(2)
    ws.write(0, 0, "Proposed Management Chart of Accounts", bk.f_title)
    hr = 2
    for c, h in enumerate(["Code", "Account", "Financial Statement Group"]):
        ws.write(hr, c, h, bk.f_hdr)
    ws.set_column(0, 0, 10); ws.set_column(1, 1, 34); ws.set_column(2, 2, 22)
    r = hr + 1
    for code, name, fsg in config.CHART_OF_ACCOUNTS:
        ws.write(r, 0, code, bk.f_text)
        ws.write(r, 1, name, bk.f_text)
        ws.write(r, 2, fsg, bk.f_text)
        r += 1
    ws.freeze_panes(hr + 1, 0)
    ws.autofilter(hr, 0, r - 1, 2)


def _sheet_mapping(bk, master):
    ws = bk.sheet("Category Mapping")
    ws.hide_gridlines(2)
    ws.write(0, 0, "Category Mapping (source category -> GL account)", bk.f_title)
    ws.write(1, 0, "Persisted in mappings/category_overrides.csv — edit to lock management decisions.",
             bk.f_sub)
    seen = {}
    for r in master:
        key = (r["original_category"], r["combined_category"],
               r["financial_statement_group"])
        seen[key] = seen.get(key, 0) + 1
    hr = 3
    for c, h in enumerate(["Source Category", "Mapped GL Account", "FS Group", "Count"]):
        ws.write(hr, c, h, bk.f_hdr)
    ws.set_column(0, 0, 34); ws.set_column(1, 1, 26); ws.set_column(2, 2, 20)
    row = hr + 1
    for (oc, gl, fsg), n in sorted(seen.items(), key=lambda kv: -kv[1]):
        ws.write(row, 0, oc or "(blank)", bk.f_text)
        ws.write(row, 1, gl, bk.f_text)
        ws.write(row, 2, fsg, bk.f_text)
        ws.write_number(row, 3, n, bk.f_int)
        row += 1
    ws.freeze_panes(hr + 1, 0)
    ws.autofilter(hr, 0, row - 1, 3)


def _sheet_source_control(bk, master, reports, controls_results):
    ws = bk.sheet("Source Control")
    ws.hide_gridlines(2)
    ws.write(0, 0, "Source Control & Reconciliation", bk.f_title)
    ws.write(1, 0, config.DISCLAIMER, bk.f_disc)

    # Controls results
    ws.write(3, 0, "AUTOMATED CONTROLS", bk.f_sub_hdr)
    ws.write(3, 1, "", bk.f_sub_hdr); ws.write(3, 2, "", bk.f_sub_hdr)
    ws.set_column(0, 0, 46); ws.set_column(1, 1, 10); ws.set_column(2, 2, 40)
    r = 4
    for cr in controls_results:
        ws.write(r, 0, cr["control"], bk.f_text)
        ws.write(r, 1, "PASS" if cr["passed"] else "FAIL",
                 bk.f_text if cr["passed"] else bk.f_review)
        ws.write(r, 2, cr["detail"], bk.f_text)
        r += 1
    r += 1

    # Per-file reconciliation
    recon = reporting.source_reconciliation(master, reports)
    ws.write(r, 0, "PER-FILE RECONCILIATION", bk.f_sub_hdr); r += 1
    cols = ["File", "Entity", "Acct", "Imported", "Inflows", "Outflows", "Net",
            "Dups", "Xfers", "CC Pmts", "Personal", "Review", "Reconciled"]
    hr = r
    for c, h in enumerate(cols):
        ws.write(hr, c, h, bk.f_hdr)
    for c in range(3, 7):
        ws.set_column(c, c, 14)
    r = hr + 1
    for x in recon:
        ws.write(r, 0, x["file"], bk.f_text)
        ws.write(r, 1, x["entity"], bk.f_text)
        ws.write(r, 2, x["account"], bk.f_text)
        ws.write_number(r, 3, x["imported"], bk.f_int)
        ws.write_number(r, 4, round(x["gross_inflows"], 2), bk.f_num)
        ws.write_number(r, 5, round(x["gross_outflows"], 2), bk.f_num)
        ws.write_number(r, 6, round(x["net"], 2), bk.f_num)
        ws.write_number(r, 7, x["duplicates"], bk.f_int)
        ws.write_number(r, 8, x["transfers"], bk.f_int)
        ws.write_number(r, 9, x["cc_payments"], bk.f_int)
        ws.write_number(r, 10, x["personal"], bk.f_int)
        ws.write_number(r, 11, x["review"], bk.f_int)
        ws.write(r, 12, x["reconciled"],
                 bk.f_text if x["reconciled"] in ("Tie", "n/a") else bk.f_review)
        r += 1
    ws.freeze_panes(hr + 1, 0)
