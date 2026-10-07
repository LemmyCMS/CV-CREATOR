# 07 — Warm talent pool: sizing it, and making sure it gets sent

Engine: `src/cube19_analytics/talent_pool.py`. Tests: `TestTalentPool`.

## Why
Being responsive means **3 strong CVs within 48 hours** of a job landing. Gentis sent 1.99
per job and added 11,876 candidates in a year of which **85% were never sent anywhere**.
Their problem was a cold database, not a small one. The Zig needs the opposite: a small,
warm pool that gets used.

## Sizing — `warm_target()`, `pool_plan()`
warm needed = CVs per job × effective jobs ÷ (fit rate × availability)

| | Fit | Available now | Warm per profile type (1 job) | 2 simultaneous jobs |
|---|---|---|---|---|
| Contract | 50% [PRIOR] | 20% [PRIOR] (free within 6 weeks) | **30** | 45 |
| Perm | 50% [PRIOR] | 12% [PRIOR] (actively open) | **50** | 75 |

A market has 3–4 profile types (e.g. Brussels IT Infra: network, cloud/sysadmin,
security) → ~90–150 warm per market. `capacity()` checks this against the team:
~4 candidate touches per worked day, every profile re-contacted each 75 days ≈ **220 warm per
FTE**. 1.0 FTE in year one = **one market done properly**.

**Warm** = last real conversation ≤ 90 days, CV on file, GDPR consent. All three.
**Ready** = warm + (contract: mission ends within 6 weeks | perm: confirmed open to move).

## The anti-Gentis guard — `send_leaks()`
| Check | Target | Gentis |
|---|---|---|
| Never-sent rate (candidates added 30–365 days ago, never sent) | ≤ 50%, alarm above | 85% |
| Ready candidates matching an open job, not sent to it | 0 — it is a named daily call list | not measured |
| Open jobs older than 48h with < 3 CVs | 0 | 1.99 CVs/job average |
| Median days to 3rd CV | ≤ 2 | unknown |

## CRM fields this requires
Candidate: `market`, `profile`, `placement_type`, `last_contact`, `available_from`,
`open_to_move`, `cv_on_file`, `consent`. Job: `profile` (same taxonomy as candidates).
Submissions: CV-sent stage entries with dates (already the core of the model).

## Replace the priors
After two months, for each job record how many warm profiles were called, how many
fitted, how many were available. Put the measured rates into `PoolAssumptions`; the
targets recompute.
