"""Classify everything the matcher left open into standard reconciling-item categories."""
from dataclasses import dataclass, field

from . import config as C
from .dates import bdiff, business_days
from .matcher import eq

OUTSTANDING_CHECK = "Outstanding check"
DEPOSIT_IN_TRANSIT = "Deposit in transit"
BANK_FEE = "Unbooked bank fee"
INTEREST = "Unbooked interest"
DUPLICATE = "Duplicate GL entry"
AMOUNT_MISMATCH = "Amount mismatch"
UNRECORDED = "Unrecorded transaction"
STALE = "Stale item"
UNMATCHED_BOOK = "Unmatched book entry"

TIMING = {OUTSTANDING_CHECK, DEPOSIT_IN_TRANSIT, STALE}


@dataclass
class RecItem:
    account: str
    side: str                     # "bank" or "book"
    ids: list
    date: object
    description: str
    amount: float
    category: str
    likely_cause: str
    action: str
    confidence: str = "High"
    source: str = "Rule"
    bank_adj: float = 0.0         # effect on adjusted bank balance
    book_adj: float = 0.0         # effect on adjusted book balance
    je_lines: list = field(default_factory=list)   # [(acct_no, acct_name, debit, credit)]
    days_outstanding: int | None = None
    needs_review: bool = False


def _digits(x: float) -> str:
    return "".join(sorted(str(int(round(abs(x) * 100)))))


def _cash(account):
    return C.COA[account]


def classify(matcher, period_end=C.PERIOD_END) -> list[RecItem]:
    items: list[RecItem] = []
    used_bank, used_book = set(), set()
    ub, uk = matcher.ub(), matcher.uk()
    matched_book = [matcher.book[i] for i in matcher.mk]
    last_bdays = business_days(period_end.replace(day=1), period_end)[-C.DIT_BDAYS:]

    # 1. Duplicate GL entries: an open GL line identical to one already matched
    for k in uk:
        twin = next((m for m in matched_book if m["account"] == k["account"] and eq(m["amount"], k["amount"])
                     and m["memo"] == k["memo"] and m["id"] != k["id"]), None)
        if twin:
            cash_no, cash_name = _cash(k["account"])
            amt = abs(k["amount"])
            lines = ([(cash_no, cash_name, amt, 0), (*C.COA["AP"], 0, amt)] if k["amount"] < 0
                     else [(*C.COA["AR"], amt, 0), (cash_no, cash_name, 0, amt)])
            items.append(RecItem(k["account"], "book", [k["id"]], k["date"], k["memo"], k["amount"], DUPLICATE,
                                 f"Same memo and amount as {twin['je_number']}, which already cleared the bank once.",
                                 f"Reverse {k['je_number']}.", book_adj=-k["amount"], je_lines=lines))
            used_book.add(k["id"])

    # 2. Amount mismatches: same counterparty window, difference looks like a keying error
    for k in uk:
        if k["id"] in used_book:
            continue
        for b in ub:
            if b["id"] in used_bank or b["account"] != k["account"]:
                continue
            if bdiff(b["date"], k["date"]) > C.DATE_WINDOW_BDAYS or (b["amount"] > 0) != (k["amount"] > 0):
                continue
            diff = round(b["amount"] - k["amount"], 2)
            cents = int(round(abs(diff) * 100))
            if cents and cents % 9 == 0 and _digits(b["amount"]) == _digits(k["amount"]):
                cash_no, cash_name = _cash(k["account"])
                lines = ([(cash_no, cash_name, diff, 0), (*C.COA["AP"], 0, diff)] if diff > 0
                         else [(*C.COA["AP"], -diff, 0), (cash_no, cash_name, 0, -diff)])
                cause = (f"Transposition: GL {abs(k['amount']):,.2f} vs bank {abs(b['amount']):,.2f}; "
                         f"difference {abs(diff):,.2f} is divisible by 9 and digits match.")
                items.append(RecItem(k["account"], "book", [k["id"], b["id"]], k["date"],
                                     f"{k['memo']}  |  {b['description']}", k["amount"], AMOUNT_MISMATCH, cause,
                                     f"Correct {k['je_number']} to the bank amount.", book_adj=diff, je_lines=lines))
                used_book.add(k["id"])
                used_bank.add(b["id"])
                break

    # 3. Remaining book items: timing differences
    for k in uk:
        if k["id"] in used_book:
            continue
        age = (period_end - k["date"]).days
        if k["type"] == "check":
            if age > C.STALE_DAYS:
                items.append(RecItem(k["account"], "book", [k["id"]], k["date"], k["memo"], k["amount"], STALE,
                                     f"Check outstanding {age} days (over {C.STALE_DAYS}).",
                                     "Contact payee; void and reissue or escheat per policy.",
                                     bank_adj=k["amount"], days_outstanding=age, needs_review=True))
            else:
                items.append(RecItem(k["account"], "book", [k["id"]], k["date"], k["memo"], k["amount"],
                                     OUTSTANDING_CHECK, f"Check issued {age} days before period end; not yet presented.",
                                     "Timing - confirm it clears next month.", bank_adj=k["amount"],
                                     days_outstanding=age))
        elif k["amount"] > 0 and k["date"] in last_bdays:
            items.append(RecItem(k["account"], "book", [k["id"]], k["date"], k["memo"], k["amount"],
                                 DEPOSIT_IN_TRANSIT, "Deposit booked in the last business days; bank has not posted it yet.",
                                 "Timing - confirm it posts in the first days of next month.", bank_adj=k["amount"],
                                 days_outstanding=age))
        else:
            items.append(RecItem(k["account"], "book", [k["id"]], k["date"], k["memo"], k["amount"], UNMATCHED_BOOK,
                                 "GL entry with no bank activity and no timing explanation.", "Research.",
                                 confidence="Low", days_outstanding=age, needs_review=True))

    # 4. Remaining bank items
    for b in ub:
        if b["id"] in used_bank:
            continue
        desc = b["description"].upper()
        cash_no, cash_name = _cash(b["account"])
        amt = abs(b["amount"])
        if any(w in desc for w in C.FEE_KEYWORDS) and b["amount"] < 0:
            items.append(RecItem(b["account"], "bank", [b["id"]], b["date"], b["description"], b["amount"], BANK_FEE,
                                 "Bank charge not yet recorded in the GL.", "Book the fee.", book_adj=b["amount"],
                                 je_lines=[(*C.COA["BANK_FEES"], amt, 0), (cash_no, cash_name, 0, amt)]))
        elif any(w in desc for w in C.INTEREST_KEYWORDS) and b["amount"] > 0:
            items.append(RecItem(b["account"], "bank", [b["id"]], b["date"], b["description"], b["amount"], INTEREST,
                                 "Interest credited by the bank, not yet recorded.", "Book interest income.",
                                 book_adj=b["amount"],
                                 je_lines=[(cash_no, cash_name, amt, 0), (*C.COA["INTEREST"], 0, amt)]))
        else:
            lines = ([(cash_no, cash_name, amt, 0), (*C.COA["SUSPENSE"], 0, amt)] if b["amount"] > 0
                     else [(*C.COA["SUSPENSE"], amt, 0), (cash_no, cash_name, 0, amt)])
            items.append(RecItem(b["account"], "bank", [b["id"]], b["date"], b["description"], b["amount"], UNRECORDED,
                                 "Bank activity with no GL entry.", "Research; park in suspense until identified.",
                                 confidence="Low", book_adj=b["amount"], je_lines=lines, needs_review=True))
    return items
