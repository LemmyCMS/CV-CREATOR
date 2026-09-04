"""Adapter for Cube19 OneView snapshots (period aggregates, not row-level data).

OneView gives one set of totals for one period for the whole company. That is far less
than the row-level export in docs/06 - there is no market, consultant or monthly
breakdown, so no ranking, no cohorts, no ramp curves. What it *does* give is exact
company-wide ratios, and ratios are headcount-independent, which makes them the one
thing that can be compared across periods without knowing how many people were employed.

Three things this module does that reading the screen does not:

1. **Recovers the funnel placement count.** Cube19's ratio block divides by a placement
   figure that appears nowhere in the metric list. Four independent published ratios
   agree on it, so it can be recovered and cross-checked.
2. **Reconciles.** Several OneView figures contradict each other. They are surfaced as
   findings rather than quietly averaged away.
3. **Annualises.** A 3-year snapshot and a 1-year snapshot are not comparable until the
   flow metrics are put on the same footing - and the stock metrics must NOT be.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

__all__ = ["Snapshot", "Finding", "load_snapshot", "compare", "FUNNEL_RATIOS", "BENCHMARKS"]

# Ratios published by Cube19 in "N : 1" form whose denominator is the same placement
# count. Each gives an independent estimate of it.
FUNNEL_RATIOS = {
    "cv_sent_to_placements": ("cvs_sent", "divide"),
    "first_interview_to_placements": ("total_first_interviews", "divide"),
    "total_jobs_added_to_total_placements": ("total_jobs_added", "divide"),
    "total_a_jobs_to_total_placements_inverse": ("total_a_jobs_added", "multiply"),
}

# Industry reference points - see docs/03. [PRIOR], not Gentis facts.
BENCHMARKS = {
    "cvs_per_job": (3.0, 5.0),
    "cv_to_first_interview": (0.25, 0.40),
    "first_interview_to_placement": (0.20, 0.33),
    "cv_to_placement": (0.08, 0.12),
    "job_fill_rate": (0.15, 0.25),
    "further_per_first_interview": (0.50, 0.70),
    "client_call_to_meeting": (0.10, 0.20),
    "meeting_to_job": (0.35, 1.00),
}


@dataclass
class Finding:
    """Something that does not add up, or does not pass a sanity check."""

    severity: str   # fail | warn | note
    subject: str
    detail: str

    def as_dict(self) -> dict:
        return {"severity": self.severity, "subject": self.subject, "detail": self.detail}


@dataclass
class Snapshot:
    label: str
    period_start: str
    period_end: str
    years: float
    raw: dict
    activity: dict
    revenue: dict
    live: dict
    leaks: dict
    targets: dict
    published_ratios: dict
    structural_break: dict | None = None
    seasonal_window: bool = False
    nested_in: str | None = None
    funnel_placements: float | None = None
    funnel_placements_spread: float | None = None
    findings: list[Finding] = field(default_factory=list)

    # -- access helpers ------------------------------------------------------
    def a(self, key: str) -> float:
        v = self.activity.get(key)
        return float(v) if v is not None else 0.0

    def r(self, key: str) -> float:
        v = self.revenue.get(key)
        return float(v) if v is not None else 0.0

    def per_year(self, value: float) -> float:
        """Annualise a FLOW metric. Never call this on a stock/snapshot metric.

        Annualising a part-year window assumes the missing months look like the ones you
        have. In recruitment they emphatically do not: August collapses and September
        spikes, so a window covering only the strong months annualises to a number the
        business has never achieved. ``seasonal_window`` marks such snapshots, and
        ``compare`` refuses to trend against them.
        """
        return value / self.years if self.years else value

    # -- the funnel ----------------------------------------------------------
    def ratios(self) -> dict[str, float | None]:
        """Conversion ratios computed from the raw counts.

        ``cvs_sent`` (job-linked) is the funnel denominator, not ``total_cvs_sent``.
        Cube19's own published ratios confirm this, and it matters enormously: spec
        sends are the majority of all CV activity and none of it is measured.
        """
        p = self.funnel_placements
        cvs = self.a("cvs_sent")
        jobs = self.a("total_jobs_added")
        first = self.a("total_first_interviews")

        def div(n, d):
            return (n / d) if d else None

        return {
            "cvs_per_job": div(cvs, jobs),
            "cv_to_first_interview": div(first, cvs),
            "first_interview_to_placement": div(p, first) if p else None,
            "cv_to_placement": div(p, cvs) if p else None,
            "job_fill_rate": div(p, jobs) if p else None,
            # NOT a fill rate: it is placements/A-jobs, and placements are not all
            # from A-jobs. Row-level evidence puts A/A+ at ~29% of placements.
            "placements_per_a_job_naive": div(p, self.a("total_a_jobs_added")) if p else None,
            "further_per_first_interview": div(self.a("further_interviews"), first),
            "client_call_to_meeting": div(self.a("client_meetings"), self.a("client_calls")),
            "meeting_to_job": div(jobs, self.a("client_meetings")),
            "client_calls_per_a_job": div(self.a("client_calls"), self.a("total_a_jobs_added")),
            "candidate_calls_per_cv": div(self.a("candidate_calls"), cvs),
            "spec_share_of_cvs": div(self.a("spec_cvs_sent"), self.a("total_cvs_sent")),
            "a_job_share_of_jobs": div(self.a("total_a_jobs_added"), jobs),
            "ref_checks_per_placement": div(self.a("reference_checks"), self.r("total_placements")),
            "perm_share_of_placements": div(self.r("perm_placements"), self.r("total_placements")),
            "extensions_per_contract_placement": div(self.r("extensions"), self.r("contract_placements")),
        }

    def gp(self) -> dict[str, float | None]:
        perm_gp = self.r("perm_billing")
        contract_gp = self.r("contract_gp_value")
        total_gp = perm_gp + contract_gp
        placements = self.r("total_placements")
        return {
            "perm_gp": perm_gp,
            "contract_gp": contract_gp,
            "total_gp": total_gp,
            "gp_per_placement": (total_gp / placements) if placements else None,
            "gp_per_funnel_placement": (total_gp / self.funnel_placements) if self.funnel_placements else None,
            "gp_per_cv_sent": (total_gp / self.a("cvs_sent")) if self.a("cvs_sent") else None,
            "gp_per_job": (total_gp / self.a("total_jobs_added")) if self.a("total_jobs_added") else None,
            "perm_share_of_gp": (perm_gp / total_gp) if total_gp else None,
        }

    def attainment(self) -> list[dict]:
        """Actual against target for every metric that carries one, worst first.

        The shape of this list is the finding, not any single row.
        """
        pool = {**self.activity, **self.revenue}
        rows = []
        for key, target in self.targets.items():
            actual = pool.get(key)
            if actual is None or not target:
                continue
            rows.append({
                "metric": key,
                "actual": float(actual),
                "target": float(target),
                "attainment": float(actual) / float(target),
            })
        rows.sort(key=lambda r: r["attainment"])
        return rows


def load_snapshot(path: str | Path, label: str | None = None) -> Snapshot:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    snap = Snapshot(
        label=label or data.get("_period", Path(path).stem),
        period_start=data.get("period_start", ""),
        period_end=data.get("period_end", ""),
        years=float(data.get("years", 1)),
        raw=data,
        activity=data.get("activity", {}),
        revenue=data.get("revenue", {}),
        live=data.get("live", {}),
        leaks=data.get("leaks", {}),
        targets=data.get("targets", {}),
        published_ratios=data.get("cube19_published_ratios", {}),
        structural_break=data.get("structural_break"),
        seasonal_window=bool(data.get("seasonal_window")),
        nested_in=data.get("nested_in"),
    )
    _recover_funnel_placements(snap)
    _reconcile(snap)
    return snap


def _recover_funnel_placements(snap: Snapshot) -> None:
    """Recover the placement count Cube19's ratio block actually divides by.

    It is not any figure on the screen. Four published ratios each imply it
    independently, so we solve each and check they agree - if they do, the number is
    real and the funnel can be closed; if they disagree, the ratios are measuring
    different things and none of them should be trusted.
    """
    estimates = {}
    for ratio_key, (metric, op) in FUNNEL_RATIOS.items():
        ratio = snap.published_ratios.get(ratio_key)
        base = snap.activity.get(metric)
        if not ratio or not base:
            continue
        estimates[ratio_key] = (base / ratio) if op == "divide" else (base * ratio)

    if not estimates:
        snap.findings.append(Finding(
            "warn", "funnel placements",
            "No published ratios available - the funnel cannot be closed from this snapshot."))
        return

    values = list(estimates.values())
    lo, hi = min(values), max(values)
    mid = sum(values) / len(values)
    spread = (hi - lo) / mid if mid else 1.0
    snap.funnel_placements = round(mid)
    snap.funnel_placements_spread = spread

    total = snap.revenue.get("total_placements")
    if spread <= 0.02:
        detail = (
            f"{len(estimates)} independent published ratios agree on {snap.funnel_placements:,.0f} "
            f"placements (spread {spread:.1%}), but the metric list reports "
            f"{total:,.0f} total placements."
            if total else
            f"{len(estimates)} published ratios agree on {snap.funnel_placements:,.0f} placements.")
        if total and abs(total - mid) / mid > 0.05:
            snap.findings.append(Finding(
                "warn", "funnel placements",
                detail + " Cube19's ratios are therefore NOT computed over all placements - "
                "extensions and spec placements appear to be excluded. Every ratio on the "
                "screen is a ratio of new-business delivery, not of total output. "
                "[VERIFY] the exact definition before any target is built on it."))
        else:
            snap.findings.append(Finding("note", "funnel placements", detail))
    else:
        snap.findings.append(Finding(
            "fail", "funnel placements",
            f"Published ratios disagree about the placement count "
            f"({lo:,.0f} to {hi:,.0f}, spread {spread:.1%}). They are measuring different "
            "things - do not build targets on them until the definitions are resolved."))


def _reconcile(snap: Snapshot) -> None:
    """Cross-check the figures against each other. Contradictions get surfaced."""
    a, r, live = snap.activity, snap.revenue, snap.live

    def close(x, y, tol=0.01):
        return x and y and abs(x - y) / max(x, y) <= tol

    # CV components
    cvs, spec, total_cvs = a.get("cvs_sent"), a.get("spec_cvs_sent"), a.get("total_cvs_sent")
    if cvs and spec and total_cvs and not close(cvs + spec, total_cvs):
        snap.findings.append(Finding(
            "warn", "CV totals",
            f"cvs_sent ({cvs:,}) + spec_cvs_sent ({spec:,}) = {cvs+spec:,}, "
            f"but total_cvs_sent is {total_cvs:,}."))

    # Billing
    cb, pb, tb = r.get("contract_billing"), r.get("perm_billing"), r.get("total_billing")
    if cb and pb and tb and not close(cb + pb, tb, 0.02):
        snap.findings.append(Finding(
            "fail", "billing",
            f"Contract billing ({cb:,.0f}) + perm billing ({pb:,.0f}) = {cb+pb:,.0f}, but "
            f"'Total Billing' reports {tb:,.0f} - a {abs(cb+pb-tb):,.0f} gap. Two different "
            "revenue definitions are in play (likely invoiced vs contract value). Resolve "
            "this before quoting any revenue number externally."))

    # Placement components
    cp, pp, tp = r.get("contract_placements"), r.get("perm_placements"), r.get("total_placements")
    if cp and pp and tp and not close(cp + pp, tp):
        snap.findings.append(Finding(
            "warn", "placements",
            f"contract ({cp:,}) + perm ({pp:,}) = {cp+pp:,} vs total {tp:,}."))

    ext, cp_ex = r.get("extensions"), r.get("contract_placements_excl_extensions")
    if cp and ext and cp_ex and not close(cp_ex + ext, cp, 0.05):
        snap.findings.append(Finding(
            "warn", "extensions",
            f"contract placements excl extensions ({cp_ex:,}) + extensions ({ext:,}) = "
            f"{cp_ex+ext:,}, but contract placements is {cp:,}. The extension definition "
            "does not partition contract placements cleanly."))

    # Live jobs against the flow that feeds them
    lj, jobs = live.get("live_jobs"), a.get("total_jobs_added")
    if lj and jobs and lj > jobs * 2:
        snap.findings.append(Finding(
            "fail", "live jobs",
            f"{lj:,} jobs are marked live against {jobs:,} added in this period. Live jobs "
            "cannot exceed recent intake by this margin - the job pipeline is not being "
            "closed down. Any report using live jobs as a denominator is meaningless, and "
            "consultants cannot see real priorities in a list this polluted."))

    # Time to fill
    ttf = r.get("avg_time_to_fill_contract_days")
    if ttf and ttf > 365:
        snap.findings.append(Finding(
            "warn", "time to fill",
            f"Average contract time-to-fill reads {ttf:.0f} days. That is almost certainly "
            "measuring from original job creation through successive extensions rather than "
            "to first start - unusable as a speed metric until redefined."))

    # Obviously broken metric
    if r.get("avg_fee_perm_pct"):
        snap.findings.append(Finding("warn", "avg fee perm", "Reported as a percentage - misconfigured."))

    # Reference checks against placements
    ref, tp2 = a.get("reference_checks"), r.get("total_placements")
    if ref is not None and tp2:
        rate = ref / tp2
        if rate < 0.5:
            snap.findings.append(Finding(
                "warn", "reference checks",
                f"{ref:,} reference checks against {tp2:,} placements ({rate:.0%}). Either "
                "they are not being done or not being logged; both are a problem, and one "
                "of them is a compliance problem."))


def compare(prior: Snapshot, recent: Snapshot) -> dict:
    """Compare two adjacent snapshots on an annualised basis.

    Flow metrics are annualised; ratios are not (they are already rates), and stock
    metrics are excluded entirely - 'Live Jobs' and 'Contractors Out' are the same
    snapshot number on both views and comparing them would be meaningless.
    """
    guards = []
    # A corporate restructure inside a window is worse than a seasonal one: seasonality
    # distorts a rate, a restructure changes which business the rate describes. Metrics
    # the break touches are marked so no one reads them as a performance trend.
    broken_metrics: set[str] = set()
    for snap in (prior, recent):
        br = snap.structural_break
        if br and br.get("spans_this_window"):
            broken_metrics |= set(br.get("affects", []))
    if broken_metrics:
        br = recent.structural_break or prior.structural_break
        guards.append(
            f"STRUCTURAL BREAK ({br['date']}): {br['what']} {br['implication']} "
            f"Affected metrics are flagged and must not be read as performance. "
            f"({br['confidence']})")

    for snap, role in ((prior, "prior"), (recent, "recent")):
        if snap.seasonal_window:
            guards.append(
                f"The {role} snapshot ({snap.label}) covers {snap.years * 12:.0f} months of a "
                "seasonal year, so annualising it projects the strong months across the weak "
                "ones. Treat every annualised figure from it as an upper bound, and compare it "
                "only against the SAME months of another year.")
        if snap.nested_in:
            guards.append(
                f"The {role} snapshot is nested inside {snap.nested_in} - it is a sub-period of "
                "the other window, not an independent one. Differences between them are "
                "arithmetic, not trend.")

    if prior.period_end != recent.period_start:
        note = (f"Periods are not adjacent ({prior.period_end} vs {recent.period_start}) - "
                "they may overlap, which would double-count.")
    else:
        note = f"Adjacent periods, no overlap: {prior.period_start}→{prior.period_end}→{recent.period_end}."

    flow_rows = []
    for section in ("activity", "revenue"):
        pool_p = getattr(prior, section)
        pool_r = getattr(recent, section)
        for key in sorted(set(pool_p) | set(pool_r)):
            pv, rv = pool_p.get(key), pool_r.get(key)
            if pv is None or rv is None or not isinstance(pv, (int, float)) or not isinstance(rv, (int, float)):
                continue
            if key in _STOCK_METRICS or key.startswith("avg_") or key.startswith("current_"):
                continue
            p_yr, r_yr = prior.per_year(pv), recent.per_year(rv)
            if p_yr == 0:
                continue
            flow_rows.append({
                "metric": key, "section": section,
                "prior_total": pv, "prior_per_year": p_yr,
                "recent_per_year": r_yr,
                "change": (r_yr - p_yr) / p_yr,
                "structural_break": key in broken_metrics,
            })
    flow_rows.sort(key=lambda r: r["change"])

    pr, rr = prior.ratios(), recent.ratios()
    ratio_rows = []
    for key in sorted(set(pr) | set(rr)):
        pv, rv = pr.get(key), rr.get(key)
        if pv is None or rv is None or pv == 0:
            continue
        ratio_rows.append({
            "ratio": key, "prior": pv, "recent": rv, "change": (rv - pv) / pv,
            "benchmark": BENCHMARKS.get(key),
            "structural_break": key in broken_metrics,
        })

    return {
        "note": note,
        "guards": guards,
        "comparable": not guards,
        "broken_metrics": sorted(broken_metrics),
        "prior_label": prior.label, "recent_label": recent.label,
        "prior_years": prior.years, "recent_years": recent.years,
        "flow": flow_rows,
        "ratios": ratio_rows,
        "gp_prior": _annualise_gp(prior),
        "gp_recent": _annualise_gp(recent),
        "implied_prior_headcount": _implied_headcount(prior, recent),
    }


# Only these GP figures are flows. Shares and per-unit figures are already rates and
# must not be divided by the year count - matching on a "_gp" suffix silently did.
_GP_FLOWS = {"perm_gp", "contract_gp", "total_gp"}


def _annualise_gp(snap: "Snapshot") -> dict:
    return {k: (snap.per_year(v) if k in _GP_FLOWS else v)
            for k, v in snap.gp().items() if v is not None}


# Snapshot ("as of now") metrics. Identical on every OneView regardless of period.
_STOCK_METRICS = {
    "live_jobs", "contractors_out", "current_contractor_weekly_gp", "active_runners_book",
    "biggest_deal_perm", "biggest_deal_contract", "biggest_deal_total",
}


def _implied_headcount(prior: Snapshot, recent: Snapshot) -> dict:
    """What headcount would the prior period need for per-head output to be unchanged?

    OneView shows today's user count on every period, so the historical headcount is
    simply not in this data. Without it, a fall in output cannot be told apart from a
    fall in headcount - and that is the single most consequential ambiguity here, so it
    is quantified rather than glossed over.
    """
    current = recent.raw.get("active_users")
    if not current:
        return {}
    out = {}
    for metric, section in (("cvs_sent", "activity"), ("client_calls", "activity"),
                            ("total_jobs_added", "activity"), ("total_placements", "revenue")):
        pv = getattr(prior, section).get(metric)
        rv = getattr(recent, section).get(metric)
        if not pv or not rv:
            continue
        out[metric] = current * (prior.per_year(pv) / recent.per_year(rv))
    if out:
        vals = list(out.values())
        return {"current_headcount": current, "by_metric": out,
                "range": [min(vals), max(vals)],
                "note": ("If per-head productivity were unchanged, the prior period would have "
                         f"needed roughly {min(vals):.0f}-{max(vals):.0f} heads against today's "
                         f"{current}. This is a HYPOTHESIS generated from the output gap, not a "
                         "measurement. Get headcount by month (docs/06 item 2.5) - until then, "
                         "'the business shrank' and 'the team shrank' are indistinguishable.")}
    return {}


def target_diagnosis(snap: Snapshot) -> dict:
    """Are the targets arithmetic, or aspiration?

    A target set is coherent only if each stage's target is consistent with the ratio
    that connects it to the next. Comparing the ratio a target set *implies* against the
    ratio actually achieved shows whether the plan was ever reachable - and, when the
    two disagree by multiples, says plainly that the shortfall is a planning failure
    rather than an execution failure.
    """
    tg, act = snap.targets, {**snap.activity, **snap.revenue}
    links = [
        ("client_calls", "client_meetings", "client call → meeting", False),
        ("client_meetings", "total_jobs_added", "meeting → jobs", True),
        ("total_jobs_added", "cvs_sent", "CVs per job", True),
        ("cvs_sent", "total_interviews", "CV → interview", False),
        ("total_jobs_added", "total_a_jobs_added", "job → A job", False),
    ]
    rows = []
    for src, dst, label, is_rate in links:
        ts, td = tg.get(src), tg.get(dst)
        as_, ad = act.get(src), act.get(dst)
        if not ts or not td or not as_ or not ad:
            continue
        implied, actual = td / ts, ad / as_
        rows.append({
            "link": label, "implied_by_targets": implied, "actual": actual,
            "factor": implied / actual if actual else None,
            "verdict": ("targets assume better than reality" if implied > actual * 1.15
                        else "targets assume worse than reality" if implied < actual * 0.85
                        else "targets consistent with reality"),
        })

    # Does the revenue target reconcile with the placement target and the real fee?
    fee = snap.r("avg_deal_perm")
    fee_check = None
    if fee and tg.get("perm_placements") and tg.get("perm_billing"):
        implied_billing = tg["perm_placements"] * fee
        fee_check = {
            "target_perm_placements": tg["perm_placements"],
            "actual_avg_perm_fee": fee,
            "implied_billing": implied_billing,
            "target_perm_billing": tg["perm_billing"],
            "consistent": abs(implied_billing - tg["perm_billing"]) / tg["perm_billing"] < 0.1,
        }
    return {"links": rows, "fee_check": fee_check, "attainment": snap.attainment()}


def scenario(snap: Snapshot, cvs_per_job: float | None = None,
             a_job_share: float | None = None, client_calls: float | None = None,
             a_share_of_placements: float = 0.29) -> dict:
    """What a stated change is worth, in placements and GP, at this firm's own ratios.

    Deliberately simple and single-lever: each scenario changes one thing and holds the
    measured conversions constant. That assumption is optimistic for the CV lever (extra
    CVs pushed into weak jobs convert worse than the average CV does) and roughly fair
    for the A-job and calls levers, so the CV number is a ceiling, not a forecast.
    """
    ratios, gp = snap.ratios(), snap.gp()
    base_placements = snap.funnel_placements or 0
    gp_per = gp.get("gp_per_funnel_placement") or 0
    jobs = snap.a("total_jobs_added")
    out = {"baseline_placements": base_placements, "baseline_gp": gp.get("total_gp"),
           "gp_per_funnel_placement": gp_per, "levers": []}

    if cvs_per_job:
        new_cvs = jobs * cvs_per_job
        new_p = new_cvs * (ratios["cv_to_placement"] or 0)
        out["levers"].append({
            "lever": f"CVs per job {ratios['cvs_per_job']:.2f} → {cvs_per_job:.2f}",
            "requires": f"{new_cvs - snap.a('cvs_sent'):,.0f} more CVs on the SAME jobs",
            "placements": new_p, "delta_placements": new_p - base_placements,
            "delta_gp": (new_p - base_placements) * gp_per,
            "caveat": "Ceiling, not forecast: extra CVs land in the weaker jobs, which "
                      "convert below the average CV.",
        })

    if a_job_share:
        # Split the funnel in two using the row-level share of placements that carry an
        # A/A+ priority. Without this the naive placements-per-A-job figure (~1.1) reads
        # as a 110% fill rate, which would say every placement comes from an A-job - and
        # the row data plainly shows it does not.
        a_jobs = snap.a("total_a_jobs_added")
        non_a_jobs = jobs - a_jobs
        a_placements = base_placements * a_share_of_placements
        non_a_placements = base_placements - a_placements
        a_fill = a_placements / a_jobs if a_jobs else 0
        non_a_fill = non_a_placements / non_a_jobs if non_a_jobs else 0

        new_a = jobs * a_job_share
        new_p = new_a * a_fill + (jobs - new_a) * non_a_fill
        out["a_job_economics"] = {
            "a_jobs": a_jobs, "non_a_jobs": non_a_jobs,
            "a_share_of_placements": a_share_of_placements,
            "a_fill_rate": a_fill, "non_a_fill_rate": non_a_fill,
            "advantage": (a_fill / non_a_fill) if non_a_fill else None,
        }
        out["levers"].append({
            "lever": f"A-jobs {ratios['a_job_share_of_jobs']:.1%} → {a_job_share:.1%} of jobs",
            "requires": f"{new_a - a_jobs:,.0f} more jobs qualified to A standard, out of the "
                        "same job intake - a qualification change, not more BD",
            "placements": new_p, "delta_placements": new_p - base_placements,
            "delta_gp": (new_p - base_placements) * gp_per,
            "caveat": f"A-jobs fill at {a_fill:.0%} against {non_a_fill:.0%} for the rest "
                      f"({(a_fill/non_a_fill if non_a_fill else 0):.1f}x). Reclassifying a job "
                      "does not improve it, so the real gain is smaller - this sizes the prize, "
                      "it does not promise it.",
        })

    if client_calls:
        # More calls buy more jobs of the CURRENT mix, not more A-jobs specifically.
        per_meeting = ratios["client_call_to_meeting"] or 0
        jobs_per_meeting = ratios["meeting_to_job"] or 0
        new_jobs = client_calls * per_meeting * jobs_per_meeting
        new_p = new_jobs * (ratios["job_fill_rate"] or 0)
        heads = snap.raw.get("active_users")
        per_head_day = client_calls / heads / 220 if heads else None
        out["levers"].append({
            "lever": f"Client calls {snap.a('client_calls'):,.0f} → {client_calls:,.0f}",
            "requires": (f"{per_head_day:.1f} client calls per head per working day "
                         f"(currently {snap.a('client_calls')/heads/220:.1f})") if heads else "",
            "placements": new_p, "delta_placements": new_p - base_placements,
            "delta_gp": (new_p - base_placements) * gp_per,
            "caveat": "Buys more jobs of the CURRENT quality mix, so it inherits the "
                      f"{ratios['job_fill_rate']:.1%} blended fill rate. The call→meeting→job "
                      "chain has barely moved in four years, so this lever is real but the "
                      "most expensive of the three.",
        })

    return out
