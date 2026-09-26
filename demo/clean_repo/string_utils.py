"""
Clean string utilities module — no bugs.
All tests pass.
"""


def reverse_string(s: str) -> str:
    """Return the reversed string."""
    return s[::-1]


def count_vowels(s: str) -> int:
    """Return the number of vowels (a e i o u) in s (case-insensitive)."""
    return sum(1 for ch in s.lower() if ch in "aeiou")


def is_palindrome(s: str) -> bool:
    """Return True if s is a palindrome (case-insensitive, ignores spaces)."""
    cleaned = s.replace(" ", "").lower()
    return cleaned == cleaned[::-1]


def title_case(s: str) -> str:
    """Return s with the first letter of each word capitalised."""
    return " ".join(word.capitalize() for word in s.split())


def truncate(s: str, max_len: int, suffix: str = "...") -> str:
    """Truncate s to max_len characters, appending suffix if truncated."""
    if len(s) <= max_len:
        return s
    return s[: max_len - len(suffix)] + suffix
