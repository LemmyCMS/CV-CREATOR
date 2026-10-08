# Project memory — Gentis / The Zig recruitment analytics

Durable context for future sessions. Written 2026-09-04.

## The situation

Gentis is migrating off **Cube19** (the Bullhorn analytics layer at `app.cube19.io`).
Before it is switched off, the goal is to mine it for everything of lasting value:
the metric definitions, the conversion ratios, and above all **the historical data** —
Gentis's own conversion coefficients per market, per client and per consultant, over
several years. Those coefficients are the irreplaceable asset. The software is not.

The stack, per the company's own notes (`Recruitment Project Overview.docx` in
mutale@thezig.io's OneDrive): **Bullhorn** is today's CRM and the source of truth →
**Cube19** reads it for analytics → **Wiggli** is the intended replacement CRM.
HubSpot portal "The Zig" (id 149249094) exists but was empty as of 2026-09-04.

## REAL DATA IS NOW IN (2026-09-04)

The user pasted Cube19 OneView screens and Slice & Dice pages directly. They live in
`analytics/data/gentis/` and drive `scripts/analyse_gentis.py` and the real dashboard:
https://claude.ai/code/artifact/70e3ae0c-697e-405b-a55f-a7d72744d9b9

Three windows: **Sep 2022–Sep 2025** (3y), **Sep 2025–Sep 2026** (12m, adjacent — these two
compare cleanly), and **Oct 2025–May 2026** (7m, NESTED in the 12m and covering only the
strong season — the engine refuses to trend against it, and so should you).

### STRUCTURAL BREAK — read before any number

**Gentis Consultancy (freelance/contract) was separated from Perm in March** (reported by the
user 2026-09-04; **exact date and year still to be confirmed** — assumed 2026-03-01 because it
falls inside both the 12-month and Oct–May windows).

Every perm and total figure in the two most recent windows therefore **spans two different
organisations**. `oneview.py` records this as a first-class `structural_break` and flags the
ten affected metrics (`perm_placements`, `perm_billing`, `perm_jobs_added`,
`perm_first_interviews`, `total_placements`, `total_billing`, `total_jobs_added`, the perm
share metrics, `avg_deal_perm`). Those are scope changes, not performance.

**What survives the filter — and this is the real finding:** the top-of-funnel collapse is
not perm-specific. New organisations −93%, new client contacts −84%, CVs sent −87%, spec CVs
−90%, reference checks −85%, LinkedIn InMails 45,257/yr → 11. None of that is explained by a
perm carve-out.

### The findings that matter

**Volume collapsed ~65%/yr; conversion did not.** CV→placement went 3.26%→3.68%, CV→interview
27.5%→29.7%, meeting→job 1.47→1.59, GP per CV €796→€1,474, avg perm fee €14.3k→€16.4k.
A business that got *better* at converting and shrank anyway does not have a delivery
problem. What died is the top of the funnel: new organisations −93%, new client contacts
−84%, LinkedIn InMails 45,257/yr → 11.

**Perm vs contract — do NOT read as performance.** Perm GP −70%/yr and contract GP −17%/yr
straddle the March separation. The perm fall is at least partly perm leaving the entity.
Re-derive this once the break date is confirmed and the pre/post scopes are known.

**The recovered funnel placement count.** Cube19's ratio block divides by a number that
appears nowhere on the screen — 257 for the 12m window, 2,086 for the 3y — recovered from
four independent published ratios that agree to 0.3%. The metric list shows 606 and 3,629
total placements. **So every OneView ratio describes new-business delivery only**, excluding
extensions and spec placements. Anyone building a target from a screen ratio and measuring
it against total placements is comparing two different funnels.

**The targets were never arithmetic.** Calls landed at 93–99% of target; everything
downstream at 7–32%. The target set implies a 35.1% call→meeting rate (actual 10.7%), 58.2%
CV→interview (actual 35.5%), and 38.4% of jobs being A-jobs (actual 6.7%). The *fee*
assumption was correct — 819 perm placements × €16,410 = the €13.5M perm target almost
exactly. The plan priced deals right and then asked for 6.3x more of them than the funnel
has ever produced.

