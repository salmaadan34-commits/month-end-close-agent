"""Bank Reconciliation Agent - command-line entry point.

    python -m bankrec                 # rule-based, runs offline
    python -m bankrec --llm           # adds Claude review of unexplained items (needs ANTHROPIC_API_KEY)
"""
import argparse
import time
from pathlib import Path

from bankrec import config as C
from bankrec.classifier import TIMING
from bankrec.pipeline import run
from bankrec.report import write_audit_log, write_cash_position, write_workpaper


def main():
    p = argparse.ArgumentParser(description="Reconcile bank statements to GL cash.")
    p.add_argument("--data", default="data/bank_rec", help="folder with the input CSVs")
    p.add_argument("--out", default="output", help="folder for the workpaper and reports")
    p.add_argument("--llm", action="store_true", help="use Claude to review unexplained items")
    a = p.parse_args()

    t0 = time.time()
    res = run(a.data, use_llm=a.llm)
    out = Path(a.out)
    out.mkdir(exist_ok=True)
    period = C.PERIOD_END.strftime("%Y-%m")
    write_workpaper(res, out / f"bank_rec_{period}.xlsx")
    write_cash_position(res, out / "cash_position.md")
    write_audit_log(res, out / "audit_log.csv")

    print(f"\nBank Reconciliation - period ended {C.PERIOD_END}")
    print("-" * 64)
    for rec in res.accounts.values():
        status = "TIED" if abs(rec.difference) < 0.005 else f"OUT BY {rec.difference:,.2f}"
        print(f"{rec.account:<10} bank {rec.bank_end:>14,.2f}  adj bank {rec.adjusted_bank:>14,.2f}  "
              f"adj book {rec.adjusted_book:>14,.2f}  {status}  ({rec.match_rate:.0%} auto-matched)")
    print(f"\n{len(res.matches)} matches, {len(res.items)} reconciling items "
          f"({sum(i.category not in TIMING or i.category == 'Stale item' for i in res.items)} need attention) in {time.time() - t0:.1f}s")
    print(f"Outputs written to {out}/")


if __name__ == "__main__":
    main()
