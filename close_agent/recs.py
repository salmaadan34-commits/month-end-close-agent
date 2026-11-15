"""Reconciliations: bank-to-GL and GL-to-subledger."""
import pandas as pd

from .data import CloseInputs


def months_elapsed(start, through: pd.Timestamp) -> int:
    s = pd.Timestamp(start)
    return max(0, (through.year - s.year) * 12 + (through.month - s.month) + 1)


def schedule_balance(df: pd.DataFrame, through: pd.Timestamp) -> float:
    """Remaining balance of a straight-line schedule (prepaids, deferred revenue) at month end."""
    bal = 0.0
    for r in df.itertuples():
        elapsed = min(r.months, months_elapsed(r.start, through))
        bal += r.total - r.total / r.months * elapsed
    return round(bal, 2)


def bank_rec(inputs: CloseInputs) -> dict:
    """Match GL cash activity to the bank statement by amount within a date window."""
    window = pd.Timedelta(days=inputs.config["bank"]["match_date_window_days"])
    gl = inputs["gl_cash_detail"].copy()
    bank = inputs["bank_statement"].copy()
    gl["date"], bank["date"] = pd.to_datetime(gl.date), pd.to_datetime(bank.date)
    gl["matched_to"], bank["matched"] = None, False

    for i, g in gl.iterrows():
        cands = bank[(~bank.matched) & (bank.amount.round(2) == round(g.amount, 2))
                     & ((bank.date - g.date).abs() <= window)]
        if not cands.empty:
            j = cands.index[0]
            bank.at[j, "matched"] = True
            gl.at[i, "matched_to"] = bank.at[j, "ref"]

    unmatched_gl = gl[gl.matched_to.isna()]
    unmatched_bank = bank[~bank.matched]
    deposits_in_transit = unmatched_gl[unmatched_gl.amount > 0]
    outstanding_checks = unmatched_gl[unmatched_gl.amount < 0]

    bank_end = float(inputs["bank_statement_summary"].ending_balance.iloc[0])
    gl_end = inputs.tb_balance(inputs.config["bank"]["gl_account"])
    adjusted_bank = bank_end + deposits_in_transit.amount.sum() + outstanding_checks.amount.sum()
    adjusted_gl = gl_end + unmatched_bank.amount.sum()
    diff = round(adjusted_bank - adjusted_gl, 2)

    def rows(df):
        return [{"date": d.date.strftime("%Y-%m-%d"), "ref": d.ref, "description": d.description,
                 "amount": round(float(d.amount), 2)} for d in df.itertuples()]

    return {
        "bank_ending_balance": bank_end,
        "gl_ending_balance": gl_end,
        "deposits_in_transit": rows(deposits_in_transit),
        "outstanding_checks": rows(outstanding_checks),
        "unrecorded_bank_items": rows(unmatched_bank),
        "matched_count": int(bank.matched.sum()),
        "adjusted_bank_balance": round(adjusted_bank, 2),
        "adjusted_gl_balance": round(adjusted_gl, 2),
        "unexplained_difference": diff,
        "reconciled": abs(diff) < inputs.config["thresholds"]["rec_tolerance"],
    }


def subledger_recs(inputs: CloseInputs) -> list[dict]:
    """Tie each balance sheet account to its supporting schedule (before current-month entries)."""
    acct, end = inputs.config["accounts"], inputs.period_end
    prior_end = (end - pd.offsets.MonthEnd(1)).normalize()
    fa = inputs["fixed_asset_register"]
    accum_prior = sum(r.cost / r.life_months * min(r.life_months, months_elapsed(r.in_service, prior_end))
                      for r in fa.itertuples())
    deferred = inputs["deferred_revenue_schedule"]

    checks = [
        ("Accounts Receivable", acct["ar"], inputs["ar_aging"].amount.sum(), "AR aging"),
        ("Accounts Payable", acct["ap"], -inputs["ap_aging"].amount.sum(), "AP aging"),
        ("Prepaid Expenses", acct["prepaid"], schedule_balance(inputs["prepaid_schedule"], prior_end),
         "Prepaid schedule (through prior month)"),
        ("Fixed Assets - Cost", acct["fixed_assets"], fa.cost.sum(), "Fixed asset register"),
        ("Accumulated Depreciation", acct["accum_depreciation"], -round(accum_prior, 2),
         "FA register (through prior month)"),
        ("Deferred Revenue", acct["deferred_revenue"], -schedule_balance(deferred, prior_end),
         "Deferred revenue schedule (through prior month)"),
    ]
    tol = inputs.config["thresholds"]["rec_tolerance"]
    out = []
    for name, account, support, source in checks:
        gl = inputs.tb_balance(account)
        diff = round(gl - support, 2)
        out.append({"account": account, "name": name, "gl_balance": gl, "support_balance": round(support, 2),
                    "support_source": source, "difference": diff, "reconciled": abs(diff) < tol})
    return out