**A-jobs: corrected.** Cube19 shows "Total A jobs to total placements 1 : 1.1", which reads
as a 110% fill rate implying every placement comes from an A-job. **The row-level export
disproves that** — only 29% of placements carry an A/A+ priority and 16% carry none at all.
Splitting the funnel on that share: A-jobs fill at **32%**, everything else at **5.6%** — a
**5.7x** advantage, still the biggest structural lever, but 5.7x not 15x. Never quote the
naive ratio.

**Most recent window (Oct 2025–May 2026), against rebased targets:** client calls 140%,
total jobs 120%, contract placements 163% — but perm placements 17%, A-jobs 13%, reference
checks 10%. **The activity engine restarted; the qualification and perm engine did not.**

**Levers priced at Gentis's own conversions** (`scenario()` in `oneview.py`): CVs per job
1.99→3.00 = +129 placements; A-jobs 6.7%→15% of jobs = +77; client calls 20.5k→61.6k
(3.3→10.0 per head per day) = +514 but at the blended 7.3% fill rate, so the most expensive.

### The contract book — the clean read (2026-09-04, row-level, 121 rows)

Contract did NOT cross the March perm separation, so unlike perm these are performance
numbers. `data/gentis/contract_placements_sample.csv`, analysed in `_contract_sample()`.

**Contract margin is compressing: median fee 19.4% → 15.6% (−19%).** Mean 21.9% → 17.3%.
26% of current contract placements sit below a 12% margin. Applied to €8.18M of contract
GP a year, restoring the prior margin is worth roughly **€1.5M a year and needs no extra
placements at all** — larger than any activity lever in `scenario()`. This is the single
biggest number found in the whole exercise, and it is invisible on every OneView screen.

**Owner attribution has collapsed: `Ghost_*` placeholders went from 2% to 36% of contract
placements**, holding 14% of sampled GP (Ghost_Bxl-IT, Ghost_Paris-IT, Ghost_Antwerp-IT,
Ghost_Bxl-IT-INFRA, Ghost_Bxl-Engineering, Ghost_Bxl-HR, Ghost France). Nobody is credited,
nobody is accountable, and every leaderboard, commission and coaching number is wrong by
that margin. Cheapest fix on the list.

**Contract time-to-fill is 38 days median (p90 118), not the 578–593 OneView reports.**
The reported metric measures through successive extensions. Contract delivery speed is a
strength being reported as a disaster — do not "fix" it.

**Desk margin does not follow desk volume.** Brussels IT Dev is the biggest contract desk
by GP and the *lowest* margin (14.6%); Brussels IT Infrastructure earns 27.2% on a fraction
of the volume. Luxembourg IT 19.0%. That mix is where the margin went.

Also: 8% of contract jobs are typed "Opportunity" rather than a confirmed role; `Contract
Type` cleanly separates "Original" from "Contract Extension 1"; and "Perm Belgium" rows
appear inside a *contract* export (mis-grouped).

### Data quality — fix before quoting anything externally

- **Billing contradiction**: contract €7.45M + perm €2.12M = €9.56M, but "Total Billing"
  says €4.67M. Two revenue definitions in play. (Same fault in the 3y window: €18.5M gap.)
- **Live Jobs 16,812** against 3,501 added in a year, and identical on every window — a
  stale "as of now" snapshot. Any report using live jobs as a denominator is meaningless.
- **Contract time-to-fill 578 days** — measuring through extensions, not to first start.
- **Reference checks 33% of placements**, down from 110%. Compliance exposure.
- **~12% of perm "placements" are retainer bookings** (candidate field literally reads
  "Candidate Retainer"), median €5,000 against €15,400 for real placements. They inflate
  placement counts and flatter CV→placement, because a retainer needs no CV.
- **4% of placements have €0 billing value.**
- **New candidates never sent anywhere: 80% (77,584 of 96,955) in the 3y window, 85%
  (10,104 of 11,876) in the last 12 months.** Sourcing volume that produces nothing, and
  it was already the norm before the decline.
- **`Ghost_*` owners** (Ghost_Bxl-IT, Ghost_Paris-IT, Ghost_Antwerp-IT, …) appear as
  placement *owner*, not just job owner — unattributable placements that break per-consultant
  analysis.
- **Desk taxonomy churn is real**: `[deleted]` groups still carry history, compound groups
  ("Perm Brussels Construction/Engineering/Sales") were later split, and "Gentis Consultancy"
  is used as an unassigned catch-all. A crosswalk is mandatory for any year-by-year market view.
