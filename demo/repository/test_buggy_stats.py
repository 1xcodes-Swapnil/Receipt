"""
Tests for buggy_stats module.

These tests FAIL against the current (buggy) implementation of mean().
They are designed for the Phase 3 immunity pipeline demo:

  TestRunner → FAIL → BUG_DETECTED → ImmunityPipeline → Reproduce → ... → Fix → Verify
"""
import pytest
from buggy_stats import mean, median, variance


class TestMean:
    def test_basic_mean(self):
        # BUG: returns 3.0 (last value / 3) instead of 2.0 ((1+2+3)/3)
        assert mean([1.0, 2.0, 3.0]) == 2.0

    def test_mean_single(self):
        assert mean([5.0]) == 5.0

    def test_mean_negative(self):
        assert mean([-1.0, 1.0]) == 0.0

    def test_mean_empty_raises(self):
        with pytest.raises(ValueError):
            mean([])

    def test_mean_identical_values(self):
        assert mean([4.0, 4.0, 4.0]) == 4.0


class TestMedian:
    def test_odd_count(self):
        assert median([3.0, 1.0, 2.0]) == 2.0

    def test_even_count(self):
        assert median([1.0, 2.0, 3.0, 4.0]) == 2.5

    def test_single(self):
        assert median([7.0]) == 7.0


class TestVariance:
    def test_basic(self):
        # variance of [2, 4, 4, 4, 5, 5, 7, 9] = 4.0
        assert variance([2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0]) == 4.0

    def test_single_raises(self):
        with pytest.raises(ValueError):
            variance([1.0])
