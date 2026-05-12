"""Tests for multi_seed bootstrap CIs, schedule parsing, and aggregation."""

import statistics

from reviewstem.multi_seed import (
    CellScores,
    DEFAULT_SEED_SCHEDULE,
    MultiSeedResult,
    bootstrap_ci,
    is_significant,
    parse_seed_schedule,
)


def test_bootstrap_ci_is_deterministic():
    samples = [0.85, 0.90, 0.92, 0.88, 0.86]
    lo_1, hi_1 = bootstrap_ci(samples)
    lo_2, hi_2 = bootstrap_ci(samples)
    assert (lo_1, hi_1) == (lo_2, hi_2)


def test_bootstrap_ci_contains_mean_for_iid_samples():
    samples = [0.80, 0.85, 0.90, 0.95, 1.0]
    lo, hi = bootstrap_ci(samples)
    mean = statistics.fmean(samples)
    assert lo <= mean <= hi


def test_bootstrap_ci_handles_singleton():
    lo, hi = bootstrap_ci([0.7])
    assert lo == 0.7 and hi == 0.7


def test_bootstrap_ci_handles_empty_sample():
    assert bootstrap_ci([]) == (0.0, 0.0)


def test_is_significant_when_intervals_do_not_overlap():
    high = CellScores(case_id="x", condition="rs", raw_scores=[0.92, 0.95, 0.94, 0.93, 0.96])
    low = CellScores(case_id="x", condition="g", raw_scores=[0.40, 0.45, 0.42, 0.43, 0.41])
    assert is_significant(high, low) is True


def test_not_significant_when_intervals_overlap():
    a = CellScores(case_id="x", condition="rs", raw_scores=[0.85, 0.88, 0.87, 0.86, 0.84])
    b = CellScores(case_id="x", condition="g", raw_scores=[0.82, 0.85, 0.83, 0.84, 0.86])
    assert is_significant(a, b) is False


def test_parse_seed_schedule_basic():
    schedule = parse_seed_schedule("1:0.0,2:0.2,3:0.5")
    assert schedule == [(1, 0.0), (2, 0.2), (3, 0.5)]


def test_parse_seed_schedule_rejects_malformed():
    try:
        parse_seed_schedule("not-a-pair")
    except ValueError:
        return
    raise AssertionError("expected ValueError")


def test_default_seed_schedule_mixes_temperatures():
    temps = {temp for _, temp in DEFAULT_SEED_SCHEDULE}
    assert len(temps) >= 2, "default schedule should mix at least two temperatures"


def test_multiseed_result_dict_shape():
    g = CellScores(case_id="x", condition="g", raw_scores=[0.5, 0.6, 0.55])
    s = CellScores(case_id="x", condition="s", raw_scores=[0.5, 0.6, 0.55])
    rs = CellScores(case_id="x", condition="rs", raw_scores=[0.9, 0.92, 0.91])
    result = MultiSeedResult(
        case_id="x", title="t", requires_context=False, generic=g, skilled=s, reviewstem=rs
    )
    payload = result.to_dict()
    assert payload["delta_mean"] > 0
    assert "ci_low" in payload["reviewstem"]
    assert "ci_high" in payload["reviewstem"]
    assert payload["reviewstem_vs_generic_significant"] is True
