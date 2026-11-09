"""Tests for codemap.measure. Fixture numbers are hand-checked."""

import subprocess
import sys
from pathlib import Path

from codemap import VENDOR
from codemap import measure as measure_module
from codemap.measure import blank, measure, measure_source

MIXED = Path(__file__).parent / "fixtures" / "mixed_project"
# Pushes what follows past the first lines, where generated markers count.
PAST_HEADER = "\n" * 10


def function_rows(measurement):
    """Return (id, start, end, loc, complexity, params, language) per function."""
    return [
        (f.id, f.start_line, f.end_line, f.loc, f.complexity, f.params, f.language)
        for file in measurement.files
        for f in file.functions
    ]


def test_mixed_project_functions_match_hand_checked_numbers():
    result = measure(MIXED, MIXED.iterdir())
    assert result.errors == []
    assert function_rows(result) == [
        ("Order.java::Order::shipping", 2, 10, 9, 5, 2, "java"),
        ("billing.py::build", 2, 11, 10, 5, 3, "python"),  # params include self
        ("billing.py::round_money", 13, 14, 2, 1, 1, "python"),
        ("cart.js::applyDiscount", 1, 7, 7, 5, 2, "javascript"),
        ("cart.js::total", 8, 8, 1, 1, 1, "javascript"),
        ("summary.py::describe", 4, 15, 5, 2, 1, "python"),
        ("user.ts::validate", 2, 6, 5, 5, 1, "typescript"),
    ]


def test_mixed_project_files_match_hand_checked_numbers():
    result = measure(MIXED, MIXED.iterdir())
    assert [(f.file, f.language, f.loc) for f in result.files] == [
        ("Order.java", "java", 11),
        ("billing.py", "python", 13),
        ("cart.js", "javascript", 8),
        ("summary.py", "python", 5),  # only the 5 code lines of describe()
        ("user.ts", "typescript", 7),
    ]


def test_loc_skips_blank_lines_comments_and_docstrings():
    describe = measure(MIXED, [MIXED / "summary.py"]).files[0].functions[0]
    assert describe.end_line - describe.start_line + 1 == 12
    assert describe.loc == 5


def test_callback_on_the_same_line_as_its_function_is_dropped():
    source = "const total = (c) => c.items.reduce((s, i) => s + i.price, 0);\n"
    names = [f.name for f in measure_source("cart.js", source).functions]
    assert names == ["total"]


def test_callback_on_its_own_line_is_kept():
    source = (
        "const total = (c) => {\n"
        "  return c.items.reduce(\n"
        "    (s, i) => s + i.price, 0);\n"
        "};\n"
    )
    functions = measure_source("cart.js", source).functions
    assert [(f.name, f.start_line, f.end_line) for f in functions] == [
        ("total", 1, 4),
        ("(anonymous)", 3, 3),
    ]


def test_repeated_names_get_numbered_ids():
    source = (
        "class A:\n"
        "    def run(self):\n"
        "        def inner(x):\n"
        "            return x\n"
        "        return inner(1)\n"
        "\n"
        "\n"
        "class B:\n"
        "    def run(self):\n"
        "        pass\n"
    )
    functions = measure_source("jobs.py", source).functions
    assert [(f.id, f.name) for f in functions] == [
        ("jobs.py::run", "run"),
        ("jobs.py::run.inner", "run.inner"),
        ("jobs.py::run#2", "run"),
    ]


def test_empty_file_has_no_functions():
    record = measure_source("empty.py", "")
    assert (record.language, record.loc, record.functions) == ("python", 0, [])