- **Source field** has "Linkedin" and "LinkedIn" as separate values.
- **Job Type "Opportunity"** exists alongside "Contract" — matches the internal note that
  some job-board postings are opportunities, not confirmed roles. Qualify before counting.
- **Contract Type** distinguishes "Original" from "Contract Extension 1" — that is the
  extension flag, and it resolves the extensions/placements partition.

### Long window Jan 2021 – Oct 2026 (pasted 2026-10-08) — `data/gentis/oneview_2021_2026.json`

- **Unique CVs per placement ≈ 12** (39,949 unique / 3,307 funnel placements; funnel count
  recovered from 2 published ratios agreeing to 0.1%). A floor: uniques dedupe across the whole
  5.8 years. CVs on jobs per placement 29.4; total CVs 783,949 of which only 12.4% on jobs and
  5.1% unique.
- **Re-derived anchor target (unique CVs per recruiter-day, 264 recruiter-days/yr for 2×half-time):**
  6 placements → 0.27, 10 → 0.46, 16 → 0.73. In plain CVs-on-jobs: 0.67 / 1.11 / 1.78. The old
  "2.2 CVs/day" sat above even the high case; replace it with ~0.5 unique (≈1.1 on jobs) base.
- **50% of contract finishers had no extension, CV, interview or placement** (1,587 of 3,160);
  €960,733 of weekly GP walked out unworked. Contractors out today: 178.
- The CV-sent Slice & Dice has **Owner** (the sender, current name e.g. "Ornella Scarpino (Wiggli)")
  separate from **Job Owner** — Owner is the field for `inferred_headcount()`. It also carries
  organisation rate agreements (min/max %), "Freelance Contract?" and payment terms — use the
  min % as the CRM margin floor per client. Only one page (~40 rows, Jan 2021) was pasted; it
  holds candidate names, so it is NOT stored. Ask for the full export as a file.

### The unresolved confound — get this first

OneView shows **today's** 28 users on every period. Historical headcount is simply not in
this data. If per-head output were unchanged, the prior period needed roughly **56–85 heads**.
Until headcount by month exists, "the business shrank" and "the team shrank" are
indistinguishable, and every per-head conclusion is unsafe. This is the single highest-value
missing field.

