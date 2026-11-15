"""Generate a fictional month-end close dataset for Northwind Analytics, Inc. (a SaaS company).

All names and figures are invented. Sign convention: debits positive, credits negative.
Run:  python scripts/generate_sample_data.py
"""
from pathlib import Path

import pandas as pd

OUT = Path(__file__).resolve().parents[1] / "data" / "2026-10"

ACCOUNTS = [
    ("1000", "Cash - Operating", "Asset"),
    ("1100", "Accounts Receivable", "Asset"),
    ("1300", "Prepaid Expenses", "Asset"),
    ("1500", "Fixed Assets", "Asset"),
    ("1510", "Accumulated Depreciation", "Asset"),
    ("2000", "Accounts Payable", "Liability"),
    ("2100", "Accrued Liabilities", "Liability"),
    ("2400", "Deferred Revenue", "Liability"),
    ("3000", "Common Stock", "Equity"),
    ("3100", "Retained Earnings", "Equity"),
    ("4000", "Subscription Revenue", "Revenue"),
    ("4100", "Services Revenue", "Revenue"),
    ("5000", "Cost of Revenue - Hosting", "Expense"),
    ("6000", "Salaries & Wages", "Expense"),
    ("6100", "Software & Subscriptions", "Expense"),
    ("6200", "Rent", "Expense"),
    ("6300", "Professional Fees", "Expense"),
    ("6400", "Depreciation Expense", "Expense"),
    ("6500", "Marketing", "Expense"),
    ("6600", "Insurance", "Expense"),
    ("6700", "Bank Fees", "Expense"),
    ("7000", "Interest Income", "Revenue"),
]

# --- Cash: GL detail and bank statement ---------------------------------------------------
BEGIN_CASH = 380_000.00
BOTH = [  # (gl_date, bank_date, ref, description, amount)
    ("2026-10-01", "2026-10-01", "DEP-1041", "Customer receipt INV-1041", 48_000),
    ("2026-10-03", "2026-10-03", "PR-1003", "Payroll 9/16-9/30", -62_500),
    ("2026-10-05", "2026-10-05", "ACH-3301", "October rent - Pinecrest Properties", -9_500),
    ("2026-10-08", "2026-10-09", "ACH-3302", "Cloud hosting - September usage", -7_800),
    ("2026-10-12", "2026-10-12", "DEP-1043", "Customer receipt INV-1043", 36_000),
    ("2026-10-15", "2026-10-15", "PR-1015", "Payroll 10/1-10/15", -62_500),
    ("2026-10-18", "2026-10-19", "DEP-1044", "Customer receipt INV-1044 (annual prepay)", 72_000),
    ("2026-10-20", "2026-10-21", "ACH-3303", "Project management software", -4_200),
    ("2026-10-22", "2026-10-22", "ACH-3304", "Brightline Media - October campaign", -6_000),
    ("2026-10-25", "2026-10-26", "DEP-1046", "Customer receipt INV-1046", 54_000),
]
GL_ONLY = [
    ("2026-10-29", "CHK-2051", "Harbor & Finch LLP - legal fees", -8_400),
    ("2026-10-30", "CHK-2052", "Contract data engineer", -3_150),
    ("2026-10-31", "DEP-1048", "Customer receipt INV-1048", 15_000),
]
BANK_ONLY = [
    ("2026-10-31", "SVC-FEE", "Monthly account service fee", -45),
    ("2026-10-31", "INT-OCT", "Interest earned", 120),
]

# --- Subledgers -------------------------------------------------------------------------
AR_AGING = [  # customer, invoice, invoice_date, amount, bucket
    ("Cascade Health", "INV-1039", "2026-08-28", 22_500, "61-90"),
    ("Juniper Logistics", "INV-1045", "2026-10-02", 41_000, "0-30"),
    ("Meridian Retail", "INV-1047", "2026-10-15", 58_000, "0-30"),
    ("Alder Foods", "INV-1049", "2026-10-28", 33_400, "0-30"),
    ("Summit Dental", "INV-1042", "2026-09-20", 31_000, "31-60"),
]
AR_GL_EXTRA = 600  # credit memo CM-0007 issued in billing system, never posted to GL

