# Month-End Close Agent

An AI agent that prepares a month-end close package from a trial balance and supporting schedules: bank rec, balance sheet recs, proposed journal entries, adjusted TB, flux analysis, financial statements, and a close memo for the Controller.

The agent prepares the close and a person approves it. It has no tool that can post an entry.

## What it does

| Step | Output |
|---|---|
| Input check | Flags missing files before any work starts |
| Bank reconciliation | Matches GL cash to the bank statement by amount and a date window. Separates deposits in transit and outstanding checks from bank items not yet booked |
| Balance sheet recs | Ties AR, AP, prepaids, fixed assets, accumulated depreciation and deferred revenue to their schedules |
| Proposed JEs | Bank fees and interest, expense accruals (auto-reversing), prepaid amortization, depreciation, ASC 606 ratable revenue recognition |
| Controls | Every JE must balance. JEs at or above the approval threshold are flagged. Unexplained rec differences become open items, never plug entries |
| Adjusted TB | Unadjusted + proposed adjustments, with live Excel formulas |
| Flux | P&L vs prior month and vs budget. Lines over both the $ and % thresholds need commentary |
| Financial statements | Income statement and balance sheet, plus tie-out checks |
| Close memo | Status, results, open items and approvals needed |

## How the AI is used

The accounting work (matching, math, building entries) is plain Python, so it gives the same result every time and can be tested. Claude does the parts that need judgment: it calls the steps as tools, reads what each one returns, writes the flux commentary and writes the close memo. The system prompt tells it never to invent figures, never to plug an unexplained difference, and to present every entry as a proposal.

```
Claude (orchestrator)
  ├─ check_inputs
  ├─ run_bank_rec
  ├─ run_subledger_recs
  ├─ propose_journal_entries
  ├─ build_adjusted_tb
  ├─ run_flux  ──────────► record_flux_commentary   (Claude writes)
  ├─ build_financials
  ├─ get_open_items
  └─ write_close_memo                               (Claude writes)
```

## Run it

```bash
pip install -r requirements.txt

# No API key needed: same steps, rule-based commentary
python -m close_agent --offline

# Claude-driven
export ANTHROPIC_API_KEY=...
python -m close_agent
```

Output goes to `output/`:
- `close_package_2026-10.xlsx`: Summary, Bank Rec, BS Recs, Proposed JEs, Adjusted TB, Flux, Income Statement, Balance Sheet, Open Items
- `je_upload_2026-10.csv`: proposed entries in an import-ready layout
- `close_memo_2026-10.md`

A sample run is in [`examples/`](examples/).

## Deep-dive modules

Two standalone modules go further than the core close on the two areas where close time usually goes: reconciling cash and reviewing the GL before close. Each has its own sample data and answer key, and runs offline.

### Bank reconciliation agent (`bankrec/`)

```bash
python -m bankrec          # add --llm for Claude review of unexplained items
```

- **Matching in five passes:**
  1. Exact amount + reference
  2. Unique amount within ±3 business days
  3. Fuzzy vendor-name tie-break (`BRIGHTLINE CONSULT` ↔ `Brightline Consulting`)
  4. Many-to-one (one Stripe payout = 4 GL receipts)
  5. Claude review of anything left
- **Classifies every open item:** outstanding checks, deposits in transit, stale checks (>60 days), unbooked fees and interest, duplicate GL entries, transposition errors (difference divisible by 9), unrecorded wires. Each comes with a balanced proposed JE.
- **Result on the sample month (267 bank lines, 2 accounts):** 98% / 100% auto-matched, 16 of 16 planted exceptions caught, ties to $0.00.
- **Outputs:** the rec workpaper (live formulas), a daily cash position report and an audit log. See [`examples/bank_rec_2026-10.xlsx`](examples/bank_rec_2026-10.xlsx).

### Pre-close checks + driver-based flux (`preclose/`)

```bash
python -m preclose         # add --llm for Claude to polish the commentary
```

- **Tests 100% of journal lines, no sampling:**
  - Unbalanced JEs
  - Manual JEs with no approver
  - Segregation of duties (same preparer and approver)
  - Duplicate invoices
  - Vendors coded to the wrong account vs their history
  - Cutoff (service period after the close month)
  - Unusual amounts (annual renewals routed to prepaid)
  - Missing department, vendor or memo

  Fixable findings come with a balanced proposed reclass.
- **Flux with drivers:** breaks each material change into vendors, customers or departments, labeled new, stopped, up or down. It **links drivers to pre-close findings**: when rent shows −100% and software +275% because WeWork was miscoded, the commentary cites the finding instead of explaining a booking error as a real variance.
- **Result on the sample month (108 lines, 4 months of history):** 13 of 13 planted issues found and 9 accounts flagged, each with the correct driver.
- **Outputs:** [`examples/close_review_2026-10.xlsx`](examples/close_review_2026-10.xlsx) and a draft CFO memo, [`examples/flux_commentary_2026-10.md`](examples/flux_commentary_2026-10.md).

### Machine-readable outputs

Both modules also write a JSON summary (`examples/bank_rec_summary_2026-10.json`, `examples/preclose_summary_2026-10.json`). The [Controller AI Team](https://github.com/salmaadan34-commits/controller-ai-team) hub reads these files, so its Close team shows this agent's real results.

## Sample data

`data/2026-10/` is an October close for **Northwind Analytics, Inc.**, a fictional SaaS company. Run `python scripts/generate_sample_data.py` to rebuild it. Issues were planted in it on purpose so the agent has something to find:

- Two outstanding checks, a deposit in transit, and ACH items that clear one day after the GL date
- A bank fee and interest income that are on the statement but not in the GL
- An audit invoice received in November for October work (accrued, auto-reverses 11/1)
- Prepaid amortization, depreciation (including a new asset placed in service in October) and revenue recognition not yet booked
- A $600 AR difference from a credit memo that is in the billing system but not in the GL. The agent lists it as an open item instead of plugging it

## Configure for your company

Set your own policy in `close_config.yaml`: flux thresholds, the JE approval limit, rec tolerance and account mapping. The defaults are placeholders, and the agent does not invent approval policy. Add lessons from each review under `known_patterns` so the next close starts from them.

To run your own close, replace the CSVs in `data/YYYY-MM/` with exports from your ERP using the same columns.

## Tests

```bash
python -m pytest
```

The tests cover bank matching, the no-plug rule for unexplained differences, JE balancing and amounts, auto-reversal, the approval threshold, step order, the export, and the agent tool loop (with a stub client, so no API calls).

The deep-dive modules are tested against their answer keys (`data/bank_rec/answer_key.csv` and `data/preclose_flux/answer_key_*.csv`). The tests check that every planted issue is found with the right category, recs tie to $0.00, proposed JEs balance and flux drivers are named correctly.

## Roadmap

- Cash flow statement (indirect method)
- Read the trial balance directly from NetSuite or QuickBooks instead of CSV exports
- Payroll accrual from the payroll register
- Multi-entity close with intercompany eliminations
