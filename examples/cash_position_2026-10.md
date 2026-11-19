# Daily Cash Position - Friday, October 30, 2026

| Account | Bank balance | Change vs prior day | Book balance (GL) | Adjusted balance | Rec status |
|---|---:|---:|---:|---:|---|
| OPERATING (1010) | 1,107,152.75 | +167.37 | 1,100,108.11 | 1,128,695.48 | Tied |
| PAYROLL (1020) | 24,816.55 | -139,912.10 | 24,816.55 | 24,816.55 | Tied |
| RESERVE (1030) | 3,841,487.97 | +0.00 | 3,841,487.97 | 3,841,487.97 | Tied |
| **Total** | **4,973,457.27** | **-139,744.73** | | | |

## Needs attention (7)

| Item | Account | Amount | Category | Likely cause | Next step |
|---|---|---:|---|---|---|
| Vendor payment - Cloudhost Inc Bill-4471 | OPERATING | -3,180.00 | Duplicate GL entry | Same memo and amount as JE-1267, which already cleared the bank once. | Reverse JE-1268. |
| Vendor payment - Office Depot Bill-6012  /  ACH  | OPERATING | -1,524.00 | Amount mismatch | Transposition: GL 1,524.00 vs bank 1,254.00; difference 270.00 is divisible by 9 and digits match. | Correct JE-1269 to the bank amount. |
| Check 10233 - Olympic Supply Co | OPERATING | -875.50 | Stale item | Check outstanding 105 days (over 60). | Contact payee; void and reissue or escheat per policy. |
| OUTGOING WIRE FEE | OPERATING | -30.00 | Unbooked bank fee | Bank charge not yet recorded in the GL. | Book the fee. |
| INCOMING WIRE FROM ACME HOLDINGS LLC REF FT26102 | OPERATING | 25,000.00 | Unrecorded transaction | Incoming wire from Acme Holdings LLC with no AR receipt or GL entry - likely an unapplied customer payment, investor funding or loan proceeds. | Confirm purpose with Acme Holdings LLC / AR; park in suspense until applied. |
| INTEREST PAYMENT | OPERATING | 212.37 | Unbooked interest | Interest credited by the bank, not yet recorded. | Book interest income. |
| MONTHLY SERVICE FEE | OPERATING | -45.00 | Unbooked bank fee | Bank charge not yet recorded in the GL. | Book the fee. |

## Timing items (8) - expected to clear next month

- Deposits in transit: 34,677.96
- Outstanding checks: -12,259.73
