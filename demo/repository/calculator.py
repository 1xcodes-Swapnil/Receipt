"""
Demo calculator module.
Used by the Receipts demo review to verify the Test Runner pipeline.
"""


def add(a: float, b: float) -> float:
    """Return the sum of a and b."""
    return a + b


def subtract(a: float, b: float) -> float:
    """Return a minus b."""
    return a - b


def multiply(a: float, b: float) -> float:
    """Return a multiplied by b."""
    return a * b


def divide(a: float, b: float) -> float:
    """Return a divided by b. Raises ZeroDivisionError if b is zero."""
    if b == 0:
        raise ZeroDivisionError("Cannot divide by zero")
    return a / b


def is_even(n: int) -> bool:
    """Return True if n is even."""
    return n % 2 == 0
