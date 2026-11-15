"""Proposed journal entries. Nothing here posts to an ERP: output is a reviewable upload file."""
from dataclasses import dataclass, field

import pandas as pd

from .data import CloseInputs
from .recs import months_elapsed


@dataclass
class JournalEntry:
    je_id: str
    description: str
    lines: list  # [(account, debit, credit, memo)]
    support: str
    reversal_date: str | None = None
    needs_approval: bool = False
    flags: list = field(default_factory=list)

    @property
    def amount(self) -> float:
        return round(sum(l[1] for l in self.lines), 2)

    @property
    def balanced(self) -> bool:
        return round(sum(l[1] for l in self.lines) - sum(l[2] for l in self.lines), 2) == 0

    def to_dict(self) -> dict:
        return {"je_id": self.je_id, "description": self.description, "amount": self.amount,
                "support": self.support, "reversal_date": self.reversal_date,
                "needs_approval": self.needs_approval, "balanced": self.balanced, "flags": self.flags,
                "lines": [{"account": a, "debit": d, "credit": c, "memo": m} for a, d, c, m in self.lines]}


def _straight_line(df, through, amount_col, months_col, start_col):
    rows = []
    for r in df.itertuples():
        if 0 < months_elapsed(getattr(r, start_col), through) <= getattr(r, months_col):
            rows.append((r, round(getattr(r, amount_col) / getattr(r, months_col), 2)))
    return rows


def propose_entries(inputs: CloseInputs, bank_result: dict) -> list[JournalEntry]:
    acct, end = inputs.config["accounts"], inputs.period_end
    period = inputs.config["period"]
    jes: list[JournalEntry] = []

    def next_id():
        return f"JE-{period}-{len(jes) + 1:02d}"

    # 1. Bank items not yet in the GL
    for item in bank_result["unrecorded_bank_items"]:
        amt = abs(item["amount"])
        if item["amount"] < 0:
            lines = [(acct["bank_fees"], amt, 0, item["description"]), (acct["cash"], 0, amt, item["ref"])]
        else:
            lines = [(acct["cash"], amt, 0, item["ref"]), (acct["interest_income"], 0, amt, item["description"])]
        jes.append(JournalEntry(next_id(), f"Record bank item: {item['description']}", lines,
                                f"Bank statement {item['date']} {item['ref']}"))

    # 2. Expense accruals for invoices received after cutoff (auto-reverse day 1 of next month)
    reversal = (end + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    for r in inputs["unrecorded_invoices"].itertuples():
        jes.append(JournalEntry(
            next_id(), f"Accrue {r.vendor} {r.invoice}: {r.description}",
            [(str(r.expense_account), r.amount, 0, r.description),
             (acct["accrued_liabilities"], 0, r.amount, f"{r.vendor} {r.invoice}")],
            f"Invoice {r.invoice} received {r.received_date}", reversal_date=reversal))

    # 3. Prepaid amortization, grouped by expense account
    amort = _straight_line(inputs["prepaid_schedule"], end, "total", "months", "start")
    if amort:
        lines = [(str(r.expense_account), a, 0, r.item) for r, a in amort]
        total = round(sum(a for _, a in amort), 2)
        lines.append((acct["prepaid"], 0, total, "Prepaid amortization"))
        jes.append(JournalEntry(next_id(), "Prepaid amortization", lines, "prepaid_schedule.csv"))

    # 4. Depreciation (full-month convention in the month placed in service)
    dep = _straight_line(inputs["fixed_asset_register"], end, "cost", "life_months", "in_service")
    if dep:
        total = round(sum(a for _, a in dep), 2)
        jes.append(JournalEntry(
            next_id(), "Monthly depreciation",
            [(acct["depreciation_expense"], total, 0, f"{len(dep)} assets"),
             (acct["accum_depreciation"], 0, total, "Accumulated depreciation")],
            "fixed_asset_register.csv"))

    # 5. Revenue recognition: release deferred revenue ratably (ASC 606, over-time obligations)
    rev = _straight_line(inputs["deferred_revenue_schedule"], end, "total", "months", "start")
    if rev:
        total = round(sum(a for _, a in rev), 2)
        lines = [(acct["deferred_revenue"], total, 0, "Release deferred revenue")]
        lines += [(acct["subscription_revenue"], 0, a, f"{r.contract} {r.customer}") for r, a in rev]
        jes.append(JournalEntry(next_id(), "Recognize subscription revenue", lines,
                                "deferred_revenue_schedule.csv"))

    # Controls
    limit = inputs.config["thresholds"]["je_approval"]
    for je in jes:
        je.needs_approval = je.amount >= limit
        if not je.balanced:
            je.flags.append("UNBALANCED")
        if je.amount >= 1000 and je.amount % 1000 == 0 and "accrue" in je.description.lower():
            je.flags.append("Round-number accrual: confirm against invoice")
    return jes


def je_activity(jes: list[JournalEntry]) -> pd.Series:
    """Net debit/credit by account across all proposed entries."""
    rows = [(a, d - c) for je in jes for a, d, c, _ in je.lines]
    return pd.DataFrame(rows, columns=["account", "net"]).groupby("account").net.sum().round(2)
