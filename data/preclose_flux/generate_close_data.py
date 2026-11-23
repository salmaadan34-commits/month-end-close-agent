"""Generate a synthetic GL detail (Jul-Oct 2026), October budget, and seeded close issues.

Writes:
  gl_detail.csv            journal lines (both sides) for 4 months
  chart_of_accounts.csv    accounts with type
  budget.csv               October 2026 budget by P&L account
  answer_key_preclose.csv  seeded pre-close issues (tests only)
  answer_key_flux.csv      accounts expected to need commentary + their main driver (tests only)
"""
import csv
import random
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from bankrec.dates import business_days  # noqa: E402

OUT = Path(__file__).resolve().parent
rng = random.Random(7)

COA = [("1200", "Accounts Receivable", "BS"), ("1010", "Cash - Operating", "BS"),
       ("1400", "Prepaid Expenses", "BS"), ("2000", "Accounts Payable", "BS"),
       ("2100", "Accrued Liabilities", "BS"), ("2200", "Accrued Payroll", "BS"),
       ("4000", "Subscription Revenue", "Revenue"), ("5000", "Hosting (COGS)", "Expense"),
       ("6000", "Salaries & Wages", "Expense"), ("6010", "Payroll Taxes", "Expense"),
       ("6020", "Employee Benefits", "Expense"), ("6100", "Software Subscriptions", "Expense"),
       ("6200", "Rent", "Expense"), ("6300", "Marketing - Advertising", "Expense"),
       ("6310", "Marketing - Events", "Expense"), ("6400", "Professional Fees", "Expense"),
       ("6500", "Office Supplies", "Expense"), ("6600", "Travel & Meals", "Expense"),
       ("6700", "Utilities & Telecom", "Expense")]
NAME = {a: n for a, n, _ in COA}

# vendor, default account, department, monthly base, memo, invoice prefix
VENDORS = [("Amazon Web Services", "5000", "Engineering", 45000, "Cloud hosting", "AWS"),
           ("Salesforce", "6100", "Sales", 6200, "CRM licenses", "SF"),
           ("Adobe", "6100", "Marketing", 1400, "Creative Cloud licenses", "ADB"),
           ("Slack", "6100", "G&A", 2100, "Slack Business+", "SLK"),
           ("Zoom", "6100", "G&A", 900, "Zoom licenses", "ZM"),
           ("HubSpot", "6100", "Marketing", 3800, "Marketing Hub", "HS"),
           ("DocuSign", "6100", "G&A", 650, "eSignature licenses", "DS"),
           ("WeWork", "6200", "G&A", 18500, "Office rent - Seattle", "WW"),
           ("Google Ads", "6300", "Marketing", 12000, "Search ads", "GA"),
           ("Pemberton Legal LLP", "6400", "G&A", 9500, "Legal retainer", "PL"),
           ("Staples", "6500", "G&A", 1250, "Office supplies", "STP"),
           ("Uline", "6500", "G&A", 600, "Shipping supplies", "UL"),
           ("Navan Travel", "6600", "Sales", 3500, "Sales travel", "NV"),
           ("Comcast Business", "6700", "G&A", 450, "Internet service", "CMC"),
           ("Puget Sound Energy", "6700", "G&A", 1100, "Electricity", "PSE")]
PAYROLL = {"Engineering": 180000, "Sales": 90000, "Marketing": 60000, "Customer Success": 50000, "G&A": 70000}
CUSTOMERS = {f: rng.randint(3000, 25000) for f in [
    "Acme Robotics", "Bluepeak Health", "Cobalt Logistics", "Driftwood Media", "Evergreen Dental",
    "Foxglove Labs", "Granite Analytics", "Harborview Hotels", "Ironclad Security", "Juniper Foods",
    "Keystone Realty", "Lumen Energy", "Maple Street Bakery", "Nimbus Software", "Orchid Retail",
    "Pinecrest Schools", "Quarry Construction", "Redwood Capital", "Summit Outdoor", "Tidewater Marine"]}

