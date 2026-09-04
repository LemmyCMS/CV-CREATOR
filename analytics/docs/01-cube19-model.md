# How Cube19 actually works (and what we must replicate)

> Status of this document: reconstructed model. Cube19's tenant (`app.cube19.io`) is
> login-gated and blocked by our network policy, so this is built from (a) Bullhorn's
> public entity model, which Cube19 sits on top of, (b) Bullhorn/Cube19 public product
> documentation and marketing collateral, and (c) The Zig's own internal notes on how
> Gentis used it (`Recruitment Project Overview.docx`, `The Zig Recruitment.pptx`).
> Anything marked **[VERIFY]** should be confirmed against the live tenant before we
> hard-code it. Anything marked **[PRIOR]** is an industry benchmark, not a Gentis fact.

---

## 1. The one-sentence version

Cube19 is **not a data source**. It is a read-only analytics layer that mirrors the
Bullhorn ATS/CRM database into its own warehouse, converts Bullhorn rows into
*countable events*, and then does three things with them: **counts** (metrics),
**divides** (ratios), and **compares to a number you set** (targets).

That is the whole product. Everything else — One View, OnPoint, cubeTV, the dashboards
module — is presentation over those three operations.

This matters enormously for us: **the value we are mining is not the software, it is
(1) the event definitions, (2) the ratio set, and (3) the historical data.** We can
rebuild (1) and (2) from first principles. (3) we can only get by exporting before
Gentis switches Cube19 off.

## 2. The data substrate: Bullhorn entities

Cube19 reads Bullhorn's core entities. The ones that generate every metric that matters:

| Bullhorn entity | What it is | What Cube19 derives from it |
|---|---|---|
| `ClientCorporation` | The client company | Client dimension, account penetration, GP by client |
| `ClientContact` | Hiring manager / contact | BD universe, contacts added, contact coverage per account |
| `Candidate` | Candidate record | Candidates added, registrations/qualifications |
| `JobOrder` | The live vacancy | Jobs taken, job type (Perm/Contract), fill rate denominator |
| `JobSubmission` | Candidate ↔ Job link, with a `status` | **The funnel.** CV sent, interview stages, offer |
| `JobSubmissionHistory` | Status transition log with timestamps | Stage *transitions* and stage-to-stage timing |
| `Placement` | The won deal | Placements, GP/NFI, fees, start dates, contract runners |
| `Note` / `NoteEntity` | Logged activity, with an `action` | Calls, emails, meetings, BD activity |
| `Appointment` | Diarised meeting | Client meetings, candidate interviews (when diarised) |
| `CorporateUser` | The consultant | Consultant dimension, leaderboards, targets |

### The critical subtlety: `JobSubmission.status`

The recruitment funnel in Bullhorn is **not** a set of separate tables. It is one table
(`JobSubmission`) whose `status` field advances through a configurable pipeline. Cube19
counts a "CV Sent" or a "1st Interview" by matching that status string — against a
**per-tenant configured list**.

This is the single biggest reverse-engineering risk. Gentis will have customised these
strings. Typical Bullhorn defaults look like:

```
New Lead → Internally Submitted → Client Submission (= CV SENT) →
Interview Scheduled (= 1ST INTERVIEW) → Interview Completed →
2nd Interview → Offered → Placed (= PLACEMENT) / Client Declined / Candidate Rejected
```

**[VERIFY]** Pull Gentis's actual status list. Without it, every ratio is computed off
the wrong denominators. This is item #1 in the extraction runbook (`06-migration-extraction.md`).

Two counting rules Cube19 applies that we must copy or we will not reconcile:

1. **Furthest-stage vs. every-stage counting.** A submission that reaches Placed has
   also passed through CV Sent and Interview. Cube19 counts each *stage entry event*
   once (from `JobSubmissionHistory`), not the submission's current status. If you count
   current status only, your CV-sent number collapses and every ratio inflates.
