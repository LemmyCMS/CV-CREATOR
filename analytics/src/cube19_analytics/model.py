"""Canonical data model.

Cube19 sits on Bullhorn's entities. We do not copy those entities - we normalise them
into the smallest shape that can answer the questions in docs/03 and docs/05, so that a
Cube19 export, a Bullhorn API pull or a HubSpot pipeline can all land in the same place.

The central idea is the **stage event**: one row every time a submission enters a funnel
stage, with the timestamp. Not "what state is this submission in now" - that loses the
funnel. See docs/01 section 2.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum

__all__ = [
    "Stage",
    "STAGE_ORDER",
    "PlacementType",
    "StageEvent",
    "Placement",
    "Job",
    "Activity",
    "Consultant",
    "Client",
    "Dataset",
]


class Stage(str, Enum):
    """Funnel stages, in order. The strings are the tenant-independent names -
    Gentis's Bullhorn status strings map onto these in ingest.py."""

    INTERNAL_SUBMISSION = "internal_submission"
    CV_SENT = "cv_sent"
    FIRST_INTERVIEW = "first_interview"
    FURTHER_INTERVIEW = "further_interview"
    OFFER = "offer"
    PLACED = "placed"
    REJECTED = "rejected"


STAGE_ORDER: list[Stage] = [
    Stage.INTERNAL_SUBMISSION,
    Stage.CV_SENT,
    Stage.FIRST_INTERVIEW,
    Stage.FURTHER_INTERVIEW,
    Stage.OFFER,
    Stage.PLACED,
]


class PlacementType(str, Enum):
    PERM = "perm"
    CONTRACT = "contract"


@dataclass(frozen=True)
class StageEvent:
    """A submission entering a funnel stage. The atom of the whole system."""

    submission_id: str
    job_id: str
    candidate_id: str
    client_id: str
    consultant_id: str
    market: str
    stage: Stage
    event_date: date
    placement_type: PlacementType = PlacementType.PERM

    @property
    def year(self) -> int:
        return self.event_date.year

    @property
    def month(self) -> str:
        return f"{self.event_date.year:04d}-{self.event_date.month:02d}"


@dataclass(frozen=True)
class Placement:
    placement_id: str
    job_id: str
    client_id: str
    consultant_id: str
    market: str
    start_date: date
    gp: float
    placement_type: PlacementType = PlacementType.PERM
    fell_off: bool = False
    submission_id: str | None = None

    @property
    def year(self) -> int:
        return self.start_date.year

    @property
    def month(self) -> str:
        return f"{self.start_date.year:04d}-{self.start_date.month:02d}"


@dataclass(frozen=True)
class Job:
    job_id: str
    client_id: str
    consultant_id: str
    market: str
    date_opened: date
    date_closed: date | None = None
    exclusive: bool = False
    seniority: str = "mid"
    placement_type: PlacementType = PlacementType.PERM

    @property
    def year(self) -> int:
        return self.date_opened.year


@dataclass(frozen=True)
class Activity:
    """Band-1/2 outreach. ``count`` lets aggregate exports land here too."""

    activity_date: date
    consultant_id: str
    market: str
    action: str  # call | connect | email | client_meeting | linkedin
    client_id: str | None = None
    count: int = 1

    @property
    def year(self) -> int:
        return self.activity_date.year


@dataclass(frozen=True)
class Consultant:
    consultant_id: str
    name: str
    market: str
    start_date: date
    end_date: date | None = None

    def tenure_months_at(self, when: date) -> float:
        if when < self.start_date:
            return 0.0
        return (when - self.start_date).days / 30.44

    def active_in_year(self, year: int) -> bool:
        if self.start_date.year > year:
            return False
        return self.end_date is None or self.end_date.year >= year


@dataclass(frozen=True)
class Client:
    client_id: str
    name: str
    market: str
    geo: str = "BE"
    date_added: date | None = None
    industry: str = ""


@dataclass
class Dataset:
    """Everything the engine needs, in memory. Recruitment histories are small -
    a decade of a 100-head agency is a few hundred thousand rows."""

    stage_events: list[StageEvent] = field(default_factory=list)
    placements: list[Placement] = field(default_factory=list)
    jobs: list[Job] = field(default_factory=list)
    activities: list[Activity] = field(default_factory=list)
    consultants: list[Consultant] = field(default_factory=list)
    clients: list[Client] = field(default_factory=list)

    # -- lookups -------------------------------------------------------------
    def consultant(self, consultant_id: str) -> Consultant | None:
        return next((c for c in self.consultants if c.consultant_id == consultant_id), None)

    def client(self, client_id: str) -> Client | None:
        return next((c for c in self.clients if c.client_id == client_id), None)

    @property
    def markets(self) -> list[str]:
        return sorted({j.market for j in self.jobs} | {e.market for e in self.stage_events})

    @property
    def years(self) -> list[int]:
        years = {p.year for p in self.placements} | {e.year for e in self.stage_events}
        years |= {j.year for j in self.jobs}
        return sorted(years)

    @property
    def horizon(self) -> date:
        """The last date the data actually covers.

        Not the same as the last year present: a placement with a start date three
        months in the future creates a 'year' with almost nothing in it.
        """
        candidates = (
            [p.start_date for p in self.placements]
            + [e.event_date for e in self.stage_events]
            + [j.date_opened for j in self.jobs]
        )
        return max(candidates) if candidates else date.today()

    @property
    def complete_years(self) -> list[int]:
        """Years with a full twelve months of data.

        Trend and momentum must only ever be computed over these. A partial year at the
        edge reads as a collapse and will otherwise flip a growing market to 'Exit' -
        which is the single easiest way for this whole model to give catastrophic advice.
        """
        horizon = self.horizon
        # A trailing year is complete only if the data runs to the end of December, and
        # a leading year only if it starts in January - both edges can be stubs.
        first = min(self.years) if self.years else horizon.year
        earliest = min(
            [p.start_date for p in self.placements]
            + [e.event_date for e in self.stage_events]
            + [j.date_opened for j in self.jobs],
            default=date(first, 1, 1),
        )
        years = []
        for y in self.years:
            if y == horizon.year and horizon.month < 12:
                continue
            if y == earliest.year and earliest.month > 1:
                continue
            years.append(y)
        return years

    @property
    def partial_years(self) -> list[int]:
        return [y for y in self.years if y not in set(self.complete_years)]

    def summary(self) -> dict:
        return {
            "stage_events": len(self.stage_events),
            "placements": len(self.placements),
            "jobs": len(self.jobs),
            "activities": len(self.activities),
            "consultants": len(self.consultants),
            "clients": len(self.clients),
            "markets": len(self.markets),
            "years": self.years,
            "total_gp": round(sum(p.gp for p in self.placements), 2),
        }
