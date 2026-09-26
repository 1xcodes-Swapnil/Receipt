"""
Tests for math_utils — all pass, no known defects.
"""
import pytest
from math_utils import factorial, gcd, is_prime, lcm


class TestFactorial:
    def test_zero(self):
        assert factorial(0) == 1

    def test_one(self):
        assert factorial(1) == 1

    def test_five(self):
        assert factorial(5) == 120

    def test_ten(self):
        assert factorial(10) == 3628800

    def test_negative_raises(self):
        with pytest.raises(ValueError):
            factorial(-1)


class TestGcd:
    def test_basic(self):
        assert gcd(12, 8) == 4

    def test_coprime(self):
        assert gcd(7, 13) == 1

    def test_same_number(self):
        assert gcd(6, 6) == 6


class TestLcm:
    def test_basic(self):
        assert lcm(4, 6) == 12

    def test_with_zero(self):
        assert lcm(0, 5) == 0

    def test_coprime(self):
        assert lcm(3, 7) == 21


class TestIsPrime:
    def test_two_is_prime(self):
        assert is_prime(2) is True

    def test_one_not_prime(self):
        assert is_prime(1) is False

    def test_composite(self):
        assert is_prime(9) is False

    def test_large_prime(self):
        assert is_prime(97) is True
