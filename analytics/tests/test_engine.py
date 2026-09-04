"""Tests for the analytics engine.

stdlib unittest, no install required - the same constraint as the engine itself, so
this suite runs anywhere the data lands.

    python3 -m unittest discover -s tests -v
"""

from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from cube19_analytics.ingest import DEFAULT_STATUS_MAP, load_dataset, normalise_stage  # noqa: E402
from cube19_analytics.metrics import Slice, compute_metrics  # noqa: E402
from cube19_analytics.model import (  # noqa: E402
    Activity, Client, Consultant, Dataset, Job, Placement, PlacementType, Stage, StageEvent,
)
from cube19_analytics.quality import assess  # noqa: E402
from cube19_analytics.ratios import RatioKind, compute_ratios, decompose_change  # noqa: E402
from cube19_analytics.stats import (  # noqa: E402
    beta_posterior, beta_ppf, prob_greater, regularized_incomplete_beta, sample_size_for,
)
from cube19_analytics.targets import back_solve  # noqa: E402
from cube19_analytics.timeseries import momentum  # noqa: E402


class TestBetaMath(unittest.TestCase):
    def test_incomplete_beta_symmetric_case(self):
        # I_0.5(a, a) = 0.5 for any a, by symmetry.
        for a in (1.0, 2.5, 5.0, 20.0):
            self.assertAlmostEqual(regularized_incomplete_beta(a, a, 0.5), 0.5, places=8)

    def test_incomplete_beta_uniform_case(self):
        # Beta(1,1) is uniform, so the CDF is the identity.
        for x in (0.1, 0.35, 0.9):
            self.assertAlmostEqual(regularized_incomplete_beta(1.0, 1.0, x), x, places=8)

    def test_ppf_inverts_cdf(self):
        for q in (0.05, 0.5, 0.95):
            x = beta_ppf(3.0, 7.0, q)
            self.assertAlmostEqual(regularized_incomplete_beta(3.0, 7.0, x), q, places=6)


class TestShrinkage(unittest.TestCase):
    """The core defence against the leaderboard problem."""

    def test_small_sample_pulled_toward_prior(self):
        # 1 placement from 3 CVs is a 33% raw rate; it must not survive as one.
        post = beta_posterior(1, 3, prior_rate=0.10, prior_strength=30)
        self.assertAlmostEqual(post.raw, 1 / 3, places=6)
        self.assertLess(post.rate, 0.15)
        self.assertGreater(post.rate, 0.10)   # still nudged above the prior
        self.assertFalse(post.is_measured)

    def test_large_sample_dominates_prior(self):
        post = beta_posterior(30, 200, prior_rate=0.10, prior_strength=30)
        self.assertAlmostEqual(post.rate, 33 / 230, places=6)
        self.assertLess(abs(post.rate - post.raw), 0.01)
        self.assertTrue(post.is_measured)

    def test_more_data_narrows_the_interval(self):
        thin = beta_posterior(3, 30, 0.10, 30)
        thick = beta_posterior(30, 300, 0.10, 30)
        self.assertLess(thick.hi - thick.lo, thin.hi - thin.lo)

    def test_prior_strength_zero_returns_raw(self):
        post = beta_posterior(5, 20, 0.10, prior_strength=0.0)
        self.assertAlmostEqual(post.rate, 0.25, places=6)

    def test_prob_greater_is_uncertain_for_thin_data(self):
        a = beta_posterior(1, 3, 0.10, 30)
        b = beta_posterior(1, 3, 0.10, 30)
        self.assertAlmostEqual(prob_greater(a, b), 0.5, delta=0.05)

    def test_prob_greater_resolves_for_clear_difference(self):
        good = beta_posterior(60, 200, 0.10, 30)
        bad = beta_posterior(5, 200, 0.10, 30)
        self.assertGreater(prob_greater(good, bad), 0.99)


class TestSampleSize(unittest.TestCase):
    def test_bigger_gaps_are_cheaper_to_detect(self):
        easy = sample_size_for(0.10, 0.30)
        hard = sample_size_for(0.10, 0.15)
        self.assertLess(easy, hard)

    def test_matches_documented_values(self):
        # These numbers are quoted in docs/05 - keep them honest.
        self.assertEqual(sample_size_for(0.10, 0.30), 49)
        self.assertEqual(sample_size_for(0.10, 0.20), 157)


