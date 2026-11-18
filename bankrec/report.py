"""Write the reconciliation workpaper (.xlsx), daily cash position (.md) and audit log (.csv)."""
import csv
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from . import classifier as K
from . import config as C

NUM = '#,##0.00;(#,##0.00);"-"'
HDR_FILL = PatternFill("solid", fgColor="1F3864")
HDR_FONT = Font(bold=True, color="FFFFFF")
TOTAL_FONT = Font(bold=True)
INPUT_FONT = Font(color="0000FF")          # hard-coded inputs in blue, formulas in black
THIN = Side(style="thin", color="999999")
CAT_ORDER = [K.BANK_FEE, K.INTEREST, K.UNRECORDED, K.DUPLICATE, K.AMOUNT_MISMATCH]


def _header(ws, row, headers, widths=None):
    for c, h in enumerate(headers, 1):
        cell = ws.cell(row=row, column=c, value=h)
        cell.fill, cell.font = HDR_FILL, HDR_FONT
        cell.alignment = Alignment(vertical="center", wrap_text=True)
    if widths:
        for c, w in enumerate(widths, 1):
            ws.column_dimensions[get_column_letter(c)].width = w
    ws.freeze_panes = ws.cell(row=row + 1, column=1)


def _summary(wb, res):
    ws = wb.active
    ws.title = "Rec Summary"
    ws["A1"] = "Bank Reconciliation"
    ws["A1"].font = Font(bold=True, size=14)
    ws["A2"] = f"Period ended {C.PERIOD_END:%B %d, %Y}   |   Prepared by: Bank Rec Agent   |   Reviewed by: ________"
    ws.column_dimensions["A"].width = 46
    ws.column_dimensions["B"].width = 18
    ws.column_dimensions["C"].width = 54
    r = 4
    for rec in res.accounts.values():
        ws.cell(row=r, column=1, value=f"{rec.account} - GL {rec.gl_account}").font = Font(bold=True, size=12)
        r += 1
        top = r
        rows = [("Balance per bank statement", rec.bank_end, "input"),
                ("Add: deposits in transit", rec.dit, "input"),
                ("Less: outstanding checks (incl. stale)", rec.os_checks, "input")]
        for label, val, _ in rows:
            ws.cell(row=r, column=1, value=label)
            c = ws.cell(row=r, column=2, value=val)
            c.number_format, c.font = NUM, INPUT_FONT
            r += 1
        ws.cell(row=r, column=1, value="Adjusted bank balance").font = TOTAL_FONT
        adj_bank = ws.cell(row=r, column=2, value=f"=SUM(B{top}:B{r - 1})")
        adj_bank.number_format, adj_bank.font = NUM, TOTAL_FONT
        adj_bank.border = Border(top=THIN)
        adj_bank_row = r
        r += 2
        book_top = r
        ws.cell(row=r, column=1, value="Balance per books (GL)")
        c = ws.cell(row=r, column=2, value=rec.gl_end)
        c.number_format, c.font = NUM, INPUT_FONT
        r += 1
        for cat in CAT_ORDER:
            ws.cell(row=r, column=1, value=f"Adj: {cat.lower()}")
            c = ws.cell(row=r, column=2, value=rec.book_adjustments.get(cat, 0))
            c.number_format, c.font = NUM, INPUT_FONT
            r += 1
        ws.cell(row=r, column=1, value="Adjusted book balance").font = TOTAL_FONT
        adj_book = ws.cell(row=r, column=2, value=f"=SUM(B{book_top}:B{r - 1})")
        adj_book.number_format, adj_book.font = NUM, TOTAL_FONT
        adj_book.border = Border(top=THIN)
        adj_book_row = r
        r += 2
        ws.cell(row=r, column=1, value="Difference").font = TOTAL_FONT
        d = ws.cell(row=r, column=2, value=f"=ROUND(B{adj_bank_row}-B{adj_book_row},2)")
        d.number_format, d.font = NUM, TOTAL_FONT
        s = ws.cell(row=r, column=3, value=f'=IF(ABS(B{r})<0.005,"TIED","OUT OF BALANCE")')
        s.font = TOTAL_FONT
        r += 1
        ws.cell(row=r, column=1, value="Auto-match rate (bank lines)")
        ws.cell(row=r, column=2, value=rec.match_rate).number_format = "0.0%"
        ws.cell(row=r, column=3, value=f"{rec.matched_lines} of {rec.bank_lines} bank lines matched")
        r += 3


def _exceptions(wb, res):
    ws = wb.create_sheet("Exceptions")
    _header(ws, 1, ["Item", "Account", "Side", "Date", "Description", "Amount", "Category", "Likely cause",
                    "Next step", "Confidence", "Source", "Days out", "Needs review", "Controller sign-off"],
            [7, 12, 7, 11, 46, 14, 22, 60, 46, 11, 26, 9, 12, 18])
    for n, i in enumerate(res.items, 1):
        ws.append([f"E{n:02d}", i.account, i.side, i.date, i.description, i.amount, i.category, i.likely_cause,
                   i.action, i.confidence, i.source, i.days_outstanding, "Yes" if i.needs_review else "", ""])
        i.ref = f"E{n:02d}"
    for row in ws.iter_rows(min_row=2):
        row[3].number_format = "yyyy-mm-dd"
        row[5].number_format = NUM
        for c in (row[4], row[7], row[8]):
            c.alignment = Alignment(wrap_text=True, vertical="top")
    ws.auto_filter.ref = ws.dimensions