AP_AGING = [
    ("Pinecrest Properties", "PP-1101", "2026-10-28", 9_500, "0-30"),
    ("Cloud hosting provider", "CH-0926", "2026-10-02", 8_100, "0-30"),
    ("Brightline Media", "BM-552", "2026-10-24", 6_000, "0-30"),
    ("Harbor & Finch LLP", "HF-3390", "2026-09-30", 11_600, "31-60"),
    ("Office Supply Co", "OS-7781", "2026-10-11", 1_200, "0-30"),
    ("Contract recruiter", "CR-118", "2026-10-19", 4_800, "0-30"),
]

UNRECORDED_INVOICES = [  # received after cutoff for October services -> accrue, auto-reverse
    ("Baker & Lane CPAs", "BL-2026-114", "2026-11-04", "Q3 review procedures performed in October", "6300", 3_200),
]

PREPAIDS = [  # item, gl_account (expense), start, months, total
    ("D&O insurance policy", "6600", "2026-04-01", 12, 18_000),
    ("CRM annual subscription", "6100", "2026-01-01", 12, 24_000),
    ("Security tooling annual license", "6100", "2026-07-01", 12, 18_000),
]

FIXED_ASSETS = [  # asset_id, description, in_service, cost, life_months
    ("FA-001", "Office furniture", "2024-01-01", 36_000, 60),
    ("FA-002", "Servers and network gear", "2024-07-01", 72_000, 36),
    ("FA-003", "Employee laptops - 2025 refresh", "2025-03-01", 43_200, 36),
    ("FA-004", "Employee laptops - new hires", "2026-10-01", 7_200, 36),
]

DEFERRED_REVENUE = [  # contract, customer, start, months, total
    ("C-201", "Juniper Logistics", "2026-01-01", 12, 60_000),
    ("C-207", "Meridian Retail", "2026-04-01", 12, 48_000),
    ("C-212", "Cascade Health", "2026-07-01", 24, 96_000),
    ("C-219", "Alder Foods", "2026-10-01", 12, 72_000),
]

PNL_SEP = {"4000": -128_000, "4100": -15_000, "5000": 7_500, "6000": 124_000, "6100": 5_500,
           "6200": 9_500, "6300": 4_000, "6400": 3_300, "6500": 18_000, "6600": 1_500,
           "6700": 45, "7000": -110}
PNL_OCT_UNADJ = {"4000": -118_000, "4100": -22_000, "5000": 7_800, "6000": 125_000, "6100": 4_200,
                 "6200": 9_500, "6300": 8_400, "6400": 0, "6500": 6_000, "6600": 0,
                 "6700": 0, "7000": 0}
BUDGET_OCT = {"4000": -132_000, "4100": -18_000, "5000": 8_000, "6000": 125_000, "6100": 6_500,
              "6200": 9_500, "6300": 5_000, "6400": 3_500, "6500": 10_000, "6600": 1_500,
              "6700": 50, "7000": -100}


def months_between(start: str, period_end: str) -> int:
    """Number of months of a schedule elapsed through the end of the given month (inclusive)."""
    s, e = pd.Timestamp(start), pd.Timestamp(period_end)
    return max(0, (e.year - s.year) * 12 + (e.month - s.month) + 1)


def schedule_balance(rows, through: str, total_idx: int, months_idx: int, start_idx: int) -> float:
    bal = 0.0
    for r in rows:
        elapsed = min(r[months_idx], months_between(r[start_idx], through))
        bal += r[total_idx] - r[total_idx] / r[months_idx] * elapsed
    return round(bal, 2)


