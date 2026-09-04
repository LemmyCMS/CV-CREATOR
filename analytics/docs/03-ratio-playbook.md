# The ratio playbook

This is the priority deliverable. Ratios are how you convert "we made N calls" into
"we will bill €X", and they are the only honest basis for setting a target.

---

## 1. The ratio chain

Every recruitment business is one chain of conditional probabilities. Write it once and
everything else follows:

```
outreach → conversation → meeting → job → CV sent → 1st interview → offer → placement → GP
```

Formally, expected GP from a block of activity is:

```
GP  =  Outreach
       × P(job | outreach)
       × E[CVs per job]
       × P(1st interview | CV sent)
       × P(offer | 1st interview)
       × P(placement | offer)
       × E[GP per placement]
```

Two things fall out of this immediately, and they are the two most useful facts in the
whole document:

1. **The chain is multiplicative, so improvements compound.** Lifting three stages by
   15% each is a 52% lift in GP, not 15%. Lifting one stage by 50% is a 50% lift.
   Multiple small gains beat one heroic push.
2. **The weakest *relative* link, not the lowest absolute rate, is where the money is.**
   A 5% offer→placement rate is not a problem if 5% is the market norm. A 20%
   CV→interview rate is a catastrophe if the market norm is 35%. Always compare each
   link to its own benchmark, never to the other links.

## 2. The ratio set

`ratio_id` values are the keys used in `ratios.py` and the dashboard JSON.

### Core funnel ratios (compute these first, always)

| ratio_id | Numerator / Denominator | Reads as |
|---|---|---|
| `cv_to_interview` | `first_interviews / cvs_sent` | Quality of your shortlist. **The flagship ratio.** |
| `interview_to_offer` | `offers / first_interviews` | Candidate prep + client fit |
| `offer_to_placement` | `placements / offers` | Closing / counter-offer control |
| `cv_to_placement` | `placements / cvs_sent` | End-to-end delivery efficiency |
| `job_fill_rate` | `placements / jobs_taken` | Job qualification quality |
| `cvs_per_job` | `cvs_sent / jobs_taken` | Effort per job; data-quality canary |
| `interview_to_placement` | `placements / first_interviews` | Late-funnel strength |
| `first_to_further_interview` | `further_interviews / first_interviews` | Client process depth |

### BD ratios (only if call logging is trustworthy)

| ratio_id | Numerator / Denominator | Reads as |
|---|---|---|
| `call_to_connect` | `connects / calls` | Dial quality / list quality |
| `connect_to_meeting` | `client_meetings / connects` | Pitch strength |
| `meeting_to_job` | `jobs_taken / client_meetings` | BD conversion |
| `call_to_job` | `jobs_taken / calls` | Whole-BD efficiency |
| `calls_per_placement` | `calls / placements` | The number people quote at each other |

### Money ratios (the ones that actually rank things)

| ratio_id | Definition | Use |
|---|---|---|
| `gp_per_cv` | `gp / cvs_sent` | **Rank markets and clients with this.** Combines conversion and fee size into one comparable number. |
| `gp_per_job` | `gp / jobs_taken` | Which jobs are worth working |
| `gp_per_interview` | `gp / first_interviews` | Late-funnel value density |
| `gp_per_head_month` | `gp / (consultants × months)` | Capacity planning |

## 3. Benchmark priors — **[PRIOR]**, replace with measured data

These are industry reference points for European white-collar perm recruitment, used as
Bayesian priors until Gentis's actual export replaces them. **Do not present these to
anyone as Gentis numbers.** They exist so the system produces sane output on day one and
so low-volume cells shrink toward something reasonable instead of toward zero or infinity.

| Ratio | Weak | Typical | Strong |
|---|---|---|---|
| `cvs_per_job` | < 2 | 3 – 5 | 3 – 4 with high fill |
| `cv_to_interview` | < 20% | 25 – 40% | > 45% |
| `interview_to_offer` | < 15% | 20 – 30% | > 35% |
| `offer_to_placement` | < 65% | 75 – 85% | > 90% |
| `cv_to_placement` | < 5% | 8 – 12% | > 15% |
| `job_fill_rate` (contingent) | < 10% | 15 – 25% | > 30% |
| `job_fill_rate` (exclusive/retained) | < 50% | 65 – 85% | > 90% |
| `first_to_further_interview` | — | 50 – 70% | — |

Notes that matter more than the numbers:

- **More CVs per job is not better.** `cvs_per_job` rising while `cv_to_interview` falls
  means consultants are spraying. The healthy pattern is *fewer* CVs at a *higher*
  interview rate. Judge them as a pair, never alone.
