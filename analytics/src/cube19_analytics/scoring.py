"""Ranking markets and clients - see docs/05-market-client-scoring.md.

Cube19 ranks people. This ranks opportunities, which is the decision that actually
moves revenue: where the next head goes, which accounts get BD time, which quietly
consume a year and never convert.

Every score ranks on the *lower bound* of a credible interval, so an opportunity you
have barely tested cannot outrank one with a proven record.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date

from .metrics import Slice, compute_metrics, group_by
from .model import Dataset, Stage
from .ratios import compute_ratios
from .stats import sample_size_for
from .timeseries import momentum, time_to_fill, yearly_series

__all__ = [
    "MARKET_WEIGHTS", "CLIENT_WEIGHTS", "score_markets", "score_clients",
    "dormant_accounts", "contact_coverage", "bounded_test_plan",
]

# Weights encode strategy, not truth. Argue about them deliberately and record why.
MARKET_WEIGHTS = {
    "gp_per_cv_lb": 0.35,
    "momentum": 0.20,
    "fill_rate_lb": 0.15,
    "cycle_speed": 0.10,
    "headroom": 0.10,
    "concentration_penalty": 0.10,
}

CLIENT_WEIGHTS = {
    "gp_per_cv_lb": 0.30,
    "fill_rate_lb": 0.20,
    "repeat_rate": 0.15,
    "avg_fee": 0.15,
    "exclusivity": 0.10,
    "recency": 0.10,
}


def _normalise(values: dict[str, float]) -> dict[str, float]:
    """Min-max to 0..1. Ties (or a single value) map to 0.5, which is the honest
    answer when there is nothing to distinguish."""
    if not values:
        return {}
    lo, hi = min(values.values()), max(values.values())
    if hi - lo < 1e-12:
        return {k: 0.5 for k in values}
    return {k: (v - lo) / (hi - lo) for k, v in values.items()}


def _hhi(shares: list[float]) -> float:
    """Herfindahl index of GP concentration. 1.0 = one client is the whole market."""
    total = sum(shares)
    if total <= 0:
        return 1.0
    return sum((s / total) ** 2 for s in shares)


def score_markets(
    ds: Dataset,
    weights: dict[str, float] | None = None,
    headroom: dict[str, float] | None = None,
    firm_priors: dict[str, float] | None = None,
) -> list[dict]:
    """Rank markets. Returns rows sorted best-first, each with a tier and a reason.

    ``headroom`` (market -> 0..1, 'how much room is left') needs external market-size
    data we do not have in the CRM. Absent it every market gets a neutral 0.5, which
    means the factor cancels out of the ranking rather than silently biasing it.
    """
    weights = weights or MARKET_WEIGHTS
    headroom = headroom or {}

    firm_ms = compute_metrics(ds)
    firm_ratios = compute_ratios(firm_ms)
    priors = firm_priors or {rid: rr.value for rid, rr in firm_ratios.items() if rr.measured}

    by_market = group_by(ds, "market")
    series = yearly_series(ds, "market")
    ttf = time_to_fill(ds, "market")
    complete = ds.complete_years

    gp_by_market_client: dict[str, list[float]] = defaultdict(list)
    for market in ds.markets:
        per_client: dict[str, float] = defaultdict(float)
        for p in ds.placements:
            if p.market == market:
                per_client[p.client_id] += p.gp
        gp_by_market_client[market] = list(per_client.values())

    raw: dict[str, dict] = {}
    for market, ms in by_market.items():
        ratios = compute_ratios(ms, priors=priors)
        gp_cv = ratios["gp_per_cv"]
        fill = ratios["job_fill_rate"]
        median_ttf = ttf.get(market, {}).get("median_days")
        raw[market] = {
            "market": market,
            "gp": ms.get("gp"),
            "placements": ms.get("placements"),
            "cvs_sent": ms.get("cvs_sent"),
            "jobs_taken": ms.get("jobs_taken"),
            "avg_fee": ms.get("avg_fee"),
            "active_consultants": ms.get("active_consultants"),
            "gp_per_head": ms.get("gp_per_head"),
            "gp_per_cv": gp_cv.value,
            "gp_per_cv_lb": gp_cv.lo,
            "gp_per_cv_ub": gp_cv.hi,
            "gp_per_cv_measured": gp_cv.measured,
            "fill_rate": fill.value,
            "fill_rate_lb": fill.lo,
            "cv_to_interview": ratios["cv_to_interview"].value,
            "cv_to_placement": ratios["cv_to_placement"].value,
            "momentum": momentum(series.get(market, []), complete_years=complete),
            "median_time_to_fill": median_ttf,
            "cycle_speed": (1.0 / median_ttf) if median_ttf else 0.0,
            "hhi": _hhi(gp_by_market_client.get(market, [])),
            "headroom": headroom.get(market, 0.5),
        }

    norm = {
        factor: _normalise({m: r[factor] for m, r in raw.items()})
        for factor in ("gp_per_cv_lb", "fill_rate_lb", "cycle_speed", "headroom")
    }
    # Unknown momentum is not bad momentum. Markets without enough complete years get a
    # neutral 0.5 so the factor cancels rather than dragging them to the bottom.
    known = {m: r["momentum"] for m, r in raw.items() if r["momentum"] is not None}
    norm_known = _normalise(known)
    norm["momentum"] = {m: norm_known.get(m, 0.5) for m in raw}
    norm["concentration_penalty"] = _normalise({m: 1.0 - r["hhi"] for m, r in raw.items()})

    rows = []
    for market, r in raw.items():
        score = sum(weights[f] * norm[f].get(market, 0.5) for f in weights)
        r["score"] = round(score, 4)
        r["factors"] = {f: round(norm[f].get(market, 0.5), 3) for f in weights}
        rows.append(r)

    # Compare each market against the rest of the firm, not against a firm average it
    # helps set. Without this the largest market is measured against itself and always
    # comes back "no different from average", which is true and useless.
    total_gp = sum(r["gp"] for r in rows)
    total_cvs = sum(r["cvs_sent"] for r in rows)
    for r in rows:
        others_gp = total_gp - r["gp"]
        others_cvs = total_cvs - r["cvs_sent"]
        r["peer_gp_per_cv"] = (others_gp / others_cvs) if others_cvs > 0 else firm_ratios["gp_per_cv"].value

    rows.sort(key=lambda r: r["score"], reverse=True)
    _assign_market_tiers(rows)
    return rows


def _assign_market_tiers(rows: list[dict]) -> None:
    """Assign tiers on economics and on what the data can actually support.

    Three rules do the work here, and each exists because the obvious version is wrong:

    1. **Compare against peers, not the firm.** Each market is judged against the rest
       of the business (``peer_gp_per_cv``), because the largest market substantially
       *is* the firm average and would otherwise always look average.
    2. **Separate "confidently worse" from "not yet known".** A credible interval that
       straddles the peer average has not shown the market is weak - it has shown
       nothing. Telling a business to exit such a market is the most expensive mistake
       this model could make.
    3. **Unresolved is not always testable.** If the interval is already tight and still
       straddles, more CVs will not resolve it (docs/05: a market that is only slightly
       better is not provable at our volumes). That is a Hold, not a Test.

    Rank position is deliberately unused: with five markets, "top third" is one market,
    so the second-best economics in the business would land in Exit.
    """
    if not rows:
        return

    for r in rows:
        mom = r["momentum"]
        mom_txt = f"{mom:+.0%}" if mom is not None else "not yet measurable"
        declining = mom is not None and mom < -0.15

        baseline = r["peer_gp_per_cv"] or 1.0
        lo, hi, point = r["gp_per_cv_lb"], r["gp_per_cv_ub"], r["gp_per_cv"]
        confidently_better = lo >= baseline
        confidently_worse = hi < baseline
        # Relative interval width: how much resolving power more data could still buy.
        precision = (hi - lo) / point if point > 0 else 99.0
        already_well_tested = precision < 0.5

        if not r["gp_per_cv_measured"]:
            r["tier"] = "Test"
            r["reason"] = (
                f"Only {int(r['cvs_sent'])} CVs sent - not enough to judge. "
                "Run a bounded test with a CV budget and a decision date.")
        elif confidently_worse:
            r["tier"] = "Exit or fix"
            r["reason"] = (
                f"GP/CV sits below the rest of the business across its whole credible range "
                f"(EUR {lo:,.0f}-{hi:,.0f} vs EUR {baseline:,.0f} elsewhere)"
                + (f" and declining {mom_txt}" if declining else "")
                + " - the same effort earns more in another market.")
        elif confidently_better and not declining:
            r["tier"] = "Attack"
            r["reason"] = (
                f"GP/CV beats the rest of the business even at its lower bound "
                f"(EUR {lo:,.0f} vs EUR {baseline:,.0f}); momentum {mom_txt}"
                + (". GP is concentrated in few clients - verify before adding heads"
                   if r["hhi"] > 0.4 else "."))
        elif confidently_better and declining:
            r["tier"] = "Hold"
            r["reason"] = (
                f"Strong economics (GP/CV lower bound EUR {lo:,.0f}) but declining {mom_txt} "
                "- hold the desk, do not add heads until the trend turns.")
        elif already_well_tested:
            r["tier"] = "Hold"
            r["reason"] = (
                f"Performs in line with the rest of the business (EUR {point:,.0f} vs "
                f"EUR {baseline:,.0f}) and has enough volume that more data will not change "
                f"that verdict. Momentum {mom_txt}. Maintain; decide expansion on fee size "
                "and accessibility, not on conversion.")
        else:
            looks_strong = point >= baseline
            r["tier"] = "Test"
            r["reason"] = (
                f"Unresolved: GP/CV EUR {point:,.0f}, but the credible range "
                f"EUR {lo:,.0f}-{hi:,.0f} straddles the EUR {baseline:,.0f} earned elsewhere. "
                + ("Point estimate is above peers - worth a funded test."
                   if looks_strong else
                   "Point estimate is below peers - test only if fee size justifies it."))

        r["gp_per_cv_vs_peers"] = round(lo / baseline, 3)
        r["interval_precision"] = round(precision, 3)
        r["confidence"] = (
            "confidently above peers" if confidently_better else
            "confidently below peers" if confidently_worse else
            "not distinguishable from peers")


def score_clients(
    ds: Dataset,
    weights: dict[str, float] | None = None,
    as_of: date | None = None,
    min_cvs: int = 1,
) -> list[dict]:
    """Rank client accounts into Farm / Grow / Qualify / Deprioritise.

    Deprioritise is the money-maker: accounts that have consumed real effort and never
    converted at a viable rate are invisible on every Cube19 screen, because Cube19
    reports what happened, not what it cost.
    """
    weights = weights or CLIENT_WEIGHTS
    as_of = as_of or max((p.start_date for p in ds.placements), default=date.today())

    firm_ratios = compute_ratios(compute_metrics(ds))
    priors = {rid: rr.value for rid, rr in firm_ratios.items() if rr.measured}

    by_client = group_by(ds, "client")
    last_activity: dict[str, date] = {}
    for e in ds.stage_events:
        prev = last_activity.get(e.client_id)
        if prev is None or e.event_date > prev:
            last_activity[e.client_id] = e.event_date
    for j in ds.jobs:
        prev = last_activity.get(j.client_id)
        if prev is None or j.date_opened > prev:
            last_activity[j.client_id] = j.date_opened

    contacts = contact_coverage(ds)

    raw: dict[str, dict] = {}
    for client_id, ms in by_client.items():
        if ms.get("cvs_sent") < min_cvs and ms.get("placements") == 0:
            continue
        client = ds.client(client_id)
        ratios = compute_ratios(ms, priors=priors)
        jobs = [j for j in ds.jobs if j.client_id == client_id]
        exclusivity = (sum(1 for j in jobs if j.exclusive) / len(jobs)) if jobs else 0.0
        last_seen = last_activity.get(client_id)
        days_since = (as_of - last_seen).days if last_seen else 9999
        years_known = max(
            ((as_of - min((j.date_opened for j in jobs), default=as_of)).days / 365.25), 0.5
        )
        raw[client_id] = {
            "client_id": client_id,
            "name": client.name if client else client_id,
            "market": client.market if client else ms.slice.market or "Unknown",
            "gp": ms.get("gp"),
            "placements": ms.get("placements"),
            "cvs_sent": ms.get("cvs_sent"),
            "jobs_taken": ms.get("jobs_taken"),
            "avg_fee": ms.get("avg_fee"),
            "gp_per_cv": ratios["gp_per_cv"].value,
            "gp_per_cv_lb": ratios["gp_per_cv"].lo,
            "gp_per_cv_measured": ratios["gp_per_cv"].measured,
            "fill_rate": ratios["job_fill_rate"].value,
            "fill_rate_lb": ratios["job_fill_rate"].lo,
            "repeat_rate": ms.get("placements") / years_known,
            "exclusivity": exclusivity,
            "days_since_activity": days_since,
            "recency": 1.0 / (1.0 + days_since / 180.0),
            "contacts_engaged": contacts.get(client_id, 0),
        }

    norm = {
        f: _normalise({c: r[f] for c, r in raw.items()})
        for f in ("gp_per_cv_lb", "fill_rate_lb", "repeat_rate", "avg_fee", "exclusivity", "recency")
    }

    rows = []
    for client_id, r in raw.items():
        r["score"] = round(sum(weights[f] * norm[f].get(client_id, 0.5) for f in weights), 4)
        rows.append(r)

    rows.sort(key=lambda r: r["score"], reverse=True)
    _assign_client_tiers(rows, firm_ratios["cv_to_placement"].value)
    return rows


def _assign_client_tiers(rows: list[dict], firm_cv_to_placement: float) -> None:
    for r in rows:
        proven = r["gp_per_cv_measured"]
        converts = r["placements"] > 0
        real_effort = r["cvs_sent"] >= 15

        if proven and converts and r["repeat_rate"] >= 1.0:
            r["tier"] = "Farm"
            r["action"] = "Protect. Named owner, contact-coverage target, quarterly review."
        elif converts and r["fill_rate"] >= firm_cv_to_placement:
            r["tier"] = "Grow"
            r["action"] = "Best use of BD time - widen contacts and job flow here."
        elif real_effort and not converts:
            r["tier"] = "Deprioritise"
            r["action"] = (
                f"{int(r['cvs_sent'])} CVs, zero placements. Stop proactive time; inbound only.")
        elif not real_effort:
            r["tier"] = "Qualify"
            r["action"] = "Unproven. Bounded test with a fixed CV budget and a decision date."
        else:
            r["tier"] = "Deprioritise"
            r["action"] = "Below-average economics after real effort. Inbound only."

        if r["tier"] in ("Farm", "Grow") and r["contacts_engaged"] < 3:
            r["flag"] = (
                f"Single-threaded: only {r['contacts_engaged']} contact(s) engaged. "
                "Widen before this account walks.")


def contact_coverage(ds: Dataset) -> dict[str, int]:
    """Distinct candidates-per-client is a poor proxy for contacts; use activity where
    we have it, and fall back to distinct consultants touching the account.

    Contacts engaged predicts account growth better than any other single metric - one
    contact is a single point of failure.
    """
    per_client: dict[str, set] = defaultdict(set)
    for a in ds.activities:
        if a.client_id and a.action in ("call", "connect", "client_meeting", "email"):
            per_client[a.client_id].add(a.consultant_id)
    for j in ds.jobs:
        per_client[j.client_id].add(j.consultant_id)
    return {client_id: len(users) for client_id, users in per_client.items()}


def dormant_accounts(ds: Dataset, as_of: date | None = None,
                     min_gp: float = 1.0, min_days: int = 270) -> list[dict]:
    """Clients that placed before and have gone quiet - the cheapest revenue there is.

    Ranked by historical economics decayed by how long it has been. What matters most
    is whether the hiring manager who liked you is still there; the CRM cannot always
    tell us, so we surface the list and flag the question.
    """
    as_of = as_of or max((p.start_date for p in ds.placements), default=date.today())
    last_seen: dict[str, date] = {}
    for j in ds.jobs:
        prev = last_seen.get(j.client_id)
        if prev is None or j.date_opened > prev:
            last_seen[j.client_id] = j.date_opened

    gp_by_client: dict[str, float] = defaultdict(float)
    placements_by_client: dict[str, int] = defaultdict(int)
    for p in ds.placements:
        gp_by_client[p.client_id] += p.gp
        placements_by_client[p.client_id] += 1

    rows = []
    for client_id, gp in gp_by_client.items():
        if gp < min_gp:
            continue
        seen = last_seen.get(client_id)
        days = (as_of - seen).days if seen else 9999
        if days < min_days:
            continue
        client = ds.client(client_id)
        decay = 0.5 ** (days / 540.0)  # ~18-month half-life
        rows.append({
            "client_id": client_id,
            "name": client.name if client else client_id,
            "market": client.market if client else "Unknown",
            "historical_gp": round(gp, 2),
            "placements": placements_by_client[client_id],
            "days_since_last_job": days,
            "reactivation_score": round(gp * decay, 2),
            "check": "Confirm the hiring manager is still in post before calling - "
                     "if they moved, this is a cold account and a warm lead elsewhere.",
        })
    rows.sort(key=lambda r: r["reactivation_score"], reverse=True)
    return rows


def bounded_test_plan(ds: Dataset, market: str, target_multiple: float = 2.0) -> dict:
    """How many CVs to commit before deciding on an unproven market.

    Turns 'we think that might be good' into an experiment with a budget and a decision
    date. Note the asymmetry: proving a market is twice as good is cheap; proving one is
    slightly better is not affordable at our volumes - so do not try.
    """
    firm = compute_ratios(compute_metrics(ds))
    baseline = firm["cv_to_placement"].value
    detectable = min(baseline * target_multiple, 0.95)
    n = sample_size_for(baseline, detectable)
    ms = compute_metrics(ds, Slice(market=market))
    already = int(ms.get("cvs_sent"))
    return {
        "market": market,
        "firm_baseline_cv_to_placement": round(baseline, 4),
        "detectable_rate": round(detectable, 4),
        "cvs_required": n,
        "cvs_already_sent": already,
        "cvs_remaining": max(n - already, 0),
        "verdict": (
            f"Send {max(n - already, 0)} more CVs into {market}, then decide. "
            f"If it has not beaten {detectable:.0%} CV→placement by then, stop."
            if n > already else
            f"{market} already has enough volume to judge - read the score, do not test further."
        ),
    }
