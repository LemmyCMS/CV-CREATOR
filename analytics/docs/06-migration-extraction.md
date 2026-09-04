# Extraction runbook — get this out of Cube19 before it goes dark

**This is the time-critical document.** The dashboard can be rebuilt any time. Gentis's
historical conversion coefficients cannot be rebuilt once the tenant is switched off.

Priority order below is deliberate: if you only get through item 1, you have preserved
most of the value; if you only get through item 3, you can still rebuild every ratio.

---

## Priority 1 — The configuration (do this first, it is small and it unlocks everything)

Without this, every export below is uninterpretable.

| # | What | Where | Why it is first |
|---|---|---|---|
| 1.1 | The `JobSubmission` status list, in pipeline order | Bullhorn admin → field maps, or Cube19 metric definitions | Defines what counts as a CV sent / interview. Every ratio depends on it. |
| 1.2 | Which statuses Cube19 maps to each metric | Cube19 metric config screens | The mapping is the product. Screenshot every metric definition. |
| 1.3 | The market / desk / team taxonomy, with history of restructures | Bullhorn teams + Cube19 groupings | Year-by-year market comparison is impossible without the crosswalk |
| 1.4 | Target values that were set, per user per period | Cube19 Targets module | Shows what management believed the ratios were — a useful prior and a useful sanity check |
| 1.5 | GP / NFI calculation rules (perm fee basis, contract margin basis, rebate rules) | Cube19 config + finance | Two different GP definitions will not reconcile and someone will spend a week on it |

Screenshots are acceptable for all of Priority 1. Getting it imperfectly is far better
than getting it never.

## Priority 2 — Aggregate history (small files, enormous value)

If the raw export fails, these still let us rebuild every ratio in this repo.

Export each of these at **monthly** grain, for **every year available** (go back as far
as the tenant holds — ideally 5+ years):

| # | Export | Breakdown by | Target file |
|---|---|---|---|
| 2.1 | All Band 1–4 metrics | month × consultant | `agg_metrics_by_consultant_month.csv` |
| 2.2 | All Band 1–4 metrics | month × market/desk | `agg_metrics_by_market_month.csv` |
| 2.3 | All Band 1–4 metrics | month × client | `agg_metrics_by_client_month.csv` |
| 2.4 | GP and placements | month × market × placement type (perm/contract) | `agg_gp_by_market_type_month.csv` |
| 2.5 | Headcount / active consultants | month × market | `agg_headcount_month.csv` |

Metrics to include in each: `calls, connects, emails, client_meetings, new_contacts,
jobs_taken, cvs_sent, first_interviews, further_interviews, offers, placements, gp`.

**2.5 is the one everyone forgets.** Without headcount by month you cannot compute
per-head productivity, you cannot separate "the market grew" from "we put more people on
it", and every YoY comparison is confounded. Get it.

## Priority 3 — Row-level history (the real prize)

Aggregates answer the questions we already know to ask. Row-level data answers the ones
we discover later — cohort analysis, lag distributions, ramp curves, concentration, and
anything the model suggests in six months.

| # | Export | One row per | Must include |
|---|---|---|---|
| 3.1 | Submissions | `JobSubmission` | submission id, job id, candidate id, client id, consultant, **every status change with its timestamp**, market, placement type |
| 3.2 | Placements | `Placement` | placement id, job id, candidate id, client, consultant(s) + split %, start date, GP/fee, perm/contract, fall-off flag, rebate outcome |
| 3.3 | Jobs | `JobOrder` | job id, client, date opened, date closed, status, exclusivity, market, seniority, salary/rate band, number of CVs sent |
| 3.4 | Activity | `Note` | date, consultant, client/contact, action type |
| 3.5 | Clients & contacts | `ClientCorporation`, `ClientContact` | ids, names, date added, owner, industry, geo, active flag |
| 3.6 | Consultants | `CorporateUser` | id, name, start date, leave date, team/market history |

**3.1's status-change timestamps are the single highest-value field in the entire
extraction.** They give the true funnel (every stage entry, not just current status), the
lag distribution, and the cohort attribution. If you can only save one file, save 3.1.

**3.6's start dates are the second.** No start dates means no ramp curves, and ramp
curves are how you set targets for every new hire from now on.

## Practical notes on getting the data out

- Cube19 report screens export to CSV/XLSX. Any report that can be filtered can be
  exported. Aim to export *unfiltered* and filter locally — filtered exports lose the
  denominators.
- Row limits are the usual trap. If a report caps at N rows, split by year and re-export.
  Verify totals against the on-screen number every time.
- Prefer **one file per year** for row-level exports. Easier to retry, easier to verify.
- Bullhorn's REST API is the better route for 3.1–3.6 if credentials are available —
  it gives complete `JobSubmissionHistory`, which the UI export may truncate. Worth
  asking Gentis for API credentials explicitly, and worth doing before the contract ends.
- **Save the raw exports untouched** alongside anything cleaned. Every cleaning decision
  we make will need revisiting.

## Verification before you call it done

Run these checks while the tenant is still live and you can still fix a bad export:

1. **Totals reconcile.** GP by year in the export == GP by year on the Cube19 screen. If
   not, you filtered something.
2. **No cliff.** Plot `cvs_sent` by month across the whole history. A sudden drop is
   usually a status rename, not a business event. Ask before assuming.
3. **Spot-check five placements** end to end: job → submissions → status history → GP.
   If one does not reconcile, the whole file is suspect.
4. **Check the earliest date.** Confirm how far back the tenant actually holds data —
   Cube19 may show 5 years while Bullhorn holds 10, or vice versa.
5. **Check consultant coverage.** Leavers must be present. A history that only contains
   current staff is missing most of its placements.

## Where the files go

Drop exports into `analytics/data/raw/` (git-ignored — they contain client and candidate
personal data and must not be committed). Then:

```bash
python3 -m cube19_analytics.ingest --source cube19-export --path analytics/data/raw
python3 analytics/scripts/build_dashboard.py
```

The ingest adapter is tolerant of column-name variation and reports what it could not
map rather than failing — check its mapping report before trusting the output.

## Data protection

These exports contain candidate and client personal data and fall under GDPR. Keep them
out of git, keep them in the company tenant (SharePoint/OneDrive), restrict access to
those who need it, and delete raw candidate PII once the aggregates are derived. The
analytics in this repo only need ids, dates, amounts and categories — not names, CVs, or
contact details. Strip PII at ingest where you can.
