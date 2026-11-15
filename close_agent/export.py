"""Write the close package: one Excel workbook for review, the JE upload file, and the close memo."""
from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .engine import CloseRun

HEADER = PatternFill("solid", fgColor="1F3A5F")
FLAG = PatternFill("solid", fgColor="FDECEA")
OK = PatternFill("solid", fgColor="E8F5E9")
MONEY = '#,##0.00;(#,##0.00);"-"'
PCT = "0.0%"


def _sheet(wb, title, headers, rows, money_cols=(), pct_cols=(), widths=None):
    ws = wb.create_sheet(title)
    ws.append(headers)
    for c in ws[1]:
        c.font, c.fill = Font(bold=True, color="FFFFFF"), HEADER
    for r in rows:
        ws.append(list(r))
    for idx in money_cols:
        for cell in ws.iter_cols(min_col=idx, max_col=idx, min_row=2):
            for c in cell:
                c.number_format = MONEY
    for idx in pct_cols:
        for cell in ws.iter_cols(min_col=idx, max_col=idx, min_row=2):
            for c in cell:
                c.number_format = PCT
    for i, h in enumerate(headers, 1):
        ws.column_dimensions[get_column_letter(i)].width = (widths or {}).get(i, max(12, len(str(h)) + 2))
    ws.freeze_panes = "A2"
    return ws


