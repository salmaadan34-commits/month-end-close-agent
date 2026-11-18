"""Load bank, GL and prior-period files into plain dict rows."""
import csv
from datetime import date
from pathlib import Path


def _read(path: Path) -> list[dict]:
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["date"] = date.fromisoformat(r["date"])
        for k in ("amount", "balance", "gl_opening", "bank_opening"):
            if k in r and r[k] != "":
                r[k] = float(r[k])
    return rows


def load(data_dir: str | Path) -> dict:
    d = Path(data_dir)
    bank = _read(d / "bank_statement.csv")
    for i, r in enumerate(bank, 1):
        r["id"] = f"B{i:04d}"

    gl = _read(d / "gl_cash_detail.csv")
    for i, r in enumerate(gl, 1):
        r["id"], r["source"] = f"G{i:04d}", "gl"

    prior = _read(d / "prior_outstanding.csv")
    for i, r in enumerate(prior, 1):
        r["id"], r["source"] = f"P{i:04d}", "prior"

    with open(d / "opening_balances.csv", newline="") as f:
        opening = {r["account"]: {"gl_account": r["gl_account"],
                                  "gl_opening": float(r["gl_opening"]),
                                  "bank_opening": float(r["bank_opening"])}
                   for r in csv.DictReader(f)}

    return {"bank": bank, "book": gl + prior, "opening": opening}