def _proposed_jes(wb, res):
    ws = wb.create_sheet("Proposed JEs")
    _header(ws, 1, ["Proposed JE", "Date", "GL acct", "Account name", "Debit", "Credit", "Memo", "Exception",
                    "Approved (Y/N)", "Approver"], [12, 11, 9, 30, 14, 14, 52, 10, 14, 14])
    n = 0
    for i in res.items:
        if not i.je_lines:
            continue
        n += 1
        start = ws.max_row + 1
        for acct, name, dr, cr in i.je_lines:
            ws.append([f"PJE-{n:02d}", C.PERIOD_END, acct, name, dr or None, cr or None,
                       f"{i.category}: {i.description[:60]}", i.ref, "", ""])
        end = ws.max_row
        ws.append(["", "", "", "Check (Dr = Cr)", f"=SUM(E{start}:E{end})", f"=SUM(F{start}:F{end})",
                   f'=IF(ROUND(E{end + 1}-F{end + 1},2)=0,"Balanced","NOT BALANCED")'])
        for c in ws[ws.max_row]:
            c.font = Font(italic=True, color="666666")
    for row in ws.iter_rows(min_row=2):
        row[1].number_format = "yyyy-mm-dd"
        row[4].number_format = row[5].number_format = NUM
    ws.cell(row=ws.max_row + 2, column=1,
            value="Agent proposes only. Nothing is posted to the ERP until the controller approves.").font = Font(italic=True)


def _matched(wb, res):
    ws = wb.create_sheet("Matched")
    _header(ws, 1, ["Account", "Rule", "Bank date", "Bank description", "Bank amount", "GL date(s)", "GL JE(s)",
                    "GL memo(s)", "Confidence", "Detail"], [12, 16, 11, 44, 14, 24, 22, 60, 11, 52])
    for m in res.matches:
        bks = [res.bank[i] for i in m.bank_ids]
        gls = [res.book[i] for i in m.book_ids]
        ws.append([m.account, m.rule, bks[0]["date"], " + ".join(b["description"] for b in bks),
                   round(sum(b["amount"] for b in bks), 2),
                   ", ".join(sorted({g["date"].isoformat() for g in gls})), ", ".join(g["je_number"] for g in gls),
                   " | ".join(g["memo"] for g in gls), m.confidence, m.detail])
    for row in ws.iter_rows(min_row=2):
        row[2].number_format = "yyyy-mm-dd"
        row[4].number_format = NUM
    ws.auto_filter.ref = ws.dimensions


def write_workpaper(res, path: Path):
    wb = Workbook()
    _summary(wb, res)
    _exceptions(wb, res)
    _proposed_jes(wb, res)
    _matched(wb, res)
    wb.save(path)


def write_audit_log(res, path: Path):
    ts = datetime.now().isoformat(timespec="seconds")
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["timestamp", "step", "rule_or_category", "account", "bank_ids", "book_ids", "amount", "detail"])
        for m in res.matches:
            amt = round(sum(res.bank[i]["amount"] for i in m.bank_ids), 2)
            w.writerow([ts, "match", m.rule, m.account, ";".join(m.bank_ids), ";".join(m.book_ids), amt, m.detail])
        for i in res.items:
            bank_ids = ";".join(x for x in i.ids if x.startswith("B"))
            book_ids = ";".join(x for x in i.ids if not x.startswith("B"))
            w.writerow([ts, f"classify ({i.source})", i.category, i.account, bank_ids, book_ids, i.amount,
                        i.likely_cause])


def write_cash_position(res, path: Path):
    as_of = max(r["date"] for r in res.bank.values())
    lines = [f"# Daily Cash Position - {as_of:%A, %B %d, %Y}", "",
             "| Account | Bank balance | Change vs prior day | Book balance (GL) | Adjusted balance | Rec status |",
             "|---|---:|---:|---:|---:|---|"]
    tot_bank = tot_chg = 0.0
    for rec in res.accounts.values():
        rows = sorted((r for r in res.bank.values() if r["account"] == rec.account), key=lambda r: (r["date"], r["id"]))
        today = rows[-1]["balance"]
        prior = [r for r in rows if r["date"] < as_of]
        chg = today - (prior[-1]["balance"] if prior else today)
        tot_bank += today
        tot_chg += chg
        status = "Tied" if abs(rec.difference) < 0.005 else f"Out by {rec.difference:,.2f}"
        lines.append(f"| {rec.account} ({rec.gl_account}) | {today:,.2f} | {chg:+,.2f} | {rec.gl_end:,.2f} | "
                     f"{rec.adjusted_book:,.2f} | {status} |")
    lines.append(f"| **Total** | **{tot_bank:,.2f}** | **{tot_chg:+,.2f}** | | | |")

    review = [i for i in res.items if i.category not in K.TIMING or i.category == K.STALE]
    timing = [i for i in res.items if i.category in K.TIMING and i.category != K.STALE]
    lines += ["", f"## Needs attention ({len(review)})", "",
              "| Item | Account | Amount | Category | Likely cause | Next step |", "|---|---|---:|---|---|---|"]
    for i in review:
        lines.append(f"| {i.description.replace('|', '/')[:48]} | {i.account} | {i.amount:,.2f} | {i.category} | {i.likely_cause} | "
                     f"{i.action} |")
    lines += ["", f"## Timing items ({len(timing)}) - expected to clear next month", "",
              f"- Deposits in transit: {sum(i.amount for i in timing if i.category == K.DEPOSIT_IN_TRANSIT):,.2f}",
              f"- Outstanding checks: {sum(i.amount for i in timing if i.category == K.OUTSTANDING_CHECK):,.2f}"]
    path.write_text("\n".join(lines) + "\n")
