"""Tests for the test-repository tools: the lists, the runner's summary, compare."""

import json

import pytest

from compare import current, differences, dumps_baseline, snapshot
from repos import REPOS_FILE, load_repos
from run_test_repos import RUN_INFO, Result, index_html, text_table

COMMIT = "0123456789abcdef0123456789abcdef01234567"


def write(path, text):
    path.write_text(text, encoding="utf-8")
    return path


def entry(name, commit=COMMIT, url="https://example.com/x"):
    return f'[[repo]]\nname = "{name}"\nurl = "{url}"\ncommit = "{commit}"\n'


def test_the_committed_list_is_valid_and_pinned():
    repos = load_repos(repos_file=REPOS_FILE, local_file=REPOS_FILE.with_name("none"))
    assert len(repos) >= 8
    assert all(repo.url and repo.commit and not repo.private for repo in repos)


def test_local_list_adds_private_repos_and_checkouts(tmp_path):
    public = write(tmp_path / "repos.toml", entry("one"))
    local = write(
        tmp_path / "repos.local.toml",
        entry("two") + '[[repo]]\nname = "work"\npath = "C:/code/work"\n',
    )
    repos = load_repos(repos_file=public, local_file=local, clones=tmp_path / "clones")

    assert [(r.name, r.private, r.url is None) for r in repos] == [
        ("one", False, False),
        ("two", True, False),
        ("work", True, True),
    ]
    assert repos[0].path == tmp_path / "clones" / "one"
    names = load_repos(["work"], repos_file=public, local_file=local)
    assert [r.name for r in names] == ["work"]


@pytest.mark.parametrize(
    ("text", "message"),
    [
        (entry("one", commit="main"), "full 40-character commit"),
        (entry("One"), "lowercase"),
        (entry("one") + entry("one"), "more than once"),
        ('[[repo]]\nname = "one"\npath = "C:/x"\n', "needs a url"),  # only locally
    ],
)
def test_bad_lists_are_refused(tmp_path, text, message):
    public = write(tmp_path / "repos.toml", text)
    with pytest.raises(ValueError, match=message):
        load_repos(repos_file=public, local_file=tmp_path / "none")


def test_unknown_names_in_only_are_refused(tmp_path):
    public = write(tmp_path / "repos.toml", entry("one"))
    with pytest.raises(ValueError, match="not in the lists: nope"):
        load_repos(["nope"], repos_file=public, local_file=tmp_path / "none")


def report(functions=(("a.py::f", 1, 9, 8, 3, False),), danger=0):
    """A small report.json with the given functions in one file."""
    nodes = [
        {
            "type": "function",
            "id": fid,
            "name": fid.split("::")[1],
            "value": loc,
            "start_line": start,
            "end_line": end,
            "loc": loc,
            "complexity": cc,
            "params": 0,
            "forgiven": forgiven,
            "status": "ok",
        }
        for fid, start, end, loc, cc, forgiven in functions
    ]
    file = {
        "type": "file",
        "name": "a.py",
        "path": "a.py",
        "value": 9,
        "children": nodes,
    }
    return {
        "summary": {
            "files": 1,
            "functions": len(nodes),
            "loc": 9,
            "danger_zone": danger,
        },
        "thresholds": {"max_loc": 50, "max_complexity": 10},
        "offenders": [],
        "tree": {
            "type": "folder",
            "name": "<root>",
            "path": "",
            "value": 9,
            "children": [file],
        },
        "errors": [{"file": "b.js", "error": "lizard failed"}],
        "warnings": [],
        "skipped_generated": [{"file": "c_pb2.py", "marker": "DO NOT EDIT"}],
    }


