"""End-to-end tests: fat_functions.py writes report.json and a summary."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from codemap import VENDOR
from fat_functions import main

MIXED = Path(__file__).parent / "fixtures" / "mixed_project"
SCRIPT = VENDOR.parent / "fat_functions.py"


def run(capsys, *args):
    """Run the tool; return its exit code and stdout."""
    code = main([str(arg) for arg in args])
    return code, capsys.readouterr().out


def copy_mixed(tmp_path):
    project = tmp_path / "project"
    shutil.copytree(MIXED, project)
    return project


def test_report_json_for_the_mixed_project(tmp_path, capsys):
    project = copy_mixed(tmp_path)

    code, out = run(capsys, project)

    assert code == 0
    report_dir = project / ".fat-functions"
    report = json.loads((report_dir / "report.json").read_text(encoding="utf-8"))
    assert list(report) == [
        "summary",
        "thresholds",
        "offenders",
        "tree",
        "errors",
        "warnings",
        "skipped_generated",
    ]
    assert report["summary"] == {
        "files": 5,
        "functions": 7,
        "loc": 44,
        "danger_zone": 0,
    }
    assert report["thresholds"] == {"max_loc": 50, "max_complexity": 10}
    assert [f["id"] for f in report["offenders"]] == [
        "billing.py::build",  # 10 x 5
        "Order.java::Order::shipping",  # 9 x 5
        "cart.js::applyDiscount",  # 7 x 5
        "user.ts::validate",  # 5 x 5
        "summary.py::describe",  # 5 x 2
        "billing.py::round_money",  # 2 x 1
        "cart.js::total",  # 1 x 1
    ]
    assert report["offenders"][0] == {
        "id": "billing.py::build",
        "name": "build",
        "file": "billing.py",
        "start_line": 2,
        "end_line": 11,
        "loc": 10,
        "complexity": 5,
        "params": 3,
        "language": "python",
        "forgiven": False,
        "status": "ok",
    }
    assert report["tree"]["value"] == 44
    assert (report["errors"], report["warnings"], report["skipped_generated"]) == (
        [],
        [],
        [],
    )
    assert (report_dir / ".gitignore").read_text(encoding="utf-8").endswith("\n*\n")
    assert out.splitlines()[:4] == [
        "Fat Functions: 5 files, 7 functions, 44 lines of code.",
        "Danger zone (more than 50 lines of code and complexity over 10): 0 functions.",
        "Worst offenders (ranked by lines of code times complexity):",
        "  1. build: 10 lines of code, complexity 5, Simple (billing.py:2)",
    ]
    assert out.splitlines()[-1] == f"Report: {report_dir / 'report.json'}"


def test_same_input_gives_the_same_bytes(tmp_path, capsys):
    project = copy_mixed(tmp_path)
    run(capsys, project)
    first = (project / ".fat-functions" / "report.json").read_bytes()
    run(capsys, project)
    second = (project / ".fat-functions" / "report.json").read_bytes()
    assert first == second
    assert b"\r\n" not in first


def test_options_and_everything_that_was_not_measured(tmp_path, capsys):
    project = tmp_path / "project"
    (project / "tests").mkdir(parents=True)
    (project / "tests" / "test_x.py").write_text("def t():\n    pass\n")
    (project / "api_pb2.py").write_text("# DO NOT EDIT!\ndef f():\n    pass\n")
    deep = "function f() {" + "{" * 3000 + "}" * 3000 + "}\n"
    (project / "deep.js").write_text(deep)
    late = "\n" * 10 + "function a() { return 1; }\n// GENERATED CODE\n"
    (project / "late.js").write_text(late)
    (project / "jobs.py").write_text(
        "def fat(x):\n"
        "    #lizard forgive\n"
        "    if x:\n"
        "        x += 1\n"
        "    if x > 2:\n"
        "        x += 2\n"
        "    return x\n"
    )
    out_dir = tmp_path / "reports"

    code, out = run(
        capsys,
        project,
        "--out",
        out_dir,
        "--exclude",
        "tests",
        "--max-loc",
        "3",
        "--max-complexity",
        "2",
    )

    assert code == 0
    report = json.loads((out_dir / "report.json").read_text(encoding="utf-8"))
    assert report["summary"]["danger_zone"] == 1
    assert report["thresholds"] == {"max_loc": 3, "max_complexity": 2}
    assert [f["id"] for f in report["offenders"]] == ["jobs.py::fat", "late.js::a"]
    assert report["offenders"][0]["forgiven"] is True
    assert [e["file"] for e in report["errors"]] == ["deep.js"]
    assert [(w["file"], w["line"]) for w in report["warnings"]] == [("late.js", 12)]
    assert report["skipped_generated"] == [
        {"file": "api_pb2.py", "marker": "DO NOT EDIT"}
    ]
    # def, two ifs, two additions and return: 6 lines of code; the comment is not.
    assert (
        "  1. fat: 6 lines of code, complexity 3, Simple, Forgiven (jobs.py:1)" in out
    )
    assert (
        "Not fully measured: 1 error, 1 warning, 1 generated file skipped; "
        "see report.json." in out
    )

    run(capsys, project, "--out", out_dir, "--include-generated")
    report = json.loads((out_dir / "report.json").read_text(encoding="utf-8"))
    assert report["skipped_generated"] == []
    assert "api_pb2.py::f" in [f["id"] for f in report["offenders"]]
    assert "tests/test_x.py::t" in [f["id"] for f in report["offenders"]]


def test_an_existing_out_folder_gets_no_gitignore(tmp_path, capsys):
    project = copy_mixed(tmp_path)
    out_dir = tmp_path / "docs"
    out_dir.mkdir()
    run(capsys, project, "--out", out_dir)
    assert sorted(p.name for p in out_dir.iterdir()) == ["report.json"]


def test_a_path_that_is_not_a_folder_is_an_error(tmp_path, capsys):
    code = main([str(tmp_path / "missing")])
    assert code == 2
    assert "not a folder" in capsys.readouterr().err


def test_names_the_console_cannot_show_do_not_crash(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "units.py").write_text("def größe():\n    return 1\n", encoding="utf-8")
    env = {**os.environ, "PYTHONIOENCODING": "ascii"}
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(project)],
        capture_output=True,
        text=True,
        encoding="ascii",
        errors="replace",
        env=env,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "1. gr??e: 2 lines of code" in result.stdout


def test_runs_without_its_folder_on_sys_path(tmp_path):
    # python -I (and the embeddable Windows Python) leave the script's folder
    # off sys.path; the script must still find codemap/.
    project = copy_mixed(tmp_path)
    result = subprocess.run(
        [sys.executable, "-I", str(SCRIPT), str(project)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("Fat Functions: 5 files, 7 functions")
