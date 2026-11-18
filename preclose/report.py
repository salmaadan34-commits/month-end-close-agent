"""Write the close review workbook (.xlsx) and the flux commentary memo (.md)."""
from collections import Counter
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from . import gl as G

NUM = '#,##0;(#,##0);"-"'
NUM2 = '#,##0.00;(#,##0.00);"-"'
PCT = '0%;(0%);"-"'
HDR_FILL = PatternFill("solid", fgColor="1F3864")
HDR_FONT = Font(bold=True, color="FFFFFF")
INPUT = Font(color="0000FF")
BOLD = Font(bold=True)
FLAG_FILL = PatternFill("solid", fgColor="FFF2CC")
SEV_FILL = {"High": PatternFill("solid", fgColor="F8CBAD"), "Medium": PatternFill("solid", fgColor="FFE699"),
            "Low": PatternFill("solid", fgColor="E2EFDA")}
WRAP = Alignment(wrap_text=True, vertical="top")


def _header(ws, headers, widths, row=1):
    for c, (h, w) in enumerate(zip(headers, widths), 1):
        cell = ws.cell(row=row, column=c, value=h)
        cell.fill, cell.font, cell.alignment = HDR_FILL, HDR_FONT, Alignment(wrap_text=True, vertical="center")
        ws.column_dimensions[get_column_letter(c)].width = w
    ws.freeze_panes = ws.cell(row=row + 1, column=1)


def _summary(wb, findings, stats, flux):
    ws = wb.active
    ws.title = "Summary"
    ws.column_dimensions["A"].width = 44
    ws.column_dimensions["B"].width = 16
    ws["A1"] = f"Close Review - {G.PERIOD}"
    ws["A1"].font = Font(bold=True, size=14)
    ws["A2"] = f"Generated {datetime.now():%Y-%m-%d %H:%M} by Close Agent   |   Reviewed by: ________"
    sev = Counter(f.severity for f in findings)
    rows = [("Pre-close checks", None),
            ("Journal lines tested (100%, no sampling)", stats["lines_checked"]),
            ("Journal entries tested", stats["jes_checked"]),
            ("Findings - High", sev["High"]), ("Findings - Medium", sev["Medium"]), ("Findings - Low", sev["Low"]),
            ("Proposed reclasses / corrections", sum(1 for f in findings if f.reclass)),
            ("", None), ("Flux analysis", None),
            ("P&L accounts reviewed", len(flux)),
            ("Accounts needing commentary", sum(1 for f in flux if f.flagged)),
            ("Threshold", f"≥ ${G.MATERIALITY:,} and ≥ {G.PCT_THRESHOLD:.0%}")]
    for i, (k, v) in enumerate(rows, 4):
        ws.cell(row=i, column=1, value=k).font = BOLD if v is None and k else Font()
        if v is not None:
            ws.cell(row=i, column=2, value=v)
    ws.cell(row=len(rows) + 6, column=1,
            value="The agent proposes; the controller decides. Nothing is posted automatically.").font = \
        Font(italic=True, color="666666")


def _findings(wb, findings):
    ws = wb.create_sheet("Pre-close Findings")
    _header(ws, ["ID", "Severity", "Check", "JE", "Line", "Date", "Account", "Counterparty", "Amount", "Issue",
                 "Suggested fix", "Controller decision"], [8, 10, 20, 16, 6, 11, 9, 22, 13, 60, 52, 20])
    for f in findings:
        ws.append([f.id, f.severity, f.check, f.je_number, f.line, f.date, f.account, f.counterparty, f.amount,
                   f.issue, f.fix, ""])
        r = ws.max_row
        ws.cell(row=r, column=2).fill = SEV_FILL[f.severity]
        ws.cell(row=r, column=9).number_format = NUM2
        for c in (10, 11):
            ws.cell(row=r, column=c).alignment = WRAP
    ws.auto_filter.ref = ws.dimensions


