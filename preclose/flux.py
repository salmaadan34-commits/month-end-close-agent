"""Flux analysis: break each material P&L change into its drivers and draft the commentary."""
import re
from collections import defaultdict
from dataclasses import dataclass, field

from . import gl as G


@dataclass
class Driver:
    key: str
    current: float
    prior: float
    memo: str
    status: str            # "new", "stopped", "up", "down"
    finding_refs: list = field(default_factory=list)

    @property
    def change(self):
        return round(self.current - self.prior, 2)


@dataclass
class FluxLine:
    account: str
    name: str
    type: str
    current: float
    prior: float
    budget: float
    avg3: float
    drivers: list = field(default_factory=list)
    commentary: str = ""
    commentary_source: str = ""

    @property
    def var(self):
        return round(self.current - self.prior, 2)

    @property
    def pct(self):
        return self.var / abs(self.prior) if self.prior else None

    @property
    def bud_var(self):
        return round(self.current - self.budget, 2)

    @property
    def flagged(self):
        def hit(v, base):
            return abs(v) >= G.MATERIALITY and (not base or abs(v / base) >= G.PCT_THRESHOLD)
        return hit(self.var, self.prior) or hit(self.bud_var, self.budget)


def _prev(period):
    y, m = map(int, period.split("-"))
    return f"{y - 1}-12" if m == 1 else f"{y}-{m - 1:02d}"


def _driver_key(r):
    if r["source"] == "Payroll":
        return r["department"] or "(no department)"
    return r["counterparty"] or r["memo"] or "(unlabeled)"


def _k(x):
    return f"${abs(x) / 1000:,.1f}K"


def run(data, findings, period=G.PERIOD):
    lines, coa, budget = data["lines"], data["coa"], data["budget"]
    prior_p = _prev(period)
    p3 = [prior_p, _prev(prior_p), _prev(_prev(prior_p))]

    totals = defaultdict(float)
    groups = defaultdict(lambda: defaultdict(lambda: {"cur": 0.0, "prior": 0.0, "cur_lines": []}))
    for r in lines:
        if r["type"] not in ("Revenue", "Expense"):
            continue
        totals[(r["account"], r["period"])] += r["pl_amount"]
        g = groups[r["account"]][_driver_key(r)]
        if r["period"] == period:
            g["cur"] += r["pl_amount"]
            g["cur_lines"].append(r)
        elif r["period"] == prior_p:
            g["prior"] += r["pl_amount"]

    by_je = defaultdict(list)
    by_cp = defaultdict(list)
    for f in findings:
        by_je[f.je_number].append(f)
        if f.counterparty:
            by_cp[f.counterparty].append(f)

    out = []
    for a, acc in coa.items():
        if acc["type"] not in ("Revenue", "Expense"):
            continue
        fl = FluxLine(a, acc["account_name"], acc["type"], round(totals[(a, period)], 2),
                      round(totals[(a, prior_p)], 2), budget.get((period, a), 0.0),
                      round(sum(totals[(a, p)] for p in p3) / 3, 2))
        if fl.flagged and fl.var:
            fl.drivers = _drivers(groups[a], fl.var, by_je, by_cp, a)
            fl.commentary = _template(fl, period)
            fl.commentary_source = "Template"
        out.append(fl)
    return out


def _drivers(grp, total_var, by_je, by_cp, account):
    ds = []
    for key, g in grp.items():
        cur, pri = round(g["cur"], 2), round(g["prior"], 2)
        if abs(cur - pri) < 0.01:
            continue
        top = max(g["cur_lines"], key=lambda r: abs(r["pl_amount"]), default=None)
        status = "new" if not pri else "stopped" if not cur else ("up" if cur > pri else "down")
        refs = {f.id: f for r in g["cur_lines"] for f in by_je.get(r["je_number"], [])}
        if status == "stopped":  # e.g. vendor booked to a different account this month
            refs.update({f.id: f for f in by_cp.get(key, []) if f.account != account})
        ds.append(Driver(key, cur, pri, top["memo"] if top else "", status, list(refs.values())))
    # largest movers first; keep any that explain at least 15% of the change (max 4)
    ds.sort(key=lambda d: -abs(d.change))
    floor = max(1000, 0.15 * abs(total_var))
    picked = [d for d in ds if abs(d.change) >= floor][:4] or ds[:1]
    return picked


def _useful_memo(d):
    """Show the memo only if it adds something beyond the driver name and period."""
    rest = re.sub(r"\d{4}-\d{2}|[-()]", " ", d.memo.replace(d.key, ""))
    return len(rest.split()) >= 2


def _describe(d):
    if d.status == "new":
        txt = f"{d.key} {_k(d.current)} new this month"
    elif d.status == "stopped":
        txt = f"{d.key} {_k(d.prior)} not booked here this month"
    else:
        txt = f"{d.key} {'+' if d.change > 0 else '-'}{_k(d.change)}"
    if _useful_memo(d) and d.status != "stopped":
        txt += f" ({d.memo})"
    for f in d.finding_refs:
        txt += f" [see {f.id}: {f.check}]"
    return txt


def _template(fl, period):
    word = "up" if fl.var > 0 else "down"
    pct = f"{fl.pct:+.0%}" if fl.pct is not None else "n/m - nothing booked last month"
    bud = (f"{_k(fl.bud_var)} {'over' if fl.bud_var > 0 else 'under'} budget" if fl.budget
           else "not budgeted")
    s = f"{fl.name} {word} {_k(fl.var)} ({pct}) vs prior month; {bud}. "
    s += "Drivers: " + "; ".join(_describe(d) for d in fl.drivers) + "."
    if any(d.finding_refs for d in fl.drivers):
        s += " Part of this change comes from items flagged in pre-close; resolve those before finalizing."
    return s
