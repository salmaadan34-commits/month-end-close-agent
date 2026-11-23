"""Pre-close checks: test every journal line in the period instead of sampling."""
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date
from statistics import median

from . import gl as G

SEV_ORDER = {"High": 0, "Medium": 1, "Low": 2}


@dataclass
class Finding:
    check: str
    severity: str
    je_number: str
    line: int | None
    date: str
    account: str
    counterparty: str
    amount: float
    issue: str
    fix: str
    reclass: list = field(default_factory=list)   # [(account, account_name, debit, credit, memo)]
    id: str = ""


def run(data, period=G.PERIOD):
    lines, coa = data["lines"], data["coa"]
    cur = [r for r in lines if r["period"] == period]
    hist = [r for r in lines if r["period"] < period]
    findings: list[Finding] = []
    name = lambda a: coa[a]["account_name"]  # noqa: E731

    jes = defaultdict(list)
    for r in cur:
        jes[r["je_number"]].append(r)

    # 1. JE-level controls
    for n, legs in jes.items():
        h = legs[0]
        dr, cr = round(sum(r["debit"] for r in legs), 2), round(sum(r["credit"] for r in legs), 2)
        if dr != cr:
            findings.append(Finding("Unbalanced JE", "High", n, None, h["date"], legs[0]["account"], "", dr - cr,
                                    f"Debits {dr:,.2f} vs credits {cr:,.2f} (out by {dr - cr:,.2f}).",
                                    "Return to preparer; correct the entry before posting."))
        if h["source"] == "Manual":
            if not h["approved_by"]:
                findings.append(Finding("Missing approval", "High", n, None, h["date"], legs[0]["account"], "", dr,
                                        f"Manual JE '{h['memo']}' by {h['created_by']} has no approver.",
                                        "Obtain approval with support before close."))
            elif h["approved_by"] == h["created_by"]:
                findings.append(Finding("Segregation of duties", "High", n, None, h["date"], legs[0]["account"], "",
                                        dr, f"Manual JE '{h['memo']}' created and approved by {h['created_by']}.",
                                        "Have an independent reviewer approve; note as a control exception."))

    # Vendor history for account / amount tests
    vend_accts, vend_amts, vend_periods = defaultdict(Counter), defaultdict(list), defaultdict(set)
    for r in hist:
        if r["source"] == "AP" and r["type"] == "Expense" and r["counterparty"]:
            vend_accts[r["counterparty"]][r["account"]] += 1
            vend_amts[r["counterparty"]].append(r["pl_amount"])
            vend_periods[r["counterparty"]].add(r["period"])

    seen_invoice = {}
    for r in sorted(cur, key=lambda x: (x["date"], x["je_number"])):
        if r["type"] not in ("Expense", "Revenue"):
            continue
        base = dict(je_number=r["je_number"], line=r["line"], date=r["date"], account=r["account"],
                    counterparty=r["counterparty"], amount=r["pl_amount"])

        # 2. Required fields
        if r["type"] == "Expense" and not r["department"]:
            findings.append(Finding("Missing field", "Medium", issue="Department missing on expense line.",
                                    fix="Assign department (needed for dept P&L and budget reporting).", **base))
        if r["source"] == "AP" and not r["counterparty"]:
            findings.append(Finding("Missing field", "Medium", issue="Vendor missing on AP expense line.",
                                    fix="Attach vendor (1099 tracking, spend analysis).", **base))
        if not r["memo"]:
            findings.append(Finding("Missing field", "Low", issue="Memo blank.",
                                    fix="Add description so the entry is auditable.", **base))

        if r["source"] != "AP" or not r["counterparty"]:
            continue
        v = r["counterparty"]

        # 3. Duplicates
        key = (v, r["invoice_number"])
        if r["invoice_number"] and key in seen_invoice and seen_invoice[key] != r["je_number"]:
            findings.append(Finding("Duplicate", "High",
                                    issue=f"Invoice {r['invoice_number']} from {v} already booked in "
                                          f"{seen_invoice[key]}.",
                                    fix=f"Void {r['je_number']}; confirm vendor was not paid twice.",
                                    reclass=[("2000", "Accounts Payable", r["pl_amount"], 0, f"Void duplicate {v}"),
                                             (r["account"], name(r["account"]), 0, r["pl_amount"],
                                              f"Void duplicate {v}")], **base))
        seen_invoice.setdefault(key, r["je_number"])

        # 4. Wrong account (vendor consistently coded elsewhere)
        hist_accts = vend_accts.get(v)
        if hist_accts:
            usual, count = hist_accts.most_common(1)[0]
            if usual != r["account"] and count >= 2 and len(hist_accts) == 1:
                findings.append(Finding("Wrong account", "High",
                                        issue=f"{v} coded to {r['account']} {name(r['account'])}; "
                                              f"history is {usual} {name(usual)} ({count} of {count} months).",
                                        fix=f"Reclass to {usual} {name(usual)}.",
                                        reclass=[(usual, name(usual), r["pl_amount"], 0, f"Reclass {v}"),
                                                 (r["account"], name(r["account"]), 0, r["pl_amount"],
                                                  f"Reclass {v}")], **base))

        # 5. Unusual amount vs vendor history
        amts = vend_amts.get(v)
        if amts:
            med = median(amts)
            if med > 0 and r["pl_amount"] > G.UNUSUAL_MULTIPLE * med and r["pl_amount"] - med > G.UNUSUAL_MIN_DIFF:
                annual = any(w in r["memo"].lower() for w in ("annual", "renewal", "12 month", "yearly"))
                acct = f"{r['account']} {name(r['account'])}"
                prepaid = round(r["pl_amount"] * 11 / 12, 2)
                monthly = round(r["pl_amount"] / 12, 2)
                ps = sorted(vend_periods[v])
                basis = (f"median of {len(amts)} monthly invoices, {ps[0]} to {ps[-1]}" if len(ps) > 1
                         else f"{ps[0]} invoice")
                fix = (f"12-month charge. Reclass {prepaid:,.2f} from {acct} to 1400 Prepaid Expenses "
                       f"(Dr 1400 / Cr {r['account']}), leaving one month ({monthly:,.2f}) in {acct}; amortize "
                       f"{monthly:,.2f}/month to {acct} over the term."
                       if annual else "Confirm with budget owner; check for prepaid or one-time item.")
                rc = ([("1400", "Prepaid Expenses", prepaid, 0, f"Prepay {v}"),
                       (r["account"], name(r["account"]), 0, prepaid, f"Prepay {v}")]
                      if annual else [])
                findings.append(Finding("Unusual amount", "Medium",
                                        issue=f"{r['pl_amount']:,.2f} is {r['pl_amount'] / med:.1f}x {v}'s typical "
                                              f"{med:,.2f} ({basis}). Memo: '{r['memo']}'.", fix=fix, reclass=rc, **base))

        # 6. Cutoff
        if r["service_period"] and r["service_period"] > period:
            findings.append(Finding("Cutoff", "High",
                                    issue=f"Service period {r['service_period']} booked in {period}.",
                                    fix=(f"Reclass {r['pl_amount']:,.2f} from {r['account']} {name(r['account'])} to 1400 "
                                         f"Prepaid Expenses (Dr 1400 / Cr {r['account']}) to reverse the {period} expense; "
                                         f"expense it to {r['account']} in {r['service_period']}, the service month."),
                                    reclass=[("1400", "Prepaid Expenses", r["pl_amount"], 0, f"Cutoff {v}"),
                                             (r["account"], name(r["account"]), 0, r["pl_amount"],
                                              f"Cutoff {v}")], **base))

    findings.sort(key=lambda f: (SEV_ORDER[f.severity], f.check, f.date))
    for i, f in enumerate(findings, 1):
        f.id = f"PC-{i:02d}"
    stats = dict(lines_checked=len(cur), jes_checked=len(jes))
    return findings, stats
