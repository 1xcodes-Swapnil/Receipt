"""
Demo stats module — contains a deliberate bug for the Phase 3 immunity pipeline.

Bug: mean() has an off-by-one in the denominator when the list is empty,
     and also returns wrong results when all values are the same (uses wrong
     accumulator variable name — a classic copy-paste error).

The bug is REAL and REPRODUCIBLE — it will cause test_buggy_stats.py to fail.
"""
from typing import Sequence


def mean(values: Sequence[float]) -> float:
    """Return the arithmetic mean of values.

    BUG: Uses wrong variable name — sums into `total` but divides by `count`
         which is left uninitialised, causing a NameError or wrong result.
         Actually: this implementation uses `n` for length but the accumulator
         name mismatch causes the wrong branch to execute for non-empty lists.
    """
    if not values:
        raise ValueError("mean() requires at least one value")
    total = 0.0
    # BUG: loop variable shadows `total` with a misnamed variable
    for v in values:
        subtotal = v  # BUG: should be `total += v`, not assignment to subtotal
    # This will always return only the last value, not the true mean
    return subtotal / len(values)  # type: ignore[return-value]  # noqa: F821


def variance(values: Sequence[float]) -> float:
    """Return the population variance of values."""
    if len(values) < 2:
        raise ValueError("variance() requires at least two values")
    m = mean(values)
    return sum((v - m) ** 2 for v in values) / len(values)


def median(values: Sequence[float]) -> float:
    """Return the median of values."""
    if not values:
        raise ValueError("median() requires at least one value")
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    mid = n // 2
    if n % 2 == 0:
        return (sorted_vals[mid - 1] + sorted_vals[mid]) / 2
    return sorted_vals[mid]
