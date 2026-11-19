"""Generate synthetic bank + GL data for October 2026 with seeded reconciliation issues.

Writes:
  bank_statement.csv     bank activity for three accounts (with running balance)
  gl_cash_detail.csv     GL cash detail export (NetSuite/QBO style)
  prior_outstanding.csv  outstanding items carried forward from the September rec
  opening_balances.csv   GL and bank opening balances per account
  answer_key.csv         the seeded issues (used only by tests, never by the agent)
"""
import csv
import random
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from bankrec.dates import add_bdays, business_days  # noqa: E402

OUT = Path(__file__).resolve().parent
rng = random.Random(42)
BDAYS = business_days(date(2026, 10, 1), date(2026, 10, 31))
EARLY = BDAYS[:-3]  # through Oct 27, so normal items clear inside the month

CUSTOMERS = ["Acme Robotics", "Bluepeak Health", "Cobalt Logistics", "Driftwood Media",
             "Evergreen Dental", "Foxglove Labs", "Granite Analytics", "Harborview Hotels",
             "Ironclad Security", "Juniper Foods", "Keystone Realty", "Lumen Energy",
             "Maple Street Bakery", "Nimbus Software", "Orchid Retail", "Pinecrest Schools",
             "Quarry Construction", "Redwood Capital", "Summit Outdoor", "Tidewater Marine"]
VENDORS = [("Amazon Web Services", "AMAZON WEB SERVICES"), ("Adobe Inc", "ADOBE INC"),
           ("Salesforce", "SALESFORCE.COM"), ("WeWork", "WEWORK COMPANIES"),
           ("Comcast Business", "COMCAST BUSINESS"), ("Staples", "STAPLES INC"),
           ("FedEx", "FEDEX CORP"), ("Zoom Video", "ZOOM.US"),
           ("Slack Technologies", "SLACK TECHNOLOGIES"), ("Puget Sound Energy", "PUGET SOUND ENERGY"),
           ("Delta Dental", "DELTA DENTAL WA"), ("Cintas", "CINTAS CORP"),
           ("Uline", "ULINE SHIP SUPPLIES"), ("DocuSign", "DOCUSIGN INC"),
           ("Kaiser Permanente", "KAISER FOUNDATION"), ("HubSpot", "HUBSPOT INC"),
           ("Grainger", "W W GRAINGER"), ("Iron Mountain", "IRON MOUNTAIN INC")]
PAYEES = ["Cascade Janitorial", "Rainier Printing", "Sound Movers", "Elliott Bay Catering",
          "Lakeside Plumbing", "Capitol Hill Locksmith", "Ballard Signs", "Fremont Events"]

used: set[float] = set()
bank, gl, prior, key = [], [], [], []
_je = iter(range(1001, 99999))


def amt(lo, hi):
    while True:
        a = round(rng.uniform(lo, hi), 2)
        if a not in used:
            used.add(a)
            return a


def G(acct, d, typ, ref, memo, amount):
    je = f"JE-{next(_je)}"
    gl.append(dict(account=acct, date=d, je_number=je, type=typ, reference=ref, memo=memo,
                   amount=round(amount, 2)))
    return je


def B(acct, d, desc, ref, amount):
    bank.append(dict(account=acct, date=d, description=desc, reference=ref, amount=round(amount, 2)))


def K(acct, side, d, amount, desc, category):
    key.append(dict(account=acct, side=side, date=d, amount=round(amount, 2), description=desc,
                    expected_category=category))


OP, PR = "OPERATING", "PAYROLL"

# ---------- Normal operating activity ----------
for _ in range(90):  # customer ACH receipts
    c = rng.choice(CUSTOMERS)
    d = rng.choice(EARLY)
    inv = f"INV-{rng.randint(20000, 29999)}"
    a = amt(1500, 45000)
    G(OP, d, "deposit", inv, f"Customer payment - {c} {inv}", a)
    B(OP, add_bdays(d, rng.randint(0, 2)), f"ACH CREDIT {c.upper()} PAYMENT", "", a)

for _ in range(140):  # vendor ACH payments; ~40% carry a shared trace number
    v, bn = rng.choice(VENDORS)
    d = rng.choice(EARLY)
    a = -amt(150, 22000)
    trace = f"T{rng.randint(10**8, 10**9 - 1)}" if rng.random() < 0.4 else ""
    G(OP, d, "ach", trace, f"Vendor payment - {v} Bill-{rng.randint(3000, 6999)}", a)
    B(OP, add_bdays(d, rng.randint(0, 2)), f"ACH DEBIT {bn} {trace or rng.randint(100000, 999999)}", trace, a)

check_no = 10450
for _ in range(12):  # checks that clear in October
    p = rng.choice(PAYEES)
    d = rng.choice(BDAYS[:-8])
    a = -amt(200, 9000)
    G(OP, d, "check", str(check_no), f"Check {check_no} - {p}", a)
    B(OP, add_bdays(d, rng.randint(2, 8)), f"CHECK {check_no}", str(check_no), a)
    check_no += 1

