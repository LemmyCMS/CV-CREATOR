#!/usr/bin/env python3
"""Load data, run the engine, emit dashboard.json and a self-contained dashboard.html.

    python3 scripts/build_dashboard.py [--data DIR] [--goal 1000000]

Defaults to the synthetic sample so it runs before any export exists.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from cube19_analytics.ingest import load_dataset          # noqa: E402
from cube19_analytics.report import build_report, write_report  # noqa: E402


SKELETON = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  :root {{ color-scheme: light; }}
  body {{ margin: 0; font: 14px/1.5 system-ui, sans-serif; background: #eef0f3; }}
  img {{ max-width: 100%; }}
  [hidden] {{ display: none !important; }}
</style>
</head>
<body>
{body}
</body>
</html>
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(ROOT / "data" / "sample"))
    ap.add_argument("--status-map", default=None,
                    help="JSON map of tenant status strings to canonical stages")
    ap.add_argument("--goal", type=float, default=1_000_000.0)
    ap.add_argument("--job-capacity", type=int, default=40)
    ap.add_argument("--job-life-days", type=float, default=55.0)
    ap.add_argument("--out", default=str(ROOT / "dashboard"))
    args = ap.parse_args()

    ds, report_in = load_dataset(args.data, args.status_map)
    print(report_in.render())
    print()

    if not ds.placements:
        print("No placements loaded - nothing to report. Check the ingestion report above.")
        return 1

    data = build_report(ds, gp_goal=args.goal,
                        live_job_capacity=args.job_capacity,
                        avg_job_life_days=args.job_life_days)

    out_dir = Path(args.out)
    json_path = write_report(data, out_dir / "dashboard.json")
    print(f"Wrote {json_path}")

    template = out_dir / "template.html"
    if template.exists():
        body = template.read_text(encoding="utf-8").replace(
            "/*__DASHBOARD_DATA__*/null",
            json.dumps(data, default=str),
        )
        # template.html is a body fragment so it can also be published as an artifact
        # (which supplies its own document skeleton). Wrap it here so the file on disk
        # opens straight from the filesystem.
        target = out_dir / "dashboard.html"
        target.write_text(SKELETON.format(body=body), encoding="utf-8")
        print(f"Wrote {target} ({target.stat().st_size / 1024:.0f} KB, self-contained)")
    else:
        print(f"No template at {template} - JSON only")

    print()
    _summary(data)
    return 0


def _summary(d: dict) -> None:
    firm = d["firm"]["ratios"]
    print("=" * 68)
    print("HEADLINE")
    print("=" * 68)
    ds = d["dataset"]
    print(f"  {ds['placements']:,} placements, EUR {ds['total_gp']:,.0f} GP, "
          f"{ds['markets']} markets, {ds['years'][0]}-{ds['years'][-1]}")
    print("\n  RATIOS")
    for rid, r in firm.items():
        flag = "" if r["measured"] else "   [not enough data]"
        print(f"    {r['label']:<24} {r['value']:>10.4f}  [{r['lo']:.4f}, {r['hi']:.4f}]{flag}")
    print("\n  MARKETS, BEST FIRST")
    for m in d["markets"]:
        mom = f"{m['momentum']:+.0%}" if m["momentum"] is not None else "n/a"
        print(f"    {m['tier']:<12} {m['market']:<16} score {m['score']:.3f}  "
              f"GP/CV EUR {m['gp_per_cv']:>7,.0f}  momentum {mom:>7}")
    print("\n  CLIENT TIERS")
    for t in d["client_tier_summary"]:
        print(f"    {t['tier']:<14} {t['clients']:>3} clients  EUR {t['gp']:>11,.0f} GP  "
              f"GP/CV EUR {t['gp_per_cv']:>7,.0f}")
    plan = d["target"]["plan"]
    print(f"\n  TARGET: EUR {plan['gp_goal']:,.0f} needs {plan['placements_needed']:.0f} placements")
    for s in plan["steps"]:
        mark = "  <- anchor here" if s["anchor"] else ""
        print(f"    {s['to']:<18} p50 {s['p50']:>9,.0f}   p80 {s['p80']:>9,.0f}{mark}")
    for w in plan["warnings"]:
        print(f"    ! {w}")
    print("=" * 68)


if __name__ == "__main__":
    raise SystemExit(main())
