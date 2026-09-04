"""Year-by-year evolution, ramp curves and seasonality.

Answers the 'how did this market/person evolve' half of the brief. Kept separate from
scoring because these series are worth reading directly - a ranked list tells you where
to go, a trend tells you whether you are early or late.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import date

from .metrics import Slice, compute_metrics, group_by
from .model import Dataset, Stage

__all__ = [
    "yearly_series", "momentum", "ramp_curve", "seasonality_index",
    "time_to_fill", "cohort_conversion",
]


def yearly_series(ds: Dataset, dimension: str = "market",
                  metrics: tuple[str, ...] = ("gp", "placements", "cvs_sent", "jobs_taken")
                  ) -> dict[str, list[dict]]:
    """One series per dimension value, one point per year.

    Always carries ``active_consultants`` and ``gp_per_head`` alongside the raw totals -
    without them a rising GP line cannot be distinguished from a rising headcount line,
    and that mistake drives more bad strategy than any other in this business.
    """
    out: dict[str, list[dict]] = defaultdict(list)
    for year in ds.years:
        grouped = group_by(ds, dimension, Slice(year=year))
        for key, ms in grouped.items():
            point = {"year": year}
            for m in metrics:
                point[m] = round(ms.get(m), 2)
            point["active_consultants"] = ms.get("active_consultants")
            point["gp_per_head"] = round(ms.get("gp_per_head"), 2)
            point["avg_fee"] = round(ms.get("avg_fee"), 2)
            out[key].append(point)
    return dict(out)


def momentum(
    series: list[dict],
    metric: str = "gp",
    years: int = 3,
    complete_years: list[int] | None = None,
) -> float | None:
    """Recency-weighted YoY growth. Positive = growing. None = not enough data to say.

    Recent years get more weight because a market that was great four years ago and has
    declined since is a trap, and an unweighted CAGR hides exactly that shape.

    ``complete_years`` must be supplied wherever the caller can: a partial year at the
    edge of the data reads as a collapse, and momentum weights the most recent year
    hardest, so the two faults multiply. Returning None rather than 0.0 matters too -
    0.0 means 'flat', which is a claim, and on a market with two data points we are not
    entitled to it.
    """
    points = sorted(series, key=lambda p: p["year"])
    if complete_years is not None:
        allowed = set(complete_years)
        points = [p for p in points if p["year"] in allowed]
    points = points[-(years + 1):]
    if len(points) < 2:
        return None
    growths, weights = [], []
    for i in range(1, len(points)):
        prev, curr = points[i - 1][metric], points[i][metric]
        if prev <= 0:
            continue
        growths.append((curr - prev) / prev)
        weights.append(float(i))  # later years weigh more
    if not growths:
        return None
    return sum(g * w for g, w in zip(growths, weights)) / sum(weights)


def ramp_curve(ds: Dataset, bucket_months: int = 3, max_months: int = 36) -> list[dict]:
    """GP by months-since-start, pooled across all historical hires.

    This is how you set a fair target for a new starter. Targeting them at desk average
    guarantees failure and early attrition; targeting them at nothing wastes a year.
    """
    buckets: dict[int, list[float]] = defaultdict(list)
    for c in ds.consultants:
        placements = [p for p in ds.placements if p.consultant_id == c.consultant_id]
        if not placements and c.end_date is None:
            continue
        horizon = c.end_date or max((p.start_date for p in placements), default=c.start_date)
        months_active = int(min((horizon - c.start_date).days / 30.44, max_months))
        by_bucket: dict[int, float] = defaultdict(float)
        for p in placements:
            m = int(c.tenure_months_at(p.start_date))
            if m > max_months:
                continue
            by_bucket[(m // bucket_months) * bucket_months] += p.gp
        # Include zero months explicitly - dropping them inflates the early curve and
        # makes new hires look far more productive than they are.
        for b in range(0, months_active + 1, bucket_months):
            buckets[b].append(by_bucket.get(b, 0.0))

    curve = []
    for bucket in sorted(buckets):
        values = buckets[bucket]
        if not values:
            continue
        curve.append({
            "months_since_start": bucket,
            "label": f"{bucket}-{bucket + bucket_months}m",
            "consultants": len(values),
            "mean_gp": round(statistics.fmean(values), 2),
            "median_gp": round(statistics.median(values), 2),
        })

    steady = max((c["mean_gp"] for c in curve), default=0.0)
    for point in curve:
        point["pct_of_steady_state"] = round(point["mean_gp"] / steady, 3) if steady else 0.0
    return curve


def seasonality_index(ds: Dataset, metric: str = "placements") -> list[dict]:
    """Monthly index where 1.0 = an average month.

    Used to pro-rate targets. A flat monthly target in a business with an August
    collapse and a September spike sets people up to fail twice a year.
    """
    monthly: dict[int, list[float]] = defaultdict(list)
    per_year_month: dict[tuple[int, int], float] = defaultdict(float)

    if metric == "gp":
        for p in ds.placements:
            per_year_month[(p.start_date.year, p.start_date.month)] += p.gp
    elif metric == "cvs_sent":
        for e in ds.stage_events:
            if e.stage is Stage.CV_SENT:
                per_year_month[(e.event_date.year, e.event_date.month)] += 1
    else:
        for p in ds.placements:
            per_year_month[(p.start_date.year, p.start_date.month)] += 1

    for (_year, month), value in per_year_month.items():
        monthly[month].append(value)

    overall = statistics.fmean([v for vals in monthly.values() for v in vals]) if monthly else 0.0
    return [
        {
            "month": m,
            "index": round(statistics.fmean(monthly[m]) / overall, 3) if overall and monthly.get(m) else 1.0,
            "observations": len(monthly.get(m, [])),
        }
        for m in range(1, 13)
    ]


def time_to_fill(ds: Dataset, by: str = "market") -> dict[str, dict]:
    """Median and p90 days from job open to placement start.

    p90 is the number that sets the cohort maturity window in cohort_conversion - use
    the measured value, not the 120-day default (docs/03 section 4.2).
    """
    jobs = {j.job_id: j for j in ds.jobs}
    durations: dict[str, list[float]] = defaultdict(list)
    for p in ds.placements:
        job = jobs.get(p.job_id)
        if job is None:
            continue
        days = (p.start_date - job.date_opened).days
        if 0 <= days <= 730:  # drop backfilled or clearly bad rows
            key = getattr(p, by, "Unknown") if by != "market" else p.market
            durations[key].append(float(days))

    return {
        key: {
            "n": len(vals),
            "median_days": round(statistics.median(vals), 1),
            "p90_days": round(sorted(vals)[int(0.9 * (len(vals) - 1))], 1),
            "mean_days": round(statistics.fmean(vals), 1),
        }
        for key, vals in durations.items() if vals
    }


def cohort_conversion(
    ds: Dataset,
    maturity_days: int = 120,
    as_of: date | None = None,
    by: str = "market",
) -> dict[str, dict]:
    """CV→placement conversion attributed to the period of the CV, not the placement.

    Within-period ratios are only valid in a steady state. On a growing desk they
    understate conversion, on a shrinking one they flatter it (docs/03 section 4.2).
    Cohorts younger than ``maturity_days`` are reported separately as provisional
    rather than dragging the headline rate down.
    """
    as_of = as_of or max((p.start_date for p in ds.placements), default=date.today())
    placed_submissions = {
        p.submission_id for p in ds.placements if p.submission_id and not p.fell_off
    }

    cohorts: dict[str, dict[str, dict]] = defaultdict(lambda: defaultdict(
        lambda: {"cvs": 0, "placements": 0, "mature": True}))

    seen: set[str] = set()
    for e in ds.stage_events:
        if e.stage is not Stage.CV_SENT or e.submission_id in seen:
            continue
        seen.add(e.submission_id)
        key = e.market if by == "market" else getattr(e, by, "Unknown")
        period = f"{e.event_date.year}"
        cell = cohorts[key][period]
        cell["cvs"] += 1
        if e.submission_id in placed_submissions:
            cell["placements"] += 1
        if (as_of - e.event_date).days < maturity_days:
            cell["mature"] = False

    out: dict[str, dict] = {}
    for key, periods in cohorts.items():
        rows = []
        for period in sorted(periods):
            cell = periods[period]
            rows.append({
                "period": period,
                "cvs": cell["cvs"],
                "placements": cell["placements"],
                "rate": round(cell["placements"] / cell["cvs"], 4) if cell["cvs"] else None,
                "mature": cell["mature"],
            })
        mature = [r for r in rows if r["mature"] and r["cvs"] > 0]
        total_cvs = sum(r["cvs"] for r in mature)
        total_pl = sum(r["placements"] for r in mature)
        out[key] = {
            "cohorts": rows,
            "mature_rate": round(total_pl / total_cvs, 4) if total_cvs else None,
            "mature_cvs": total_cvs,
        }
    return out
