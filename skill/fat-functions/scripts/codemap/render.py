"""Write the report: report.json and the stdout summary (the HTML comes later)."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import asdict
from pathlib import Path

from codemap.measure import FileError, Measurement
from codemap.score import LABELS, Scores, Thresholds

REPORT_JSON = "report.json"
# Offenders listed in the stdout summary.
SUMMARY_OFFENDERS = 5


def build_report(
    measurement: Measurement,
    scan_errors: Iterable[FileError],
    scores: Scores,
    thresholds: Thresholds,
    tree: dict,
) -> dict:
    """Return the content of report.json (docs/DESIGN.md section 8)."""
    errors = sorted([*scan_errors, *measurement.errors], key=lambda e: e.file)
    return {
        "summary": {
            "files": len(measurement.files),
            "functions": sum(len(file.functions) for file in measurement.files),
            "loc": tree["value"],
            "danger_zone": scores.danger_zone,
        },
        "thresholds": asdict(thresholds),
        "offenders": [asdict(function) for function in scores.offenders],
        "tree": tree,
        "errors": [asdict(error) for error in errors],
        "warnings": [asdict(warning) for warning in measurement.warnings],
        "skipped_generated": [asdict(g) for g in measurement.skipped_generated],
    }


def write_report(report: dict, out_dir: Path) -> Path:
    """Write report.json into `out_dir` and return its path.

    A folder this creates gets a `.gitignore` that ignores everything in it,
    so reports stay out of git; a folder that already existed is left as is.
    """
    if not out_dir.exists():
        out_dir.mkdir(parents=True)
        ignore_all = "# Written by Fat Functions: keep its reports out of git.\n*\n"
        _write_text(out_dir / ".gitignore", ignore_all)
    path = out_dir / REPORT_JSON
    _write_text(path, json.dumps(report, indent=1, ensure_ascii=False) + "\n")
    return path


def summary_text(report: dict, report_path: Path) -> str:
    """Return the few lines printed after a run, so Copilot rarely needs the JSON.

    Plain ASCII apart from names from the code: whoever reads the output may
    decode it with a different code page than Python wrote it in.
    """
    summary, limits = report["summary"], report["thresholds"]
    totals = (
        f"{_count(summary['files'], 'file')}, "
        f"{_count(summary['functions'], 'function')}, "
        f"{summary['loc']:,} lines of code"
    )
    danger = (
        f"more than {limits['max_loc']} lines of code and complexity over "
        f"{limits['max_complexity']}"
    )
    lines = [
        f"Fat Functions: {totals}.",
        f"Danger zone ({danger}): {_count(summary['danger_zone'], 'function')}.",
    ]
    offenders = report["offenders"][:SUMMARY_OFFENDERS]
    if offenders:
        lines.append("Worst offenders (ranked by lines of code times complexity):")
    for rank, function in enumerate(offenders, start=1):
        forgiven = ", Forgiven" if function["forgiven"] else ""
        lines.append(
            f"  {rank}. {function['name']}: {function['loc']:,} lines of code, "
            f"complexity {function['complexity']}, {LABELS[function['status']]}"
            f"{forgiven} ({function['file']}:{function['start_line']})"
        )
    not_measured = [
        _count(len(report["errors"]), "error"),
        _count(len(report["warnings"]), "warning"),
        _count(len(report["skipped_generated"]), "generated file") + " skipped",
    ]
    if report["errors"] or report["warnings"] or report["skipped_generated"]:
        lines.append(f"Not fully measured: {', '.join(not_measured)}; see report.json.")
    lines.append(f"Report: {report_path}")
    return "\n".join(lines)


def _count(number: int, noun: str) -> str:
    return f"{number:,} {noun}{'' if number == 1 else 's'}"


def _write_text(path: Path, text: str) -> None:
    # The same bytes on every OS: UTF-8 with "\n" line endings.
    with open(path, "w", encoding="utf-8", newline="\n") as file:
        file.write(text)
