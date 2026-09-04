"""Assemble everything into the JSON the dashboard renders.

One function, one contract. If a number appears on the dashboard it comes from here,
which means the funnel, the leaderboard and the market ranking cannot disagree about
what a CV sent is.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

from .metrics import Slice, compute_metrics, group_by
from .model import Dataset
from .quality import assess, reliable_metrics
from .ratios import compute_ratios, decompose_change
from .scoring import bounded_test_plan, dormant_accounts, score_clients, score_markets
from .stats import prob_greater, beta_posterior
from .targets import back_solve, feasibility, improvement_potential
from .timeseries import (
    cohort_conversion, momentum, ramp_curve, seasonality_index, time_to_fill, yearly_series,
)

__all__ = ["build_report", "write_report"]

HEADLINE_RATIOS = [
    "cvs_per_job", "cv_to_interview", "interview_to_offer", "offer_to_placement",
    "cv_to_placement", "job_fill_rate", "gp_per_cv",
]


def build_report(
    ds: Dataset,
    gp_goal: float = 1_000_000.0,
    live_job_capacity: int = 40,
    avg_job_life_days: float = 55.0,
) -> dict:
    firm = compute_metrics(ds)
    firm_ratios = compute_ratios(firm)
    reliable = reliable_metrics(ds)
    # Nest the priors: a consultant shrinks toward their firm, not toward an industry
    # average. This is what makes per-head numbers trustworthy on thin data.
    priors = {rid: rr.value for rid, rr in firm_ratios.items() if rr.measured}

    complete = ds.complete_years
    plan = back_solve(gp_goal, firm_ratios, firm.get("avg_fee") or 1.0, reliable=reliable)

    markets = score_markets(ds)
    clients = score_clients(ds)

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "provenance": {
            "source": "synthetic sample data" if _looks_synthetic(ds) else "loaded export",
            "warning": (
                "Every number here is computed from the loaded dataset. If that dataset is "
                "the synthetic sample, none of it is Gentis data - it exists to prove the "
                "engine runs. Replace data/sample with a real Cube19 export (docs/06)."
            ),
        },
        "dataset": ds.summary(),
        "quality": [f.as_dict() for f in assess(ds)],
        "reliable_metrics": sorted(reliable),
        "firm": {
            "metrics": firm.as_dict(),
            "funnel": _funnel(firm),
            "ratios": {k: firm_ratios[k].as_dict() for k in HEADLINE_RATIOS if k in firm_ratios},
            "all_ratios": {k: v.as_dict() for k, v in firm_ratios.items()},
        },
        "years": complete,
        "partial_years": ds.partial_years,
        "horizon": ds.horizon.isoformat(),
        "yearly": {
            "firm": _firm_yearly(ds),
            "by_market": yearly_series(ds, "market"),
            "by_consultant": yearly_series(ds, "consultant"),
        },
        "markets": markets,
        "market_comparison": _market_comparison(ds, markets),
        "clients": clients[:60],
        "client_tier_summary": _tier_summary(clients),
        "dormant": dormant_accounts(ds)[:20],
        "consultants": _consultant_matrix(ds, priors),
        "ramp_curve": ramp_curve(ds),
        "seasonality": seasonality_index(ds),
        "time_to_fill": time_to_fill(ds, "market"),
        "cohorts": cohort_conversion(ds),
        "target": {
            "plan": plan.as_dict(),
            "per_working_day": {
                m: round(plan.per_working_day(m) or 0, 2)
                for m in ("cvs_sent", "first_interviews", "jobs_taken", "calls")
                if plan.required(m) is not None
            },
            "improvement_potential": improvement_potential(
                gp_goal, firm_ratios, firm.get("avg_fee") or 1.0),
            "feasibility": feasibility(plan, live_job_capacity, avg_job_life_days),
        },
        "yoy_decomposition": _yoy_decomposition(ds),
        "bounded_tests": [
            bounded_test_plan(ds, m["market"]) for m in markets if m["tier"] == "Test"
        ],
    }


def _looks_synthetic(ds: Dataset) -> bool:
    return any(c.consultant_id.startswith("U0") for c in ds.consultants[:3])


def _funnel(ms) -> list[dict]:
    stages = [
        ("Jobs taken", "jobs_taken"), ("CVs sent", "cvs_sent"),
        ("1st interviews", "first_interviews"), ("Further interviews", "further_interviews"),
        ("Offers", "offers"), ("Placements", "placements"),
    ]
    top = ms.get("cvs_sent") or 1
    return [
        {"label": label, "metric": key, "value": ms.get(key),
         "pct_of_cvs": round(ms.get(key) / top, 4)}
        for label, key in stages
    ]


def _firm_yearly(ds: Dataset) -> list[dict]:
    rows = []
    for year in ds.years:
        ms = compute_metrics(ds, Slice(year=year))
        rr = compute_ratios(ms)
        rows.append({
            "year": year,
            "gp": round(ms.get("gp"), 2),
            "placements": ms.get("placements"),
            "cvs_sent": ms.get("cvs_sent"),
            "jobs_taken": ms.get("jobs_taken"),
            "first_interviews": ms.get("first_interviews"),
            "calls": ms.get("calls"),
            "avg_fee": round(ms.get("avg_fee"), 2),
            "active_consultants": ms.get("active_consultants"),
            "gp_per_head": round(ms.get("gp_per_head"), 2),
            "cv_to_placement": round(rr["cv_to_placement"].value, 4),
            "cv_to_interview": round(rr["cv_to_interview"].value, 4),
            "gp_per_cv": round(rr["gp_per_cv"].value, 2),
        })
    return rows


def _market_comparison(ds: Dataset, markets: list[dict]) -> list[dict]:
    """Pairwise P(A better than B) on CV→placement, so 'better' is a probability
    rather than an assertion. Anything in 0.4-0.6 means the data cannot tell them apart."""
    grouped = group_by(ds, "market")
    posteriors = {}
    for market, ms in grouped.items():
        cvs, placements = ms.get("cvs_sent"), ms.get("placements")
        if cvs <= 0:
            continue
        posteriors[market] = beta_posterior(min(placements, cvs), cvs, 0.10, 30.0)

    ordered = [m["market"] for m in markets if m["market"] in posteriors]
    out = []
    for i, a in enumerate(ordered):
        for b in ordered[i + 1:]:
            p = prob_greater(posteriors[a], posteriors[b])
            out.append({
                "a": a, "b": b, "p_a_better": round(p, 3),
                "verdict": (
                    f"{a} better" if p > 0.8 else
                    f"{b} better" if p < 0.2 else
                    "no clear difference - decide on fee size and accessibility"
                ),
            })
    return out


def _tier_summary(clients: list[dict]) -> list[dict]:
    tiers: dict[str, dict] = {}
    for c in clients:
        tier = c.get("tier", "Unknown")
        row = tiers.setdefault(tier, {"tier": tier, "clients": 0, "gp": 0.0, "cvs_sent": 0.0})
        row["clients"] += 1
        row["gp"] += c["gp"]
        row["cvs_sent"] += c["cvs_sent"]
    for row in tiers.values():
        row["gp"] = round(row["gp"], 2)
        row["gp_per_cv"] = round(row["gp"] / row["cvs_sent"], 2) if row["cvs_sent"] else 0.0
    order = {"Farm": 0, "Grow": 1, "Qualify": 2, "Deprioritise": 3}
    return sorted(tiers.values(), key=lambda r: order.get(r["tier"], 9))


def _consultant_matrix(ds: Dataset, priors: dict[str, float]) -> list[dict]:
    """The OnPoint replica: every consultant x every metric, with shrunk ratios.

    Shrinkage is the whole point here. Raw per-head conversion on 20 CVs is noise, and
    ranking people on it is how a leaderboard rewards luck.
    """
    rows = []
    for c in ds.consultants:
        ms = compute_metrics(ds, Slice(consultant_id=c.consultant_id))
        if ms.get("cvs_sent") == 0 and ms.get("placements") == 0:
            continue
        rr = compute_ratios(ms, priors=priors)
        first_year = min((p.start_date.year for p in ds.placements
                          if p.consultant_id == c.consultant_id), default=c.start_date.year)
        rows.append({
            "consultant_id": c.consultant_id,
            "name": c.name,
            "market": c.market,
            "start_date": c.start_date.isoformat(),
            "end_date": c.end_date.isoformat() if c.end_date else None,
            "tenure_months": round(c.tenure_months_at(date.today()), 1),
            "gp": round(ms.get("gp"), 2),
            "placements": ms.get("placements"),
            "cvs_sent": ms.get("cvs_sent"),
            "first_interviews": ms.get("first_interviews"),
            "jobs_taken": ms.get("jobs_taken"),
            "calls": ms.get("calls"),
            "avg_fee": round(ms.get("avg_fee"), 2),
            "cv_to_interview": round(rr["cv_to_interview"].value, 4),
            "cv_to_interview_raw": round(rr["cv_to_interview"].raw, 4) if rr["cv_to_interview"].raw else None,
            "cv_to_placement": round(rr["cv_to_placement"].value, 4),
            "cv_to_placement_raw": round(rr["cv_to_placement"].raw, 4) if rr["cv_to_placement"].raw else None,
            "gp_per_cv": round(rr["gp_per_cv"].value, 2),
            "measured": rr["cv_to_placement"].measured,
            "first_placement_year": first_year,
        })
    rows.sort(key=lambda r: r["gp"], reverse=True)
    return rows


def _yoy_decomposition(ds: Dataset) -> list[dict]:
    """Split each year's ratio movement into performance vs mix.

    A firm-wide conversion rate can fall while every market improves, if volume shifts
    toward the harder market. Reporting the movement without this is how a team
    concludes it got worse in a year it got better.
    """
    out = []
    years = ds.years
    for prev, curr in zip(years, years[1:]):
        before = group_by(ds, "market", Slice(year=prev))
        after = group_by(ds, "market", Slice(year=curr))
        for ratio_id in ("cv_to_placement", "cv_to_interview"):
            row = decompose_change(before, after, ratio_id)
            row["from_year"], row["to_year"] = prev, curr
            out.append(row)
    return out


def write_report(report: dict, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    return path
