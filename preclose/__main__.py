"""Close Agent (module 2): pre-close checks + flux commentary.

    python -m preclose            # rules + template commentary, runs offline
    python -m preclose --llm      # Claude polishes the commentary (needs ANTHROPIC_API_KEY)
"""
import argparse
import time
from pathlib import Path

from preclose import flux, gl, preclose
from preclose.llm import polish
from preclose.report import write_memo, write_summary_json, write_workbook


def main():
    p = argparse.ArgumentParser(description="Run pre-close checks and flux analysis.")
    p.add_argument("--data", default="data/preclose_flux")
    p.add_argument("--out", default="output")
    p.add_argument("--llm", action="store_true", help="have Claude polish the flux commentary")
    a = p.parse_args()

    t0 = time.time()
    data = gl.load(a.data)
    findings, stats = preclose.run(data)
    fl = polish(flux.run(data, findings), use_llm=a.llm)

    out = Path(a.out)
    out.mkdir(exist_ok=True)
    write_workbook(findings, stats, fl, out / f"close_review_{gl.PERIOD}.xlsx")
    write_memo(findings, fl, out / "flux_commentary.md")
    write_summary_json(findings, stats, fl, out / f"preclose_summary_{gl.PERIOD}.json")

    print(f"\nClose Review - {gl.PERIOD}")
    print("-" * 64)
    print(f"Pre-close: tested {stats['lines_checked']} lines in {stats['jes_checked']} JEs -> {len(findings)} findings")
    for f in findings:
        print(f"  {f.id} {f.severity:<6} {f.check:<22} {f.je_number}  {f.counterparty[:22]:<22} {f.amount:>11,.2f}")
    flagged = [f for f in fl if f.flagged]
    print(f"\nFlux: {len(flagged)} of {len(fl)} P&L accounts need commentary")
    for f in flagged:
        pct = f"{f.pct:+.0%}" if f.pct is not None else "n/m"
        print(f"  {f.account} {f.name:<26} {f.var:>+12,.0f} {pct:>6}")
    print(f"\nDone in {time.time() - t0:.1f}s. Outputs written to {out}/")


if __name__ == "__main__":
    main()
