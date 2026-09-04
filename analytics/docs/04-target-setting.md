# Target setting: back-solving activity from revenue

Cube19 targets are typed in by a manager and then measured against. That is backwards.
A target should be the *output* of the ratio chain, not an input to it.

---

## 1. The back-solve

Given a GP goal, walk the chain in reverse. Each step divides by a measured ratio:

```
GP goal
  ÷ avg_gp_per_placement   → placements needed
  ÷ offer_to_placement     → offers needed
  ÷ interview_to_offer     → 1st interviews needed
  ÷ cv_to_interview        → CVs to send
  ÷ cvs_per_job            → jobs needed
  ÷ meeting_to_job         → client meetings needed
  ÷ connect_to_meeting     → connects needed
  ÷ call_to_connect        → calls needed
```

Worked example, using benchmark priors **[PRIOR]** — replace every coefficient with
Gentis's measured values before anyone commits to these numbers:

| Step | Ratio used | Result |
|---|---|---|
| GP goal | — | €500,000 |
| ÷ €18,000 avg fee | `avg_fee` | **27.8 placements** |
| ÷ 0.80 | `offer_to_placement` | 34.7 offers |
| ÷ 0.25 | `interview_to_offer` | 138.9 first interviews |
| ÷ 0.32 | `cv_to_interview` | **434 CVs to send** |
| ÷ 3.5 | `cvs_per_job` | 124 jobs needed |
| ÷ 0.35 | `meeting_to_job` | 355 client meetings |
| ÷ 0.20 | `connect_to_meeting` | 1,773 connects |
| ÷ 0.25 | `call_to_connect` | **7,092 calls** |

Over 220 working days that is **32 calls and 2 CVs per day** for the whole desk. That is
the number a consultant can actually act on tomorrow morning, and it is the entire point
of the exercise.

## 2. Why the interval matters more than the number

Each ratio is estimated, not known. Multiplying eight uncertain numbers compounds the
uncertainty fast. A point-estimate target of 434 CVs is a fiction; the honest statement
is "somewhere between 360 and 560, and here is why".

The engine (`targets.py`) propagates uncertainty by Monte Carlo: draw each ratio from its
Beta posterior, run the chain, repeat 10,000 times, report the distribution of required
activity. You get three numbers that mean different things:

| Number | What it is | Use it for |
|---|---|---|
| **p50** | Median required activity | The plan |
| **p80** | Activity that hits goal in 80% of draws | The commitment / the target you set |
| **p20** | Optimistic case | Stretch, never the plan |

**Set targets at p80, plan capacity at p50.** Targeting the median means missing half the
time by construction, which destroys the credibility of the whole system in one quarter.

## 3. Where the money actually is

There is a trap here worth stating plainly, because it is counter-intuitive and it
changes what you do.

**Elasticity is flat.** In a multiplicative chain, a 10% relative improvement is worth
exactly the same wherever you get it. Run `targets.py: sensitivity()` on our sample data
and every link between CVs and revenue returns the *same* −9.09% change in required
activity — average fee included. So "which ratio matters most" is the wrong question;
they all matter identically per unit of relative gain.

**Headroom is not flat.** What separates the inputs is how far each one can realistically
move. That is what `targets.py: improvement_potential()` measures — it moves each ratio
to the strong end of its benchmark band and reports the activity saved. On the sample
data:

| Input | Current → achievable | Headroom | CVs saved |
|---|---|---|---|
| Offer → placement | 0.72 → 0.90 | 26% | **20.4%** |
| Average fee (move up-market) | €19.3k → €24.1k | 25% | **20.0%** |
| CV → 1st interview | 0.37 → 0.45 | 23% | **18.6%** |
| 1st interview → offer | 0.31 → 0.35 | 14% | 12.1% |

Two things follow:

1. **A ratio already at the top of its band has nothing left to give.** Coaching it is
   wasted effort no matter how important the stage sounds.
2. **Average fee is the one input with no ceiling in the data.** Every conversion ratio
   is bounded at 1.0 and most are already past halfway; fee is bounded only by which
   market and which clients you choose. That — not elasticity — is why market and client
   selection (`05-market-client-scoring.md`) outranks activity coaching over any horizon
   longer than a quarter.

A third finding, about uncertainty rather than headroom: **early-funnel ratios have the
widest intervals** because they are the worst-logged. If `call_to_connect` is barely
measured, the calls number in the table above is nearly meaningless. `quality.py` decides
this explicitly — it measures the share of *employed consultant-months* carrying any
logged activity, rather than trusting raw volume, and blocks the back-solver from
anchoring a target on a metric that fails.

**Anchor rule: set the target at the earliest stage that is reliably measured.** For most
recruitment businesses that is CVs sent, not calls.

## 4. Individual vs desk targets

Do not hand every consultant the same ratios. A consultant's own history is the better
predictor once they have enough volume — and shrinkage tells you exactly when that is.

```
consultant_target_ratio = shrink(consultant_history, prior = market_ratio, k = 30)
```

Practically:

- **< 30 CVs of history** (new starter): use the market ratio and the ramp curve, not
  their own numbers. Their target is an activity target only.
- **30–150 CVs**: blended. Their conversion is emerging; target activity, monitor conversion.
- **> 150 CVs**: their own measured ratios dominate. Target GP; let them choose the
  activity mix that gets there.

### The ramp curve

New consultants do not produce linearly. Fit GP by months-since-start across all
historical hires (`timeseries.py: ramp_curve()`) and target new starters against the
*cohort curve*, not against the desk average. The typical shape for perm desks
**[PRIOR]**: negligible GP for months 1–3, first placements months 4–6, ~60% of steady
state by month 9, steady state around month 12–18.

Getting this wrong is expensive in both directions: targeting a new starter at desk
average guarantees failure and early attrition; targeting them at nothing wastes a year.

## 5. System-level targets

Roll up bottom-up, then sanity-check top-down against capacity:

```
system_gp_target = Σ (consultant_capacity × market_gp_per_cv × expected_cvs)
```

Then check the constraint that actually binds. It is almost never CVs — it is usually
**live qualified jobs** or **interview slots with clients**. If the plan needs 124 jobs
and the desk has historically carried 40 live jobs at a time with an average life of 45
days, the plan needs ~330 job-days-of-capacity it does not have. The engine flags this in
`targets.py: feasibility()`.

A target that fails a feasibility check is not a stretch goal, it is a fiction. Fix the
constraint (more jobs, better job quality, more heads) or lower the goal.

## 6. Cadence

| Horizon | What you set | Reviewed |
|---|---|---|
| Annual | GP per market, headcount plan | Quarterly |
| Quarterly | GP + placements per consultant | Monthly |
| Monthly | CVs sent, interviews, jobs taken | Weekly |
| Weekly | Calls / outreach, meetings | Daily stand-up |

Ratios get re-estimated **monthly** on a trailing 12-month window. Re-estimating weekly
chases noise; re-estimating annually means acting on a market that has moved.
