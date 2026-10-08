"""Warm talent pool: how many candidates to keep warm, and proof they get sent.

Two jobs, both lessons from Gentis:

1. **Size the pool.** Being able to send 3 strong CVs within 48 hours of a job landing
   means holding enough *warm* candidates per profile type that, after the ones who do
   not fit and the ones not available this week drop out, three remain. Worked
   backwards that is ~30 per profile type for contract and ~50 for perm.

2. **Make the pool earn its keep.** Gentis added 11,876 candidates in 12 months and 85%
   were never sent anywhere (80% over three years). Sourcing volume that produces nothing.
   A warm pool is only worth its upkeep if it flows into CVs, so the leak checks here
   are the other half of the target, not an add-on: every warm, available candidate that
   matches an open job and has not been sent is surfaced by name.

The fit and availability rates are ``[PRIOR]`` - educated guesses, not Gentis data.
Measure them in the first two months (of the warm profiles called per job, how many
fitted, how many were free) and replace them; the pool targets move with them.

Warm means all three: spoken to within ``warm_days``, CV on file, GDPR consent recorded.
A name in the database is not warm.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

from .model import Job, PlacementType, Stage, StageEvent

__all__ = [
    "PoolAssumptions",
    "Candidate",
    "warm_target",
    "capacity",
    "pool_plan",
    "pool_health",
    "send_leaks",
    "cv_counts",
]

GENTIS_NEVER_SENT_12M = 0.85   # 10,104 of 11,876 new candidates, Sep 2025-Sep 2026
GENTIS_NEVER_SENT_3Y = 0.80    # 77,584 of 96,955, Sep 2022-Sep 2025


@dataclass(frozen=True)
class PoolAssumptions:
    cvs_per_job: float = 3.0            # Gentis sends 1.99; 3.00 = +129 placements in scenario()
    sla_days: int = 2                   # job opened -> third CV sent
    fit_rate: float = 0.50              # [PRIOR] share of warm profiles that fit a given brief
    avail_contract: float = 0.20        # [PRIOR] freelancers free within the start window
    avail_perm: float = 0.12            # [PRIOR] perm candidates actively open to move
    reuse: float = 0.50                 # [PRIOR] share of shortlist reusable on a 2nd same-profile job
    warm_days: int = 90                 # last real conversation within this many days
    contract_window_days: int = 42      # contract "ready" = free within 6 weeks
    candidate_touches_per_day: float = 4.0  # [PRIOR] per worked day; the rest of the calls are BD
    worked_days_per_month_fte: float = 22.0
    refresh_days: int = 75              # every warm profile re-contacted this often
    never_sent_grace_days: int = 30     # a new candidate should be sent somewhere within this
    never_sent_ceiling: float = 0.50    # alarm above this; Gentis ran at 0.85

    def availability(self, ptype: PlacementType) -> float:
        return self.avail_contract if ptype == PlacementType.CONTRACT else self.avail_perm


@dataclass(frozen=True)
class Candidate:
    """The fields the CRM must capture for this to work. Every one is required."""

    candidate_id: str
    market: str
    profile: str
    placement_type: PlacementType
    added: date
    last_contact: date | None = None
    available_from: date | None = None   # contract: current mission end date
    open_to_move: bool = False           # perm: actively looking, confirmed in conversation
    cv_on_file: bool = False
    consent: bool = False

    def is_warm(self, as_of: date, a: PoolAssumptions) -> bool:
        return (self.consent and self.cv_on_file and self.last_contact is not None
                and (as_of - self.last_contact).days <= a.warm_days)

    def is_ready(self, as_of: date, a: PoolAssumptions) -> bool:
        """Warm and sendable now: the subset that answers a job inside the SLA."""
        if not self.is_warm(as_of, a):
            return False
        if self.placement_type == PlacementType.CONTRACT:
            return (self.available_from is not None
                    and self.available_from <= as_of + timedelta(days=a.contract_window_days))
        return self.open_to_move


# -- sizing ---------------------------------------------------------------------

def warm_target(ptype: PlacementType, concurrent_jobs: int = 1,
                a: PoolAssumptions = PoolAssumptions()) -> dict:
    """Warm profiles needed for one profile type to meet the CV SLA.

    A second simultaneous job of the same profile does not double the need: part of the
    first shortlist can go to it too (``reuse``).
    """
    k = max(1, concurrent_jobs)
    effective_jobs = 1 + (k - 1) * (1 - a.reuse)
    yield_per_profile = a.fit_rate * a.availability(ptype)
    needed = math.ceil(a.cvs_per_job * effective_jobs / yield_per_profile)
    return {
        "placement_type": ptype.value,
        "concurrent_jobs": k,
        "warm_needed": needed,
        "ready_needed": math.ceil(a.cvs_per_job * effective_jobs / a.fit_rate),
        "math": (f"{a.cvs_per_job:g} CVs x {effective_jobs:g} jobs / "
                 f"({a.fit_rate:.0%} fit x {a.availability(ptype):.0%} available)"),
    }


def capacity(fte: float, a: PoolAssumptions = PoolAssumptions()) -> int:
    """Warm relationships a team can actually keep warm.

    Every profile has to be re-contacted each ``refresh_days``; candidate time per worked
    day is finite. A pool bigger than this goes cold however it is targeted.
    """
    worked_days = fte * a.worked_days_per_month_fte * a.refresh_days / 30.44
    return int(worked_days * a.candidate_touches_per_day)


def pool_plan(profiles: list[dict], fte: float,
              a: PoolAssumptions = PoolAssumptions()) -> dict:
    """Targets per profile and market, checked against team capacity.

    ``profiles``: [{"market", "profile", "placement_type": "contract"|"perm",
    "concurrent_jobs": int}].
    """
    rows, by_market = [], defaultdict(int)
    for p in profiles:
        t = warm_target(PlacementType(p["placement_type"]), p.get("concurrent_jobs", 1), a)
        rows.append({"market": p["market"], "profile": p["profile"], **t})
        by_market[p["market"]] += t["warm_needed"]
    total = sum(by_market.values())
    cap = capacity(fte, a)
    return {
        "profiles": rows,
        "markets": [{"market": m, "warm_needed": n} for m, n in by_market.items()],
        "total_warm_needed": total,
        "capacity": cap,
        "fits_capacity": total <= cap,
        "verdict": (f"{total} warm profiles needed, team can hold {cap}."
                    + ("" if total <= cap else
                       " Over capacity: open fewer markets or profile types, not a bigger"
                       " cold database.")),
    }


# -- measuring ------------------------------------------------------------------

def _cv_sends(events: list[StageEvent]) -> dict[str, list[StageEvent]]:
    sends = defaultdict(list)
    for e in events:
        if e.stage == Stage.CV_SENT:
            sends[e.candidate_id].append(e)
    return sends


def pool_health(candidates: list[Candidate], plan: dict, as_of: date,
                a: PoolAssumptions = PoolAssumptions()) -> list[dict]:
    """Warm and ready counts per profile, against target."""
    warm, ready = defaultdict(int), defaultdict(int)
    for c in candidates:
        key = (c.market, c.profile)
        warm[key] += c.is_warm(as_of, a)
        ready[key] += c.is_ready(as_of, a)
    out = []
    for p in plan["profiles"]:
        key = (p["market"], p["profile"])
        w, target = warm[key], p["warm_needed"]
        status = "ok" if w >= target else ("building" if w >= 0.5 * target else "thin")
        out.append({"market": key[0], "profile": key[1], "warm": w, "warm_target": target,
                    "ready": ready[key], "ready_target": p["ready_needed"],
                    "gap": max(0, target - w), "status": status})
    return out


def send_leaks(candidates: list[Candidate], events: list[StageEvent], jobs: list[Job],
               as_of: date, a: PoolAssumptions = PoolAssumptions()) -> dict:
    """The Gentis failure, measured: candidates kept warm but never put forward."""
    sends = _cv_sends(events)

    # 1. Never-sent rate on candidates old enough to have been sent somewhere.
    cohort = [c for c in candidates
              if a.never_sent_grace_days <= (as_of - c.added).days <= 365]
    never = [c for c in cohort if not any(e.event_date <= as_of for e in sends[c.candidate_id])]
    rate = len(never) / len(cohort) if cohort else None

    # 2. Ready candidates matching an open job they have not been sent to. The action list.
    open_jobs = [j for j in jobs
                 if j.date_opened <= as_of and (j.date_closed is None or j.date_closed > as_of)]
    sent_to = {(e.candidate_id, e.job_id) for es in sends.values() for e in es}
    idle = []
    for c in candidates:
        if not c.is_ready(as_of, a):
            continue
        matches = [j.job_id for j in open_jobs
                   if j.market == c.market and j.profile == c.profile
                   and j.placement_type == c.placement_type
                   and (c.candidate_id, j.job_id) not in sent_to]
        if matches:
            last = max((e.event_date for e in sends[c.candidate_id]), default=None)
            idle.append({"candidate_id": c.candidate_id, "market": c.market,
                         "profile": c.profile, "open_jobs": matches,
                         "days_since_last_send": (as_of - last).days if last else None})
    idle.sort(key=lambda r: -(r["days_since_last_send"] or 10_000))

    # 3. Open jobs past the SLA without enough CVs.
    per_job = defaultdict(list)
    for es in sends.values():
        for e in es:
            per_job[e.job_id].append(e.event_date)
    breaches = []
    for j in open_jobs:
        dates = sorted(d for d in per_job[j.job_id] if d <= as_of)
        age = (as_of - j.date_opened).days
        if age > a.sla_days and len(dates) < a.cvs_per_job:
            breaches.append({"job_id": j.job_id, "market": j.market, "profile": j.profile,
                             "age_days": age, "cvs_sent": len(dates)})

    # 4. Days to the Nth CV on jobs that got there - the responsiveness number.
    n = math.ceil(a.cvs_per_job)
    ttn = sorted((sorted(per_job[j.job_id])[n - 1] - j.date_opened).days
                 for j in jobs if len(per_job[j.job_id]) >= n)

    return {
        "never_sent_rate": rate,
        "never_sent_count": len(never),
        "never_sent_cohort": len(cohort),
        "never_sent_alarm": rate is not None and rate > a.never_sent_ceiling,
        "gentis_benchmark": GENTIS_NEVER_SENT_12M,
        "ready_not_sent": idle,
        "sla_breaches": breaches,
        "median_days_to_third_cv": ttn[len(ttn) // 2] if ttn else None,
    }


def cv_counts(events: list[StageEvent], jobs: list[Job], start: date, end: date) -> dict:
    """CVs sent vs unique CVs sent - the anchor number is the second one.

    * ``cvs_sent``: every CV that went out, qualified job or not. Spray-and-pray counts here.
    * ``cvs_on_qualified``: CVs sent to qualified jobs only.
    * ``unique_cvs_sent``: distinct candidates sent to a qualified job in the window. A
      candidate sent to three qualified jobs counts once - at the same company or another.

    Gentis, Sep 2025-Sep 2026: 24,885 total CVs (17,901 of them spec), 6,984 on jobs,
    3,920 unique by candidate - 16% of everything sent.
    """
    qualified = {j.job_id for j in jobs if j.qualified}
    sends = [e for e in events if e.stage == Stage.CV_SENT and start <= e.event_date <= end]
    on_q = [e for e in sends if e.job_id in qualified]
    unique = {e.candidate_id for e in on_q}
    return {
        "cvs_sent": len(sends),
        "cvs_on_qualified": len(on_q),
        "unique_cvs_sent": len(unique),
        "unique_share": len(unique) / len(sends) if sends else None,
    }
