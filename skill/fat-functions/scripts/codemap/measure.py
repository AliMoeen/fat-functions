"""Measure the size and complexity of every function in source files."""

from __future__ import annotations

import contextlib
import io
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

import lizard

ANONYMOUS = "(anonymous)"

# Generated files say so in their first lines; only these lines are checked.
HEADER_LINES = 10
# How tools mark the files they write. The earliest match in the header wins.
GENERATED_MARKERS = re.compile(
    r"GENERATED CODE"  # lizard's own marker; Dart's build_runner
    r"|DO NOT EDIT(?! THIS LINE)"  # Go, protobuf, gRPC; not bump2version's lines
    r"|@generated"  # Meta's convention: Relay, Hack, Buck and others
    r"|(?i:auto-?generated|automatically generated)"  # .NET, pygments, many more
)


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
    forgiven: bool = False  # marked "#lizard forgive"; measured all the same
    status: str | None = None  # set by score.py


@dataclass
class FileWarning:
    """Something in a file that limits what could be measured."""

    file: str
    line: int
    warning: str


@dataclass
class FileRecord:
    """One measured source file and the functions in it."""

    file: str
    language: str
    loc: int
    functions: list[FunctionRecord]
    warnings: list[FileWarning] = field(default_factory=list)


@dataclass
class FileError:
    """A file that could not be measured, and why."""

    file: str
    error: str


@dataclass
class GeneratedFile:
    """A file left out because its first lines say it was generated."""

    file: str
    marker: str


@dataclass
class Measurement:
    """Everything measured in one run."""

    files: list[FileRecord]
    errors: list[FileError]
    skipped_generated: list[GeneratedFile]

    @property
    def warnings(self) -> list[FileWarning]:
        """Every file's warnings, in file order."""
        return [warning for file in self.files for warning in file.warnings]


class MeasureError(Exception):
    """A file could not be measured."""


def measure(
    root: Path, paths: Iterable[Path], include_generated: bool = False
) -> Measurement:
    """Measure each file in `paths` (all inside `root`); never stop on a bad one.

    Files whose first lines say they were generated go in `skipped_generated`
    instead, unless `include_generated` is set.
    """
    relative = sorted((path.relative_to(root).as_posix(), path) for path in paths)
    files, errors, skipped = [], [], []
    for file, path in relative:
        try:
            # Same decoding on every OS; bad bytes cannot move line numbers.
            source = path.read_text(encoding="utf-8-sig", errors="replace")
        except OSError as exc:
            errors.append(FileError(file, f"cannot read file: {exc.strerror or exc}"))
            continue
        marker = generated_marker(source)
        if marker and not include_generated:
            skipped.append(GeneratedFile(file, marker))
            continue
        try:
            files.append(measure_source(file, source))
        except MeasureError as exc:
            errors.append(FileError(file, str(exc)))
        except Exception as exc:  # noqa: BLE001  a lizard bug must not stop the run
            message = f"lizard failed: {type(exc).__name__}: {exc}"
            errors.append(FileError(file, message))
    return Measurement(files, errors, skipped)


def generated_marker(source: str) -> str | None:
    """Return the text in the file's first lines that says it was generated."""
    header = "\n".join(source.split("\n", HEADER_LINES)[:HEADER_LINES])
    match = GENERATED_MARKERS.search(header)
    return match.group(0) if match else None


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


def blank(text: str, phrase: str) -> str:
    """Replace `phrase` with spaces of the same length; no line or column moves."""
    return text.replace(phrase, " " * len(phrase))


# --- lizard ------------------------------------------------------------------
# The only code that knows about lizard (docs/DESIGN.md section 4). Swapping
# the parser means rewriting this section and nothing else.

# A comment containing this makes lizard stop reading the file.
LIZARD_STOP = "GENERATED CODE"
# A comment starting "#lizard forgive" makes lizard leave a function out.
LIZARD_FORGIVE = "lizard forgive"
LIZARD_STOP_WARNING = (
    'lizard stops reading at this "GENERATED CODE" comment: functions after it'
    " are not measured (in Python, nor the one it is in or follows)"
)


def is_supported(path: Path) -> bool:
    """Whether lizard can measure a file with this name."""
    return lizard.get_reader_for(path.name) is not None


def _from_lizard(file: str, source: str) -> FileRecord:
    """Run lizard on one file and convert its result to our records."""
    reader = lizard.get_reader_for(file)
    if reader is None:
        raise MeasureError("unsupported file type")
    language = reader.language_names[0]
    # The header is ours: a marker there means the whole file is generated, and
    # measure() has chosen to include it, so let lizard read past it.
    lines = source.split("\n", HEADER_LINES)
    lines[:HEADER_LINES] = [blank(line, LIZARD_STOP) for line in lines[:HEADER_LINES]]
    source = "\n".join(lines)

    warnings = []
    stop_line = _lizard_stop_line(reader(lizard.FileInfoBuilder(file)), source)
    if stop_line is not None:
        warnings.append(FileWarning(file, stop_line, LIZARD_STOP_WARNING))

    info = _run_lizard(file, source)
    forgiven: set[tuple[str, int, int]] = set()
    if LIZARD_FORGIVE in source:
        # Measure forgiven functions anyway. Blanking the directive keeps every
        # line in place; the functions only that run finds are the forgiven ones.
        kept_by_lizard = _function_keys(info)
        info = _run_lizard(file, blank(source, LIZARD_FORGIVE))
        forgiven = _function_keys(info) - kept_by_lizard

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
            forgiven=_key(function) in forgiven,
        )
        for function in info.function_list
    ]
    return FileRecord(file, language, info.nloc, functions, warnings)


def _run_lizard(file: str, source: str) -> lizard.FileInformation:
    """Analyze one file's text; raise MeasureError if lizard reports a failure."""
    # lizard reports some failures, like a RecursionError, only on stderr and
    # then returns partial results. Capture them so they become errors.
    lizard_errors = io.StringIO()
    with contextlib.redirect_stderr(lizard_errors):
        info = lizard.analyze_file.analyze_source_code(file, source)
    message = lizard_errors.getvalue().strip()
    if message:
        raise MeasureError(f"lizard: {message.splitlines()[0]}")
    return info


def _key(function) -> tuple[str, int, int]:
    """Identify a lizard function across two runs on the same file."""
    return (function.name, function.start_line, function.end_line)


def _function_keys(info: lizard.FileInformation) -> set[tuple[str, int, int]]:
    return {_key(function) for function in info.function_list}


def _lizard_stop_line(reader, source: str) -> int | None:
    """Return the line of the comment where lizard stops reading, if any.

    Uses lizard's own tokens and comment rules, so the phrase in a string, or
    in a comment style lizard does not see, does not count.
    """
    if LIZARD_STOP not in source:
        return None
    line = 1
    for token in lizard.preprocessing(reader.generate_tokens(source), reader):
        comment = reader.get_comment_from_token(token)
        if comment is not None and LIZARD_STOP in comment:
            return line + comment[: comment.index(LIZARD_STOP)].count("\n")
        line += token.count("\n")
    return None
