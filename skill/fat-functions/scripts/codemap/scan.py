"""Find the source files to measure under a folder."""

from __future__ import annotations

import fnmatch
import os
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import pathspec

from codemap.measure import FileError, is_supported

# Folders of dependencies, environments, caches, build output and our reports.
SKIP_DIRS = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "__pycache__",
        "site-packages",
        "node_modules",
        "build",
        "dist",
        "target",
        ".fat-functions",
    }
)
# Files that look like source but are machine-written.
SKIP_FILES = ("*.min.js",)


@dataclass
class ScanResult:
    """The files to measure, and folders that could not be read."""

    files: list[Path]
    errors: list[FileError]


def scan(root: Path, exclude: Iterable[str] = ()) -> ScanResult:
    """Return the source files under `root` worth measuring, sorted by path.

    Skips SKIP_DIRS, SKIP_FILES, anything a `.gitignore` in `root` or below
    ignores, file types lizard cannot read, and anything matching `exclude`:
    `.gitignore`-style patterns relative to `root`, like "tests" or "src/old/".
    Decides by path only; measure.py decides by content (generated files).
    """
    user_rules = pathspec.GitIgnoreSpec.from_lines(exclude)
    rules: dict[Path, list[tuple[Path, pathspec.GitIgnoreSpec]]] = {}
    files: list[Path] = []
    errors: list[FileError] = []

    def relative(path: Path) -> str:
        return path.relative_to(root).as_posix()

    def on_walk_error(exc: OSError) -> None:
        reason = f"cannot read folder: {exc.strerror or exc}"
        errors.append(FileError(relative(Path(exc.filename)), reason))

    def ignored(path: Path, folder: Path, is_dir: bool) -> bool:
        suffix = "/" if is_dir else ""
        if user_rules.match_file(relative(path) + suffix):
            return True
        return any(
            spec.match_file(path.relative_to(base).as_posix() + suffix)
            for base, spec in rules[folder]
        )

    for folder_name, dir_names, file_names in os.walk(root, onerror=on_walk_error):
        folder = Path(folder_name)
        # A folder's rules are its parents' plus its own .gitignore, if any.
        rules[folder] = rules.get(folder.parent, []) if folder != root else []
        gitignore = folder / ".gitignore"
        if gitignore.is_file():
            try:
                lines = gitignore.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                on_walk_error(exc)
            else:
                spec = pathspec.GitIgnoreSpec.from_lines(lines.splitlines())
                rules[folder] = [*rules[folder], (folder, spec)]

        dir_names[:] = sorted(
            name
            for name in dir_names
            if name not in SKIP_DIRS and not ignored(folder / name, folder, True)
        )
        for name in sorted(file_names):
            path = folder / name
            if any(fnmatch.fnmatchcase(name, pattern) for pattern in SKIP_FILES):
                continue
            if is_supported(path) and not ignored(path, folder, False):
                files.append(path)

    files.sort(key=relative)
    errors.sort(key=lambda error: error.file)
    return ScanResult(files, errors)
