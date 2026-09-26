"""
Tests for string_utils — all pass, no known defects.
"""
import pytest
from string_utils import (
    count_vowels,
    is_palindrome,
    reverse_string,
    title_case,
    truncate,
)


class TestReverseString:
    def test_basic(self):
        assert reverse_string("hello") == "olleh"

    def test_empty(self):
        assert reverse_string("") == ""

    def test_single_char(self):
        assert reverse_string("a") == "a"

    def test_palindrome_unchanged(self):
        assert reverse_string("racecar") == "racecar"


class TestCountVowels:
    def test_basic(self):
        assert count_vowels("hello") == 2

    def test_no_vowels(self):
        assert count_vowels("rhythm") == 0

    def test_all_vowels(self):
        assert count_vowels("aeiou") == 5

    def test_case_insensitive(self):
        assert count_vowels("HELLO") == 2


class TestIsPalindrome:
    def test_simple_palindrome(self):
        assert is_palindrome("racecar") is True

    def test_not_palindrome(self):
        assert is_palindrome("hello") is False

    def test_with_spaces(self):
        assert is_palindrome("a man a plan a canal panama") is True

    def test_case_insensitive(self):
        assert is_palindrome("Racecar") is True


class TestTitleCase:
    def test_basic(self):
        assert title_case("hello world") == "Hello World"

    def test_already_title(self):
        assert title_case("Hello World") == "Hello World"

    def test_single_word(self):
        assert title_case("python") == "Python"


class TestTruncate:
    def test_no_truncation(self):
        assert truncate("hello", 10) == "hello"

    def test_truncation(self):
        assert truncate("hello world", 8) == "hello..."

    def test_exact_length(self):
        assert truncate("hello", 5) == "hello"
