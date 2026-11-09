"""The test repositories: where they are listed, cloned, measured and recorded.

Shared by fetch_test_repos.py, run_test_repos.py and compare.py.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

ROOT = Path(__file__).resolve().parent.parent
LISTS = ROOT / "test-repos"
REPOS_FILE = LISTS / "repos.toml"
# Private repositories: never committed, kept out of baseline.json.
LOCAL_REPOS_FILE = LISTS / "repos.local.toml"
BASELINE = LISTS / "baseline.json"
LOCAL_BASELINE = LISTS / "baseline.local.json"
CLONES = ROOT / ".test-repos"
OUT = ROOT / ".test-repos-out"
SCRIPT = ROOT / "skill" / "fat-functions" / "scripts" / "fat_functions.py"

NAME = re.compile(r"[a-z0-9][a-z0-9._-]*")
COMMIT = re.compile(r"[0-9a-f]{40}")


@dataclass
class Repo:
    """One test repository and where its code is on disk."""

    name: str
    path: Path
    url: str | None = None  # None: an existing checkout, measured in place
    commit: str | None = None
    private: bool = False


def load_repos(
    only: Iterable[str] = (),
    repos_file: Path = REPOS_FILE,
    local_file: Path = LOCAL_REPOS_FILE,
    clones: Path = CLONES,
) -> list[Repo]:
    """Return the listed repositories (all, or those named in `only`) in list order."""
    repos = _read(repos_file, clones, private=False)
    if local_file.is_file():
        repos += _read(local_file, clones, private=True)
    names = [repo.name for repo in repos]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        raise ValueError(f"listed more than once: {', '.join(duplicates)}")
    wanted = list(only)
    unknown = [name for name in wanted if name not in names]
    if unknown:
        raise ValueError(f"not in the lists: {', '.join(unknown)}")
    return [repo for repo in repos if not wanted or repo.name in wanted]


def _read(path: Path, clones: Path, private: bool) -> list[Repo]:
    with open(path, "rb") as file:
        entries = tomllib.load(file).get("repo", [])
    repos = []
    for entry in entries:
        name = entry.get("name", "")
        where = f"{path.name}, repo {name or '(no name)'}"
        if not NAME.fullmatch(name):
            raise ValueError(f"{where}: name must be lowercase letters, digits, . _ -")
        if "path" in entry and private:
            repos.append(Repo(name, Path(entry["path"]), private=True))
            continue
        url, commit = entry.get("url"), entry.get("commit", "")
        if not url:
            raise ValueError(
                f"{where}: needs a url and commit" + (" or a path" if private else "")
            )
        if not COMMIT.fullmatch(commit):
            raise ValueError(f"{where}: commit must be a full 40-character commit hash")
        repos.append(Repo(name, clones / name, url, commit, private))
    return repos