def _tiny_dataset() -> Dataset:
    """A hand-built dataset with known counts, so assertions are exact."""
    ds = Dataset()
    ds.consultants.append(Consultant("U1", "Test One", "Alpha", date(2022, 1, 1)))
    ds.clients.append(Client("C1", "Client One", "Alpha"))
    ds.jobs.append(Job("J1", "C1", "U1", "Alpha", date(2023, 1, 10)))
    for i in range(10):
        ds.stage_events.append(StageEvent(
            f"S{i}", "J1", f"K{i}", "C1", "U1", "Alpha", Stage.CV_SENT, date(2023, 2, 1)))
    for i in range(4):
        ds.stage_events.append(StageEvent(
            f"S{i}", "J1", f"K{i}", "C1", "U1", "Alpha", Stage.FIRST_INTERVIEW, date(2023, 3, 1)))
    ds.stage_events.append(StageEvent(
        "S0", "J1", "K0", "C1", "U1", "Alpha", Stage.OFFER, date(2023, 4, 1)))
    ds.placements.append(Placement(
        "P1", "J1", "C1", "U1", "Alpha", date(2023, 5, 1), 20000.0, submission_id="S0"))
    return ds


class TestMetrics(unittest.TestCase):
    def test_counts_are_exact(self):
        ms = compute_metrics(_tiny_dataset())
        self.assertEqual(ms.get("cvs_sent"), 10)
        self.assertEqual(ms.get("first_interviews"), 4)
        self.assertEqual(ms.get("offers"), 1)
        self.assertEqual(ms.get("placements"), 1)
        self.assertEqual(ms.get("jobs_taken"), 1)
        self.assertEqual(ms.get("gp"), 20000.0)

    def test_slice_filters(self):
        ds = _tiny_dataset()
        self.assertEqual(compute_metrics(ds, Slice(year=2023)).get("cvs_sent"), 10)
        self.assertEqual(compute_metrics(ds, Slice(year=2024)).get("cvs_sent"), 0)
        self.assertEqual(compute_metrics(ds, Slice(market="Nope")).get("cvs_sent"), 0)

    def test_fall_offs_excluded_from_gp(self):
        ds = _tiny_dataset()
        ds.placements.append(Placement(
            "P2", "J1", "C1", "U1", "Alpha", date(2023, 6, 1), 50000.0, fell_off=True))
        ms = compute_metrics(ds)
        self.assertEqual(ms.get("gp"), 20000.0)      # the fall-off contributes nothing
        self.assertEqual(ms.get("placements"), 2)    # but it is still counted
        self.assertEqual(ms.get("fall_offs"), 1)


class TestRatios(unittest.TestCase):
    def test_raw_ratio_is_preserved_alongside_shrunk(self):
        rr = compute_ratios(compute_metrics(_tiny_dataset()))
        self.assertAlmostEqual(rr["cv_to_interview"].raw, 0.4, places=6)

    def test_proportion_is_capped_at_one(self):
        """Split desks and backfilled data really do produce num > den."""
        ds = _tiny_dataset()
        for i in range(20):  # 20 interviews from 10 CVs - impossible, but it happens
            ds.stage_events.append(StageEvent(
                f"X{i}", "J1", f"K{i}", "C1", "U1", "Alpha",
                Stage.FIRST_INTERVIEW, date(2023, 3, 2)))
        rr = compute_ratios(ds and compute_metrics(ds))
        self.assertLessEqual(rr["cv_to_interview"].value, 1.0)

    def test_rate_ratio_may_exceed_one(self):
        """CVs per job is not a proportion - Beta would wrongly cap it."""
        rr = compute_ratios(compute_metrics(_tiny_dataset()))
        self.assertIs(rr["cvs_per_job"].kind, RatioKind.RATE)
        self.assertGreater(rr["cvs_per_job"].value, 1.0)

    def test_zero_denominator_falls_back_to_prior(self):
        ds = Dataset()
        ds.consultants.append(Consultant("U1", "x", "Alpha", date(2022, 1, 1)))
        rr = compute_ratios(compute_metrics(ds))
        self.assertEqual(rr["cv_to_interview"].value, rr["cv_to_interview"].prior)
        self.assertFalse(rr["cv_to_interview"].measured)

    def test_interval_brackets_the_estimate(self):
        rr = compute_ratios(compute_metrics(_tiny_dataset()))
        for r in rr.values():
            self.assertLessEqual(r.lo, r.value + 1e-9, r.ratio_id)
            self.assertGreaterEqual(r.hi, r.value - 1e-9, r.ratio_id)


