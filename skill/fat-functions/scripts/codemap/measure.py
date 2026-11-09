"""Measure the size and complexity of every function in source files."""

from __future__ import annotations

import contextlib
import io
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import lizard

ANONYMOUS = "(anonymous)"


@dataclass
class FunctionRecord:
    """One function: where it is, how big and how complex."""

    id: str
    name: str
    file: str
    start_line: int
    end_line: int
    loc: int  # code lines: no blank lines, comments or docstrings
    complexity: int
    params: int
    language: str
    status: str | None = None  # set by score.py


@dataclass
class FileRecord:
    """One measured source file and the functions in it."""

    file: str
    language: str
    loc: int
    functions: list[FunctionRecord]


@dataclass
class FileError:
    """A file that could not be measured, and why."""

    file: str
    error: str


@dataclass
class Measurement:
    """Everything measured in one run."""

    files: list[FileRecord]
    errors: list[FileError]


class MeasureError(Exception):
    """A file could not be measured."""


def measure(root: Path, paths: Iterable[Path]) -> Measurement:
    """Measure each file in `paths` (all inside `root`); never stop on a bad one."""
    relative = sorted((path.relative_to(root).as_posix(), path) for path in paths)
    files, errors = [], []
    for file, path in relative:
        try:
            # Same decoding on every OS; bad bytes cannot move line numbers.
            source = path.read_text(encoding="utf-8-sig", errors="replace")
        except OSError as exc:
            errors.append(FileError(file, f"cannot read file: {exc.strerror or exc}"))
            continue
        try:
            files.append(measure_source(file, source))
        except MeasureError as exc:
            errors.append(FileError(file, str(exc)))
        except Exception as exc:  # noqa: BLE001  a lizard bug must not stop the run
            message = f"lizard failed: {type(exc).__name__}: {exc}"
            errors.append(FileError(file, message))
    return Measurement(files, errors)


def measure_source(file: str, source: str) -> FileRecord:
    """Measure one file's text; `file` is its path relative to the root."""
    record = _from_lizard(file, source)
    functions = sorted(
        _drop_nested_duplicates(record.functions),
        key=lambda f: (f.start_line, -f.end_line, f.name),
    )
    _make_ids_unique(functions)
    record.functions = functions
    return record


def _from_lizard(file: str, source: str) -> FileRecord:
    """Run lizard on one file and convert its result to our records.

    The only code that knows about lizard (docs/DESIGN.md section 4).
    """
    reader = lizard.get_reader_for(file)
    if reader is None:
        raise MeasureError("unsupported file type")
    language = reader.language_names[0]
    # lizard reports some failures, like a RecursionError, only on stderr and
    # then returns partial results. Capture them so they become errors.
    lizard_errors = io.StringIO()
    with contextlib.redirect_stderr(lizard_errors):
        info = lizard.analyze_file.analyze_source_code(file, source)
    message = lizard_errors.getvalue().strip()
    if message:
        raise MeasureError(f"lizard: {message.splitlines()[0]}")
    functions = [
        FunctionRecord(
            id=f"{file}::{function.name}",
            name=function.name,
            file=file,
            start_line=function.start_line,
            end_line=function.end_line,
            loc=function.nloc,
            complexity=function.cyclomatic_complexity,
            params=function.parameter_count,
            language=language,
        )
        for function in info.function_list
    ]
    return FileRecord(file=file, language=language, loc=info.nloc, functions=functions)


def _drop_nested_duplicates(functions: list[FunctionRecord]) -> list[FunctionRecord]:
    """Keep one function per line range.

    A callback on the same line as the function around it, like the inner
    arrow in `const total = (c) => c.items.reduce((s, i) => s + i, 0);`, gets
    the same range and would be counted twice. Keep a named function over an
    anonymous one, then the outermost, which lizard reports last.
    """
    kept: dict[tuple[int, int], int] = {}
    for index, function in enumerate(functions):
        line_range = (function.start_line, function.end_line)
        previous = kept.get(line_range)
        keep_previous = (
            previous is not None
            and function.name == ANONYMOUS
            and functions[previous].name != ANONYMOUS
        )
        if not keep_previous:
            kept[line_range] = index
    return [functions[index] for index in sorted(kept.values())]


def _make_ids_unique(functions: list[FunctionRecord]) -> None:
    """Number repeated ids in source order: a.py::run, a.py::run#2, ..."""
    seen: dict[str, int] = {}
    for function in functions:
        count = seen[function.id] = seen.get(function.id, 0) + 1
        if count > 1:
            function.id = f"{function.id}#{count}"
