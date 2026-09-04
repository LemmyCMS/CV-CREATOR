"""The ratio engine - see docs/03-ratio-playbook.md.

Three kinds of ratio need three kinds of statistics, and conflating them is the most
common way these numbers mislead:

* PROPORTION - bounded 0..1 (cv_to_interview). Beta-Binomial posterior.
* RATE       - counts per count, unbounded (cvs_per_job). Gamma-Poisson posterior.
* MONETARY   - money per count (gp_per_cv). Fee distributions are skewed, so the mean
               is shrunk toward the parent group and the interval comes from a
               bootstrap over actual fees rather than a normal assumption.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from enum import Enum

from .metrics import MetricSet
from .stats import Posterior, beta_posterior

__all__ = ["RatioKind", "RatioDef", "RATIOS", "RatioResult", "compute_ratios", "decompose_change"]


class RatioKind(str, Enum):
    PROPORTION = "proportion"
    RATE = "rate"
    MONETARY = "monetary"


@dataclass(frozen=True)
class RatioDef:
    ratio_id: str
    label: str
    numerator: str
    denominator: str
    kind: RatioKind
    prior: float          # benchmark prior - see docs/03 section 3. [PRIOR], not a Gentis fact.
    band: str
    higher_is_better: bool = True
    note: str = ""


RATIOS: dict[str, RatioDef] = {r.ratio_id: r for r in [
    # --- core funnel -------------------------------------------------------
    RatioDef("cv_to_interview", "CV → 1st interview", "first_interviews", "cvs_sent",
             RatioKind.PROPORTION, 0.32, "delivery",
             note="The flagship ratio. Quality of the shortlist."),
    RatioDef("interview_to_offer", "1st interview → offer", "offers", "first_interviews",
             RatioKind.PROPORTION, 0.25, "delivery",
             note="Candidate prep and client calibration."),
    RatioDef("offer_to_placement", "Offer → placement", "placements", "offers",
             RatioKind.PROPORTION, 0.80, "delivery",
             note="Closing strength. Counter-offers show up here."),
    RatioDef("cv_to_placement", "CV → placement", "placements", "cvs_sent",
             RatioKind.PROPORTION, 0.10, "delivery",
             note="End-to-end delivery efficiency. ~10% means ~10 CVs per placement."),
    RatioDef("interview_to_placement", "1st interview → placement", "placements",
             "first_interviews", RatioKind.PROPORTION, 0.20, "delivery"),
    RatioDef("first_to_further_interview", "1st → further interview", "further_interviews",
             "first_interviews", RatioKind.PROPORTION, 0.60, "delivery"),
    RatioDef("job_fill_rate", "Job fill rate", "placements", "jobs_taken",
             RatioKind.PROPORTION, 0.22, "bd",
             note="Job qualification quality. Exclusive jobs run 3-5x contingent."),
    RatioDef("cvs_per_job", "CVs per job", "cvs_sent", "jobs_taken",
             RatioKind.RATE, 3.5, "delivery",
             note="Read with cv_to_interview. Rising here + falling there = spraying."),
    # --- business development ---------------------------------------------
    RatioDef("call_to_connect", "Call → connect", "connects", "calls",
             RatioKind.PROPORTION, 0.25, "bd"),
    RatioDef("connect_to_meeting", "Connect → meeting", "client_meetings", "connects",
             RatioKind.PROPORTION, 0.20, "bd"),
    RatioDef("meeting_to_job", "Meeting → job", "jobs_taken", "client_meetings",
             RatioKind.PROPORTION, 0.35, "bd"),
    RatioDef("call_to_job", "Call → job", "jobs_taken", "calls",
             RatioKind.PROPORTION, 0.018, "bd"),
    # --- money -------------------------------------------------------------
    RatioDef("gp_per_cv", "GP per CV sent", "gp", "cvs_sent",
             RatioKind.MONETARY, 1800.0, "money",
             note="Rank markets and clients on this. Combines conversion and fee size."),
    RatioDef("gp_per_job", "GP per job taken", "gp", "jobs_taken",
             RatioKind.MONETARY, 6300.0, "money"),
    RatioDef("gp_per_interview", "GP per 1st interview", "gp", "first_interviews",
             RatioKind.MONETARY, 5600.0, "money"),
]}


@dataclass
class RatioResult:
    ratio_id: str
    label: str
    kind: RatioKind
    numerator: float
    denominator: float
    raw: float | None
    value: float           # shrunk estimate - display this
    lo: float
    hi: float
    prior: float
    measured: bool
    band: str
    note: str = ""

    @property
    def vs_prior(self) -> float | None:
        """Ratio of our estimate to the benchmark. 1.0 = at benchmark."""
        return self.value / self.prior if self.prior else None

    def as_dict(self) -> dict:
        return {
            "ratio_id": self.ratio_id,
            "label": self.label,
            "kind": self.kind.value,
            "numerator": round(self.numerator, 2),
            "denominator": round(self.denominator, 2),
            "raw": round(self.raw, 5) if self.raw is not None else None,
            "value": round(self.value, 5),
            "lo": round(self.lo, 5),
            "hi": round(self.hi, 5),
            "prior": self.prior,
            "vs_prior": round(self.vs_prior, 3) if self.vs_prior else None,
            "measured": self.measured,
            "band": self.band,
            "note": self.note,
        }


def compute_ratios(
    ms: MetricSet,
    priors: dict[str, float] | None = None,
    prior_strength: float = 30.0,
    only: list[str] | None = None,
    seed: int = 19,
) -> dict[str, RatioResult]:
    """Compute every ratio for a metric slice.

    ``priors`` overrides the benchmark defaults - pass the parent group's measured
    ratios here so a consultant shrinks toward their market, not toward an industry
    average. That nesting is what makes per-head numbers trustworthy.
    """
    priors = priors or {}
    results: dict[str, RatioResult] = {}

    for ratio_id, rd in RATIOS.items():
        if only and ratio_id not in only:
            continue
        num = ms.get(rd.numerator)
        den = ms.get(rd.denominator)
        prior = priors.get(ratio_id, rd.prior)

        if rd.kind is RatioKind.PROPORTION:
            # Guard against impossible inputs: a stage cannot exceed its own denominator
            # by much, but split desks and backfilled data do produce num > den.
            capped = min(num, den) if den > 0 else 0.0
            post = beta_posterior(capped, den, prior, prior_strength)
            value, lo, hi, raw = post.rate, post.lo, post.hi, post.raw
            measured = post.is_measured
        elif rd.kind is RatioKind.RATE:
            value, lo, hi, raw, measured = _gamma_rate(num, den, prior, prior_strength, seed)
        else:
            value, lo, hi, raw, measured = _monetary_rate(
                ms.gp_values, den, prior, prior_strength, seed
            )

        results[ratio_id] = RatioResult(
            ratio_id=ratio_id, label=rd.label, kind=rd.kind,
            numerator=num, denominator=den, raw=raw, value=value, lo=lo, hi=hi,
            prior=prior, measured=measured, band=rd.band, note=rd.note,
        )
    return results


def _gamma_rate(num, den, prior, k, seed, draws=4000):
    """Counts-per-count with a Gamma-Poisson posterior.

    Beta is wrong here - 'CVs per job' is not bounded at 1 and routinely exceeds it.
    """
    if den <= 0:
        return prior, 0.0, prior * 3, None, False
    alpha = prior * k + num
    beta = k + den
    mean = alpha / beta
    rng = random.Random(seed)
    draws_v = sorted(rng.gammavariate(alpha, 1.0 / beta) for _ in range(draws))
    lo = draws_v[int(0.05 * draws)]
    hi = draws_v[int(0.95 * draws)]
    return mean, lo, hi, num / den, den >= 10


def _monetary_rate(gp_values, den, prior, k, seed, draws=2000):
    """Money-per-unit-of-effort, with a bootstrap interval.

    Most CVs produce nothing and a few produce a large fee, so the sampling
    distribution is nothing like normal. We bootstrap over a vector of length ``den``
    holding the real fees and zeros elsewhere - which reproduces exactly that shape,
    and honestly shows how wide the uncertainty is on a small desk.
    """
    if den <= 0:
        return prior, 0.0, prior * 3, None, False
    n = int(round(den))
    fees = [g for g in gp_values if g > 0]
    vector = fees + [0.0] * max(n - len(fees), 0)
    raw = sum(fees) / den

    weight = den / (den + k)
    value = weight * raw + (1 - weight) * prior

    rng = random.Random(seed)
    size = len(vector)
    means = []
    for _ in range(draws):
        total = 0.0
        for _ in range(size):
            total += vector[rng.randrange(size)]
        means.append(total / size)
    means.sort()
    lo_raw, hi_raw = means[int(0.05 * draws)], means[int(0.95 * draws)]
    # Shrink the interval bounds the same way as the point estimate, so a thin slice
    # reports a bound near the prior rather than a spuriously precise zero.
    lo = weight * lo_raw + (1 - weight) * prior * 0.5
    hi = weight * hi_raw + (1 - weight) * prior * 1.5
    # 32 CVs and 4 fees is not a measured market. Money-per-effort needs both
    # volume and enough non-zero outcomes before the estimate means anything.
    return value, lo, hi, raw, den >= 50 and len(fees) >= 5


def decompose_change(
    before: dict[str, MetricSet],
    after: dict[str, MetricSet],
    ratio_id: str,
) -> dict:
    """Split a ratio's movement into rate change vs mix change.

    Simpson's paradox is not a curiosity here - it happens whenever volume shifts
    between segments, and it is how a team convinces itself performance fell when every
    segment improved. Never report a YoY ratio move without running this.
    """
    rd = RATIOS[ratio_id]
    segments = sorted(set(before) | set(after))

    def parts(ms_map):
        num = {s: ms_map[s].get(rd.numerator) if s in ms_map else 0.0 for s in segments}
        den = {s: ms_map[s].get(rd.denominator) if s in ms_map else 0.0 for s in segments}
        total_den = sum(den.values())
        rate = {s: (num[s] / den[s] if den[s] else 0.0) for s in segments}
        share = {s: (den[s] / total_den if total_den else 0.0) for s in segments}
        overall = sum(num.values()) / total_den if total_den else 0.0
        return rate, share, overall

    rate0, share0, overall0 = parts(before)
    rate1, share1, overall1 = parts(after)

    # Standard shift-share: hold one factor at its 'before' level to isolate the other.
    rate_effect = sum(share0[s] * (rate1[s] - rate0[s]) for s in segments)
    mix_effect = sum(rate0[s] * (share1[s] - share0[s]) for s in segments)
    interaction = (overall1 - overall0) - rate_effect - mix_effect

    return {
        "ratio_id": ratio_id,
        "before": round(overall0, 5),
        "after": round(overall1, 5),
        "change": round(overall1 - overall0, 5),
        "rate_effect": round(rate_effect, 5),
        "mix_effect": round(mix_effect, 5),
        "interaction": round(interaction, 5),
        "verdict": _mix_verdict(rate_effect, mix_effect),
        "segments": [
            {
                "segment": s,
                "rate_before": round(rate0[s], 4),
                "rate_after": round(rate1[s], 4),
                "share_before": round(share0[s], 4),
                "share_after": round(share1[s], 4),
            }
            for s in segments
        ],
    }


def _mix_verdict(rate_effect: float, mix_effect: float) -> str:
    if abs(mix_effect) > abs(rate_effect) * 1.5:
        direction = "toward harder" if mix_effect < 0 else "toward easier"
        return f"Driven by mix shift {direction} segments, not by performance."
    if abs(rate_effect) > abs(mix_effect) * 1.5:
        return "Driven by real per-segment performance change."
    return "Rate and mix both material - read the segment table before concluding."