class TestSimpsonsParadox(unittest.TestCase):
    """Every segment improves while the total falls - the decomposition must say so."""

    def _seg(self, cvs, interviews):
        ds = Dataset()
        for i in range(cvs):
            ds.stage_events.append(StageEvent(
                f"S{i}", "J", "K", "C", "U", "M", Stage.CV_SENT, date(2023, 1, 1)))
        for i in range(interviews):
            ds.stage_events.append(StageEvent(
                f"S{i}", "J", "K", "C", "U", "M", Stage.FIRST_INTERVIEW, date(2023, 1, 1)))
        return compute_metrics(ds)

    def test_mix_shift_is_identified(self):
        # Easy segment: 50% -> 55%. Hard segment: 10% -> 15%. Both improve.
        before = {"easy": self._seg(100, 50), "hard": self._seg(100, 10)}
        # Volume swings hard toward the difficult segment.
        after = {"easy": self._seg(20, 11), "hard": self._seg(200, 30)}
        result = decompose_change(before, after, "cv_to_interview")

        self.assertLess(result["after"], result["before"])     # headline rate fell
        self.assertGreater(result["rate_effect"], 0)           # yet performance improved
        self.assertLess(result["mix_effect"], 0)               # mix did the damage
        self.assertIn("mix", result["verdict"].lower())

    def test_effects_sum_to_the_change(self):
        before = {"a": self._seg(100, 40), "b": self._seg(100, 20)}
        after = {"a": self._seg(150, 66), "b": self._seg(50, 12)}
        r = decompose_change(before, after, "cv_to_interview")
        total = r["rate_effect"] + r["mix_effect"] + r["interaction"]
        self.assertAlmostEqual(total, r["change"], places=6)


class TestTargets(unittest.TestCase):
    def setUp(self):
        self.ds, _ = load_dataset(ROOT / "data" / "sample")
        self.ms = compute_metrics(self.ds)
        self.rr = compute_ratios(self.ms)

    def test_placements_needed_is_goal_over_fee(self):
        plan = back_solve(500_000, self.rr, 20_000, draws=200)
        self.assertAlmostEqual(plan.placements_needed, 25.0, places=6)

    def test_chain_divides_by_each_ratio(self):
        plan = back_solve(500_000, self.rr, 20_000, draws=200)
        running = plan.placements_needed
        for step in plan.steps:
            running = running / step.ratio_used
            self.assertAlmostEqual(step.required, running, places=4)

    def test_uncertainty_widens_down_the_chain(self):
        """The compounding point: each extra uncertain ratio widens the band."""
        plan = back_solve(500_000, self.rr, 20_000, draws=3000)
        spreads = [(s.p80 - s.p20) / s.p50 for s in plan.steps if s.p50 > 0]
        self.assertGreater(spreads[-1], spreads[0])

    def test_p80_exceeds_p50(self):
        plan = back_solve(500_000, self.rr, 20_000, draws=2000)
        for s in plan.steps:
            self.assertGreaterEqual(s.p80, s.p50, s.to_metric)

    def test_unreliable_metric_cannot_be_the_anchor(self):
        plan = back_solve(500_000, self.rr, 20_000, draws=200,
                          reliable={"cvs_sent", "first_interviews", "offers", "placements"})
        self.assertEqual(plan.anchor_metric, "cvs_sent")
        self.assertTrue(any("Not anchoring" in w for w in plan.warnings))

    def test_zero_fee_is_rejected(self):
        with self.assertRaises(ValueError):
            back_solve(500_000, self.rr, 0.0)


class TestPartialPeriods(unittest.TestCase):
    """A partial year at the edge reads as a collapse. It must never reach momentum."""

    def _ds_ending(self, last: date) -> Dataset:
        ds = Dataset()
        ds.consultants.append(Consultant("U1", "x", "Alpha", date(2019, 1, 1)))
        ds.stage_events.append(StageEvent(
            "S0", "J", "K", "C", "U1", "Alpha", Stage.CV_SENT, date(2020, 1, 5)))
        ds.stage_events.append(StageEvent(
            "S1", "J", "K", "C", "U1", "Alpha", Stage.CV_SENT, last))
        return ds

    def test_trailing_stub_year_is_excluded(self):
        ds = self._ds_ending(date(2024, 2, 1))
        self.assertIn(2024, ds.years)
        self.assertNotIn(2024, ds.complete_years)
        self.assertIn(2024, ds.partial_years)

    def test_full_year_is_kept(self):
        ds = self._ds_ending(date(2024, 12, 20))
        self.assertIn(2024, ds.complete_years)

    def test_momentum_is_none_without_enough_years(self):
        self.assertIsNone(momentum([{"year": 2024, "gp": 100}]))
        self.assertIsNone(momentum([]))

    def test_momentum_ignores_partial_years(self):
        series = [{"year": 2022, "gp": 100.0}, {"year": 2023, "gp": 200.0},
                  {"year": 2024, "gp": 5.0}]   # 2024 is a January-only stub
        self.assertLess(momentum(series), 0)                                # naive: collapse
        self.assertGreater(momentum(series, complete_years=[2022, 2023]), 0)  # correct: growth