MONTHS = [(2026, 7), (2026, 8), (2026, 9), (2026, 10)]
lines, pc_key, flux_key = [], [], []
je_seq = {}


def jenum(period):
    je_seq[period] = je_seq.get(period, 0) + 1
    return f"JE-{period.replace('-', '')}-{je_seq[period]:03d}"


def je(period, d, source, legs, created="ap_bot", approved="auto", **hdr):
    """legs: list of (account, debit, credit, department, counterparty, memo, invoice, service_period)."""
    n = jenum(period)
    for i, (acct, dr, cr, dept, cp, memo, inv, svc) in enumerate(legs, 1):
        lines.append(dict(je_number=n, line=i, date=d.isoformat(), period=period, account=acct,
                          account_name=NAME[acct], department=dept, counterparty=cp, invoice_number=inv,
                          service_period=svc, memo=memo, debit=round(dr, 2), credit=round(cr, 2),
                          source=source, created_by=created, approved_by=approved))
    return n


def ap(period, d, acct, dept, vendor, amt, memo, inv, svc=None, **kw):
    svc = svc or period
    return je(period, d, "AP", [(acct, amt, 0, dept, vendor, memo, inv, svc),
                                ("2000", 0, amt, "", vendor, memo, inv, svc)], **kw)


def pc(category, je_number, note):
    pc_key.append(dict(category=category, je_number=je_number, note=note))


for y, m in MONTHS:
    period = f"{y}-{m:02d}"
    bdays = business_days(date(y, m, 1), date(y, m, 28))
    last = business_days(date(y, m, 1), date(y, m + 1, 1) if m < 12 else date(y + 1, 1, 1))[-1]
    oct_ = m == 10
    pick = lambda: rng.choice(bdays)  # noqa: E731
    noise = lambda base: round(base * (1 + rng.uniform(-0.03, 0.03)), 2)  # noqa: E731

    # ---- Revenue ----
    custs = dict(CUSTOMERS)
    if oct_:
        custs["Northstar Payments"] = 18000
        custs["Copperline Bank"] = 12000
    legs = []
    for c, mrr in custs.items():
        inv = f"INV-{y}{m:02d}-{rng.randint(100, 999)}"
        legs += [("1200", mrr, 0, "", c, f"Subscription {period} - {c}", inv, period),
                 ("4000", 0, mrr, "", c, f"Subscription {period} - {c}", inv, period)]
    je(period, date(y, m, 1), "Revenue", legs, created="billing_sync")

    # ---- Payroll ----
    for dept, base in PAYROLL.items():
        sal = base + (51000 if oct_ and dept == "Engineering" else 0)
        memo = f"Payroll {period} - {dept}" + (" (incl. 3 new hires)" if oct_ and dept == "Engineering" else "")
        tax, ben = round(sal * 0.0765, 2), round(sal * 0.12, 2)
        je(period, last, "Payroll", [("6000", sal, 0, dept, "Gusto", memo, "", period),
                                     ("6010", tax, 0, dept, "Gusto", memo, "", period),
                                     ("6020", ben, 0, dept, "Gusto", memo, "", period),
                                     ("2200", 0, sal + tax + ben, "", "Gusto", memo, "", period)],
           created="gusto_sync")

    # ---- Monthly bonus accrual (manual) ----
    n = je(period, last, "Manual", [("6000", 10000, 0, "G&A", "", "Accrued bonus", "", period),
                                    ("2100", 0, 10000, "", "", "Accrued bonus", "", period)],
           created="mlee", approved="mlee" if oct_ else "salz")
    if oct_:
        pc("Segregation of duties", n, "Manual JE created and approved by the same user")

    # ---- Vendor bills ----
    for v, acct, dept, base, memo, pre in VENDORS:
        inv = f"{pre}-{y}{m:02d}{rng.randint(10, 99)}"
        amt, a, dp, cp, mm = noise(base), acct, dept, v, memo
        if oct_:
            if v == "Amazon Web Services":
                amt, mm = 58900.00, "Cloud hosting - usage spike from new customer onboarding"
            if v == "Salesforce":
                amt, mm = 74400.00, "Salesforce annual renewal, Oct 2026-Sep 2027"
            if v == "Google Ads":
                amt, mm = 38400.00, "Q4 lead-gen campaign"
            if v == "WeWork":
                a = "6100"
            if v == "Staples":
                a = "5000"
            if v in ("Adobe", "Zoom", "Uline"):
                dp = ""
            if v == "Navan Travel":
                cp = ""
            if v == "Comcast Business":
                mm = ""
        n = ap(period, pick(), a, dp, cp, amt, mm, inv)
        if oct_:
            if v == "Salesforce":
                pc("Unusual amount", n, "12 months billed at once (switched from monthly billing); 11 months belong in prepaid")
            if v == "WeWork":
                pc("Wrong account", n, "Rent coded to Software Subscriptions")
            if v == "Staples":
                pc("Wrong account", n, "Office supplies coded to Hosting (COGS)")
            if v in ("Adobe", "Zoom", "Uline"):
                pc("Missing field", n, "Department missing")
            if v == "Navan Travel":
                pc("Missing field", n, "Vendor missing")
            if v == "Comcast Business":
                pc("Missing field", n, "Memo missing")
            if v == "HubSpot":
                dup = ap(period, pick(), acct, dept, v, amt, memo, inv)
                pc("Duplicate", dup, "Same HubSpot invoice entered twice")

    if oct_:
        d = date(2026, 10, 28)
        ap(period, d, "6300", "Marketing", "LinkedIn Ads", 9000.00, "Q4 ABM campaign", "LI-2026101")
        ap(period, d, "6310", "Marketing", "FinTech Summit", 25000.00, "FinTech Summit 2026 sponsorship", "FTS-0042")
        n = ap(period, d, "6400", "G&A", "Pemberton Legal LLP", 9500.00, "Legal retainer - November",
               "PL-2026111", svc="2026-11")
        pc("Cutoff", n, "November service booked in October")
        n = je(period, last, "Manual", [("6310", 5000, 0, "Marketing", "", "Reclass booth costs to events", "", period),
                                        ("6300", 0, 4500, "Marketing", "", "Reclass booth costs to events", "", period)],
               created="jsmith", approved="salz")
        pc("Unbalanced JE", n, "Debits 5,000 vs credits 4,500")
        n = je(period, last, "Manual", [("6400", 6000, 0, "G&A", "", "Accrued audit fees", "", period),
                                        ("2100", 0, 6000, "", "", "Accrued audit fees", "", period)],
               created="jsmith", approved="")
        pc("Missing approval", n, "Manual JE has no approver")