**Workaround (user's idea, 2026-10-08): infer it from who sent CVs.** `quality.inferred_headcount()`
counts consultants with ≥3 CV sends in a month (Ghost_* excluded) = producing heads per month.
**`Ghost_*` = recruiters who have LEFT Gentis (their records reassigned to a placeholder), or
candidates/records with no owner any more** (user, 2026-10-08). So the Ghost rise 2%→36% of
contract placements is also a leaver signal: a lot of the book was built by people now gone.
For headcount, use the user who *sent* the CV at the time, never the record's current owner,
or leavers vanish from history. Needs a CV-sent export with **sending user + date per row** (Slice & Dice, CVs sent, monthly,
grouped by consultant is enough). The placement samples are too thin for it: 17→21 distinct
contract owners and 23→21 perm owners, which counts closers, not senders.

**Safe headcount ESTIMATE (2026-10-08, user asked for one pending the export)** — CVs on jobs per
year: Jan21–Sep22 ≈15.8k, Sep22–Sep25 21.3k, Sep25–Sep26 7.0k. Assuming today's 28 users hold
~20–28 producing recruiters (250–350 CVs on jobs/head/yr) and per-head output was the same or up
to 1.5× higher before: **2021–22 ≈ 40–60 heads, 2022–25 ≈ 45–85 (central ~60), now ~20–28.**
Cross-check: ≥16 distinct senders in just 2 days of Jan 2021. Reading: team roughly −55–65%,
CV volume −67%, so **most of the decline is fewer people**; per-head output down ~0–25%.
[VERIFY] with the Owner×month export — replace, don't average.

### Still needed

Full Slice & Dice exports (1,493 perm + 2,136 contract placements, not single pages),
headcount by month per desk, the desk crosswalk, a job-level export including jobs that
never filled, and the Cube19 status→metric map. Pasting pages into chat does not scale —
ask for the exported files.

## THE ZIG — the actual operating context (2026-09-04)

**This is The Zig's business, not Gentis's.** Gentis is the benchmark being mined; The Zig is
the company being built. Never write a plan that reads as Gentis's turnaround — the Gentis
numbers are *coefficients*, and the failures in them are *design lessons for the CRM*.

**Capacity: 2 half-time recruiters ≈ 1.0 FTE**, starting September 2026, on the Zig CRM whose
sourcing pipeline still has bugs. Year-one plan artifact:
https://claude.ai/code/artifact/56e7da4c-9fb5-44e5-b800-39acf57ee2a2

**Year one (Sep 2026 – Aug 2027), computed in `dashboard/zig_year1.json`:**
low €103k / base €174k / high €277k billed, 6–16 placements, 249–431 CVs. Base case ends the
year with 10 contractors out and ~€328k/yr already running if weighted to freelance.
Timing is favourable: September opens Gentis's strong season, which runs to May.

**The strategic point: perm banks, freelance compounds.** A perm fee is earned once; a
contractor at €713/wk is worth ~€32.8k a year for as long as they stay. Cumulative over three
years at the same placement rate: perm €174k/€349k/€523k against freelance €170k/€499k/€828k.
**The book plateaus at one year's placements** (12-month tenure) — it does not stack forever,
and modelling it without attrition overstates freelance ~2.4×. That bug was made and fixed.

**Where the CRM genuinely helps — throughput and retention, never conversion.** CVs/day
1.24→2.2 (85% of Gentis candidates never sent anywhere), extension rate 69%→90% (56% of their
finishers had no extension conversation), margin €573→€713/wk (a validation rule, not
negotiation), owner attribution 64%→100%. **CV→placement stays at Gentis's rate — claiming
software improves it would be the one dishonest number in the plan.** The sourcing pipeline is
the critical path: the entire low-to-base gap (€103k→€174k) is CVs per day.

**Daily targets, per day actually worked** (a half-timer works ~2.5 days/week, ~11 days/month):
Sep–Oct no CV target at all (you cannot send CVs to jobs you have not won) — 20 calls, 6 new
contacts, 2 live jobs; Nov–Feb 1.2 CVs, 18 calls; Mar+ 2.2 CVs, 15 calls, 7 live jobs.
**BD activity does not ramp — in month one it is the entire job.** Anchor the system on two
numbers only: **CVs sent per recruiter per day** and **extension rate on finishers**.

**Desks to open first** (from Gentis placement data, directional — 65 perm / 80 contract rows):
perm **Antwerp IT** (€24.9k median, 68-day fill) or **Brussels Construction** (€22.0k, n=7);
freelance **Brussels IT Infrastructure** (€825/wk at 27.2% margin — the best margin in Gentis's
book, while their biggest desk Brussels IT Dev runs €500/wk at 14.6%). Going where the big
agency is weakest and the margin is highest is the opportunity.

### REQUESTED, NOT YET BUILT — editable KPI targets

The user wants to **modify the target on each KPI individually, with the system suggesting
values from what it has measured, presented more intuitively.** Design agreed but deliberately
NOT built yet: each KPI row shows the editable target, what Gentis actually measured, the
benchmark band, and the delta from suggested; changing any one recalculates the whole
downstream forecast live. Persist the team's chosen values with the artifact `db` capability
(`db.doc("targets/current")`, `capabilities: {db: {}}`) so everyone opening the page sees the
same targets and they can be read back here. The forecast maths already exists in
`dashboard/zig_year1.json` and `oneview.py: scenario()` — this is a UI layer over it.

## ⚑ COMMITTED — the user is adamant these get built into the Zig system (do not drop)

Raise this list at the start of any session that touches the CRM, targets or the plan.
Status as of 2026-10-07. Tick only when it is live in the CRM, not when it is designed.

1. **Warm talent pool targets per market and profile type** — BUILT (engine) 2026-10-07,
   `analytics/src/cube19_analytics/talent_pool.py`, doc `analytics/docs/07-warm-talent-pool.md`.
   Goal: 3 strong CVs within 48h of a job landing. Needs ~30 warm per profile type
   (contract) and ~50 (perm); a 2nd simultaneous same-profile job adds 50%, not 100%.
   Warm = contacted ≤90 days + CV on file + GDPR consent. Team capacity ~220 warm per FTE
   — over that, open fewer markets, never build a bigger cold database.
   Fit 50% / availability 20% contract, 12% perm are **[PRIOR]** — measure them in the
   first two months and replace. NOT YET: CRM fields, dashboard tile.
2. **Never repeat Gentis's "never sent" failure** (85% of new candidates never sent) —
   BUILT (engine) in `send_leaks()`: never-sent rate with alarm above 50%, the named list
   of warm+ready candidates matching an open job who were not sent, open jobs past the
   48h SLA with <3 CVs, median days to 3rd CV. NOT YET: a daily queue in the CRM.
3. **Editable KPI targets with suggested values** — designed, not built (section above).
4. **Two anchor numbers**: **UNIQUE** CVs sent per recruiter per day, extension rate on finishers.
   User's definition (2026-10-08): a *CV sent* is any CV out the door (spray and pray);
   a *unique CV sent* is a candidate sent to a **qualified** job, and a candidate counts
   once however many qualified jobs or companies they go to. Gentis 12m: 24,885 total
   CVs, 17,901 spec, 6,984 on jobs, 3,920 unique = 16%. `talent_pool.cv_counts()`; Job has
   a `qualified` flag. Re-derived 2026-10-08: ~0.5 unique/recruiter-day base (0.27 low, 0.73 high) - see long-window section.
5. **CRM data rules from Gentis's failures**: no `Ghost_*`/unassigned owners (100%
   attribution); a margin floor validation on contract placements (26% of Gentis's sat
   under 12%); every contract finisher gets an extension conversation logged; every
   submission records stage entries with timestamps, never just current status.
