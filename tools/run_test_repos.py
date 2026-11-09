"""Run Fat Functions on every test repository; write their reports and a summary.

Runs the real command line, one repository per process and several at once,
into .test-repos-out/<repo>/, plus .test-repos-out/index.html linking them all.
Fetch the repositories first. Run from the repository root:

    python tools/run_test_repos.py [--only requests,flask] [--jobs 4]
"""

from __future__ import annotations

import argparse
import html
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from repos import OUT, SCRIPT, Repo, load_repos

RUN_INFO = "run.json"  # which commit was measured, and how long it took
# Repositories measured at once. More was slower in build step 7: 8 at once on
# 12 logical cores took 257 s, 3 at once 63 s, one at a time 111 s.
JOBS = 3
COLUMNS = (
    "repository",
    "files",
    "functions",
    "lines of code",
    "danger zone",
    "errors",
    "warnings",
    "generated",
    "seconds",
)


@dataclass
class Result:
    """One repository's run: its report summary, or why there is none."""

    repo: Repo
    seconds: float
    report: dict | None = None
    problem: str = ""


def run(repo: Repo, out: Path = OUT) -> Result:
    """Measure one repository with the command line, as a user would."""
    if not repo.path.is_dir():
        return Result(repo, 0.0, problem="not fetched: run tools/fetch_test_repos.py")
    report_dir = out / repo.name
    start = time.perf_counter()
    done = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            str(repo.path),
            "--out",
            str(report_dir),
            "--no-open",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    seconds = time.perf_counter() - start
    if done.returncode != 0:
        last = (done.stderr.strip().splitlines() or ["(no output)"])[-1]
        return Result(repo, seconds, problem=f"exit code {done.returncode}: {last}")
    info = {"commit": repo.commit, "seconds": round(seconds, 1)}
    (report_dir / RUN_INFO).write_text(json.dumps(info) + "\n", encoding="utf-8")
    report = json.loads((report_dir / "report.json").read_text(encoding="utf-8"))
    return Result(repo, seconds, report)


def row(result: Result) -> list[str]:
    """The summary table's cells for one result."""
    if result.report is None:
        return [result.repo.name, result.problem]
    summary, report = result.report["summary"], result.report
    share = summary["danger_zone"] / summary["functions"] if summary["functions"] else 0
    return [
        result.repo.name,
        f"{summary['files']:,}",
        f"{summary['functions']:,}",
        f"{summary['loc']:,}",
        f"{summary['danger_zone']:,} ({share:.1%})",
        f"{len(report['errors']):,}",
        f"{len(report['warnings']):,}",
        f"{len(report['skipped_generated']):,}",
        f"{result.seconds:.1f}",
    ]


def text_table(results: list[Result]) -> str:
    """The summary as a plain-text table, numbers aligned right."""
    rows = [list(COLUMNS), *(row(result) for result in results)]
    widths = [max(len(r[i]) for r in rows if len(r) > i) for i in range(len(COLUMNS))]

    def line(cells: list[str]) -> str:
        if len(cells) < len(COLUMNS):  # a run that failed: name and problem
            return f"{cells[0]:<{widths[0]}}  {cells[1]}"
        first = f"{cells[0]:<{widths[0]}}"
        rest = (f"{cell:>{width}}" for cell, width in zip(cells[1:], widths[1:]))
        return "  ".join([first, *rest])

    return "\n".join(line(cells) for cells in rows)


def index_html(results: list[Result]) -> str:
    """A page linking every report, with the summary table."""
    head = "".join(f"<th>{html.escape(column)}</th>" for column in COLUMNS)
    body = []
    for result in results:
        cells = row(result)
        name = html.escape(cells[0])
        if result.report is not None:
            name = f'<a href="{name}/report.html">{name}</a>'
            rest = "".join(f"<td>{html.escape(cell)}</td>" for cell in cells[1:])
        else:
            rest = f'<td colspan="{len(COLUMNS) - 1}">{html.escape(cells[1])}</td>'
        body.append(f"<tr><td>{name}</td>{rest}</tr>")
    return (
        "<!doctype html>\n<meta charset=utf-8>\n<title>Fat Functions: test repositories</title>\n"
        "<style>body{font-family:system-ui,sans-serif;margin:2em}"
        "table{border-collapse:collapse}th,td{padding:4px 12px;border-bottom:1px solid #ccc}"
        "td:not(:first-child){text-align:right;font-variant-numeric:tabular-nums}</style>\n"
        "<h1>Fat Functions: test repositories</h1>\n"
        f"<table><tr>{head}</tr>\n" + "\n".join(body) + "\n</table>\n"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", default="", help="comma-separated repo names")
    parser.add_argument("--jobs", type=int, default=JOBS, help="repositories at once")
    args = parser.parse_args(argv)
    repos = load_repos([name for name in args.only.split(",") if name])

    OUT.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        results = list(pool.map(run, repos))
    (OUT / "index.html").write_text(index_html(results), encoding="utf-8")
    print(text_table(results))
    print(f"Reports: {OUT / 'index.html'}")
    return 1 if any(result.report is None for result in results) else 0


if __name__ == "__main__":
    sys.exit(main())
