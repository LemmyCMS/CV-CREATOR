#!/usr/bin/env python3
"""Carolina / Verdon margin split between Lemmy (The Zig) and Nabil (Projecly).

Standard library only. All amounts EUR excl. VAT.

Usage:
  python3 split.py --month 2026-09                 # counts Belgian weekdays
  python3 split.py --days 21                       # actual timesheet days
  python3 split.py --days 21 --advance             # Lemmy covers 3% advance fee
  python3 split.py --days 21 --client 450 --contractor 315 --nabil 40 --base-margin 150
"""
import argparse
import calendar
import datetime as dt

# Deal terms (see SKILL.md for sources)
CLIENT_RATE = 450.0       # Verdon -> Projecly, per day
CONTRACTOR_RATE = 315.0   # Carolina's renegotiated rate (was 300)
NABIL_PER_DAY = 40.0      # agreed on the original deal
BASE_MARGIN = 150.0       # original margin the €40 was agreed against (450 - 300)
ADVANCE_FEE = 0.03        # Access Financial advance fee, covered by Lemmy


def easter(year):
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = (h + l - 7 * m + 114) % 31 + 1
    return dt.date(year, month, day)


def belgian_holidays(year):
    e = easter(year)
    return {
        dt.date(year, 1, 1), e + dt.timedelta(days=1), dt.date(year, 5, 1),
        e + dt.timedelta(days=39), e + dt.timedelta(days=50),
        dt.date(year, 7, 21), dt.date(year, 8, 15), dt.date(year, 11, 1),
        dt.date(year, 11, 11), dt.date(year, 12, 25),
    }


def working_days(year, month):
    hol = belgian_holidays(year)
    n = calendar.monthrange(year, month)[1]
    return sum(1 for d in range(1, n + 1)
               if dt.date(year, month, d).weekday() < 5
               and dt.date(year, month, d) not in hol)


def split(days, client, contractor, nabil, base_margin, advance):
    margin = client - contractor
    a_nabil = nabil
    b_nabil = margin * nabil / base_margin
    fee = contractor * days * ADVANCE_FEE if advance else 0.0
    rows = {
        "A fixed": (a_nabil, margin - a_nabil),
        "B proportional": (b_nabil, margin - b_nabil),
    }
    print(f"Days: {days}   Client €{client:.0f}/d   Carolina €{contractor:.0f}/d   "
          f"Margin €{margin:.2f}/d")
    print(f"Billed €{client*days:,.2f}   Carolina €{contractor*days:,.2f}   "
          f"Margin €{margin*days:,.2f}")
    if advance:
        print(f"Advance fee (3% of Carolina) paid by Lemmy: -€{fee:,.2f}")
    print()
    print(f"{'Option':<16}{'Nabil/d':>9}{'Lemmy/d':>9}{'Nabil total':>13}{'Lemmy total':>13}")
    for name, (n, l) in rows.items():
        print(f"{name:<16}{n:>9.2f}{l:>9.2f}{n*days:>13,.2f}{l*days - fee:>13,.2f}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--days", type=float)
    g.add_argument("--month", help="YYYY-MM, counts Belgian working days")
    p.add_argument("--client", type=float, default=CLIENT_RATE)
    p.add_argument("--contractor", type=float, default=CONTRACTOR_RATE)
    p.add_argument("--nabil", type=float, default=NABIL_PER_DAY)
    p.add_argument("--base-margin", type=float, default=BASE_MARGIN)
    p.add_argument("--advance", action="store_true")
    a = p.parse_args()
    if a.month:
        y, m = map(int, a.month.split("-"))
        days = working_days(y, m)
    else:
        days = a.days
    split(days, a.client, a.contractor, a.nabil, a.base_margin, a.advance)