class TestQuality(unittest.TestCase):
    def test_funnel_inversion_is_caught(self):
        ds = _tiny_dataset()
        for i in range(50):   # far more offers than CVs
            ds.stage_events.append(StageEvent(
                f"O{i}", "J1", "K", "C1", "U1", "Alpha", Stage.OFFER, date(2023, 4, 2)))
        findings = {f.metric: f for f in assess(ds)}
        self.assertIn("offers", findings)
        self.assertFalse(findings["offers"].reliable)
        self.assertEqual(findings["offers"].severity, "fail")

    def test_missing_cv_stage_is_fatal(self):
        ds = _tiny_dataset()
        ds.stage_events = [e for e in ds.stage_events if e.stage is not Stage.CV_SENT]
        findings = {f.metric: f for f in assess(ds)}
        self.assertFalse(findings["cvs_sent"].reliable)
        self.assertIn("status map", findings["cvs_sent"].detail)

    def test_silent_consultants_reduce_coverage(self):
        ds = _tiny_dataset()
        ds.consultants.append(Consultant("U2", "Silent", "Alpha", date(2023, 1, 1),
                                         date(2023, 12, 31)))
        for month in range(1, 13):   # only U1 logs anything
            ds.activities.append(Activity(date(2023, month, 15), "U1", "Alpha", "call", None, 100))
        findings = {f.metric: f for f in assess(ds)}
        self.assertFalse(findings["calls"].reliable)
        self.assertIn("never logged", findings["calls"].detail)


class TestIngest(unittest.TestCase):
    def test_header_aliases_match_regardless_of_style(self):
        for header in ("event_date", "Event Date", "eventDate", "EVENTDATE", "date"):
            ds = Dataset()
            rows = [{header: "2023-01-01", "stage": "Client Submission", "submission_id": "S1"}]
            from cube19_analytics.ingest import MappingReport, _load_stage_events
            report = MappingReport()
            _load_stage_events(ds, rows, list(rows[0]), report, "t.csv", DEFAULT_STATUS_MAP)
            self.assertEqual(len(ds.stage_events), 1, f"failed on header {header!r}")

    def test_status_normalisation_is_case_and_space_insensitive(self):
        for raw in ("Client Submission", "client submission", "  CLIENT   SUBMISSION  "):
            self.assertIs(normalise_stage(raw), Stage.CV_SENT)

    def test_unknown_status_is_reported_not_guessed(self):
        self.assertIsNone(normalise_stage("Gentis Bespoke Stage 7"))

    def test_sample_data_loads_cleanly(self):
        ds, report = load_dataset(ROOT / "data" / "sample")
        self.assertGreater(len(ds.stage_events), 1000)
        self.assertGreater(len(ds.placements), 100)
        self.assertEqual(report.unmapped_statuses, {})


class TestScoringDecisions(unittest.TestCase):
    """The tiers are advice a business would act on - test the advice, not the arithmetic."""

    def setUp(self):
        from cube19_analytics.scoring import score_markets
        ds, _ = load_dataset(ROOT / "data" / "sample")
        self.markets = {m["market"]: m for m in score_markets(ds)}

    def test_every_market_gets_a_tier_and_a_reason(self):
        for market, row in self.markets.items():
            self.assertIn(row["tier"], {"Attack", "Hold", "Test", "Exit or fix"}, market)
            self.assertTrue(row["reason"], market)

    def test_confidently_worse_market_is_exited(self):
        weak = self.markets["Public Sector"]
        self.assertEqual(weak["tier"], "Exit or fix")
        self.assertEqual(weak["confidence"], "confidently below peers")

    def test_uncertain_market_is_tested_not_exited(self):
        """The expensive mistake this model must never make."""
        unproven = self.markets["Renewables"]
        self.assertEqual(unproven["tier"], "Test")
        self.assertGreater(unproven["gp_per_cv"], unproven["peer_gp_per_cv"])

    def test_baseline_excludes_the_market_itself(self):
        for market, row in self.markets.items():
            self.assertNotAlmostEqual(row["peer_gp_per_cv"], row["gp_per_cv"], places=2,
                                      msg=f"{market} appears to be compared against itself")


if __name__ == "__main__":
    unittest.main(verbosity=2)