6. **CRM fields required** for 1–2: candidate `market`, `profile`, `placement_type`,
   `last_contact`, `available_from` (contract mission end), `open_to_move` (perm),
   `cv_on_file`, `consent`; job `profile`. Without `profile` on both sides the matching
   cannot run.

7. **Focus companies + job-signal watcher + generated call list** — requested 2026-10-08,
   NOT BUILT. Recruiter picks focus companies by market/industry in the UI. The system
   checks their careers pages daily (plus companies already committed to) and notifies
   on each new job; every incoming job auto-resolves its client's website/domain. The
   daily call list is generated from the focus + goals: yesterday's call-backs first
   (with reminders), then new-job signals at focus companies, then freelancers ending
   missions, then cold targets. Build notes: prefer public ATS job feeds (Workday,
   Greenhouse, Lever, SmartRecruiters, Teamtailor) over HTML scraping; respect robots.txt
   and site terms; store company data, not personal data, from scrapes (GDPR).
   **Gentis clients are potential business, NOT access.** Equans, AG Insurance etc. were
   Gentis's accounts/PSLs, not The Zig's. Every company carries an account status:
   target -> opening (first contact/meeting) -> active (first job) -> PSL (on the supplier
   list). Suggested lists show Gentis history as "why this company", never as a relationship.
   Only `active`/`PSL` companies are watched automatically.

8. **Job intake → qualification → automated multi-send** — stated 2026-10-08, NOT BUILT.
   ~30 jobs/day come in today (job boards, scrapes, prospection), potentially hundreds/day.
   They are UNQUALIFIED until a client conversation confirms role, budget, timing. Prospection
   emailing + client calls work the unqualified pile to convert it. Goal: **≥10 qualified jobs
   open at all times.** Once a job is qualified the system auto-matches warm candidates and
   prepares the send; one candidate can go to several qualified jobs (counts once as unique).
   **Manager target: 3 UNIQUE CVs per recruiter per day** (user confirmed "unique"). That is
   ~6.5× the Gentis-derived base (0.46) and needs ~15–20 new qualified jobs a month, i.e. a
   2–3% qualification rate on ~660 incoming jobs/month. Automation raises total CVs; only new
   distinct candidates raise unique CVs. Guardrail: candidate consent before any CV goes to a
   client (GDPR + double-submission fee disputes) - automate matching and drafting, keep
   per-candidate consent ("right to represent") before sending.
   **Speculative CVs are prospection, not waste** (user): keep them, count them separately, and
   measure spec CV -> client reply -> job opened, so their value is visible.

## Access constraints discovered (do not re-litigate these)

- `app.cube19.io` is **blocked by the container's egress proxy** (403 on CONNECT), and
  is login-gated regardless. It cannot be reached from a Claude Code cloud session.
- **Claude for Chrome cannot help from here.** It is a browser extension running on the
  user's own machine with their cookies; a cloud session has no bridge to it. There is
  no browser-control tool in this session's registry.
