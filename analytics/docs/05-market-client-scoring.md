# Which market, which client, in which order

Cube19 ranks people. This ranks opportunities — which is the question the brief actually
asks.

---

## 1. The ranking principle

Rank on **risk-adjusted expected GP per unit of effort**, where effort is measured in CVs
sent (the most reliably logged unit of real work).

```
score = lower_bound_90(gp_per_cv)  ×  momentum  ×  headroom  ×  accessibility
```

Ranking on the *lower bound* rather than the mean is deliberate: it automatically
demotes opportunities you have barely tested, which is the right posture when you are
allocating a quarter of a team's time. A market with two lucky placements will not
outrank one with a proven record.

## 2. Market score

| Factor | Definition | Weight | Rationale |
|---|---|---|---|
| `gp_per_cv_lb` | 90% credible lower bound on GP per CV sent | 0.35 | The core economics |
| `momentum` | YoY GP growth, 3-year weighted (recent years count more) | 0.20 | A declining market with great history is a trap |
| `fill_rate_lb` | Lower bound on job fill rate | 0.15 | Can you actually deliver here |
| `cycle_speed` | Inverse of median time-to-fill, normalised | 0.10 | Cash cycle and consultant morale |
| `headroom` | 1 − (our GP / estimated market size) | 0.10 | Room to grow without fighting |
| `concentration_penalty` | 1 − HHI of GP by client | 0.10 | Punishes one-client "markets" |

All factors normalised to 0–1 across markets before weighting. Weights are in
`data/scoring_weights.yaml` and are meant to be argued about — they encode strategy, not
truth. Change them deliberately and record why.

### Reading the output

The engine emits three tiers rather than a strict 1..N ranking, because differences
inside a tier are usually not statistically real:

- **Attack** — top tier, proven economics and positive momentum. Put new heads here.
- **Hold** — solid but flat, or good but concentrated. Maintain, do not expand.
- **Test or exit** — weak economics, or too little data to know. Either run a deliberate
  bounded test (a fixed number of CVs, a decision date) or stop spending time there.

"Too little data to know" is a real and common verdict. The correct response is a
**bounded experiment**, not a hunch: `sample_size_for()` tells you how many CVs you must
send into a market to distinguish its rate from the firm baseline (90% confidence, 80%
power). Against a 10% baseline:

| To detect a market at | You need |
|---|---|
| 30% (3x baseline) | **49 CVs** |
| 25% | **79 CVs** |
| 20% (2x baseline) | **157 CVs** |
| 15% | **540 CVs** |

Read that table carefully, because it drives strategy: **a market that is twice as good
is cheap to prove; a market that is only slightly better is not provable at our volumes.**
Run bounded tests where you believe the gap is large. Everywhere else, stop trying to
measure your way to an answer and decide on fee size, accessibility and momentum, which
are visible in far less data.

## 3. Client score

Same logic, different factors. This answers "which accounts to go for, in what order".

| Factor | Definition | Weight |
|---|---|---|
| `gp_per_cv_lb` | Lower bound GP per CV at this client | 0.30 |
| `fill_rate_lb` | Lower bound fill rate | 0.20 |
| `repeat_rate` | Placements per year of relationship / recency-decayed | 0.15 |
| `avg_fee` | Fee size, normalised | 0.15 |
| `exclusivity` | Share of jobs worked exclusively/retained | 0.10 |
| `responsiveness` | Inverse median days job-open → first client feedback | 0.10 |

### Client tiers

- **Farm** — proven, high fill, repeat. Protect at all costs; assign a named owner and a
  contact-coverage target (see below).
- **Grow** — good economics, low share of their spend. The best use of BD time.
- **Qualify** — high fee potential, unproven delivery. Test with a bounded number of CVs.
- **Deprioritise** — low fill after real volume, or slow/unresponsive. The most valuable
  output of the whole model: these accounts consume time invisibly.

**Deprioritise is the money-maker.** In most agencies 20–30% of consultant effort goes to
accounts that have never converted at a viable rate. Reclaiming half of that is worth
more than any conversion-rate coaching.

## 4. The dormant-account list

Cheapest revenue in any recruitment business: clients who placed before and have gone
quiet. Rank by:

```
reactivation_score = historical_gp_per_cv × recency_decay(days_since_last_job) × contact_still_there
```

`contact_still_there` matters more than anything else — if the hiring manager who liked
you has moved, this is a cold account wearing a warm account's clothes, *and* a warm lead
at the manager's new employer. The engine emits both lists.

## 5. Contact coverage, not client coverage

A client is not an account, it is a set of hiring managers. The metric that predicts
account growth better than any other is **contacts engaged per client**. One contact is a
single point of failure; four or more contacts is a real account.

The engine reports `contacts_engaged` per client and flags every Farm/Grow client sitting
on fewer than three. That flag list is a BD task list you can hand to a consultant on
Monday morning.

## 6. Sequencing — the actual answer to "in which order"

Given a ranked list and finite capacity, work in this order:

1. **Defend Farm accounts** — cheapest GP per hour, and losing one costs a year to replace.
2. **Grow accounts in Attack markets** — highest expected return per BD hour.
3. **Reactivate dormant accounts with contacts intact** — warm, fast, low effort.
4. **Bounded tests in unproven high-fee markets** — buying information, with a decision date.
5. **Everything else** — only with genuine spare capacity.

Deprioritised accounts get *no* proactive time. Inbound only.

## 7. The honest caveat

Every number here is computed from Gentis's history, which reflects where Gentis chose to
spend effort. A market can look weak because it was worked badly, not because it is weak
— the model cannot see the difference between "this market does not convert" and "we
never put a good consultant on it".

Mitigations, in order of usefulness:

1. Check whether weak markets were worked by low-tenure consultants only. If so, the
   verdict is "unproven", not "weak".
2. Prefer bounded tests over permanent exits. An exit is a decision you cannot easily
   reverse; a test is cheap.
3. Re-score quarterly. Markets move, and the model should be allowed to change its mind.
