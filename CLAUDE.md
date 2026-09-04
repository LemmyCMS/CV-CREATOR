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