- Most vendor documentation hosts (`bullhorn.com`, `knowledge.3diq.com`) are also
  egress-blocked. `WebSearch` works; `WebFetch` mostly does not.
- `pip install` times out against the proxy. **Everything written here is
  standard-library only**, deliberately, and must stay that way.

Therefore: real data reaches us only as **a CSV export the user produces**, or via
Bullhorn REST credentials. `analytics/docs/06-migration-extraction.md` is the runbook.

## What has been built — `analytics/`

A complete replica of the Cube19 metric and ratio layer, plus the analysis Cube19
does not do. Pure stdlib Python, 42 passing tests, a self-contained HTML dashboard.
Published artifact: https://claude.ai/code/artifact/699d1897-1b5a-4c6f-95f9-6fcec0cbbe31

Read `analytics/README.md` first, then the six numbered docs in `analytics/docs/`.

## The substantive findings worth keeping

**Cube19 is three operations.** It mirrors Bullhorn, converts rows into countable
events, then counts, divides, and compares to a target. Everything else — One View,
OnPoint, cubeTV — is presentation. That is why it is replicable.

**The funnel lives in one Bullhorn table.** `JobSubmission.status` advances through a
per-tenant configured pipeline; `JobSubmissionHistory` holds the transitions. Count
**stage entries**, never current status, or the funnel collapses and every ratio
inflates. Gentis's actual status strings are the single biggest unknown — item 1.1 of
the extraction runbook.

**The chain is multiplicative**, so improvements compound and elasticity is flat: a 10%
relative gain is worth the same at any link. What differs is **headroom**. Every
conversion ratio is bounded at 1.0 and most are past halfway; **average fee has no
ceiling in the data**, which is why market and client selection beats activity coaching
over any horizon longer than a quarter.

**Five corrections this engine makes that Cube19 does not:**

1. **Shrinkage.** 1 placement from 3 CVs reads as 12%, not 33%. Beta-Binomial with the
   parent group as prior, 90% credible interval on everything.
2. **"Not yet known" is a verdict.** A market whose interval straddles its peers has not
   been shown to be weak. It gets a priced experiment, not an exit. Telling the business
   to exit an unresolved market is the most expensive mistake this model could make.
3. **Peer baselines.** Each market is compared against the *rest* of the business, not
   against a firm average it helps set — otherwise the largest market is measured
   against itself and always reads "average".
4. **Partial periods excluded from trend.** A stub year at the edge reads as a collapse
   and flips growing markets to "Exit". This bug was found and fixed; keep the guard.
5. **Logging coverage gates targets.** Volume is not reliability. Coverage is measured
   over *employed consultant-months*, and a metric that fails cannot anchor a target.

**Bounded tests are asymmetric.** Against a 10% baseline: proving a market is 3x better
costs 49 CVs, 2x better costs 157, but merely 1.5x better costs 540. So test only where
the believed gap is large; everywhere else decide on fee size, accessibility and
momentum, which are visible in far less data.

**Set targets at p80, plan capacity at p50.** Eight uncertain ratios multiply, so the
band is wide. Targeting the median means missing half the time by construction.

## What to do next

1. **Get the export.** Priority 1 of the runbook (the config: status list, metric
   definitions, market taxonomy, GP rules) is small and unlocks everything else.
2. Write `analytics/data/gentis_status_map.json` mapping Gentis's real status strings
   onto the canonical stages, then re-run `scripts/build_dashboard.py`.
3. Replace every `[PRIOR]` benchmark in `docs/03` with the measured value.
4. Measure the real CV→placement lag (p90) and set the cohort maturity window to it —
   the 120-day default is a guess.
5. Feed the measured ratios into the CRM design so the new system captures the stage
   transitions and timestamps this analysis depends on. **That is the real payoff:**
   Bullhorn's data model is what made these ratios computable, and a CRM that does not
   record stage entries with timestamps cannot reproduce any of it.

## Conventions

- Standard library only. No pandas, no numpy — the proxy blocks pip and the engine has
  to run wherever the data lands.
- Never commit real exports. `analytics/data/raw/` is git-ignored; the files contain
  candidate and client personal data under GDPR.
- Benchmarks are labelled `[PRIOR]` and tenant-dependent facts `[VERIFY]`. Keep those
  markers — they are the difference between a defensible number and a made-up one.
