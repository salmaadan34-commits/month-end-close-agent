"""Reconciliation settings and chart-of-accounts mapping."""
from datetime import date

PERIOD_END = date(2026, 10, 31)

AMOUNT_TOLERANCE = 0.005      # match amounts to the cent
DATE_WINDOW_BDAYS = 3         # pass 2 / pass 3 date window
BATCH_WINDOW_BDAYS = 5        # pass 4 look-back for batched payouts
MAX_BATCH_SIZE = 6            # max items combined in one many-to-one match
MIN_SIMILARITY = 0.45         # pass 3 description similarity floor
MIN_MARGIN = 0.15             # pass 3 best-vs-second-best margin
DIT_BDAYS = 3                 # deposits booked in the last N business days = in transit
STALE_DAYS = 60               # outstanding items older than this get escalated

LLM_MODEL = "claude-sonnet-5-5"

COA = {
    "OPERATING": ("1010", "Cash - Operating"),
    "PAYROLL": ("1020", "Cash - Payroll"),
    "RESERVE": ("1030", "Cash - Money Market Reserve"),
    "AP": ("2000", "Accounts Payable"),
    "AR": ("1200", "Accounts Receivable"),
    "SUSPENSE": ("2999", "Suspense - Unidentified Cash"),
    "BANK_FEES": ("6420", "Bank Service Charges"),
    "INTEREST": ("4900", "Interest Income"),
}

FEE_KEYWORDS = ("FEE", "SERVICE CHARGE", "MAINTENANCE CHG")
INTEREST_KEYWORDS = ("INTEREST",)