# ---- Budget (October) ----
sep = {}
for ln in lines:
    if ln["period"] == "2026-09" and ln["account"][0] in "456":
        sign = -1 if ln["account"].startswith("4") else 1   # natural sign: revenue positive
        sep[ln["account"]] = sep.get(ln["account"], 0) + sign * (ln["debit"] - ln["credit"])
plan = {"6300": 30000, "6310": 20000, "6000": sep["6000"] + 34000, "4000": sep["4000"] + 15000}
budget = [dict(period="2026-10", account=a, account_name=NAME[a],
               amount=round(plan.get(a, sep.get(a, 0) * 1.02), -2)) for a, _, t in COA if t != "BS"]

flux_key = [dict(account=a, main_driver=d) for a, d in [
    ("4000", "Northstar Payments"), ("5000", "Amazon Web Services"), ("6000", "Engineering"),
    ("6100", "WeWork"), ("6200", "WeWork"), ("6300", "Google Ads"), ("6310", "FinTech Summit"),
    ("6400", "Pemberton Legal LLP")]]


def write(name, rows):
    with open(OUT / name, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


write("gl_detail.csv", lines)
write("chart_of_accounts.csv", [dict(account=a, account_name=n, type=t) for a, n, t in COA])
write("budget.csv", budget)
write("answer_key_preclose.csv", pc_key)
write("answer_key_flux.csv", flux_key)
print(f"GL lines: {len(lines)} | JEs: {sum(je_seq.values())} | seeded pre-close issues: {len(pc_key)}")
