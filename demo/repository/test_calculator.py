"""
Demo test suite for the Receipts evidence pipeline.

These tests are deterministic and always pass against the demo calculator.
They exist so the Phase 1 Test Runner has a real, executable test suite.
"""
import pytest
from calculator import add, subtract, multiply, divide, is_even


class TestAdd:
    def test_positive_numbers(self):
        assert add(2, 3) == 5

    def test_negative_numbers(self):
        assert add(-1, -1) == -2

    def test_zero(self):
        assert add(0, 5) == 5

    def test_floats(self):
        assert abs(add(1.1, 2.2) - 3.3) < 1e-9


class TestSubtract:
    def test_basic(self):
        assert subtract(10, 4) == 6

    def test_result_negative(self):
        assert subtract(3, 7) == -4


class TestMultiply:
    def test_basic(self):
        assert multiply(3, 4) == 12

    def test_by_zero(self):
        assert multiply(99, 0) == 0


class TestDivide:
    def test_basic(self):
        assert divide(10, 2) == 5.0

    def test_float_result(self):
        assert divide(7, 2) == 3.5

    def test_divide_by_zero(self):
        with pytest.raises(ZeroDivisionError):
            divide(5, 0)


class TestIsEven:
    def test_even(self):
        assert is_even(4) is True

    def test_odd(self):
        assert is_even(3) is False

    def test_zero(self):
        assert is_even(0) is True
