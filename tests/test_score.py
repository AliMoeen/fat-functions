"""Tests for codemap.score."""

import pytest

from codemap.measure import FunctionRecord
from codemap.score import TOP_OFFENDERS, Thresholds, in_danger_zone, score, status


def record(name, loc, complexity, forgiven=False):
    return FunctionRecord(
        id=f"a.py::{name}",
        name=name,
        file="a.py",
        start_line=1,
        end_line=1,
        loc=loc,
        complexity=complexity,
        params=0,
        language="python",
        forgiven=forgiven,
    )


@pytest.mark.parametrize(
    ("complexity", "expected"),
    [(1, "ok"), (5, "ok"), (6, "watch"), (10, "watch"), (11, "soon"), (20, "soon")]
    + [(21, "now"), (99, "now")],
)
def test_status_follows_the_complexity_bands(complexity, expected):
    assert status(complexity) == expected


@pytest.mark.parametrize(
    ("loc", "complexity", "expected"),
    [(51, 11, True), (50, 11, False), (51, 10, False), (500, 50, True)],
)
def test_danger_zone_is_more_than_both_maximums(loc, complexity, expected):
    assert in_danger_zone(record("f", loc, complexity), Thresholds()) is expected


def test_thresholds_can_be_changed():
    thresholds = Thresholds(max_loc=30, max_complexity=5)
    assert in_danger_zone(record("f", 31, 6), thresholds)
    assert not in_danger_zone(record("f", 30, 6), thresholds)


def test_score_sets_statuses_and_ranks_by_loc_times_complexity():
    functions = [
        record("small", 10, 1),  # 10
        record("long_simple", 300, 2),  # 600: long but simple still ranks high
        record("dense", 60, 12),  # 720
        record("tie_b", 20, 3),  # 60
        record("tie_a", 30, 2),  # 60, ties go by id
        record("accepted", 100, 25, forgiven=True),  # 2500: forgiven still ranks
    ]
    result = score(functions, Thresholds())

    assert [f.name for f in result.offenders] == [
        "accepted",
        "dense",
        "long_simple",
        "tie_a",
        "tie_b",
        "small",
    ]
    assert {f.name: f.status for f in functions} == {
        "small": "ok",
        "long_simple": "ok",
        "dense": "soon",
        "tie_b": "ok",
        "tie_a": "ok",
        "accepted": "now",
    }
    assert result.danger_zone == 2  # dense and accepted


def test_offenders_are_capped_and_do_not_depend_on_input_order():
    functions = [record(f"f{n:02}", n, 2) for n in range(1, TOP_OFFENDERS + 6)]
    forwards = score(functions, Thresholds()).offenders
    backwards = score(list(reversed(functions)), Thresholds()).offenders
    assert len(forwards) == TOP_OFFENDERS
    assert [f.id for f in forwards] == [f.id for f in backwards]
    assert forwards[0].name == f"f{TOP_OFFENDERS + 5:02}"
