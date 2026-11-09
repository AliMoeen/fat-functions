"""Give each function a status and rank the worst offenders."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from codemap.measure import FunctionRecord

# Status by cyclomatic complexity: the highest complexity for each status.
STATUS_LIMITS = (
    (5, "ok"),
    (10, "watch"),
    (20, "soon"),
)
TOP_STATUS = "now"
LABELS = {"ok": "Simple", "watch": "Watch", "soon": "Split soon", "now": "Split now"}

# How many of the worst functions report.json lists as offenders.
TOP_OFFENDERS = 20


@dataclass
class Thresholds:
    """The danger zone: more lines of code and more complexity than these."""

    max_loc: int = 50
    max_complexity: int = 10


@dataclass
class Scores:
    """The worst functions, worst first, and how many are in the danger zone."""

    offenders: list[FunctionRecord]
    danger_zone: int


def status(complexity: int) -> str:
    """Return the status for a cyclomatic complexity."""
    for limit, name in STATUS_LIMITS:
        if complexity <= limit:
            return name
    return TOP_STATUS


def in_danger_zone(function: FunctionRecord, thresholds: Thresholds) -> bool:
    """Whether a function is both too long and too complex."""
    return (
        function.loc > thresholds.max_loc
        and function.complexity > thresholds.max_complexity
    )


def score(functions: Iterable[FunctionRecord], thresholds: Thresholds) -> Scores:
    """Set every function's status and rank them by lines of code × complexity.

    Forgiven functions are ranked like the rest. Ties go by id, so the order
    never depends on input order.
    """
    functions = list(functions)
    for function in functions:
        function.status = status(function.complexity)
    ranked = sorted(functions, key=lambda f: (-f.loc * f.complexity, f.id))
    danger = sum(in_danger_zone(f, thresholds) for f in functions)
    return Scores(offenders=ranked[:TOP_OFFENDERS], danger_zone=danger)
