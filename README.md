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

## Roadmap

- Cash flow statement (indirect method)
- Read the trial balance directly from NetSuite or QuickBooks instead of CSV exports
- Payroll accrual from the payroll register
- Multi-entity close with intercompany eliminations
