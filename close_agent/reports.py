"""Adjusted trial balance, flux analysis, financial statements and tie-out checks."""
import pandas as pd

from .data import CloseInputs
from .jes import JournalEntry, je_activity

PNL_TYPES = ("Revenue", "Expense")


def adjusted_tb(inputs: CloseInputs, jes: list[JournalEntry]) -> pd.DataFrame:
    tb = inputs["trial_balance"][["account", "name", "type", "balance"]].rename(columns={"balance": "unadjusted"})
    tb["adjustments"] = tb.account.map(je_activity(jes)).fillna(0.0)
    tb["adjusted"] = (tb.unadjusted + tb.adjustments).round(2)
    return tb


def flux(inputs: CloseInputs, atb: pd.DataFrame) -> pd.DataFrame:
    """P&L lines in natural sign (revenue positive), vs prior month and budget."""
    th = inputs.config["thresholds"]
    pnl = atb[atb.type.isin(PNL_TYPES)][["account", "name", "type", "adjusted"]].copy()
    prior = inputs["prior_trial_balance"].set_index("account").balance
    budget = inputs["budget"].set_index("account").budget
    sign = pnl.type.map({"Revenue": -1, "Expense": 1})
    pnl["current"] = pnl.adjusted * sign
    pnl["prior"] = pnl.account.map(prior).fillna(0) * sign
    pnl["budget"] = pnl.account.map(budget).fillna(0) * sign
    for ref in ("prior", "budget"):
        pnl[f"vs_{ref}"] = (pnl.current - pnl[ref]).round(2)
        pnl[f"vs_{ref}_pct"] = (pnl[f"vs_{ref}"] / pnl[ref].abs().where(pnl[ref] != 0)).round(4)
        pnl[f"flag_{ref}"] = (pnl[f"vs_{ref}"].abs() > th["flux_amount"]) & (
            pnl[f"vs_{ref}_pct"].abs().fillna(1) > th["flux_percent"])
    pnl["needs_commentary"] = pnl.flag_prior | pnl.flag_budget
    pnl["commentary"] = ""
    return pnl.drop(columns="adjusted").reset_index(drop=True)


def financial_statements(atb: pd.DataFrame) -> dict:
    bal = atb.set_index("account")
    pnl = atb[atb.type.isin(PNL_TYPES)]
    revenue = -pnl[pnl.type == "Revenue"].adjusted.sum()
    expenses = pnl[pnl.type == "Expense"].adjusted.sum()
    net_income = round(revenue - expenses, 2)

    def section(t, sign=1):
        rows = atb[atb.type == t]
        return [{"account": r.account, "name": r.name, "amount": round(r.adjusted * sign, 2)} for r in rows.itertuples()]

    assets = section("Asset")
    liabilities = section("Liability", -1)
    equity = section("Equity", -1) + [{"account": "", "name": "Current period net income", "amount": net_income}]
    total_assets = round(sum(r["amount"] for r in assets), 2)
    total_le = round(sum(r["amount"] for r in liabilities + equity), 2)
    return {
        "income_statement": {"revenue": section("Revenue", -1), "expenses": section("Expense"),
                             "total_revenue": round(revenue, 2), "total_expenses": round(expenses, 2),
                             "net_income": net_income},
        "balance_sheet": {"assets": assets, "liabilities": liabilities, "equity": equity,
                          "total_assets": total_assets, "total_liabilities_and_equity": total_le},
        "cash": round(float(bal.loc["1000", "adjusted"]), 2) if "1000" in bal.index else None,
    }


def tie_out_checks(inputs, atb, jes, bank, recs, fs) -> list[dict]:
    cash_acct = inputs.config["accounts"]["cash"]
    adj_cash = float(atb.loc[atb.account == cash_acct, "adjusted"].iloc[0])
    checks = [
        ("Unadjusted TB balances to zero", round(atb.unadjusted.sum(), 2) == 0),
        ("Adjusted TB balances to zero", round(atb.adjusted.sum(), 2) == 0),
        ("All proposed JEs balance", all(j.balanced for j in jes)),
        ("Bank rec has no unexplained difference", bank["reconciled"]),
        ("Adjusted GL cash equals reconciled bank balance", round(adj_cash - bank["adjusted_bank_balance"], 2) == 0),
        ("Balance sheet balances", round(fs["balance_sheet"]["total_assets"]
                                         - fs["balance_sheet"]["total_liabilities_and_equity"], 2) == 0),
    ]
    out = [{"check": c, "passed": bool(p)} for c, p in checks]
    for r in recs:
        out.append({"check": f"{r['name']} ties to {r['support_source']}", "passed": r["reconciled"]})
    return out
