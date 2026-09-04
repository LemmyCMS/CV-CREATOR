"""Target setting by back-solving the ratio chain - see docs/04-target-setting.md.

The point of this module: a target should be arithmetic from a revenue goal, with an
honest interval, not a number a manager negotiated. And because eight uncertain ratios
multiply together, the interval is wide - which is exactly the thing a spreadsheet
hides and a team discovers the hard way in month nine.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from .ratios import RatioResult

__all__ = ["ChainStep", "TargetPlan", "back_solve", "sensitivity",
           "improvement_potential", "feasibility"]

# The chain, from money backwards to activity. Each step divides by its ratio.
# Order matters: it is the funnel in reverse.
CHAIN: list[tuple[str, str, str]] = [
    ("placements", "offer_to_placement", "offers"),
    ("offers", "interview_to_offer", "first_interviews"),
    ("first_interviews", "cv_to_interview", "cvs_sent"),
    ("cvs_sent", "cvs_per_job", "jobs_taken"),
    ("jobs_taken", "meeting_to_job", "client_meetings"),
    ("client_meetings", "connect_to_meeting", "connects"),
    ("connects", "call_to_connect", "calls"),
]


@dataclass
class ChainStep:
    from_metric: str
    ratio_id: str
    to_metric: str
    ratio_used: float
    required: float
    p20: float
    p50: float
    p80: float
    measured: bool
    anchor: bool = False   # True for the earliest reliably-measured stage

    def as_dict(self) -> dict:
        return {
            "from": self.from_metric, "ratio": self.ratio_id, "to": self.to_metric,
            "ratio_used": round(self.ratio_used, 5), "required": round(self.required, 1),
            "p20": round(self.p20, 1), "p50": round(self.p50, 1), "p80": round(self.p80, 1),
            "measured": self.measured, "anchor": self.anchor,
        }


@dataclass
class TargetPlan:
    gp_goal: float
    avg_fee: float
    placements_needed: float
    steps: list[ChainStep] = field(default_factory=list)
    anchor_metric: str = "cvs_sent"
    warnings: list[str] = field(default_factory=list)

    def required(self, metric: str) -> float | None:
        if metric == "placements":
            return self.placements_needed
        for s in self.steps:
            if s.to_metric == metric:
                return s.required
        return None

    def per_working_day(self, metric: str, working_days: int = 220) -> float | None:
        total = self.required(metric)
        return total / working_days if total is not None else None

    def as_dict(self) -> dict:
        return {
            "gp_goal": self.gp_goal,
            "avg_fee": round(self.avg_fee, 2),
            "placements_needed": round(self.placements_needed, 2),
            "anchor_metric": self.anchor_metric,
            "steps": [s.as_dict() for s in self.steps],
            "warnings": self.warnings,
        }


def back_solve(
    gp_goal: float,
    ratios: dict[str, RatioResult],
    avg_fee: float,
    draws: int = 10000,
    seed: int = 19,
    reliable: set[str] | None = None,
) -> TargetPlan:
    """Walk the chain backwards from a GP goal to required activity.

    Returns p20/p50/p80 for every stage. **Set the target at p80 and plan capacity at
    p50** - targeting the median means missing half the time by construction, which
    burns the credibility of the whole system inside one quarter.

    ``reliable`` (from quality.reliable_metrics) restricts which stage may be the
    anchor. Without it the anchor is chosen on volume alone, and a firm with 111,000
    badly-logged calls will happily anchor its targets on call activity.
    """
    if avg_fee <= 0:
        raise ValueError("avg_fee must be positive - check the GP mapping first")

    plan = TargetPlan(
        gp_goal=gp_goal, avg_fee=avg_fee, placements_needed=gp_goal / avg_fee
    )

    rng = random.Random(seed)
    # Monte Carlo the whole chain: each draw samples every ratio from its posterior, so
    # the spread at the end carries the compounded uncertainty rather than hiding it.
    trajectories: list[dict[str, float]] = []
    for _ in range(draws):
        current = plan.placements_needed
        row: dict[str, float] = {"placements": current}
        for _from, ratio_id, to_metric in CHAIN:
            rr = ratios.get(ratio_id)
            if rr is None or rr.denominator <= 0:
                row[to_metric] = float("nan")
                continue
            sampled = _sample_ratio(rr, rng)
            if sampled <= 0:
                row[to_metric] = float("nan")
                continue
            current = current / sampled
            row[to_metric] = current
        trajectories.append(row)

    running = plan.placements_needed
    for from_metric, ratio_id, to_metric in CHAIN:
        rr = ratios.get(ratio_id)
        if rr is None or rr.denominator <= 0:
            plan.warnings.append(
                f"{ratio_id} has no data - chain truncated at {from_metric}. "
                "Anchor the target here.")
            break
        running = running / rr.value if rr.value > 0 else running
        values = sorted(t[to_metric] for t in trajectories if t[to_metric] == t[to_metric])
        if not values:
            break
        plan.steps.append(ChainStep(
            from_metric=from_metric, ratio_id=ratio_id, to_metric=to_metric,
            ratio_used=rr.value, required=running,
            p20=_pct(values, 0.20), p50=_pct(values, 0.50), p80=_pct(values, 0.80),
            measured=rr.measured,
        ))

    _set_anchor(plan, reliable)
    return plan


def _sample_ratio(rr: RatioResult, rng: random.Random) -> float:
    """Draw one value from a ratio's posterior.

    Proportions have a Beta posterior we can sample exactly. For rates and monetary
    ratios we approximate with a triangular over the credible interval - crude, but it
    carries the right width, which is the part that matters here.
    """
    if rr.kind.value == "proportion":
        alpha = max(rr.value * 60, 0.5)
        beta = max((1 - rr.value) * 60, 0.5)
        return rng.betavariate(alpha, beta)
    lo, hi = max(rr.lo, 1e-9), max(rr.hi, rr.lo + 1e-9)
    return rng.triangular(lo, hi, min(max(rr.value, lo), hi))


def _pct(sorted_values: list[float], q: float) -> float:
    if not sorted_values:
        return float("nan")
    i = min(int(q * len(sorted_values)), len(sorted_values) - 1)
    return sorted_values[i]


def _set_anchor(plan: TargetPlan, reliable: set[str] | None = None) -> None:
    """Mark the earliest reliably-measured stage as the anchor.

    docs/04 section 3: set the target at the earliest stage that is actually measured.
    For most agencies the call log is not it, and pretending otherwise produces a daily
    call target nobody believes. Two tests must both pass: enough volume for the
    estimate to be stable (``measured``), and trustworthy logging (``reliable``).
    """
    measured = [
        s for s in plan.steps
        if s.measured and (reliable is None or s.to_metric in reliable)
    ]
    if reliable is not None:
        excluded = [s.to_metric for s in plan.steps if s.measured and s.to_metric not in reliable]
        if excluded:
            plan.warnings.append(
                f"Not anchoring on {', '.join(excluded)} - logging coverage is too poor for "
                "those to mean anything. Run quality.assess() for the detail.")
    if not measured:
        plan.anchor_metric = "placements"
        plan.warnings.append(
            "No stage has enough data to anchor on. Target placements and GP only until "
            "the funnel has volume.")
        return
    anchor = measured[-1]
    anchor.anchor = True
    plan.anchor_metric = anchor.to_metric
    unmeasured_after = [s for s in plan.steps if not s.measured]
    if unmeasured_after:
        plan.warnings.append(
            f"Stages beyond {anchor.to_metric} ({', '.join(s.to_metric for s in unmeasured_after)}) "
            "are not reliably measured - treat those numbers as indicative only.")


def sensitivity(
    gp_goal: float,
    ratios: dict[str, RatioResult],
    avg_fee: float,
    metric: str = "cvs_sent",
    bump: float = 0.10,
) -> list[dict]:
    """Elasticity: how much required activity moves per ``bump`` improvement in each input.

    Expect every link between ``metric`` and revenue to come back with the *same*
    number, and links upstream of ``metric`` to come back zero. That is not a bug - in a
    multiplicative chain a 10% relative gain is worth the same wherever you get it, and
    upstream stages do not affect how many CVs you must send.

    Which is why this function alone cannot tell you where to invest. Use
    ``improvement_potential()`` for that: the question is not "what if this improved by
    10%" but "how much could this realistically improve at all".
    """
    base = back_solve(gp_goal, ratios, avg_fee, draws=1).required(metric)
    if base is None:
        return []
    out = []

    improved = back_solve(gp_goal, ratios, avg_fee * (1 + bump), draws=1).required(metric)
    out.append({
        "input": "avg_fee", "label": "Average fee",
        "delta_pct": round((improved - base) / base * 100, 2) if base else None,
    })

    for _from, ratio_id, _to in CHAIN:
        rr = ratios.get(ratio_id)
        if rr is None or rr.denominator <= 0:
            continue
        tweaked = dict(ratios)
        bumped = RatioResult(**{**rr.__dict__, "value": rr.value * (1 + bump)})
        tweaked[ratio_id] = bumped
        new = back_solve(gp_goal, tweaked, avg_fee, draws=1).required(metric)
        if new is None:
            continue
        out.append({
            "input": ratio_id, "label": rr.label,
            "delta_pct": round((new - base) / base * 100, 2) if base else None,
        })

    out.sort(key=lambda r: r["delta_pct"] if r["delta_pct"] is not None else 0)
    return out


def feasibility(
    plan: TargetPlan,
    live_job_capacity: int,
    avg_job_life_days: float,
    period_days: int = 365,
) -> dict:
    """Does the plan fit inside the capacity that actually binds?

    It is almost never CVs. It is live qualified jobs, or client interview slots. A
    plan that fails this is not a stretch goal, it is a fiction - and the honest move is
    to fix the constraint or lower the goal rather than restate the target louder.
    """
    jobs_needed = plan.required("jobs_taken")
    if jobs_needed is None:
        return {"assessable": False,
                "reason": "no job-level data - cannot check the binding constraint"}

    job_days_needed = jobs_needed * avg_job_life_days
    job_days_available = live_job_capacity * period_days
    utilisation = job_days_needed / job_days_available if job_days_available else float("inf")

    return {
        "assessable": True,
        "jobs_needed": round(jobs_needed, 1),
        "job_days_needed": round(job_days_needed),
        "job_days_available": round(job_days_available),
        "utilisation": round(utilisation, 3),
        "feasible": utilisation <= 1.0,
        "verdict": (
            f"Plan needs {utilisation:.0%} of job-carrying capacity. "
            + ("Feasible." if utilisation <= 0.85 else
               "Tight - little room for job quality to slip." if utilisation <= 1.0 else
               "NOT feasible on current capacity: raise job flow, job quality or headcount, "
               "or lower the goal.")
        ),
    }


def improvement_potential(
    gp_goal: float,
    ratios: dict[str, RatioResult],
    avg_fee: float,
    targets: dict[str, float] | None = None,
    fee_uplift: float = 0.25,
    metric: str = "cvs_sent",
) -> list[dict]:
    """Where the money actually is: rank inputs by *achievable* gain, not by elasticity.

    Elasticity is flat across a multiplicative chain, so the thing that separates the
    inputs is headroom - how far each one could plausibly move. A ratio already at the
    top of its benchmark band has nothing left to give; one sitting well below has a lot.

    ``targets`` overrides the level each ratio could reach (defaults to the 'strong'
    end of the benchmark band in docs/03). ``fee_uplift`` is the assumed achievable
    improvement in average fee from moving up-market or renegotiating - the one input
    with no ceiling in the data, which is why market and client selection usually
    outrank activity coaching.
    """
    # 'Strong' end of each benchmark band - docs/03 section 3.
    strong = targets or {
        "cv_to_interview": 0.45,
        "interview_to_offer": 0.35,
        "offer_to_placement": 0.90,
        "cvs_per_job": 3.5,
        "meeting_to_job": 0.45,
        "connect_to_meeting": 0.28,
        "call_to_connect": 0.35,
    }

    base = back_solve(gp_goal, ratios, avg_fee, draws=1).required(metric)
    if base is None or base <= 0:
        return []

    rows = [{
        "input": "avg_fee",
        "label": "Average fee (move up-market)",
        "current": round(avg_fee, 2),
        "achievable": round(avg_fee * (1 + fee_uplift), 2),
        "headroom_pct": round(fee_uplift * 100, 1),
        "activity_saved_pct": round(
            (back_solve(gp_goal, ratios, avg_fee * (1 + fee_uplift), draws=1).required(metric) - base)
            / base * 100, 2),
        "note": "No ceiling in the data - the only input that can move without limit.",
    }]

    for _from, ratio_id, _to in CHAIN:
        rr = ratios.get(ratio_id)
        if rr is None or rr.denominator <= 0 or ratio_id not in strong:
            continue
        ceiling = strong[ratio_id]
        if ceiling <= rr.value:
            rows.append({
                "input": ratio_id, "label": rr.label,
                "current": round(rr.value, 4), "achievable": round(ceiling, 4),
                "headroom_pct": 0.0, "activity_saved_pct": 0.0,
                "note": "Already at or above the strong benchmark - nothing left here.",
            })
            continue
        tweaked = dict(ratios)
        tweaked[ratio_id] = RatioResult(**{**rr.__dict__, "value": ceiling})
        new = back_solve(gp_goal, tweaked, avg_fee, draws=1).required(metric)
        saved = round((new - base) / base * 100, 2) if base else None
        rows.append({
            "input": ratio_id, "label": rr.label,
            "current": round(rr.value, 4), "achievable": round(ceiling, 4),
            "headroom_pct": round((ceiling - rr.value) / rr.value * 100, 1),
            "activity_saved_pct": saved,
            "note": (
                f"Upstream of {metric} - improving it reduces the jobs and BD effort needed, "
                "not the CVs. Re-run against an upstream metric to value it."
                if saved == 0 else ""
            ),
        })

    rows.sort(key=lambda r: r["activity_saved_pct"] if r["activity_saved_pct"] is not None else 0)
    return rows
