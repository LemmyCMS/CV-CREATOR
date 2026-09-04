#!/usr/bin/env python3
"""Analyse the real Cube19 OneView snapshots and emit the dashboard payload.

    python3 scripts/analyse_gentis.py

Two adjacent periods (Sep 2022-Sep 2025, Sep 2025-Sep 2026) for Gentis Consultancy,
company-wide. Prints the findings and writes dashboard/gentis.json.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from cube19_analytics.oneview import (  # noqa: E402
    BENCHMARKS, compare, load_snapshot, scenario, target_diagnosis,
)

DATA = ROOT / "data" / "gentis"


def build() -> dict:
    prior = load_snapshot(DATA / "oneview_prior3y.json", "Sep 2022 – Sep 2025")
    recent = load_snapshot(DATA / "oneview_last12m.json", "Sep 2025 – Sep 2026")
    cmp_ = compare(prior, recent)
    diag = target_diagnosis(recent)
    scen = scenario(recent, cvs_per_job=3.0, a_job_share=0.15, client_calls=61600)
    rows = _row_sample()
    # Most recent window. Nested inside the 12-month snapshot AND covering only the strong
    # season, so it is reported as a guarded run-rate, never as a trend point.
    current = load_snapshot(DATA / "oneview_oct25_may26.json", "Oct 2025 – May 2026")
    cur_cmp = compare(recent, current)

    return {
        "generated_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "company": "Gentis Consultancy",
        "source": "Cube19 OneView, company-wide aggregate",
        "periods": {
            "prior": {"label": prior.label, "years": prior.years,
                      "start": prior.period_start, "end": prior.period_end},
            "recent": {"label": recent.label, "years": recent.years,
                       "start": recent.period_start, "end": recent.period_end},
        },
        "active_users": recent.raw.get("active_users"),
        "findings": [f.as_dict() for f in recent.findings]
                    + [f.as_dict() for f in prior.findings if f.subject != "funnel placements"],
        "funnel": {
            "recent": _funnel(recent), "prior": _funnel(prior),
            "recovered_placements_recent": recent.funnel_placements,
            "recovered_placements_prior": prior.funnel_placements,
            "recovery_spread_recent": recent.funnel_placements_spread,
            "total_placements_recent": recent.r("total_placements"),
        },
        "ratios": cmp_["ratios"],
        "flow": cmp_["flow"],
        "gp": {"prior": cmp_["gp_prior"], "recent": cmp_["gp_recent"]},
        "headcount": cmp_["implied_prior_headcount"],
        "attainment": diag["attainment"],
        "target_links": diag["links"],
        "fee_check": diag["fee_check"],
        "scenarios": scen,
        "leaks": recent.leaks,
        "live": recent.live,
        "benchmarks": {k: list(v) for k, v in BENCHMARKS.items()},
        "note": cmp_["note"],
        "structural_break": recent.structural_break,
        "guards": cmp_["guards"],
        "broken_metrics": cmp_["broken_metrics"],
        "row_sample": rows,
        "contract_sample": _contract_sample(),
        "current_window": {
            "label": current.label, "months": round(current.years * 12),
            "guards": cur_cmp["guards"], "comparable": cur_cmp["comparable"],
            "attainment": current.attainment(),
            "ratios": current.ratios(),
            "funnel_placements": current.funnel_placements,
            "raw": {"total_jobs_added": current.a("total_jobs_added"),
                    "client_calls": current.a("client_calls"),
                    "cvs_sent": current.a("cvs_sent"),
                    "total_placements": current.r("total_placements"),
                    "perm_placements": current.r("perm_placements"),
                    "contract_placements": current.r("contract_placements"),
                    "avg_deal_perm": current.r("avg_deal_perm"),
                    "linkedin_inmails": current.a("linkedin_inmails")},
        },
    }


def _row_sample() -> dict:
    """Structural findings from the Slice & Dice row-level pages.

    A partial page of each export, not the full file - far too few rows to rank a market
    or a consultant, but more than enough to establish what the data looks like and to
    settle the A-job question the aggregates could not.
    """
    import csv, statistics
    from collections import Counter
    path = DATA / "perm_placements_sample.csv"
    if not path.exists():
        return {}
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    uniq = {}
    for r in rows:
        uniq.setdefault(r["placement_id"], r)
    vals = list(uniq.values())
    pri = Counter(v["priority"] or "(blank)" for v in vals)
    a_like = sum(n for k, n in pri.items() if k in ("A", "A+"))
    ttf = sorted(int(v["time_to_fill"]) for v in vals)
    fees = sorted(float(v["fee_pct"]) for v in vals if float(v["fee_pct"]) > 0)
    return {
        "split_rows": len(rows), "unique_placements": len(vals),
        "priority_mix": [{"priority": k, "n": n, "share": n / len(vals)} for k, n in pri.most_common()],
        "a_share_of_placements": a_like / len(vals),
        "blank_priority_share": pri.get("(blank)", 0) / len(vals),
        "retainer_share": sum(1 for v in vals if v["is_retainer"] == "true") / len(vals),
        "zero_value_share": sum(1 for v in vals if float(v["billing_eur"]) == 0) / len(vals),
        "fee_median": statistics.median(fees), "fee_min": min(fees), "fee_max": max(fees),
        "ttf_median": statistics.median(ttf), "ttf_p90": ttf[int(0.9 * len(ttf))], "ttf_max": max(ttf),
        "distinct_groups": len({v["market"] for v in vals}),
        "retired_groups": sorted({v["market"] for v in vals if v["market"].startswith("[deleted]")}),
        "compound_groups": sorted({v["market"] for v in vals if "/" in v["market"]}),
        "sources": [{"source": k, "n": n} for k, n in
                    Counter(v["source"] for v in vals).most_common()],
    }


def _funnel(snap) -> list[dict]:
    a = snap.activity
    return [
        {"label": "Client calls", "value": snap.per_year(a.get("client_calls", 0))},
        {"label": "Client meetings", "value": snap.per_year(a.get("client_meetings", 0))},
        {"label": "Jobs added", "value": snap.per_year(a.get("total_jobs_added", 0))},
        {"label": "A-jobs (qualified)", "value": snap.per_year(a.get("total_a_jobs_added", 0))},
        {"label": "CVs sent (to jobs)", "value": snap.per_year(a.get("cvs_sent", 0))},
        {"label": "1st interviews", "value": snap.per_year(a.get("total_first_interviews", 0))},
        {"label": "Placements (funnel)", "value": snap.per_year(snap.funnel_placements or 0)},
    ]


def _contract_sample() -> dict:
    """Contract-side structural findings from the Slice & Dice pages.

    The contract book is the half of the business that did NOT cross the March perm
    separation, so unlike the perm figures these comparisons are about performance.
    """
    import csv, statistics
    from collections import Counter, defaultdict
    path = DATA / "contract_placements_sample.csv"
    if not path.exists():
        return {}
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    cur = [r for r in rows if r["period"] == "current"]
    pri = [r for r in rows if r["period"] == "prior"]
    fee = lambda r: float(r["fee_pct"])
    gp = lambda r: float(r["invoice_gp"])

    def margin(s):
        f = sorted(fee(r) for r in s)
        return {"n": len(f), "median": statistics.median(f), "mean": statistics.fmean(f),
                "p10": f[int(0.1 * len(f))], "p90": f[int(0.9 * len(f))]}

    desks = defaultdict(lambda: {"n": 0, "gp": 0.0, "fees": []})
    for r in cur:
        d = desks[r["market"]]
        d["n"] += 1
        d["gp"] += gp(r)
        d["fees"].append(fee(r))
    desk_rows = sorted(
        ({"desk": m, "n": d["n"], "gp": round(d["gp"], 2),
          "median_margin": round(statistics.median(d["fees"]), 2)} for m, d in desks.items()),
        key=lambda r: -r["gp"])

    ghost_cur = [r for r in cur if r["owner"].startswith("Ghost")]
    ghost_pri = [r for r in pri if r["owner"].startswith("Ghost")]
    ghost_all = [r for r in rows if r["owner"].startswith("Ghost")]
    ttf = sorted(int(r["ttf"]) for r in rows if r["ttf"])
    jt = Counter(r["job_type"] for r in rows if r["job_type"])
    thin = [r for r in cur if fee(r) < 12]

    m_pri, m_cur = margin(pri), margin(cur)
    return {
        "rows": len(rows), "prior_rows": len(pri), "current_rows": len(cur),
        "margin_prior": m_pri, "margin_current": m_cur,
        "margin_change": (m_cur["median"] - m_pri["median"]) / m_pri["median"],
        "thin_margin_share": len(thin) / len(cur) if cur else 0,
        "ghost_owner_share_prior": len(ghost_pri) / len(pri) if pri else 0,
        "ghost_owner_share_current": len(ghost_cur) / len(cur) if cur else 0,
        "ghost_gp_share": (sum(gp(r) for r in ghost_all) / sum(gp(r) for r in rows)) if rows else 0,
        "ghost_names": sorted({r["owner"] for r in ghost_all}),
        "desks": desk_rows,
        "ttf_median": statistics.median(ttf) if ttf else None,
        "ttf_p90": ttf[int(0.9 * len(ttf))] if ttf else None,
        "job_types": [{"type": k, "n": n, "share": n / sum(jt.values())} for k, n in jt.most_common()],
        "priority_mix": [{"priority": k or "(blank)", "n": n, "share": n / len(rows)}
                         for k, n in Counter(r["priority"] or "(blank)" for r in rows).most_common()],
    }


def report(d: dict) -> None:
    w = "=" * 74
    print(w); print("GENTIS CONSULTANCY — Cube19 OneView"); print(w)
    print(f"  {d['periods']['prior']['label']} (3y)  vs  {d['periods']['recent']['label']} (1y)")
    print(f"  {d['note']}")

    print("\n" + w); print("1. WHAT DOES NOT ADD UP"); print(w)
    for f in d["findings"]:
        print(f"  [{f['severity'].upper():<4}] {f['subject']}\n         {f['detail']}")

    print("\n" + w); print("2. THE FUNNEL, PER YEAR"); print(w)
    pr = {r["label"]: r["value"] for r in d["funnel"]["prior"]}
    for row in d["funnel"]["recent"]:
        p = pr.get(row["label"], 0)
        chg = (row["value"] - p) / p if p else 0
        print(f"  {row['label']:<24}{p:>12,.0f}{row['value']:>12,.0f}{chg:>+9.0%}")

    print("\n" + w); print("3. RATIOS — the part that is headcount-independent"); print(w)
    for r in d["ratios"]:
        b = r["benchmark"]
        fmt = (lambda v: f"{v:.1%}") if r["recent"] <= 1.5 else (lambda v: f"{v:.2f}")
        bt = ""
        if b:
            bt = f"{b[0]:.0%}–{b[1]:.0%}" if b[1] <= 1 else f"{b[0]:.1f}–{b[1]:.1f}"
            below = r["recent"] < b[0]
            bt = ("BELOW " + bt) if below else ("ok " + bt)
        print(f"  {r['ratio']:<34}{fmt(r['prior']):>9}{fmt(r['recent']):>9}{r['change']:>+8.0%}   {bt}")

    print("\n" + w); print("4. TARGET ATTAINMENT"); print(w)
    for r in d["attainment"]:
        bar = "#" * int(min(r["attainment"], 1.3) * 22)
        print(f"  {r['metric']:<36}{r['attainment']:>6.0%}  {bar}")

    print("\n" + w); print("5. WERE THE TARGETS EVER ARITHMETIC?"); print(w)
    for l in d["target_links"]:
        fmt = (lambda v: f"{v:.1%}") if l["actual"] <= 1.5 else (lambda v: f"{v:.2f}")
        fac = f"{l['factor']:.1f}x" if l["factor"] else "—"
        print(f"  {l['link']:<22} implied {fmt(l['implied_by_targets']):>8}  actual {fmt(l['actual']):>8}  {fac:>5}  {l['verdict']}")
    fc = d["fee_check"]
    if fc:
        print(f"\n  Fee assumption: {fc['target_perm_placements']:.0f} × €{fc['actual_avg_perm_fee']:,.0f} "
              f"= €{fc['implied_billing']:,.0f} vs €{fc['target_perm_billing']:,.0f} target — "
              f"{'CORRECT' if fc['consistent'] else 'inconsistent'}")

    print("\n" + w); print("6. WHAT THE LEVERS ARE WORTH"); print(w)
    s = d["scenarios"]
    print(f"  Baseline {s['baseline_placements']:,.0f} funnel placements · €{s['gp_per_funnel_placement']:,.0f} GP each")
    for l in s["levers"]:
        print(f"\n  {l['lever']}")
        print(f"    needs  : {l['requires']}")
        print(f"    worth  : {l['delta_placements']:+,.0f} placements · €{l['delta_gp']:+,.0f} GP")
        print(f"    caveat : {l['caveat']}")

    print("\n" + w); print("7. HEADCOUNT — the unresolved confound"); print(w)
    print("  " + d["headcount"].get("note", "n/a"))
    print(w)


if __name__ == "__main__":
    data = build()
    out = ROOT / "dashboard" / "gentis.json"
    out.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    report(data)
    print(f"\nWrote {out}")