def export_package(run: CloseRun, out_dir: Path) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    period = run.config["period"]
    wb = Workbook()
    wb.remove(wb.active)

    # Summary
    ws = _sheet(wb, "Summary", ["Check", "Result"],
                [(c["check"], "PASS" if c["passed"] else "FAIL") for c in run.checks], widths={1: 60, 2: 10})
    for row in ws.iter_rows(min_row=2):
        row[1].fill = OK if row[1].value == "PASS" else FLAG
    ws.insert_rows(1, 3)
    ws["A1"] = f"{run.config['entity']} | Close package {period}"
    ws["A1"].font = Font(bold=True, size=14)
    ws["A2"] = "Prepared by close agent. Proposed entries only: nothing has been posted."

    # Bank rec, with live formulas so a reviewer can trace it
    b = run.bank
    ws = wb.create_sheet("Bank Rec")
    ws.column_dimensions["A"].width, ws.column_dimensions["B"].width = 48, 16
    ws.append(("Bank reconciliation",))
    ws["A1"].font = Font(bold=True)
    rows = [("Balance per bank", b["bank_ending_balance"])]
    rows += [(f"  Add: deposit in transit {d['ref']}", d["amount"]) for d in b["deposits_in_transit"]]
    rows += [(f"  Less: outstanding check {d['ref']}", d["amount"]) for d in b["outstanding_checks"]]
    first, last = 2, 1 + len(rows)
    for r in rows:
        ws.append(r)
    ws.append(("Adjusted bank balance", f"=SUM(B{first}:B{last})"))
    adj_bank_row = ws.max_row
    ws.append(())
    ws.append(("Balance per GL (unadjusted)", b["gl_ending_balance"]))
    g_first = ws.max_row
    for d in b["unrecorded_bank_items"]:
        ws.append((f"  Unrecorded bank item {d['ref']} (see JEs)", d["amount"]))
    ws.append(("Adjusted GL balance", f"=SUM(B{g_first}:B{ws.max_row})"))
    adj_gl_row = ws.max_row
    ws.append(())
    ws.append(("Unexplained difference", f"=B{adj_bank_row}-B{adj_gl_row}"))
    for row in ws.iter_rows(min_col=2, max_col=2):
        for c in row:
            c.number_format = MONEY
    for r in (adj_bank_row, adj_gl_row, ws.max_row):
        ws.cell(r, 1).font = ws.cell(r, 2).font = Font(bold=True)

    # Subledger recs
    ws = _sheet(wb, "BS Recs", ["Account", "Name", "GL balance", "Support balance", "Support", "Difference", "Status"],
                [(r["account"], r["name"], r["gl_balance"], r["support_balance"], r["support_source"],
                  None, None) for r in run.recs], money_cols=(3, 4, 6), widths={2: 26, 5: 40})
    for i in range(2, ws.max_row + 1):
        ws[f"F{i}"] = f"=C{i}-D{i}"
        ws[f"G{i}"] = f'=IF(ABS(F{i})<{run.config["thresholds"]["rec_tolerance"]},"Reconciled","INVESTIGATE")'

    # Proposed JEs (also the upload file)
    acct_names = run.inputs["chart_of_accounts"].set_index("account").name
    je_rows = []
    for j in run.jes:
        for a, d, c, memo in j.lines:
            je_rows.append((j.je_id, period, a, acct_names.get(a, ""), d or None, c or None, memo, j.description,
                            j.reversal_date or "", "Yes" if j.needs_approval else "", "; ".join(j.flags), j.support))
    headers = ["JE ID", "Period", "Account", "Account name", "Debit", "Credit", "Line memo", "JE description",
               "Auto-reverse", "Needs approval", "Flags", "Support"]
    ws = _sheet(wb, "Proposed JEs", headers, je_rows, money_cols=(5, 6), widths={4: 26, 7: 32, 8: 40, 12: 34})
    n = ws.max_row
    ws.append(("Total", "", "", "", f"=SUM(E2:E{n})", f"=SUM(F2:F{n})"))
    ws.cell(ws.max_row, 5).number_format = ws.cell(ws.max_row, 6).number_format = MONEY
    ws.cell(ws.max_row, 1).font = Font(bold=True)
    pd.DataFrame(je_rows, columns=headers).to_csv(out_dir / f"je_upload_{period}.csv", index=False)

    # Adjusted TB with formulas
    ws = _sheet(wb, "Adjusted TB", ["Account", "Name", "Type", "Unadjusted", "Adjustments", "Adjusted"],
                [(r.account, r.name, r.type, r.unadjusted, r.adjustments, None) for r in run.atb.itertuples()],
                money_cols=(4, 5, 6), widths={2: 28})
    n = ws.max_row
    for i in range(2, n + 1):
        ws[f"F{i}"] = f"=D{i}+E{i}"
    ws.append(("Total", "", "", f"=SUM(D2:D{n})", f"=SUM(E2:E{n})", f"=SUM(F2:F{n})"))
    for col in "DEF":
        ws[f"{col}{ws.max_row}"].number_format = MONEY

    # Flux
    f = run.flux
    ws = _sheet(wb, "Flux", ["Account", "Name", "Current", "Prior", "vs Prior", "vs Prior %", "Budget", "vs Budget",
                             "vs Budget %", "Commentary"],
                [(r.account, r.name, r.current, r.prior, r.vs_prior, r.vs_prior_pct, r.budget, r.vs_budget,
                  r.vs_budget_pct, r.commentary) for r in f.itertuples()],
                money_cols=(3, 4, 5, 7, 8), pct_cols=(6, 9), widths={2: 28, 10: 70})
    for i, flagged in enumerate(f.needs_commentary, start=2):
        ws[f"J{i}"].alignment = Alignment(wrap_text=True, vertical="top")
        if flagged:
            for c in ws[i]:
                c.fill = FLAG

    # Financial statements
    inc, bs = run.fs["income_statement"], run.fs["balance_sheet"]
    rows = [("Revenue", None)] + [(f"  {r['name']}", r["amount"]) for r in inc["revenue"]]
    rows += [("Total revenue", inc["total_revenue"]), ("Expenses", None)]
    rows += [(f"  {r['name']}", r["amount"]) for r in inc["expenses"]]
    rows += [("Total expenses", inc["total_expenses"]), ("Net income", inc["net_income"])]
    _sheet(wb, "Income Statement", ["Line", period], rows, money_cols=(2,), widths={1: 34, 2: 16})
    rows = [("Assets", None)] + [(f"  {r['name']}", r["amount"]) for r in bs["assets"]]
    rows += [("Total assets", bs["total_assets"]), ("Liabilities", None)]
    rows += [(f"  {r['name']}", r["amount"]) for r in bs["liabilities"]]
    rows += [("Equity", None)] + [(f"  {r['name']}", r["amount"]) for r in bs["equity"]]
    rows += [("Total liabilities and equity", bs["total_liabilities_and_equity"])]
    _sheet(wb, "Balance Sheet", ["Line", period], rows, money_cols=(2,), widths={1: 34, 2: 16})

    # Open items
    _sheet(wb, "Open Items", ["Area", "Amount", "Detail"],
           [(i["area"], i["amount"], i["detail"]) for i in run.open_items()], money_cols=(2,),
           widths={1: 26, 3: 90})

    for sheet in ("Income Statement", "Balance Sheet"):
        for row in wb[sheet].iter_rows(min_row=2):
            if not str(row[0].value).startswith("  "):
                row[0].font = Font(bold=True)

    xlsx = out_dir / f"close_package_{period}.xlsx"
    wb.save(xlsx)
    memo = out_dir / f"close_memo_{period}.md"
    memo.write_text(run.memo or "")
    return {"workbook": xlsx, "je_upload": out_dir / f"je_upload_{period}.csv", "memo": memo}
