"""Tests for codemap.measure. Fixture numbers are hand-checked."""

import subprocess
import sys
from pathlib import Path

from codemap import VENDOR
from codemap import measure as measure_module
from codemap.measure import measure, measure_source

MIXED = Path(__file__).parent / "fixtures" / "mixed_project"


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
