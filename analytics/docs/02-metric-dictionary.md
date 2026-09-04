# Metric dictionary

Every metric the engine computes, its exact definition, and where it comes from in
Bullhorn. `metric_id` values are the literal keys used in code (`metrics.py`) and in the
dashboard JSON — keep them stable.

**[VERIFY]** = the Bullhorn source depends on Gentis's tenant configuration and must be
confirmed against the live system or the export before trusting the number.

---

## Band 1 — Outreach (fully consultant-controlled)

| metric_id | Name | Definition | Bullhorn source |
|---|---|---|---|
| `calls` | Calls | Count of logged call activities in period | `Note.action` in call set **[VERIFY]** |
| `connects` | Connects | Calls that reached a human (conversation) | `Note.action` = 'Spoke With' / duration > threshold **[VERIFY]** |
| `emails` | Emails out | Logged outbound emails | `Note.action` in email set |
| `linkedin_touches` | LinkedIn touches | InMails / connection messages | `Note.action` **[VERIFY]** — often not logged; may be unrecoverable |
| `outreach_total` | Total outreach | `calls + emails + linkedin_touches` | derived |

> **Data-quality warning.** Outreach is the band most vulnerable to under-logging. If
> Gentis's consultants logged calls inconsistently, Band-1 ratios are unusable and we
> must anchor the funnel at Band 3 (CVs sent) instead. Test this before relying on it:
> plot logged calls per consultant per week and look for implausible zeros or round
> numbers clustering on Fridays.

## Band 2 — Business development

| metric_id | Name | Definition | Bullhorn source |
|---|---|---|---|
| `client_meetings` | Client meetings | BD meetings held with a client contact | `Appointment` type / `Note.action` **[VERIFY]** |
| `new_contacts` | New contacts added | `ClientContact` records created in period | `ClientContact.dateAdded` |
| `new_clients` | New clients added | `ClientCorporation` created in period | `ClientCorporation.dateAdded` |
| `jobs_taken` | Jobs taken | `JobOrder` records created in period | `JobOrder.dateAdded` |
| `jobs_qualified` | Jobs qualified | Jobs meeting a quality bar (exclusive / retained / fully-briefed) | `JobOrder` custom field **[VERIFY]** |
| `jobs_live` | Live jobs | Jobs open at period end | `JobOrder.status` = Open |

## Band 3 — Delivery

| metric_id | Name | Definition | Bullhorn source |
|---|---|---|---|
| `candidates_added` | Candidates added | New `Candidate` records | `Candidate.dateAdded` |
| `internal_submissions` | Internal submissions | Candidate shortlisted internally | `JobSubmission` entry to internal status |
| `cvs_sent` | **CVs sent** | Submission reaches client-submitted status | `JobSubmissionHistory` entry to 'Client Submission' **[VERIFY]** |
| `first_interviews` | 1st interviews | Submission reaches first interview status | `JobSubmissionHistory` **[VERIFY]** |
| `further_interviews` | 2nd+ interviews | Submission reaches 2nd/3rd interview status | `JobSubmissionHistory` **[VERIFY]** |
| `offers` | Offers | Submission reaches offered status | `JobSubmissionHistory` **[VERIFY]** |

`cvs_sent` is the anchor metric of the whole system. It is the earliest point in the
funnel that is (a) reliably logged, because it is a client-facing act, and (b) directly
causal to revenue. Where outreach logging is poor, everything is normalised per CV sent.

## Band 4 — Outcome

| metric_id | Name | Definition | Bullhorn source |
|---|---|---|---|
| `placements` | Placements | `Placement` records with start date in period | `Placement.dateBegin` |
| `placements_billed` | Billed placements | Placements past rebate/guarantee period | `Placement` + rebate rule **[VERIFY]** |
| `gp` | GP / NFI | Net fee income (perm fee, or contract margin × hours) | `Placement.fee` / margin calc **[VERIFY]** |
| `avg_fee` | Average fee | `gp / placements` | derived |
| `fall_offs` | Fall-offs | Placements terminated inside guarantee period | `Placement.status` **[VERIFY]** |
| `contract_runners` | Runners | Contractors on assignment at period end | `Placement` where contract and active |

### Perm vs contract — do not mix them

Perm GP is recognised as a lump at placement. Contract GP accrues weekly over the
assignment. Mixing them in one GP series makes YoY nonsense and makes contract desks look
weak in year 1 and unbeatable in year 3. The engine keeps `placement_type` on every fact
row and every ratio can be computed within type. **Always segment before comparing markets.**

## Derived rate/efficiency metrics

| metric_id | Definition | Why it matters |
|---|---|---|
| `gp_per_cv` | `gp / cvs_sent` | The single best "money per unit of effort" measure. Ranks markets. |
| `gp_per_call` | `gp / calls` | Only meaningful where call logging is clean |
| `gp_per_head` | `gp / active consultants` | Desk productivity; the number the board looks at |
| `cvs_per_job` | `cvs_sent / jobs_taken` | Quality gate. **[PRIOR]** < 2 signals skipped steps / poor data |
| `fill_rate` | `placements / jobs_taken` | Job quality. Exclusive vs contingent differ by 3-5× |
| `time_to_first_cv` | days from job open → first CV sent | Speed metric; strongly predicts fill |
| `time_to_fill` | days from job open → placement start | Client-facing SLA |
| `time_to_money` | days from first outreach → GP recognised | Cash-cycle planning |
| `revenue_concentration` | HHI of GP by client | Risk metric — a market can look great and be one account |

## Dimensions (every metric sliceable by these)

| dimension | Values | Note |
|---|---|---|
| `consultant` | CorporateUser | Plus tenure band, for ramp curves |
| `market` | Desk / vertical / specialism | **[VERIFY]** how Gentis encoded this — may be team, division, or a job custom field |
| `client` | ClientCorporation | Plus account tier |
| `geo` | Country / region | Belgium (Flanders / Wallonia / Brussels), NL, FR, LU, DE **[VERIFY]** |
| `placement_type` | perm / contract | Never mix |
| `period` | day/week/month/quarter/year | Plus rolling 7/30/90/365 and YTD |
| `seniority` | Job level | Drives fee size and cycle time |

## The market dimension is the one to get right

The brief asks which markets to attack in which order. "Market" must be defined
consistently across the whole history or year-by-year comparison is meaningless. In
Bullhorn this is usually **not** a clean field — it is inferred from the job's category /
specialty, the consultant's team, or a custom field. Resolve it once, in `ingest.py`,
into a single canonical `market` value, and record the resolution rule. If Gentis changed
team structure mid-history (they will have), map old teams onto current markets with an
explicit crosswalk table rather than letting the series break.
