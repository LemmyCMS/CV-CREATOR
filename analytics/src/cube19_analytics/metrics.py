"""Metric computation - the counting layer.

Everything the dashboard shows is a count over a filtered slice of the dataset. Keeping
that in one place means the funnel, the leaderboard and the market ranking can never
disagree about what a "CV sent" is.

Metric ids match docs/02-metric-dictionary.md exactly.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .model import Dataset, PlacementType, Stage

__all__ = ["Slice", "MetricSet", "compute_metrics", "group_by"]

_ACTIVITY_METRICS = {
    "calls": "call",
    "connects": "connect",
    "emails": "email",
    "client_meetings": "client_meeting",
    "linkedin_touches": "linkedin",
}

_STAGE_METRICS = {
    "internal_submissions": Stage.INTERNAL_SUBMISSION,
    "cvs_sent": Stage.CV_SENT,
    "first_interviews": Stage.FIRST_INTERVIEW,
    "further_interviews": Stage.FURTHER_INTERVIEW,
    "offers": Stage.OFFER,
}


@dataclass(frozen=True)
class Slice:
    """A filter over the dataset. Every field is optional; None means 'all'.

    This is the 'slice and dice' Cube19 offers, expressed as one object so a slice can
    be passed around, serialised and compared.
    """

    market: str | None = None
    consultant_id: str | None = None
    client_id: str | None = None
    year: int | None = None
    placement_type: PlacementType | None = None
    date_from: date | None = None
    date_to: date | None = None

    def label(self) -> str:
        parts = [
            v if isinstance(v, str) else str(v)
            for v in (self.market, self.consultant_id, self.client_id, self.year)
            if v is not None
        ]
        return " / ".join(parts) or "All"

    def _in_window(self, when: date, year: int) -> bool:
        if self.year is not None and year != self.year:
            return False
        if self.date_from is not None and when < self.date_from:
            return False
        if self.date_to is not None and when > self.date_to:
            return False
        return True

    def match_stage_event(self, e) -> bool:
        return (
            (self.market is None or e.market == self.market)
            and (self.consultant_id is None or e.consultant_id == self.consultant_id)
            and (self.client_id is None or e.client_id == self.client_id)
            and (self.placement_type is None or e.placement_type == self.placement_type)
            and self._in_window(e.event_date, e.year)
        )

    def match_placement(self, p) -> bool:
        return (
            (self.market is None or p.market == self.market)
            and (self.consultant_id is None or p.consultant_id == self.consultant_id)
            and (self.client_id is None or p.client_id == self.client_id)
            and (self.placement_type is None or p.placement_type == self.placement_type)
            and self._in_window(p.start_date, p.year)
        )

    def match_job(self, j) -> bool:
        return (
            (self.market is None or j.market == self.market)
            and (self.consultant_id is None or j.consultant_id == self.consultant_id)
            and (self.client_id is None or j.client_id == self.client_id)
            and (self.placement_type is None or j.placement_type == self.placement_type)
            and self._in_window(j.date_opened, j.year)
        )

    def match_activity(self, a) -> bool:
        return (
            (self.market is None or a.market == self.market)
            and (self.consultant_id is None or a.consultant_id == self.consultant_id)
            and (self.client_id is None or a.client_id == self.client_id)
            and self._in_window(a.activity_date, a.year)
        )


@dataclass
class MetricSet:
    """Counts for one slice, plus the raw GP values behind them.

    ``gp_values`` is kept because fee distributions are skewed enough that the mean is a
    poor summary - the bootstrap in ratios.py needs the actual values, not the total.
    """

    slice: Slice
    counts: dict[str, float]
    gp_values: list[float]

    def __getitem__(self, key: str) -> float:
        return self.counts.get(key, 0.0)

    def get(self, key: str, default: float = 0.0) -> float:
        return self.counts.get(key, default)

    def as_dict(self) -> dict:
        return {"slice": self.slice.label(), **{k: round(v, 4) for k, v in self.counts.items()}}


def compute_metrics(ds: Dataset, sl: Slice | None = None) -> MetricSet:
    sl = sl or Slice()
    counts: dict[str, float] = {k: 0.0 for k in _STAGE_METRICS}
    counts.update({k: 0.0 for k in _ACTIVITY_METRICS})

    for e in ds.stage_events:
        if not sl.match_stage_event(e):
            continue
        for metric_id, stage in _STAGE_METRICS.items():
            if e.stage is stage:
                counts[metric_id] += 1

    for a in ds.activities:
        if not sl.match_activity(a):
            continue
        for metric_id, action in _ACTIVITY_METRICS.items():
            if a.action == action:
                counts[metric_id] += a.count

    jobs = [j for j in ds.jobs if sl.match_job(j)]
    counts["jobs_taken"] = float(len(jobs))
    counts["jobs_exclusive"] = float(sum(1 for j in jobs if j.exclusive))

    placements = [p for p in ds.placements if sl.match_placement(p)]
    counts["placements"] = float(len(placements))
    counts["fall_offs"] = float(sum(1 for p in placements if p.fell_off))
    gp_values = [p.gp for p in placements if not p.fell_off]
    counts["gp"] = float(sum(gp_values))
    counts["avg_fee"] = counts["gp"] / len(gp_values) if gp_values else 0.0
    counts["outreach_total"] = counts["calls"] + counts["emails"] + counts["linkedin_touches"]

    heads = _active_heads(ds, sl)
    counts["active_consultants"] = float(heads)
    counts["gp_per_head"] = counts["gp"] / heads if heads else 0.0

    return MetricSet(slice=sl, counts=counts, gp_values=gp_values)


def _active_heads(ds: Dataset, sl: Slice) -> int:
    """Headcount for the slice.

    Without this every per-head and YoY comparison silently confounds 'the market grew'
    with 'we put more people on it' - see docs/06 item 2.5.
    """
    if sl.consultant_id is not None:
        return 1
    year = sl.year
    heads = [
        c
        for c in ds.consultants
        if (sl.market is None or c.market == sl.market)
        and (year is None or c.active_in_year(year))
    ]
    return len(heads)


def group_by(
    ds: Dataset,
    dimension: str,
    base: Slice | None = None,
) -> dict[str, MetricSet]:
    """Compute metrics for every value of ``dimension``.

    dimension: 'market' | 'consultant' | 'client' | 'year'
    """
    base = base or Slice()
    out: dict[str, MetricSet] = {}

    if dimension == "market":
        for market in ds.markets:
            sl = _replace(base, market=market)
            out[market] = compute_metrics(ds, sl)
    elif dimension == "consultant":
        for c in ds.consultants:
            if base.market is not None and c.market != base.market:
                continue
            sl = _replace(base, consultant_id=c.consultant_id)
            out[c.consultant_id] = compute_metrics(ds, sl)
    elif dimension == "client":
        for c in ds.clients:
            if base.market is not None and c.market != base.market:
                continue
            sl = _replace(base, client_id=c.client_id)
            out[c.client_id] = compute_metrics(ds, sl)
    elif dimension == "year":
        for year in ds.years:
            sl = _replace(base, year=year)
            out[str(year)] = compute_metrics(ds, sl)
    else:
        raise ValueError(f"unknown dimension: {dimension}")

    return out


def _replace(sl: Slice, **kwargs) -> Slice:
    fields = {
        "market": sl.market,
        "consultant_id": sl.consultant_id,
        "client_id": sl.client_id,
        "year": sl.year,
        "placement_type": sl.placement_type,
        "date_from": sl.date_from,
        "date_to": sl.date_to,
    }
    fields.update(kwargs)
    return Slice(**fields)
