"""Checks the agent against the seeded answer key."""
import csv
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bankrec.pipeline import run  # noqa: E402


@pytest.fixture(scope="module")
def res():
    return run(ROOT / "data" / "bank_rec")


def answer_key():
    with open(ROOT / "data" / "bank_rec" / "answer_key.csv", newline="") as f:
        return list(csv.DictReader(f))


def test_every_account_ties_to_zero(res):
    for rec in res.accounts.values():
        assert rec.difference == 0, f"{rec.account} out by {rec.difference}"


def test_auto_match_rate_at_least_90pct(res):
    for rec in res.accounts.values():
        assert rec.match_rate >= 0.90, f"{rec.account} match rate {rec.match_rate:.1%}"


@pytest.mark.parametrize("row", answer_key(), ids=lambda r: f"{r['expected_category']}:{r['amount']}")
def test_seeded_issue_caught_with_correct_category(res, row):
    amount = float(row["amount"])
    hits = []
    for item in res.items:
        if item.account != row["account"] or item.category != row["expected_category"]:
            continue
        rows = [res.bank.get(i) or res.book.get(i) for i in item.ids]
        if any(r and abs(r["amount"] - amount) < 0.005 and
               (("description" in r) == (row["side"] == "bank")) for r in rows):
            hits.append(item)
    assert hits, f"Seeded issue not caught: {row}"


def test_stripe_payout_matched_to_four_receipts(res):
    m = next(m for m in res.matches if m.rule == "4-Many-to-one")
    assert "STRIPE" in res.bank[m.bank_ids[0]]["description"]
    assert len(m.book_ids) == 4


def test_same_amount_payments_paired_by_vendor_name(res):
    for m in res.matches:
        b = res.bank[m.bank_ids[0]]
        if abs(b["amount"] + 2500) < 0.005:
            memo = res.book[m.book_ids[0]]["memo"].upper()
            assert ("BRIGHTLINE" in b["description"]) == ("BRIGHTLINE" in memo)


def test_no_item_matched_twice(res):
    bank_ids = [i for m in res.matches for i in m.bank_ids]
    book_ids = [i for m in res.matches for i in m.book_ids]
    assert len(bank_ids) == len(set(bank_ids)) and len(book_ids) == len(set(book_ids))
