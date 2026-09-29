---
name: carolina-split
description: Calculate how Lemmy (The Zig) and Nabil (Projecly) split the margin on Carolina Leon Castro's Verdon contract, per day and per month. Use when asked about the Nabil split, Carolina's margin, or how much was made from Carolina in a month.
---

# Carolina / Verdon split — Lemmy & Nabil

## The deal (EUR excl. VAT)

| Term | Value | Source |
|---|---|---|
| Verdon pays Projecly | €450/day, 5 days/week, 13/04/2026 → 13/04/2028 | Convention de Collaboration + ZIG01 contrat cadre (Outlook, 7 Apr 2026) |
| Carolina's rate | **€315/day** (originally €300, she renegotiated) | Lemmy, 2026-09-29 |
| Nabil's cut | €40/day, agreed when margin was €150 | Lemmy, 2026-09-29 (verbal, not in writing) |
| Advance fee | 3% of Carolina's invoice, covered by Lemmy when she takes an advance | Lemmy's email to Access Financial, 28 Jul 2026 |

Margin now = 450 − 315 = **€135/day**.

## Two readings of the €40 — always show both until Lemmy confirms which

- **A — fixed:** Nabil €40/day, Lemmy €95/day (Lemmy absorbs the whole raise).
- **B — proportional:** Nabil keeps 40/150 = 26.7% of margin → €36/day, Lemmy €99/day.

## How to run

```bash
python3 .claude/skills/carolina-split/split.py --days <timesheet days> [--advance]
python3 .claude/skills/carolina-split/split.py --month 2026-10   # estimate from Belgian working days
```

Override any term with `--client`, `--contractor`, `--nabil`, `--base-margin`.

## Rules

1. **Always base it on the timesheet.** Carolina emails it monthly (subject "timesheet + facture (mois de …) - Carolina Leon", from leoncarolina35@gmail.com). Search Outlook for it and read the `ApprovedTS_…pdf` attachment; it has a text layer. Her own invoice PDF (`INV…pdf`) is a scan and can't be read.
   - **Count the dated rows.** The "Days" column reads 0 on every row, so don't use it. Also report the total hours (Fridays are 7 h, other days 8 h) and check that it was approved by Kevin Formica.
   - Use `--month` only when no timesheet exists yet, and label the result as an estimate.
2. Subtract the 3% advance fee from Lemmy's share only if she took an advance that month.
3. Everything is excl. VAT. Nabil gets paid first because Verdon pays Projecly, so Lemmy's share is money owed *to* Lemmy.
4. The split is verbal. If it is ever disputed, suggest a written side agreement.

## Ledger (from approved timesheets)

| Month | Days | Hours | Billed | Carolina | Margin | Nabil A / B | Lemmy A / B | Advance fee |
|---|---|---|---|---|---|---|---|---|
| Sep 2026 | 20 (no 25 or 28 Sep) | 157 | €9,000 | €6,300 | €2,700 | €800 / €720 | €1,900 / €1,980 | −€189 if she took one |