def _reclasses(wb, findings):
    ws = wb.create_sheet("Proposed Reclasses")
    _header(ws, ["Proposed JE", "Finding", "GL acct", "Account name", "Debit", "Credit", "Memo", "Approved (Y/N)"],
            [12, 9, 9, 26, 13, 13, 40, 14])
    n = 0
    for f in findings:
        if not f.reclass:
            continue
        n += 1
        start = ws.max_row + 1
        for acct, name, dr, cr, memo in f.reclass:
            ws.append([f"RJE-{n:02d}", f.id, acct, name, dr or None, cr or None, memo, ""])
        end = ws.max_row
        ws.append(["", "", "", "Check (Dr = Cr)", f"=SUM(E{start}:E{end})", f"=SUM(F{start}:F{end})",
                   f'=IF(ROUND(E{end + 1}-F{end + 1},2)=0,"Balanced","NOT BALANCED")'])
        for c in ws[ws.max_row]:
            c.font = Font(italic=True, color="666666")
    for row in ws.iter_rows(min_row=2):
        row[4].number_format = row[5].number_format = NUM2


def _flux(wb, flux):
    ws = wb.create_sheet("Flux")
    hdr = ["Account", "Name", f"{G.PERIOD} Actual", "Prior Month", "Var $", "Var %", "Budget", "Bud Var $",
           "Bud Var %", "3-Mo Avg", "Explain?", "Commentary"]
    _header(ws, hdr, [9, 26, 13, 13, 12, 9, 13, 12, 9, 13, 10, 90])
    m, p = G.MATERIALITY, G.PCT_THRESHOLD
    sections = [("Revenue", [f for f in flux if f.type == "Revenue"]),
                ("Expense", [f for f in flux if f.type == "Expense"])]
    total_rows = {}
    for label, items in sections:
        ws.append([label])
        ws.cell(row=ws.max_row, column=1).font = BOLD
        first = ws.max_row + 1
        for f in items:
            ws.append([f.account, f.name, f.current, f.prior, None, None, f.budget, None, None, f.avg3, None,
                       f.commentary])
            r = ws.max_row
            ws[f"E{r}"] = f"=C{r}-D{r}"
            ws[f"F{r}"] = f'=IF(D{r}=0,"n/m",E{r}/ABS(D{r}))'
            ws[f"H{r}"] = f"=C{r}-G{r}"
            ws[f"I{r}"] = f'=IF(G{r}=0,"n/m",H{r}/ABS(G{r}))'
            ws[f"K{r}"] = (f'=IF(OR(AND(ABS(E{r})>={m},OR(D{r}=0,ABS(E{r})>={p}*ABS(D{r}))),'
                           f'AND(ABS(H{r})>={m},OR(G{r}=0,ABS(H{r})>={p}*ABS(G{r})))),"Yes","")')
            for c in "CDGJ":
                ws[f"{c}{r}"].font = INPUT
            ws[f"L{r}"].alignment = WRAP
        last = ws.max_row
        ws.append(["", f"Total {label.lower()}"] + [f"=SUM({c}{first}:{c}{last})" for c in "CD"] +
                  [f"=C{last + 1}-D{last + 1}", f'=IF(D{last + 1}=0,"n/m",E{last + 1}/ABS(D{last + 1}))',
                   f"=SUM(G{first}:G{last})", f"=C{last + 1}-G{last + 1}",
                   f'=IF(G{last + 1}=0,"n/m",H{last + 1}/ABS(G{last + 1}))', f"=SUM(J{first}:J{last})"])
        total_rows[label] = ws.max_row
        for c in ws[ws.max_row]:
            c.font = BOLD
            c.border = Border(top=Side(style="thin"))
        ws.append([])
    rv, ex = total_rows["Revenue"], total_rows["Expense"]
    n = ex + 2
    vals = {"B": "Net income", "C": f"=C{rv}-C{ex}", "D": f"=D{rv}-D{ex}", "E": f"=C{n}-D{n}",
            "G": f"=G{rv}-G{ex}", "H": f"=C{n}-G{n}", "J": f"=J{rv}-J{ex}"}
    for col, v in vals.items():
        ws[f"{col}{n}"] = v
        ws[f"{col}{n}"].font = BOLD
    for row in ws.iter_rows(min_row=2):
        for c in (row[2], row[3], row[4], row[6], row[7], row[9]):
            c.number_format = NUM
        row[5].number_format = row[8].number_format = PCT
    ws.conditional_formatting.add(f"A2:K{ws.max_row}", FormulaRule(formula=['$K2="Yes"'], fill=FLAG_FILL))