a = -amt(8000, 15000)
G(OP, date(2026, 10, 22), "ach", "", "Corporate card payment - American Express", a)
B(OP, date(2026, 10, 23), "AMEX EPAYMENT ACH PMT", "", a)

# Two same-amount, same-day vendor payments (forces the fuzzy pass to decide)
used.add(2500.00)
G(OP, date(2026, 10, 20), "ach", "", "Vendor payment - Brightline Consulting Bill-5120", -2500.00)
G(OP, date(2026, 10, 20), "ach", "", "Vendor payment - Northwind Design Studio Bill-5121", -2500.00)
B(OP, date(2026, 10, 21), "ACH DEBIT NORTHWIND DESIGN STU 448121", "", -2500.00)
B(OP, date(2026, 10, 21), "ACH DEBIT BRIGHTLINE CONSULT 448120", "", -2500.00)

# ---------- Payroll account (funded from operating) ----------
for fund_day, pay_day, x, ref in [(date(2026, 10, 14), date(2026, 10, 15), 142380.55, "XFER-1014"),
                                 (date(2026, 10, 29), date(2026, 10, 30), 139912.10, "XFER-1029")]:
    used.add(x)
    G(OP, fund_day, "transfer", ref, "Transfer to payroll account", -x)
    B(OP, fund_day, "ONLINE TRANSFER TO PAYROLL XXXX1020", ref, -x)
    G(PR, fund_day, "transfer", ref, "Transfer from operating account", x)
    B(PR, fund_day, "ONLINE TRANSFER FROM OPERATING XXXX1010", ref, x)
    net, tax, k401 = round(x * 0.68, 2), round(x * 0.24, 2), round(x * 0.05, 2)
    ben = round(x - net - tax - k401, 2)
    tag = pay_day.strftime("%m/%d")
    for label, bdesc, val in [("net pay", "GUSTO NET PAY", net), ("payroll taxes", "GUSTO TAX", tax),
                              ("401(k)", "GUSTO 401K", k401), ("benefits", "GUSTO BENEFITS", ben)]:
        used.add(val)
        G(PR, pay_day, "ach", "", f"Payroll {tag} - {label}", -val)
        B(PR, pay_day, f"{bdesc} {rng.randint(100000, 999999)}", "", -val)
fee = amt(80, 200)
G(PR, date(2026, 10, 5), "ach", "", "Gusto monthly platform fee", -fee)
B(PR, date(2026, 10, 5), "GUSTO FEE 220410", "", -fee)

# ---------- Prior-month outstanding checks ----------
for d, no, p, a, clears in [(date(2026, 9, 28), "10412", "Cascade Janitorial", -3450.00, date(2026, 10, 2)),
                            (date(2026, 9, 25), "10398", "Rainier Printing", -1200.00, date(2026, 10, 6)),
                            (date(2026, 7, 18), "10233", "Olympic Supply Co", -875.50, None)]:
    used.add(abs(a))
    prior.append(dict(account=OP, date=d, je_number=f"JE-0{no[-3:]}", type="check", reference=no,
                      memo=f"Check {no} - {p}", amount=a))
    if clears:
        B(OP, clears, f"CHECK {no}", no, a)
    else:
        K(OP, "book", d, a, f"Check {no} - {p}", "Stale item")

# ---------- Seeded issues ----------
# Outstanding checks (issued late October, not yet cleared)
for d in [BDAYS[-7], BDAYS[-6], BDAYS[-4], BDAYS[-2], BDAYS[-1]]:
    p = rng.choice(PAYEES)
    a = -amt(300, 6000)
    G(OP, d, "check", str(check_no), f"Check {check_no} - {p}", a)
    K(OP, "book", d, a, f"Check {check_no} - {p}", "Outstanding check")
    check_no += 1

# Deposits in transit (booked on the last business days, not yet in bank)
for d in [BDAYS[-3], BDAYS[-2], BDAYS[-1]]:
    c = rng.choice(CUSTOMERS)
    inv = f"INV-{rng.randint(20000, 29999)}"
    a = amt(3000, 30000)
    G(OP, d, "deposit", inv, f"Customer payment - {c} {inv}", a)
    K(OP, "book", d, a, f"Customer payment - {c}", "Deposit in transit")

# Unbooked bank fees and interest
for d, desc, a, cat in [(date(2026, 10, 14), "OUTGOING WIRE FEE", -30.00, "Unbooked bank fee"),
                        (date(2026, 10, 30), "MONTHLY SERVICE FEE", -45.00, "Unbooked bank fee"),
                        (date(2026, 10, 30), "INTEREST PAYMENT", 212.37, "Unbooked interest")]:
    used.add(abs(a))
    B(OP, d, desc, "", a)
    K(OP, "bank", d, a, desc, cat)

