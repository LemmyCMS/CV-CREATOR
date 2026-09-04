"""Small-sample statistics for conversion ratios.

Recruitment funnel data is sparse: a consultant may have 4 CVs and 1 placement, a
market 12 CVs and 0. Raw percentages on those counts are noise, and ranking on them
is how you end up putting three heads onto a market that got lucky twice.

Everything here treats a conversion as Binomial with a Beta prior and reports a
posterior with an interval, so "we don't know yet" is a result the system can express.

Pure standard library on purpose - this has to run wherever the data lands.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

__all__ = [
    "Posterior",
    "beta_posterior",
    "beta_ppf",
    "regularized_incomplete_beta",
    "prob_greater",
    "sample_size_for",
]

_MAX_ITER = 300
_EPS = 1e-12


def _log_beta(a: float, b: float) -> float:
    return math.lgamma(a) + math.lgamma(b) - math.lgamma(a + b)


def _betacf(a: float, b: float, x: float) -> float:
    """Continued-fraction expansion for the incomplete beta (Lentz's method)."""
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < _EPS:
        d = _EPS
    d = 1.0 / d
    h = d
    for m in range(1, _MAX_ITER + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < _EPS:
            d = _EPS
        c = 1.0 + aa / c
        if abs(c) < _EPS:
            c = _EPS
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < _EPS:
            d = _EPS
        c = 1.0 + aa / c
        if abs(c) < _EPS:
            c = _EPS
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 1e-14:
            break
    return h


def regularized_incomplete_beta(a: float, b: float, x: float) -> float:
    """I_x(a, b) - the Beta CDF. Accurate enough for interval work."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    front = math.exp(a * math.log(x) + b * math.log1p(-x) - _log_beta(a, b))
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - front * _betacf(b, a, 1.0 - x) / b


def beta_ppf(a: float, b: float, q: float) -> float:
    """Inverse Beta CDF by bisection. Monotone, so bisection is safe and exact enough."""
    if q <= 0.0:
        return 0.0
    if q >= 1.0:
        return 1.0
    lo, hi = 0.0, 1.0
    for _ in range(200):
        mid = (lo + hi) / 2.0
        if regularized_incomplete_beta(a, b, mid) < q:
            lo = mid
        else:
            hi = mid
        if hi - lo < 1e-12:
            break
    return (lo + hi) / 2.0


@dataclass(frozen=True)
class Posterior:
    """A conversion rate we have partial information about.

    ``rate`` is the shrunk (posterior mean) estimate - use this for display.
    ``raw`` is the naive successes/trials - use it only to show people the difference.
    ``lo``/``hi`` bound a credible interval; ``lo`` is what you rank on.
    """

    successes: float
    trials: float
    alpha: float
    beta: float
    rate: float
    raw: float | None
    lo: float
    hi: float
    credibility: float

    @property
    def is_measured(self) -> bool:
        """True when there is enough data for the estimate to mean anything.

        The test is interval width, not trial count: 20 trials on a rare event tells
        you almost nothing, while 20 on a common one can be informative.
        """
        return self.trials >= 10 and (self.hi - self.lo) < 0.35

    def as_dict(self) -> dict:
        return {
            "successes": self.successes,
            "trials": self.trials,
            "rate": self.rate,
            "raw": self.raw,
            "lo": self.lo,
            "hi": self.hi,
            "measured": self.is_measured,
        }


def beta_posterior(
    successes: float,
    trials: float,
    prior_rate: float,
    prior_strength: float = 30.0,
    credibility: float = 0.90,
) -> Posterior:
    """Shrink an observed conversion toward ``prior_rate``.

    ``prior_strength`` is how many observations the prior is worth. At the default 30,
    a consultant needs ~30 CVs before their own numbers outweigh the group's - which
    matches how long it actually takes to form a view of someone.
    """
    prior_rate = min(max(prior_rate, 1e-6), 1.0 - 1e-6)
    alpha = prior_rate * prior_strength + successes
    beta = (1.0 - prior_rate) * prior_strength + (trials - successes)
    alpha = max(alpha, 1e-6)
    beta = max(beta, 1e-6)
    tail = (1.0 - credibility) / 2.0
    return Posterior(
        successes=successes,
        trials=trials,
        alpha=alpha,
        beta=beta,
        rate=alpha / (alpha + beta),
        raw=(successes / trials) if trials > 0 else None,
        lo=beta_ppf(alpha, beta, tail),
        hi=beta_ppf(alpha, beta, 1.0 - tail),
        credibility=credibility,
    )


def prob_greater(a: Posterior, b: Posterior, draws: int = 20000, seed: int = 19) -> float:
    """P(rate of a > rate of b), by Monte Carlo over the two posteriors.

    Read it as a betting number. Anything in 0.4-0.6 means the data cannot tell them
    apart and the decision belongs on other grounds.
    """
    rng = random.Random(seed)
    wins = 0
    for _ in range(draws):
        if rng.betavariate(a.alpha, a.beta) > rng.betavariate(b.alpha, b.beta):
            wins += 1
    return wins / draws


def sample_size_for(
    baseline: float, detectable: float, confidence: float = 0.90, power: float = 0.80
) -> int:
    """Trials needed to distinguish ``detectable`` from ``baseline``.

    This is what turns "we think that market might be good" into a bounded experiment:
    send this many CVs, then decide. Normal approximation - fine at these magnitudes.
    """
    if baseline <= 0 or detectable <= 0 or abs(detectable - baseline) < 1e-9:
        return 0
    z_alpha = _norm_ppf(1.0 - (1.0 - confidence) / 2.0)
    z_beta = _norm_ppf(power)
    p_bar = (baseline + detectable) / 2.0
    numerator = (
        z_alpha * math.sqrt(2 * p_bar * (1 - p_bar))
        + z_beta * math.sqrt(baseline * (1 - baseline) + detectable * (1 - detectable))
    ) ** 2
    return int(math.ceil(numerator / (detectable - baseline) ** 2))


def _norm_ppf(q: float) -> float:
    """Inverse standard normal CDF (Acklam's rational approximation)."""
    if not 0.0 < q < 1.0:
        raise ValueError("q must be in (0, 1)")
    a = [-3.969683028665376e01, 2.209460984245205e02, -2.759285104469687e02,
         1.383577518672690e02, -3.066479806614716e01, 2.506628277459239e00]
    b = [-5.447609879822406e01, 1.615858368580409e02, -1.556989798598866e02,
         6.680131188771972e01, -1.328068155288572e01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e00,
         -2.549732539343734e00, 4.374664141464968e00, 2.938163982698783e00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e00,
         3.754408661907416e00]
    p_low, p_high = 0.02425, 1 - 0.02425
    if q < p_low:
        s = math.sqrt(-2 * math.log(q))
        return (((((c[0] * s + c[1]) * s + c[2]) * s + c[3]) * s + c[4]) * s + c[5]) / (
            (((d[0] * s + d[1]) * s + d[2]) * s + d[3]) * s + 1)
    if q > p_high:
        s = math.sqrt(-2 * math.log(1 - q))
        return -(((((c[0] * s + c[1]) * s + c[2]) * s + c[3]) * s + c[4]) * s + c[5]) / (
            (((d[0] * s + d[1]) * s + d[2]) * s + d[3]) * s + 1)
    s = q - 0.5
    r = s * s
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * s / (
        ((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)