- **Contingent vs exclusive fill rates differ by 3-5×.** Any market comparison that
  ignores the exclusivity mix is measuring the mix, not the market.
- **`cv_to_placement` around 10% means roughly 10 CVs per placement.** This is the single
  most useful mental constant for target-setting conversations.

## 4. Three ways ratios lie, and the fixes

### 4.1 Small numbers (the leaderboard problem)

A consultant with 3 CVs and 1 placement shows 33% CV→placement and tops the board. This
is the most common analytics failure in recruitment and Cube19 does nothing about it.

**Fix: Beta-Binomial shrinkage.** Treat each conversion as a Binomial process with a Beta
prior centred on the parent group's rate (market, or firm). The posterior mean is:

```
shrunk_rate = (successes + α) / (trials + α + β)

where α = prior_rate × k,  β = (1 − prior_rate) × k,  and k is the prior strength
```

`k` is "how many observations is the prior worth" — the engine defaults to `k = 30`
trials for funnel-stage ratios. With `k = 30` and a firm rate of 10%, our 1-from-3
consultant shrinks to `(1 + 3)/(3 + 30) = 12.1%` — visible as slightly above average,
not as a superstar. With 200 CVs and 30 placements they land at `(30+3)/(200+30) = 14.3%`,
close to their raw 15%, because the data now outweighs the prior. That is exactly the
behaviour you want.

**Always report the credible interval alongside the point estimate.** The engine returns
a 90% Beta credible interval on every ratio. A market whose interval spans 4%–28% is not
"better" than one at 11%–13%; it is unmeasured.

### 4.2 Lag (the growth problem)

A CV sent in November places in January. Dividing this month's placements by this
month's CVs is only valid in a steady state. In a growing desk it understates conversion;
in a shrinking one it flatters it.

**Fix: cohort ratios.** Attribute the outcome back to the period of the *CV*, not the
period of the *placement*, and only evaluate cohorts that have had time to mature. The
engine computes `cohort_maturity_days` (default 120 **[VERIFY]** against Gentis's actual
median CV→placement lag) and marks immature cohorts as provisional rather than including
them in the headline rate.

Measure the actual lag distribution first — `time_to_fill` median and p90 — then set the
maturity window to roughly the p90. If Gentis's p90 CV→placement is 150 days, a
90-day window systematically understates every recent cohort.

### 4.3 Mix (the Simpson's paradox problem)

A market's overall conversion can fall while every sub-segment improves, if volume shifts
toward the harder segment. This will happen and someone will draw the wrong conclusion
from it.

**Fix: always decompose.** When a rate moves, split the change into (a) within-segment
rate change and (b) mix change. The engine's `decompose_change()` does this. Never report
a YoY ratio movement without it.

## 5. How to compare two markets honestly

The brief asks which markets are statistically better. The answer is not "compare the
percentages".

1. Compute the shrunk rate and 90% credible interval for each market.
2. Compare on **`gp_per_cv`**, not on conversion rate — a market with 20% conversion and
   €25k fees beats one with 35% conversion and €9k fees.
3. Rank on the **lower bound** of the interval, not the mean. This automatically
   penalises markets you have barely tested, which is the correct risk posture when you
   are deciding where to spend the next quarter.
4. Check `revenue_concentration` before acting. A market whose GP is 70% one client is a
   client, not a market.
5. Check the trend separately. A declining market with a great historical rate is a trap;
   `05-market-client-scoring.md` weights momentum explicitly.

The engine exposes `P(market A > market B)` by Monte Carlo over the two posteriors. Use
that number, not a t-test on rates, and treat anything between 0.4 and 0.6 as "no
evidence of a difference — go on other criteria".

## 6. What to do with a ratio once you have it

| If this ratio is weak | The problem is | The fix is |
|---|---|---|
| `cvs_per_job` low | Not enough candidate flow, or jobs taken too late | Sourcing capacity, earlier job capture |
| `cv_to_interview` low | Wrong candidates, or weak CV presentation | Qualification depth, briefing, CV branding |
| `interview_to_offer` low | Poor candidate prep, or bad job briefing | Interview prep process, client calibration |
| `offer_to_placement` low | Counter-offers, slow process, salary misalignment | Close earlier, pre-close on money |
| `job_fill_rate` low | Taking bad jobs | Qualification gate; walk away from contingent multi-agency |
| `gp_per_cv` low but conversion fine | Fee size / seniority mix | Move up-market, renegotiate rates |

That table is the entire management conversation. Everything the dashboard shows should
be traceable to one of those six rows.
