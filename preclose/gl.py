"""Load GL detail, chart of accounts and budget."""
import csv
from pathlib import Path

PERIOD = "2026-10"
MATERIALITY = 5000      # flux: $ threshold
PCT_THRESHOLD = 0.10    # flux: % threshold
UNUSUAL_MULTIPLE = 2.5  # pre-close: vendor amount vs historical median
UNUSUAL_MIN_DIFF = 2000
LLM_MODEL = "claude-sonnet-5-5"


def load(data_dir) -> dict:
    d = Path(data_dir)
    with open(d / "gl_detail.csv", newline="") as f:
        lines = list(csv.DictReader(f))
    for r in lines:
        r["debit"], r["credit"], r["line"] = float(r["debit"]), float(r["credit"]), int(r["line"])
    with open(d / "chart_of_accounts.csv", newline="") as f:
        coa = {r["account"]: r for r in csv.DictReader(f)}
    with open(d / "budget.csv", newline="") as f:
        budget = {(r["period"], r["account"]): float(r["amount"]) for r in csv.DictReader(f)}
    for r in lines:
        r["type"] = coa[r["account"]]["type"]
        # P&L amount in natural sign: revenue positive when credited, expense positive when debited
        r["pl_amount"] = (r["credit"] - r["debit"]) if r["type"] == "Revenue" else (r["debit"] - r["credit"])
    return {"lines": lines, "coa": coa, "budget": budget}
