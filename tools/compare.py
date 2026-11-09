"""Show what changed on the test repositories since the accepted baseline.

Compares the reports in .test-repos-out/ with test-repos/baseline.json and
prints only the differences; --accept makes the current results the baseline.
Exits with 1 when anything differs, so a CI run notices. After
run_test_repos.py, from the repository root:

    python tools/compare.py [--only requests,flask] [--accept]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from repos import BASELINE, LOCAL_BASELINE, OUT, Repo, load_repos
from run_test_repos import RUN_INFO

SHOW = 10  # items listed for each kind of change; the rest are counted
LISTS = ("errors", "warnings", "skipped_generated", "forgiven")


def snapshot(report: dict, commit: str | None) -> dict:
    """The parts of a report.json the baseline keeps, in a stable order."""
    functions: dict[str, list[int]] = {}
    forgiven: list[str] = []
    nodes = [report["tree"]]
    while nodes:
        node = nodes.pop()
        if node["type"] == "function":
            functions[node["id"]] = [
                node["start_line"],
                node["end_line"],
                node["loc"],
                node["complexity"],
            ]
            if node["forgiven"]:
                forgiven.append(node["id"])
        nodes.extend(node.get("children", []))
    return {
        "commit": commit,
        "summary": report["summary"],
        "thresholds": report["thresholds"],
        "errors": sorted(f"{e['file']}: {e['error']}" for e in report["errors"]),
        "warnings": sorted(
            f"{w['file']}:{w['line']}: {w['warning']}" for w in report["warnings"]
        ),
        "skipped_generated": sorted(
            f"{g['file']}: {g['marker']}" for g in report["skipped_generated"]
        ),
        "forgiven": sorted(forgiven),
        "functions": dict(sorted(functions.items())),
    }


def differences(old: dict | None, new: dict) -> list[str]:
    """Describe what changed from `old` to `new`; empty when nothing did."""
    if old is None:
        return ["not in the baseline yet"]
    lines = []
    if old["commit"] != new["commit"]:
        lines.append(f"commit: {old['commit']} -> {new['commit']}")
    for group in ("summary", "thresholds"):
        for key in sorted(set(old[group]) | set(new[group])):
            before, after = old[group].get(key), new[group].get(key)
            if before != after:
                change = f" ({after - before:+,})" if _numbers(before, after) else ""
                lines.append(
                    f"{group} {key}: {_number(before)} -> {_number(after)}{change}"
                )
    for group in LISTS:
        before, after = set(old[group]), set(new[group])
        lines += _listed(f"{group} added", sorted(after - before))
        lines += _listed(f"{group} removed", sorted(before - after))
    before, after = old["functions"], new["functions"]
    changed = sorted(
        key for key in before.keys() & after.keys() if before[key] != after[key]
    )
    lines += _listed("functions added", sorted(after.keys() - before.keys()))
    lines += _listed("functions removed", sorted(before.keys() - after.keys()))
    lines += _listed(
        "functions changed",
        [
            f"{key}: {_describe(before[key])} -> {_describe(after[key])}"
            for key in changed
        ],
    )
    return lines


def dumps_baseline(baseline: dict) -> str:
    """JSON with one function, error or warning per line, so accepted changes
    give a readable git diff. The same baseline always gives the same text."""

    def value(item: object) -> str:
        return json.dumps(item, ensure_ascii=False, sort_keys=True)

    repos = []
    for name in sorted(baseline):
        fields = []
        for key, item in baseline[name].items():
            if isinstance(item, list) or key == "functions":
                lines = (
                    [f"   {value(k)}: {value(v)}" for k, v in item.items()]
                    if isinstance(item, dict)
                    else [f"   {value(v)}" for v in item]
                )
                brackets = "{}" if isinstance(item, dict) else "[]"
                inner = ",\n".join(lines)
                body = f"\n{inner}\n  " if lines else ""
                fields.append(f"  {value(key)}: {brackets[0]}{body}{brackets[1]}")
            else:
                fields.append(f"  {value(key)}: {value(item)}")
        repos.append(f" {value(name)}: {{\n" + ",\n".join(fields) + "\n }")
    return "{\n" + ",\n".join(repos) + "\n}\n" if repos else "{}\n"


def current(repo: Repo, out: Path = OUT) -> tuple[dict | None, str]:
    """Return a repository's latest results as a snapshot, or why there are none."""
    report_file, info_file = out / repo.name / "report.json", out / repo.name / RUN_INFO
    if not report_file.is_file() or not info_file.is_file():
        return None, "no results: run tools/run_test_repos.py"
    commit = json.loads(info_file.read_text(encoding="utf-8"))["commit"]
    if commit != repo.commit:
        return None, f"results are for {commit}, the list says {repo.commit}: run again"
    report = json.loads(report_file.read_text(encoding="utf-8"))
    return snapshot(report, commit), ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", default="", help="comma-separated repo names")
    parser.add_argument(
        "--accept", action="store_true", help="make these results the baseline"
    )
    args = parser.parse_args(argv)
    only = [name for name in args.only.split(",") if name]
    repos = load_repos(only)
    baselines = {False: _load(BASELINE), True: _load(LOCAL_BASELINE)}

    differing = 0
    for repo in repos:
        baseline = baselines[repo.private]
        results, problem = current(repo)
        if results is None:
            print(f"{repo.name}: {problem}")
            differing += 1
            continue
        lines = differences(baseline.get(repo.name), results)
        print(f"{repo.name}: {'no changes' if not lines else 'changed'}")
        for line in lines:
            print(f"  {line}")
        differing += bool(lines)
        if args.accept:
            baseline[repo.name] = results

    if not args.accept:
        return 1 if differing else 0
    if not only:  # forget repositories no longer listed
        listed = {repo.name for repo in repos}
        for baseline in baselines.values():
            for name in [name for name in baseline if name not in listed]:
                del baseline[name]
    _write(BASELINE, baselines[False])
    if baselines[True] or LOCAL_BASELINE.exists():
        _write(LOCAL_BASELINE, baselines[True])
    print(f"Accepted as the baseline: {BASELINE}")
    return 0


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def _write(path: Path, baseline: dict) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as file:
        file.write(dumps_baseline(baseline))


def _listed(title: str, items: list[str]) -> list[str]:
    if not items:
        return []
    shown = [f"  {item}" for item in items[:SHOW]]
    more = [f"  ... and {len(items) - SHOW:,} more"] if len(items) > SHOW else []
    return [f"{title} ({len(items):,}):", *shown, *more]


def _describe(values: list[int]) -> str:
    start, end, loc, complexity = values
    return f"lines {start}-{end}, {loc} loc, complexity {complexity}"


def _numbers(*values: object) -> bool:
    return all(isinstance(v, int) and not isinstance(v, bool) for v in values)


def _number(value: object) -> str:
    return f"{value:,}" if _numbers(value) else str(value)


if __name__ == "__main__":
    sys.exit(main())
