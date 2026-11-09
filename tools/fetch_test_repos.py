"""Clone or update the test repositories into .test-repos/, at their pinned commits.

Only the pinned commit is fetched (no history), so even large repositories are
quick. Run from the repository root:

    python tools/fetch_test_repos.py [--only requests,flask]
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

from repos import Repo, load_repos

# Same bytes on every OS, and no trouble with long paths on Windows.
GIT = ["git", "-c", "core.autocrlf=false", "-c", "core.longpaths=true"]


def fetch(repo: Repo) -> str:
    """Bring one clone to its pinned commit; return what was done."""
    if repo.url is None:
        return f"{repo.name}: measured in place at {repo.path}"
    if head(repo) == repo.commit:
        return f"{repo.name}: already at {repo.commit[:12]}"
    repo.path.mkdir(parents=True, exist_ok=True)
    git(repo, "init", "--quiet")
    git(repo, "fetch", "--quiet", "--depth", "1", repo.url, repo.commit)
    git(
        repo,
        "-c",
        "advice.detachedHead=false",
        "checkout",
        "--quiet",
        "--force",
        "FETCH_HEAD",
    )
    git(repo, "clean", "--quiet", "-dffx")
    if head(repo) != repo.commit:
        raise RuntimeError(f"{repo.name}: ended at {head(repo)}, not {repo.commit}")
    return f"{repo.name}: fetched {repo.commit[:12]}"


def head(repo: Repo) -> str | None:
    """Return the commit a clone is at, or None if there is no clone."""
    if not (repo.path / ".git").is_dir():
        return None
    result = subprocess.run(
        [*GIT, "-C", str(repo.path), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def git(repo: Repo, *args: str) -> None:
    subprocess.run([*GIT, "-C", str(repo.path), *args], check=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", default="", help="comma-separated repo names")
    args = parser.parse_args(argv)
    repos = load_repos([name for name in args.only.split(",") if name])

    failed = 0
    with ThreadPoolExecutor(max_workers=4) as pool:
        for outcome in pool.map(_try_fetch, repos):
            failed += outcome.startswith("FAILED")
            print(outcome)
    return 1 if failed else 0


def _try_fetch(repo: Repo) -> str:
    try:
        return fetch(repo)
    except (OSError, subprocess.CalledProcessError, RuntimeError) as exc:
        return f"FAILED {repo.name}: {exc}"


if __name__ == "__main__":
    sys.exit(main())