# Unrecorded incoming wire
used.add(25000.00)
B(OP, date(2026, 10, 22), "INCOMING WIRE FROM ACME HOLDINGS LLC REF FT26102214", "FT26102214", 25000.00)
K(OP, "bank", date(2026, 10, 22), 25000.00, "INCOMING WIRE FROM ACME HOLDINGS LLC", "Unrecorded transaction")

# Duplicate GL entry (same bill paid once, posted twice)
used.add(3180.00)
G(OP, date(2026, 10, 9), "ach", "", "Vendor payment - Cloudhost Inc Bill-4471", -3180.00)
G(OP, date(2026, 10, 9), "ach", "", "Vendor payment - Cloudhost Inc Bill-4471", -3180.00)
B(OP, date(2026, 10, 12), "ACH DEBIT CLOUDHOST INC 771203", "", -3180.00)
K(OP, "book", date(2026, 10, 9), -3180.00, "Vendor payment - Cloudhost Inc Bill-4471", "Duplicate GL entry")

# Transposition error: bank 1,254.00 vs GL 1,524.00
used.update({1254.00, 1524.00})
G(OP, date(2026, 10, 16), "ach", "", "Vendor payment - Office Depot Bill-6012", -1524.00)
B(OP, date(2026, 10, 16), "ACH DEBIT OFFICE DEPOT 552190", "", -1254.00)
K(OP, "book", date(2026, 10, 16), -1524.00, "Vendor payment - Office Depot Bill-6012", "Amount mismatch")
K(OP, "bank", date(2026, 10, 16), -1254.00, "ACH DEBIT OFFICE DEPOT 552190", "Amount mismatch")

# Batched Stripe payout: one bank deposit = four GL receipts
parts = []
for d in [date(2026, 10, 13), date(2026, 10, 13), date(2026, 10, 14), date(2026, 10, 14)]:
    c = rng.choice(CUSTOMERS)
    inv = f"INV-{rng.randint(20000, 29999)}"
    a = amt(2000, 7000)
    parts.append(a)
    G(OP, d, "deposit", inv, f"Stripe receipt - {c} {inv}", a)
B(OP, date(2026, 10, 15), "STRIPE TRANSFER ST-8F2K9Q", "", round(sum(parts), 2))

# ---------- Money market reserve (most of Halden's cash) ----------
# Sized so October cash across all three accounts ties to Halden's balance sheet:
# $4,995K month-end cash in cfo-control-center (data/balances.csv, 2026-10).
# Interest is booked by treasury, so it matches. No rng calls here, so the other
# accounts' generated data is unchanged.
RS = "RESERVE"
RS_INTEREST = 14215.40
RS_OPENING = 3827272.57   # 3,827,272.57 + 14,215.40 = 3,841,487.97 at Oct 31
used.add(RS_INTEREST)
G(RS, date(2026, 10, 30), "deposit", "MMF-2610", "Money market interest - October", RS_INTEREST)
B(RS, date(2026, 10, 30), "MONEY MARKET DIVIDEND MMF-2610", "MMF-2610", RS_INTEREST)

# ---------- Write files ----------
opening = {OP: (850000.00, 1010), PR: (25000.00, 1020), RS: (RS_OPENING, 1030)}
prior_total = sum(p["amount"] for p in prior)
bank_open = {OP: round(opening[OP][0] - prior_total, 2), PR: opening[PR][0], RS: opening[RS][0]}

bank.sort(key=lambda r: (r["account"], r["date"], -r["amount"]))
bal = dict(bank_open)
for r in bank:
    bal[r["account"]] = round(bal[r["account"]] + r["amount"], 2)
    r["balance"] = bal[r["account"]]
gl.sort(key=lambda r: (r["account"], r["date"], r["je_number"]))


def write(name, rows, fields):
    with open(OUT / name, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: (v.isoformat() if isinstance(v, date) else v) for k, v in r.items()})


write("bank_statement.csv", bank, ["account", "date", "description", "reference", "amount", "balance"])
write("gl_cash_detail.csv", gl, ["account", "date", "je_number", "type", "reference", "memo", "amount"])
write("prior_outstanding.csv", prior, ["account", "date", "je_number", "type", "reference", "memo", "amount"])
write("opening_balances.csv",
      [dict(account=a, gl_account=opening[a][1], gl_opening=opening[a][0], bank_opening=bank_open[a])
       for a in (OP, PR, RS)], ["account", "gl_account", "gl_opening", "bank_opening"])
write("answer_key.csv", key, ["account", "side", "date", "amount", "description", "expected_category"])
print(f"bank lines: {len(bank)} | GL lines: {len(gl)} | prior O/S: {len(prior)} | seeded issues: {len(key)}")
