"""Checks module 2 against the seeded answer keys."""
import csv
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from preclose import flux, gl, preclose  # noqa: E402

DATA = ROOT / "data" / "preclose_flux"


@pytest.fixture(scope="module")
def results():
    data = gl.load(DATA)
    findings, stats = preclose.run(data)
    return data, findings, stats, {f.account: f for f in flux.run(data, findings)}


def _key(name):
    with open(DATA / name, newline="") as f:
        return list(csv.DictReader(f))


def test_every_line_is_tested(results):
    data, _, stats, _ = results
    assert stats["lines_checked"] == sum(1 for r in data["lines"] if r["period"] == gl.PERIOD)


@pytest.mark.parametrize("row", _key("answer_key_preclose.csv"), ids=lambda r: f"{r['category']}:{r['je_number']}")
def test_seeded_preclose_issue_found(results, row):
    data, findings, _, _ = results
    cp = next((r["counterparty"] for r in data["lines"] if r["je_number"] == row["je_number"]), "")
    hits = [f for f in findings if f.check == row["category"]
            and (f.je_number == row["je_number"] or (row["category"] == "Duplicate" and f.counterparty == cp))]
    assert hits, f"Not found: {row}"


def test_proposed_reclasses_balance(results):
    _, findings, _, _ = results
    for f in findings:
        if f.reclass:
            assert round(sum(x[2] for x in f.reclass) - sum(x[3] for x in f.reclass), 2) == 0, f.id


@pytest.mark.parametrize("row", _key("answer_key_flux.csv"), ids=lambda r: r["account"])
def test_flux_flags_account_and_names_driver(results, row):
    *_, fl = results
    line = fl[row["account"]]
    assert line.flagged, f"{row['account']} not flagged"
    assert row["main_driver"] in [d.key for d in line.drivers]
    assert row["main_driver"] in line.commentary


def test_quiet_accounts_not_flagged(results):
    *_, fl = results
    for acct in ("6600", "6700"):
        assert not fl[acct].flagged


def test_miscode_is_linked_in_commentary(results):
    *_, fl = results
    assert "Wrong account" in fl["6200"].commentary and "Wrong account" in fl["6100"].commentary
