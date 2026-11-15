"""Offline mode: runs the same steps in a fixed order with rule-based commentary (no API key needed)."""
from .engine import CloseRun


def _money(x):
    return f"${abs(x):,.0f}"


def rule_based_commentary(run: CloseRun) -> dict:
    comments = {}
    for line in run.flux[run.flux.needs_commentary].itertuples():
        parts = []
        if line.flag_prior:
            parts.append(f"{'Up' if line.vs_prior > 0 else 'Down'} {_money(line.vs_prior)} vs prior month")
        if line.flag_budget:
            parts.append(f"{'over' if line.vs_budget > 0 else 'under'} budget by {_money(line.vs_budget)}")
        jes = [j.je_id for j in run.jes if any(l[0] == line.account for l in j.lines)]
        if jes:
            parts.append(f"includes {', '.join(jes)}")
        comments[line.account] = "; ".join(parts) + ". Driver to be confirmed by reviewer."
    return comments


def build_memo(run: CloseRun) -> str:
    cfg, fs = run.config, run.fs
    inc = fs["income_statement"]
    passed = sum(c["passed"] for c in run.checks)
    lines = [
        f"# Close memo: {cfg['entity']}, {cfg['period']}",
        "",
        "**Status:** Prepared for review. Nothing has been posted to the ERP.",
        "",
        "## Results",
        f"- Revenue {_money(inc['total_revenue'])}, expenses {_money(inc['total_expenses'])}, "
        f"net {'income' if inc['net_income'] >= 0 else 'loss'} {_money(inc['net_income'])}",
        f"- Cash {_money(fs['cash'])}; bank rec {'reconciled' if run.bank['reconciled'] else 'NOT reconciled'}",
        f"- {len(run.jes)} proposed JEs totaling {_money(sum(j.amount for j in run.jes))}",
        f"- Tie-out checks: {passed} of {len(run.checks)} passed",
        "",
        "## Open items",
    ]
    items = run.open_items()
    lines += [f"- **{i['area']}**: {i['detail']}" for i in items] or ["- None"]
    lines += ["", "## Flux highlights"]
    flagged = run.flux[run.flux.needs_commentary]
    lines += [f"- {r.name}: {r.commentary}" for r in flagged.itertuples()] or ["- No lines over threshold"]
    return "\n".join(lines) + "\n"


def run_offline(run: CloseRun) -> CloseRun:
    status = run.check_inputs()
    if not status["ready"]:
        raise SystemExit(f"Missing inputs: {', '.join(status['missing'])}")
    run.run_bank_rec()
    run.run_subledger_recs()
    run.propose_journal_entries()
    run.build_adjusted_tb()
    run.run_flux()
    run.record_flux_commentary(rule_based_commentary(run))
    run.build_financials()
    run.write_close_memo(build_memo(run))
    return run