def _drivers(wb, flux):
    ws = wb.create_sheet("Drivers")
    _header(ws, ["Account", "Name", "Driver", "Current", "Prior", "Change", "Share of var", "Status", "Memo",
                 "Pre-close refs"], [9, 26, 26, 13, 13, 13, 11, 9, 50, 30])
    for f in flux:
        for d in f.drivers:
            ws.append([f.account, f.name, d.key, d.current, d.prior, d.change, d.change / f.var if f.var else None,
                       d.status, d.memo, ", ".join(f"{x.id} {x.check}" for x in d.finding_refs)])
    for row in ws.iter_rows(min_row=2):
        for c in row[3:6]:
            c.number_format = NUM
        row[6].number_format = PCT


def write_workbook(findings, stats, flux, path: Path):
    wb = Workbook()
    _summary(wb, findings, stats, flux)
    _findings(wb, findings)
    _reclasses(wb, findings)
    _flux(wb, flux)
    _drivers(wb, flux)
    wb.save(path)


def write_memo(findings, flux, path: Path):
    flagged = [f for f in flux if f.flagged]
    rev = sum(f.current for f in flux if f.type == "Revenue")
    exp = sum(f.current for f in flux if f.type == "Expense")
    rev_p = sum(f.prior for f in flux if f.type == "Revenue")
    exp_p = sum(f.prior for f in flux if f.type == "Expense")
    high = [f for f in findings if f.severity == "High"]
    out = [f"# Flux Commentary - {G.PERIOD} vs prior month", "",
           f"**Revenue** {rev:,.0f} ({rev - rev_p:+,.0f}) | **Expenses** {exp:,.0f} ({exp - exp_p:+,.0f}) | "
           f"**Net income** {rev - exp:,.0f} ({(rev - exp) - (rev_p - exp_p):+,.0f})", "",
           f"> Draft. {len(high)} high-severity pre-close findings are open; commentary marked [see PC-xx] "
           "will change once they are resolved.", ""]
    for f in flagged:
        out += [f"### {f.account} {f.name}", "", f.commentary, ""]
    out += ["## Open pre-close findings (High)", ""]
    out += [f"- **{f.id} {f.check}** - {f.je_number} {f.counterparty}: {f.issue}" for f in high]
    path.write_text("\n".join(out) + "\n")


def write_summary_json(findings, stats, flux, path: Path):
    """Machine-readable summary other projects can consume (e.g. the controller-ai-team hub)."""
    import json
    fs = [dict(id=f.id, severity=f.severity, check=f.check, je_number=f.je_number, date=f.date,
               account=f.account, counterparty=f.counterparty, amount=round(f.amount, 2), issue=f.issue, fix=f.fix,
               reclass=[[a, n, round(dr, 2), round(cr, 2), m] for a, n, dr, cr, m in f.reclass]) for f in findings]
    fl = [dict(account=f.account, name=f.name, type=f.type, current=f.current, prior=f.prior, var=f.var,
               pct=None if f.pct is None else round(f.pct, 4), budget=f.budget, flagged=f.flagged,
               commentary=f.commentary) for f in flux]
    path.write_text(json.dumps({"module": "preclose", "period": G.PERIOD, "stats": stats,
                                "findings": fs, "flux": fl}, indent=1))