def build_tb(bs: dict, pnl: dict) -> pd.DataFrame:
    bal = {**bs, **pnl}
    bal["3100"] = -round(sum(bal.values()), 2)  # retained earnings (opening for the month) balances the TB
    rows = [(a, n, t, round(bal.get(a, 0.0), 2)) for a, n, t in ACCOUNTS]
    return pd.DataFrame(rows, columns=["account", "name", "type", "balance"])


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(ACCOUNTS, columns=["account", "name", "type"]).to_csv(OUT / "chart_of_accounts.csv", index=False)

    gl = [(g, r, d, a) for g, _, r, d, a in BOTH] + GL_ONLY
    gl_df = pd.DataFrame(gl, columns=["date", "ref", "description", "amount"]).sort_values("date")
    gl_df.to_csv(OUT / "gl_cash_detail.csv", index=False)
    bank = [(b, r, d, a) for _, b, r, d, a in BOTH] + BANK_ONLY
    bank_df = pd.DataFrame(bank, columns=["date", "ref", "description", "amount"]).sort_values("date")
    bank_df.to_csv(OUT / "bank_statement.csv", index=False)
    pd.DataFrame([{"beginning_balance": BEGIN_CASH,
                   "ending_balance": round(BEGIN_CASH + bank_df.amount.sum(), 2)}]).to_csv(
        OUT / "bank_statement_summary.csv", index=False)

    pd.DataFrame(AR_AGING, columns=["customer", "invoice", "invoice_date", "amount", "bucket"]).to_csv(
        OUT / "ar_aging.csv", index=False)
    pd.DataFrame(AP_AGING, columns=["vendor", "invoice", "invoice_date", "amount", "bucket"]).to_csv(
        OUT / "ap_aging.csv", index=False)
    pd.DataFrame(UNRECORDED_INVOICES, columns=["vendor", "invoice", "received_date", "description",
                                               "expense_account", "amount"]).to_csv(
        OUT / "unrecorded_invoices.csv", index=False)
    pd.DataFrame(PREPAIDS, columns=["item", "expense_account", "start", "months", "total"]).to_csv(
        OUT / "prepaid_schedule.csv", index=False)
    pd.DataFrame(FIXED_ASSETS, columns=["asset_id", "description", "in_service", "cost", "life_months"]).to_csv(
        OUT / "fixed_asset_register.csv", index=False)
    pd.DataFrame(DEFERRED_REVENUE, columns=["contract", "customer", "start", "months", "total"]).to_csv(
        OUT / "deferred_revenue_schedule.csv", index=False)

    # Balance sheet before October adjustments (schedules rolled through September)
    fa_cost = sum(a[3] for a in FIXED_ASSETS)
    accum_sep = sum(a[3] / a[4] * min(a[4], months_between(a[2], "2026-09-30")) for a in FIXED_ASSETS)
    bs_oct = {
        "1000": round(BEGIN_CASH + gl_df.amount.sum(), 2),
        "1100": sum(r[3] for r in AR_AGING) + AR_GL_EXTRA,
        "1300": schedule_balance(PREPAIDS, "2026-09-30", 4, 3, 2),
        "1500": fa_cost,
        "1510": -round(accum_sep, 2),
        "2000": -sum(r[3] for r in AP_AGING),
        "2100": -12_000,  # accrued bonus, unchanged
        "2400": -schedule_balance(DEFERRED_REVENUE, "2026-09-30", 4, 3, 2),
        "3000": -250_000,
    }
    bs_sep = {"1000": BEGIN_CASH, "1100": 201_300, "1300": schedule_balance(PREPAIDS, "2026-09-30", 4, 3, 2),
              "1500": fa_cost - 7_200,
              "1510": -round(accum_sep, 2), "2000": -38_900, "2100": -12_000,
              "2400": -schedule_balance([d for d in DEFERRED_REVENUE if d[0] != "C-219"], "2026-09-30", 4, 3, 2),
              "3000": -250_000}

    build_tb(bs_sep, PNL_SEP).to_csv(OUT / "prior_trial_balance.csv", index=False)
    build_tb(bs_oct, PNL_OCT_UNADJ).to_csv(OUT / "trial_balance.csv", index=False)
    pd.DataFrame([(a, v) for a, v in BUDGET_OCT.items()], columns=["account", "budget"]).to_csv(
        OUT / "budget.csv", index=False)
    print(f"Sample data written to {OUT}")


if __name__ == "__main__":
    main()
