# Cube19 replacement — funnel analytics engine

A working replica of what Cube19 computes on top of Bullhorn, plus the things Cube19
does not do: shrinkage on small samples, credible intervals, cohort-corrected ratios,
back-solved targets, and a ranking of markets and accounts rather than of people.

**Nothing here needs installing.** Pure standard-library Python 3.11+, no dependencies.

## Run it

```bash
cd analytics
python3 scripts/generate_sample_data.py     # synthetic 7-year history (already committed)
python3 scripts/build_dashboard.py          # engine -> dashboard/dashboard.{json,html}
python3 -m unittest discover -s tests       # 42 tests
```

`dashboard/dashboard.html` is self-contained — open it in a browser.

## Point it at real data

```bash
python3 scripts/build_dashboard.py \
    --data analytics/data/raw \
    --status-map analytics/data/gentis_status_map.json \
    --goal 2000000
```

The loader reads whatever CSVs it recognises by filename (`stage_events`, `placements`,
`jobs`, `activities`, `consultants`, `clients`), matches column headers loosely, and
prints a mapping report saying what it could not understand. **Read that report before
reading any number.** `data/sample/` doubles as the format spec.

`docs/06-migration-extraction.md` is the runbook for getting the data out of Cube19 —
that is the time-critical piece, since the coefficients disappear when the tenant does.

## What's here

| Path | What it is |
|---|---|
| `docs/01-cube19-model.md` | How Cube19 works on Bullhorn, and what we must replicate |
| `docs/02-metric-dictionary.md` | Every metric, its definition, its Bullhorn source |
| `docs/03-ratio-playbook.md` | **The ratio set, benchmarks, and the three ways ratios lie** |
| `docs/04-target-setting.md` | Back-solving activity targets from a revenue goal |
| `docs/05-market-client-scoring.md` | Which market, which client, in which order |
| `docs/06-migration-extraction.md` | **What to export before Cube19 goes dark** |
| `src/cube19_analytics/stats.py` | Beta/Gamma posteriors, shrinkage, sample sizing |
| `src/cube19_analytics/metrics.py` | Counting layer — one definition of "CV sent" |
| `src/cube19_analytics/ratios.py` | Ratio engine, three ratio kinds, mix decomposition |
| `src/cube19_analytics/quality.py` | Decides which metrics are safe to build targets on |
| `src/cube19_analytics/targets.py` | Back-solver, sensitivity, improvement potential, feasibility |
| `src/cube19_analytics/scoring.py` | Market and client ranking, dormant accounts, bounded tests |
| `src/cube19_analytics/timeseries.py` | YoY, ramp curves, seasonality, cohorts |
| `schema/schema.sql` | The same model as SQL, for when it outgrows memory |

## The five decisions this engine makes differently from Cube19

1. **Shrinkage.** A consultant with 1 placement from 3 CVs reads as 12%, not 33%.
   Everything is a Beta-Binomial posterior with a 90% credible interval.
2. **"Not yet known" is a result.** A market whose interval straddles its peers has not
   been shown to be weak. It gets a priced experiment, not an exit.
3. **Peer baselines, not firm averages.** Each market is compared against the *rest* of
   the business, so the largest market is not measured against itself.
4. **Partial periods are excluded from trend.** A stub year at the edge of the data
   reads as a collapse and will otherwise flip a growing market to "Exit".
5. **Logging coverage gates target anchoring.** 111,000 logged calls mean nothing if a
   third of the team never logged; coverage is measured over employed consultant-months.
