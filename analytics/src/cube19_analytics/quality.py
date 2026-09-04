"""Data-quality checks that decide which numbers are safe to build targets on.

Statistical volume is not the same as reliability. A firm can have 111,000 logged calls
and still have unusable call data, because a third of the team never logged and the rest
logged in round numbers on a Friday. Volume tests cannot see that; these can.

This module exists because docs/04 says "anchor the target at the earliest *reliably
measured* stage" - and something has to decide what reliable means.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from .model import Dataset, Stage

__all__ = ["QualityFinding", "assess", "reliable_metrics"]

_ACTIVITY_ACTIONS = {"call": "calls", "connect": "connects",
                     "email": "emails", "client_meeting": "client_meetings"}


@dataclass
class QualityFinding:
    metric: str
    reliable: bool
    severity: str          # ok | warn | fail
    detail: str
    coverage: float | None = None

    def as_dict(self) -> dict:
        return {"metric": self.metric, "reliable": self.reliable, "severity": self.severity,
                "detail": self.detail,
                "coverage": round(self.coverage, 3) if self.coverage is not None else None}


def assess(ds: Dataset, min_coverage: float = 0.80) -> list[QualityFinding]:
    """Check every metric band for the failure modes that actually occur."""
    findings: list[QualityFinding] = []
    findings.extend(_activity_coverage(ds, min_coverage))
    findings.extend(_funnel_integrity(ds))
    findings.extend(_gp_integrity(ds))
    return findings


def _active_months(ds: Dataset) -> dict[str, set[tuple[int, int]]]:
    """Months in which each consultant was employed - the denominator for coverage."""
    horizon = max(
        [p.start_date for p in ds.placements] + [e.event_date for e in ds.stage_events]
        or [date.today()]
    )
    out: dict[str, set[tuple[int, int]]] = defaultdict(set)
    for c in ds.consultants:
        end = c.end_date or horizon
        y, m = c.start_date.year, c.start_date.month
        while (y, m) <= (end.year, end.month):
            out[c.consultant_id].add((y, m))
            m += 1
            if m > 12:
                y, m = y + 1, 1
    return out


def _activity_coverage(ds: Dataset, min_coverage: float) -> list[QualityFinding]:
    """What share of employed consultant-months carry any logged activity?

    Under-logging is not random - it concentrates in the people who log nothing at all.
    Averaging across the team hides that, so we measure coverage, not volume.
    """
    findings = []
    employed = _active_months(ds)
    total_months = sum(len(v) for v in employed.values())
    if not total_months:
        return [QualityFinding(a, False, "fail", "No consultant records - coverage unknowable")
                for a in _ACTIVITY_ACTIONS.values()]

    logged: dict[str, set[tuple[int, int]]] = defaultdict(set)
    for a in ds.activities:
        if a.count > 0:
            logged[a.action].add((a.consultant_id, a.activity_date.year, a.activity_date.month))

    for action, metric in _ACTIVITY_ACTIONS.items():
        covered = sum(
            1
            for consultant_id, months in employed.items()
            for (y, m) in months
            if (consultant_id, y, m) in logged[action]
        )
        coverage = covered / total_months
        silent = [
            c.consultant_id for c in ds.consultants
            if employed[c.consultant_id]
            and not any((c.consultant_id, y, m) in logged[action] for (y, m) in employed[c.consultant_id])
        ]
        if coverage >= min_coverage:
            findings.append(QualityFinding(
                metric, True, "ok",
                f"Logged in {coverage:.0%} of employed consultant-months", coverage))
        else:
            severity = "fail" if coverage < 0.5 else "warn"
            detail = (f"Only {coverage:.0%} of employed consultant-months have any {metric} logged"
                      + (f"; {len(silent)} consultant(s) never logged any" if silent else "")
                      + ". Ratios built on this measure logging habits, not performance.")
            findings.append(QualityFinding(metric, False, severity, detail, coverage))
    return findings


def _funnel_integrity(ds: Dataset) -> list[QualityFinding]:
    """Does the funnel behave like a funnel?

    Later stages exceeding earlier ones means the status map is wrong or stage events
    are being recorded from current status rather than transitions - both of which
    silently invert every ratio downstream.
    """
    findings = []
    counts = defaultdict(int)
    for e in ds.stage_events:
        counts[e.stage] += 1

    cvs = counts[Stage.CV_SENT]
    if cvs == 0:
        return [QualityFinding("cvs_sent", False, "fail",
                               "No CV-sent events. The status map does not match this tenant "
                               "(docs/06 item 1.1) - fix it before reading any delivery ratio.")]

    findings.append(QualityFinding("cvs_sent", True, "ok", f"{cvs:,} CV-sent events"))

    ordered = [(Stage.CV_SENT, "cvs_sent"), (Stage.FIRST_INTERVIEW, "first_interviews"),
               (Stage.OFFER, "offers")]
    for (earlier, e_name), (later, l_name) in zip(ordered, ordered[1:]):
        if counts[later] > counts[earlier]:
            findings.append(QualityFinding(
                l_name, False, "fail",
                f"{l_name} ({counts[later]:,}) exceeds {e_name} ({counts[earlier]:,}) - "
                "stages are not being recorded as transitions, or the status map is wrong."))

    # Submissions that appear at a later stage without ever passing the earlier one
    seen: dict[str, set] = defaultdict(set)
    for e in ds.stage_events:
        seen[e.submission_id].add(e.stage)
    skipped = sum(1 for stages in seen.values()
                  if Stage.FIRST_INTERVIEW in stages and Stage.CV_SENT not in stages)
    if skipped and skipped / max(len(seen), 1) > 0.02:
        findings.append(QualityFinding(
            "cv_to_interview", False, "warn",
            f"{skipped:,} submissions reached interview with no CV-sent event. "
            "Cohort ratios will understate conversion; check for backfilled records."))

    return findings


def _gp_integrity(ds: Dataset) -> list[QualityFinding]:
    if not ds.placements:
        return [QualityFinding("gp", False, "fail", "No placements loaded")]
    zero = sum(1 for p in ds.placements if p.gp <= 0)
    share = zero / len(ds.placements)
    if share > 0.10:
        return [QualityFinding("gp", False, "fail" if share > 0.3 else "warn",
                               f"{zero}/{len(ds.placements)} placements carry zero GP - check the "
                               "fee mapping and the perm/contract rules (docs/06 item 1.5).",
                               1 - share)]
    fees = [p.gp for p in ds.placements if p.gp > 0]
    median = statistics.median(fees)
    # A handful of enormous fees is normal and important; a *majority* of outliers means
    # perm lump sums and contract accruals have been added together.
    outliers = sum(1 for f in fees if f > median * 8)
    findings = [QualityFinding("gp", True, "ok",
                               f"{len(fees)} placements, median fee {median:,.0f}", 1 - share)]
    if outliers / len(fees) > 0.05:
        findings.append(QualityFinding(
            "avg_fee", False, "warn",
            f"{outliers} fees exceed 8x the median. Perm and contract GP may be mixed - "
            "segment by placement_type before comparing markets (docs/02)."))
    return findings


def reliable_metrics(ds: Dataset, min_coverage: float = 0.80) -> set[str]:
    """The metrics a target may be anchored on."""
    findings = assess(ds, min_coverage)
    unreliable = {f.metric for f in findings if not f.reliable}
    everything = {
        "calls", "connects", "emails", "client_meetings", "jobs_taken",
        "cvs_sent", "first_interviews", "further_interviews", "offers", "placements", "gp",
    }
    return everything - unreliable
