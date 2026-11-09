"""Fat Functions: find the functions worth splitting, as a map of the code.

Usage: python fat_functions.py [path] [options]. Writes report.html and
report.json into <path>/.fat-functions/, prints a short summary and opens the
report in the browser. See docs/DESIGN.md.
"""

from __future__ import annotations

import argparse
import sys
import webbrowser
from pathlib import Path

# Find codemap/ next to this script even when Python leaves the script's folder
# off sys.path (python -I or -P, the embeddable Windows Python).
sys.path.insert(0, str(Path(__file__).resolve().parent))

from codemap.measure import measure
from codemap.render import build_report, summary_text, write_report
from codemap.scan import scan
from codemap.score import Thresholds, score
from codemap.tree import build_tree

REPORT_FOLDER = ".fat-functions"


def main(argv: list[str] | None = None) -> int:
    """Measure the folder in `argv`, write the report and print the summary."""
    args = _parse_args(argv)
    root = Path(args.path).resolve()
    if not root.is_dir():
        print(f"fat_functions.py: not a folder: {args.path}", file=sys.stderr)
        return 2
    out_dir = Path(args.out) if args.out else root / REPORT_FOLDER
    thresholds = Thresholds(args.max_loc, args.max_complexity)

    scanned = scan(root, args.exclude)
    measured = measure(root, scanned.files, include_generated=args.include_generated)
    functions = [function for file in measured.files for function in file.functions]
    scores = score(functions, thresholds)
    tree = build_tree(measured.files)
    report = build_report(measured, scanned.errors, scores, thresholds, tree)
    html_path, json_path = write_report(report, out_dir, root.name)
    print(summary_text(report, html_path, json_path))
    if not args.no_open:
        webbrowser.open(html_path.resolve().as_uri())
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    defaults = Thresholds()
    parser = argparse.ArgumentParser(
        prog="fat_functions.py",
        description="Measure function size and complexity and find what to split.",
    )
    parser.add_argument("path", nargs="?", default=".", help="folder to measure")
    parser.add_argument(
        "--out", help=f"folder for the report (default: <path>/{REPORT_FOLDER})"
    )
    parser.add_argument(
        "--exclude",
        nargs="+",
        action="extend",
        default=[],
        metavar="PATTERN",
        help='.gitignore-style patterns to skip, like "tests" or "src/old/"',
    )
    parser.add_argument(
        "--max-loc",
        type=int,
        default=defaults.max_loc,
        help="danger zone: more lines of code than this (default: %(default)s)",
    )
    parser.add_argument(
        "--max-complexity",
        type=int,
        default=defaults.max_complexity,
        help="danger zone: more complexity than this (default: %(default)s)",
    )
    parser.add_argument(
        "--include-generated",
        action="store_true",
        help="measure generated files instead of skipping them",
    )
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="do not open the report in the browser",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    # Function names can hold any character; never crash on a console that
    # cannot show one.
    sys.stdout.reconfigure(errors="replace")
    sys.exit(main())