2. **Attribution to the acting user, not the record owner.** A CV sent by consultant A
   on consultant B's job credits A for the activity and (usually, split-dependent)
   B for the placement. Cube19 exposes both `owner` and `sendingUser`. Gentis ran
   360°/split desks **[VERIFY]**, so split rules materially change per-head numbers.

## 3. The metric layer

Cube19 metrics fall into four bands. This ordering *is* the funnel, and it is the
skeleton of everything we build:

```
BAND 1  OUTREACH        Calls · Emails · LinkedIn touches · Connects (conversations)
   │                     ─ these are the only things a consultant fully controls
BAND 2  BUSINESS DEV    Client meetings · New contacts added · New clients ·
   │                     Jobs taken (JobOrder created) · Job qualification
BAND 3  DELIVERY        Candidates added · Internal submissions (shortlist) ·
   │                     CVs sent · 1st interviews · 2nd/further interviews · Offers
BAND 4  OUTCOME         Placements · GP / NFI · Contract runners · Margin ·
                        Average fee · Time-to-fill · Fall-off
```

Cube19's own product line — "find your perfect ratio of activity to money" — is exactly
the claim that Band 1 predicts Band 4 through fixed conversion coefficients. That claim
is testable, and testing it on Gentis's data is the highest-value thing we can do with
the export.

## 4. The dashboard surfaces (what we replicate)

| Cube19 surface | What it does | Our replica |
|---|---|---|
| **One View** | Real-time KPI tiles for a user/team over a period, with trend | `dashboard/` KPI band + sparkline |
| **OnPoint** | A *matrix*: every consultant × every metric, heat-mapped, with performance-vs-target | Leaderboard matrix with heat map |
| **Dashboards module** | Widget canvas: activity over trailing 90 days, YTD progress, trends and ratios | Funnel + ratio cards + YoY charts |
| **cubeTV** | Gamified leaderboard + real-time "deal flash" | Out of scope; noted for CRM parity |
| **Targets** | Per-user/team/period target per metric; RAG status vs. actual, pro-rated to date | `targets.py` back-solver + attainment |
| **Slice & dice** | Filter any metric by client / job / candidate / interview stage / owner / period | Group-by dimensions in the engine |

Standard period grain: **day / week / month / quarter / year**, plus rolling windows
(last 7 / 30 / 90 days, last 12 months) and YTD. Every metric is available at every
grain — that is what makes the "year by year, per market, per individual" analysis the
brief asks for possible.

## 5. What Cube19 does badly (our opportunity)

Worth being explicit, because we are not just cloning it — we are trying to beat it:

1. **It reports ratios, it does not model them.** A consultant with 3 CVs and 1 placement
   shows a 33% CV→placement rate and tops the leaderboard. That is noise, not skill.
   No shrinkage, no confidence intervals. We fix this with Beta-Binomial shrinkage
   (see `03-ratio-playbook.md`).
2. **It has no lag model.** A CV sent in November places in January. Cube19's
   within-period ratio (CVs this month ÷ placements this month) is biased whenever
   volume is changing. We fix this with cohort-based ratios: track the CV cohort forward.
3. **It sets targets by negotiation, not by arithmetic.** Targets are typed in by a
   manager. We back-solve them from the revenue goal through the measured ratio chain,
   with a credible interval on the required activity.
4. **It ranks people, not opportunities.** It will tell you consultant X is behind. It
   will not tell you which *account* or *market* to attack next. That is the ranking
   engine in `05-market-client-scoring.md`.
5. **It has no forward prediction.** No expected-GP-per-100-CVs by market, no
   time-to-money. That is the point of the whole exercise.

## 6. Where this leaves us

We can rebuild the metric and ratio layer with high fidelity — it is arithmetic over
well-understood entities. The irreplaceable asset is the **history**: Gentis's actual
conversion coefficients per market, per client and per consultant, over multiple years.
Once Cube19 is switched off, those coefficients are gone unless exported.

Every hour spent on the export runbook is worth more than an hour spent on the dashboard.
