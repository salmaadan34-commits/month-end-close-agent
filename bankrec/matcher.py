"""Deterministic matching passes 1-4. Nothing here guesses: every match records the rule used."""
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from itertools import combinations

from . import config as C
from .dates import bdiff

STOPWORDS = {"ACH", "DEBIT", "CREDIT", "PAYMENT", "PMT", "VENDOR", "CUSTOMER", "INC", "LLC",
             "CORP", "CO", "THE", "RECEIPT", "BILL", "INV", "CHECK"}


@dataclass
class Match:
    account: str
    bank_ids: list
    book_ids: list
    rule: str
    detail: str
    confidence: str = "High"
    extra: dict = field(default_factory=dict)


def _tokens(text: str) -> list[str]:
    words = re.findall(r"[A-Z][A-Z.&]+", text.upper())
    return [w for w in words if w not in STOPWORDS and len(w) > 1]


def similarity(bank_desc: str, memo: str) -> float:
    """Name similarity that tolerates bank truncation (e.g. 'CONSULT' vs 'Consulting')."""
    a, b = _tokens(bank_desc), _tokens(memo)
    if not a or not b:
        return 0.0
    hits = sum(1 for x in a if any(y.startswith(x[:4]) or x.startswith(y[:4]) for y in b))
    overlap = hits / max(len(a), len(b))
    ratio = SequenceMatcher(None, " ".join(a), " ".join(b)).ratio()
    return round(max(overlap, ratio), 3)


def eq(x: float, y: float) -> bool:
    return abs(x - y) < C.AMOUNT_TOLERANCE


class Matcher:
    def __init__(self, bank_rows, book_rows):
        self.bank = {r["id"]: r for r in bank_rows}
        self.book = {r["id"]: r for r in book_rows}
        self.mb, self.mk = set(), set()
        self.matches: list[Match] = []

    # -- helpers --------------------------------------------------------------
    def ub(self):
        return [r for r in self.bank.values() if r["id"] not in self.mb]

    def uk(self):
        return [r for r in self.book.values() if r["id"] not in self.mk]

    def _add(self, bank_rows, book_rows, rule, detail, confidence="High", **extra):
        self.mb.update(r["id"] for r in bank_rows)
        self.mk.update(r["id"] for r in book_rows)
        self.matches.append(Match(bank_rows[0]["account"], [r["id"] for r in bank_rows],
                                  [r["id"] for r in book_rows], rule, detail, confidence, extra))

    def _window_cands(self, b):
        return [k for k in self.uk() if k["account"] == b["account"] and eq(k["amount"], b["amount"])
                and bdiff(k["date"], b["date"]) <= C.DATE_WINDOW_BDAYS]

    # -- pass 1: exact reference ---------------------------------------------
    def pass1_exact(self):
        for b in self.ub():
            if not b["reference"]:
                continue
            cands = [k for k in self.uk() if k["account"] == b["account"]
                     and k["reference"] == b["reference"] and eq(k["amount"], b["amount"])]
            if len(cands) == 1:
                k = cands[0]
                self._add([b], [k], "1-Exact", f"Amount + reference {b['reference']} match")

    # -- pass 2: amount + date window, unique both ways ------------------------
    def pass2_window(self):
        for b in self.ub():
            if b["id"] in self.mb:
                continue
            cands = self._window_cands(b)
            if len(cands) != 1:
                continue
            k = cands[0]
            rivals = [x for x in self.ub() if x["account"] == k["account"] and eq(x["amount"], k["amount"])
                      and bdiff(x["date"], k["date"]) <= C.DATE_WINDOW_BDAYS]
            if len(rivals) == 1:
                lag = bdiff(k["date"], b["date"])
                self._add([b], [k], "2-Date window", f"Unique amount match, {lag} business day(s) apart")

    # -- pass 3: fuzzy description to break ties -------------------------------
    def pass3_fuzzy(self):
        proposals = []
        for b in self.ub():
            cands = self._window_cands(b)
            if not cands:
                continue
            scored = sorted(((similarity(b["description"], k["memo"]), k) for k in cands),
                            key=lambda t: (-t[0], t[1]["je_number"]))
            best_score, best = scored[0]
            second = scored[1][0] if len(scored) > 1 else 0.0
            identical_twin = len(scored) > 1 and scored[1][1]["memo"] == best["memo"]
            if best_score < C.MIN_SIMILARITY:
                continue
            if best_score - second < C.MIN_MARGIN and not identical_twin:
                continue
            note = " (identical GL twin left open - possible duplicate)" if identical_twin else ""
            proposals.append((best_score, b, best, note))
        for score, b, k, note in sorted(proposals, key=lambda t: -t[0]):
            if b["id"] in self.mb or k["id"] in self.mk:
                continue
            conf = "High" if score >= 0.7 else "Medium"
            self._add([b], [k], "3-Fuzzy", f"Amount match; description similarity {score:.2f}{note}", conf)

    # -- pass 4: many-to-one / one-to-many (batched payouts, split payments) ---
    def pass4_batches(self):
        for b in self.ub():
            pool = [k for k in self.uk() if k["account"] == b["account"]
                    and (k["amount"] > 0) == (b["amount"] > 0)
                    and k["date"] <= b["date"] and bdiff(k["date"], b["date"]) <= C.BATCH_WINDOW_BDAYS]
            combo = self._subset_sum(pool, b["amount"])
            if combo:
                self._add([b], combo, "4-Many-to-one",
                          f"Bank deposit = {len(combo)} GL entries within {C.BATCH_WINDOW_BDAYS} business days")
        for k in self.uk():
            pool = [b for b in self.ub() if b["account"] == k["account"]
                    and (k["amount"] > 0) == (b["amount"] > 0)
                    and b["date"] >= k["date"] and bdiff(k["date"], b["date"]) <= C.BATCH_WINDOW_BDAYS]
            combo = self._subset_sum(pool, k["amount"])
            if combo:
                self._add(combo, [k], "4-One-to-many",
                          f"GL entry = {len(combo)} bank lines within {C.BATCH_WINDOW_BDAYS} business days")

    @staticmethod
    def _subset_sum(pool, target):
        if len(pool) < 2 or len(pool) > 25:
            return None
        for size in range(2, min(C.MAX_BATCH_SIZE, len(pool)) + 1):
            for combo in combinations(pool, size):
                if eq(sum(r["amount"] for r in combo), target):
                    return list(combo)
        return None

    def run(self):
        self.pass1_exact()
        self.pass2_window()
        self.pass3_fuzzy()
        self.pass4_batches()
        return self
