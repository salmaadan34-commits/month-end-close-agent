"""Run the full reconciliation: load -> match -> classify -> review -> tie out."""
from dataclasses import dataclass, field

from . import classifier as K
from . import config as C
from .loader import load
from .llm import review
from .matcher import Matcher


@dataclass
class AccountRec:
    account: str
    gl_account: str
    bank_end: float
    gl_end: float
    dit: float = 0.0
    os_checks: float = 0.0
    book_adjustments: dict = field(default_factory=dict)
    bank_lines: int = 0
    matched_lines: int = 0

    @property
    def adjusted_bank(self):
        return round(self.bank_end + self.dit + self.os_checks, 2)

    @property
    def adjusted_book(self):
        return round(self.gl_end + sum(self.book_adjustments.values()), 2)

    @property
    def difference(self):
        return round(self.adjusted_bank - self.adjusted_book, 2)

    @property
    def match_rate(self):
        return self.matched_lines / self.bank_lines if self.bank_lines else 1.0


@dataclass
class RecResult:
    accounts: dict
    matches: list
    items: list
    bank: dict
    book: dict


def run(data_dir, use_llm: bool = False) -> RecResult:
    data = load(data_dir)
    m = Matcher(data["bank"], data["book"]).run()
    items = review(K.classify(m), use_llm=use_llm)

    accounts = {}
    for acct, ob in data["opening"].items():
        bank_rows = [r for r in data["bank"] if r["account"] == acct]
        gl_rows = [r for r in data["book"] if r["account"] == acct and r["source"] == "gl"]
        rec = AccountRec(acct, ob["gl_account"],
                         bank_end=round(ob["bank_opening"] + sum(r["amount"] for r in bank_rows), 2),
                         gl_end=round(ob["gl_opening"] + sum(r["amount"] for r in gl_rows), 2),
                         bank_lines=len(bank_rows),
                         matched_lines=sum(1 for r in bank_rows if r["id"] in m.mb))
        for i in (x for x in items if x.account == acct):
            if i.category == K.DEPOSIT_IN_TRANSIT:
                rec.dit = round(rec.dit + i.bank_adj, 2)
            elif i.category in (K.OUTSTANDING_CHECK, K.STALE):
                rec.os_checks = round(rec.os_checks + i.bank_adj, 2)
            if i.book_adj:
                rec.book_adjustments[i.category] = round(rec.book_adjustments.get(i.category, 0) + i.book_adj, 2)
        accounts[acct] = rec

    return RecResult(accounts, m.matches, items, m.bank, m.book)