def test_bad_files_become_errors_and_the_run_continues(tmp_path, capsys):
    (tmp_path / "ok.py").write_text("def ok():\n    return 1\n", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("not code\n", encoding="utf-8")
    # Nesting this deep makes lizard give up with a RecursionError.
    deep = "function f() {" + "{" * 3000 + "}" * 3000 + "}\n"
    (tmp_path / "deep.js").write_text(deep, encoding="utf-8")
    paths = [tmp_path / name for name in ("ok.py", "notes.txt", "deep.js", "gone.py")]

    result = measure(tmp_path, paths)

    assert [f.file for f in result.files] == ["ok.py"]
    errors = {e.file: e.error for e in result.errors}
    assert list(errors) == ["deep.js", "gone.py", "notes.txt"]
    assert errors["deep.js"].startswith("lizard: ")
    assert "RecursionError" in errors["deep.js"]
    assert errors["gone.py"].startswith("cannot read file: ")
    assert errors["notes.txt"] == "unsupported file type"
    assert capsys.readouterr().err == ""  # lizard's own message was captured


def test_unexpected_lizard_failure_becomes_an_error(tmp_path, monkeypatch):
    real_from_lizard = measure_module._from_lizard

    def crash_on_bad(file, source):
        if file == "bad.py":
            raise IndexError("list index out of range")
        return real_from_lizard(file, source)

    monkeypatch.setattr(measure_module, "_from_lizard", crash_on_bad)
    for name in ("bad.py", "good.py"):
        (tmp_path / name).write_text("def f():\n    return 1\n", encoding="utf-8")

    result = measure(tmp_path, tmp_path.iterdir())

    assert [f.file for f in result.files] == ["good.py"]
    assert [(e.file, e.error) for e in result.errors] == [
        ("bad.py", "lizard failed: IndexError: list index out of range")
    ]


def test_syntax_errors_do_not_stop_the_run(tmp_path):
    # lizard does not report syntax errors; see docs/DESIGN.md section 4.
    (tmp_path / "broken.py").write_text("def broken(:\n    if x\n", encoding="utf-8")
    (tmp_path / "ok.py").write_text("def ok():\n    return 1\n", encoding="utf-8")
    result = measure(tmp_path, tmp_path.iterdir())
    assert result.errors == []
    assert [f.id for f in result.files[1].functions] == ["ok.py::ok"]


def test_bom_crlf_non_english_and_non_utf8_files(tmp_path):
    bom_crlf = "\ufeffdef größe(x):\r\n    return x\r\n".encode()
    (tmp_path / "größe.py").write_bytes(bom_crlf)
    latin1 = "def f():\n    # café\n    return 1\n".encode("latin-1")
    (tmp_path / "latin1.py").write_bytes(latin1)

    result = measure(tmp_path, tmp_path.iterdir())

    assert result.errors == []
    assert function_rows(result) == [
        ("größe.py::größe", 1, 2, 2, 1, 1, "python"),
        ("latin1.py::f", 1, 3, 2, 1, 0, "python"),
    ]


def test_tests_use_the_vendored_lizard():
    module_file = Path(sys.modules["lizard"].__file__)
    assert VENDOR in module_file.parents, module_file


def test_engine_imports_lizard_and_pygments_from_the_vendored_wheels():
    # pytest imports its own pygments before any test runs, so check in a
    # fresh, isolated interpreter, the way fat_functions.py will run.
    code = (
        "import sys; sys.path.insert(0, sys.argv[1]); import codemap.measure; "
        "print('\\n'.join(sys.modules[m].__file__ for m in ('lizard', 'pygments')))"
    )
    scripts = str(VENDOR.parent)
    result = subprocess.run(
        [sys.executable, "-I", "-c", code, scripts],
        capture_output=True,
        text=True,
        check=True,
    )
    module_files = [Path(line) for line in result.stdout.splitlines()]
    assert len(module_files) == 2
    for module_file in module_files:
        assert VENDOR in module_file.parents, module_file


GENERATED = {
    "Model.cs": "// <auto-generated>\n//   Made by a tool.\n// </auto-generated>\n"
    "class A { int F() { return 1; } }\n",
    "dart_like.py": "# GENERATED CODE - DO NOT MODIFY BY HAND\ndef f():\n    return 1\n",
    "mapping.py": "# Automatically generated by scripts/gen.py.\n# DO NOT EDIT BY HAND.\n"
    "def f():\n    return 1\n",
    "pb.go": "// Code generated by protoc-gen-go. DO NOT EDIT.\n"
    "package p\nfunc F() int { return 1 }\n",
    "relay.js": "/**\n * @generated SignedSource<<abc>>\n */\nfunction f() { return 1; }\n",
    # Not generated: the marker is past the header, or is bump2version's.
    "late.py": PAST_HEADER + "# DO NOT EDIT\ndef f():\n    return 1\n",
    "version.py": '__version__ = "1.0"  # DO NOT EDIT THIS LINE MANUALLY\n'
    "def f():\n    return 1\n",
}


def test_generated_files_are_listed_with_the_text_that_marks_them(tmp_path):
    for name, text in GENERATED.items():
        (tmp_path / name).write_text(text, encoding="utf-8")

    result = measure(tmp_path, tmp_path.iterdir())

    assert [(g.file, g.marker) for g in result.skipped_generated] == [
        ("Model.cs", "auto-generated"),
        ("dart_like.py", "GENERATED CODE"),
        ("mapping.py", "Automatically generated"),
        ("pb.go", "DO NOT EDIT"),
        ("relay.js", "@generated"),
    ]
    assert [f.file for f in result.files] == ["late.py", "version.py"]


def test_include_generated_measures_generated_files_in_full(tmp_path):
    for name, text in GENERATED.items():
        (tmp_path / name).write_text(text, encoding="utf-8")

    result = measure(tmp_path, tmp_path.iterdir(), include_generated=True)

    assert result.skipped_generated == []
    assert result.warnings == []
    # dart_like.py starts with lizard's own marker, which would stop it reading.
    assert [(f.file, len(f.functions)) for f in result.files] == [
        ("Model.cs", 1),
        ("dart_like.py", 1),
        ("late.py", 1),
        ("mapping.py", 1),
        ("pb.go", 1),
        ("relay.js", 1),
        ("version.py", 1),
    ]


def test_generated_code_comment_later_on_gives_a_warning_with_its_line(tmp_path):
    source = (
        PAST_HEADER
        + "function a() { return 1; }\n// GENERATED CODE below\nfunction b() {}\n"
    )
    (tmp_path / "mixed.js").write_text(source, encoding="utf-8")

    result = measure(tmp_path, tmp_path.iterdir())

    assert [f.name for f in result.files[0].functions] == ["a"]
    assert [(w.file, w.line) for w in result.warnings] == [("mixed.js", 12)]
    assert "functions after it are not measured" in result.warnings[0].warning


def test_in_python_lizard_also_loses_the_function_before_the_stop():
    source = PAST_HEADER + (
        "def a():\n"
        "    return 1\n"
        "\n"
        "def b():\n"
        "    return 2\n"
        "\n"
        "# GENERATED CODE\n"
        "def c():\n"
        "    return 3\n"
    )
    record = measure_source("late.py", source)
    assert [f.name for f in record.functions] == ["a"]
    assert [w.line for w in record.warnings] == [17]


def test_generated_code_in_a_string_does_not_stop_lizard():
    source = (
        PAST_HEADER + 'def a():\n    return "GENERATED CODE"\n\ndef b():\n    pass\n'
    )
    record = measure_source("strings.py", source)
    assert [f.name for f in record.functions] == ["a", "b"]
    assert record.warnings == []


def test_forgiven_functions_are_measured_and_flagged():
    source = (
        "def a():\n"
        "    return 1\n"
        "\n"
        "def b(x):\n"
        "    #lizard forgive\n"
        "    if x:\n"
        "        return 2\n"
        "    return 3\n"
        "\n"
        "def c():\n"
        "    return 4\n"
    )
    functions = measure_source("jobs.py", source).functions
    # Hand-checked: blanking the comment moved no line.
    assert [
        (f.name, f.start_line, f.end_line, f.loc, f.complexity, f.forgiven)
        for f in functions
    ] == [
        ("a", 1, 2, 2, 1, False),
        ("b", 4, 8, 4, 2, True),
        ("c", 10, 11, 2, 1, False),
    ]


def test_forgive_follows_lizards_rules_for_each_language():
    source = (
        "function a() {\n"
        "  // #lizard forgive\n"
        "  return 1;\n"
        "}\n"
        "function b() {\n"
        "  // lizard forgive\n"  # without "#", lizard ignores it
        "  return 2;\n"
        "}\n"
    )
    functions = measure_source("app.js", source).functions
    assert [(f.name, f.forgiven) for f in functions] == [("a", True), ("b", False)]


def test_blank_keeps_every_line_and_column_in_place():
    source = "def b():\n    #lizard forgive\n    return 2  # lizard forgive\n"
    blanked = blank(source, "lizard forgive")
    assert "lizard forgive" not in blanked
    assert len(blanked) == len(source)
    newlines = [i for i, char in enumerate(source) if char == "\n"]
    assert [i for i, char in enumerate(blanked) if char == "\n"] == newlines
