"""
Escalate-repo source module.

This file exists so the repo looks like a real Python project.
There are intentionally NO test files in this directory.
The TestRunner agent will find no test suite → INSUFFICIENT_EVIDENCE → ESCALATE.
"""


def process(data: list) -> list:
    """Filter out None values from a list."""
    return [x for x in data if x is not None]


def summarise(data: list) -> dict:
    """Return a basic summary dict for a list of numbers."""
    if not data:
        return {"count": 0, "total": 0, "mean": None}
    total = sum(data)
    return {"count": len(data), "total": total, "mean": total / len(data)}