def test_snapshot_keeps_what_compare_needs():
    functions = (("a.py::f", 1, 9, 8, 3, False), ("a.py::g", 11, 12, 2, 1, True))
    assert snapshot(report(functions), COMMIT) == {
        "commit": COMMIT,
        "summary": {"files": 1, "functions": 2, "loc": 9, "danger_zone": 0},
        "thresholds": {"max_loc": 50, "max_complexity": 10},
        "errors": ["b.js: lizard failed"],
        "warnings": [],
        "skipped_generated": ["c_pb2.py: DO NOT EDIT"],
        "forgiven": ["a.py::g"],
        "functions": {"a.py::f": [1, 9, 8, 3], "a.py::g": [11, 12, 2, 1]},
    }


def test_differences_show_only_what_changed():
    old = snapshot(
        report((("a.py::f", 1, 9, 8, 3, False), ("a.py::g", 11, 12, 2, 1, False))),
        COMMIT,
    )
    new = snapshot(
        report(
            (("a.py::f", 1, 9, 60, 12, False), ("a.py::h", 14, 15, 2, 1, False)),
            danger=1,
        ),
        COMMIT,
    )
    assert differences(old, old) == []
    assert differences(None, new) == ["not in the baseline yet"]
    assert differences(old, new) == [
        "summary danger_zone: 0 -> 1 (+1)",
        "functions added (1):",
        "  a.py::h",
        "functions removed (1):",
        "  a.py::g",
        "functions changed (1):",
        "  a.py::f: lines 1-9, 8 loc, complexity 3 -> lines 1-9, 60 loc, complexity 12",
    ]


def test_long_lists_of_changes_are_cut_short():
    many = tuple((f"a.py::f{n:02}", n, n, 1, 1, False) for n in range(15))
    lines = differences(snapshot(report(()), COMMIT), snapshot(report(many), COMMIT))
    assert lines[0] == "summary functions: 0 -> 15 (+15)"
    assert lines[1] == "functions added (15):"
    assert lines[-1] == "  ... and 5 more"


def test_baseline_text_is_stable_and_one_function_per_line():
    baseline = {
        "zeta": snapshot(report(), COMMIT),
        "alpha": snapshot(report((("a.py::f", 1, 2, 2, 1, False),)), None),
    }
    text = dumps_baseline(baseline)
    assert json.loads(text) == baseline
    assert text == dumps_baseline(json.loads(text))
    assert text.index('"alpha"') < text.index('"zeta"')
    assert '   "a.py::f": [1, 9, 8, 3]\n' in text
    assert dumps_baseline({}) == "{}\n"


def test_current_needs_results_for_the_listed_commit(tmp_path):
    (repo,) = load_repos(
        repos_file=write(tmp_path / "repos.toml", entry("one")),
        local_file=tmp_path / "x",
    )
    assert current(repo, tmp_path)[1].startswith("no results")
    (tmp_path / "one").mkdir()
    write(tmp_path / "one" / "report.json", json.dumps(report()))
    write(tmp_path / "one" / RUN_INFO, json.dumps({"commit": "f" * 40}))
    assert "the list says" in current(repo, tmp_path)[1]
    write(tmp_path / "one" / RUN_INFO, json.dumps({"commit": COMMIT}))
    results, problem = current(repo, tmp_path)
    assert (problem, results["functions"]) == ("", {"a.py::f": [1, 9, 8, 3]})


def test_summary_table_and_index_page(tmp_path):
    public = write(tmp_path / "repos.toml", entry("one") + entry("two"))
    one, two = load_repos(repos_file=public, local_file=tmp_path / "x")
    results = [
        Result(one, 2.25, report(danger=1)),
        Result(two, 0.0, problem="not fetched"),
    ]

    table = text_table(results).splitlines()
    assert table[0].split() == [
        "repository", "files", "functions", "lines", "of", "code", "danger", "zone",
        "errors", "warnings", "generated", "seconds",
    ]  # fmt: skip
    assert table[1].split() == [
        "one",
        "1",
        "1",
        "9",
        "1",
        "(100.0%)",
        "1",
        "0",
        "1",
        "2.2",
    ]
    assert table[2].split() == ["two", "not", "fetched"]
    page = index_html(results)
    assert '<a href="one/report.html">one</a>' in page
    assert "not fetched" in page
