# CV-CREATOR

## `analytics/` — Cube19 replacement

A working replica of the Cube19 funnel analytics layer, built to preserve Gentis's
conversion ratios and historical performance data before the Cube19 tenant is switched
off, and to inform the design of the replacement CRM.

Pure standard-library Python, no dependencies, 42 tests.

```bash
cd analytics
python3 scripts/build_dashboard.py     # -> dashboard/dashboard.html
python3 -m unittest discover -s tests
```

Start with [`analytics/README.md`](analytics/README.md). The time-critical piece is
[`analytics/docs/06-migration-extraction.md`](analytics/docs/06-migration-extraction.md) —
what to export from Cube19 before access ends.

Project context and decisions are in [`CLAUDE.md`](CLAUDE.md).
