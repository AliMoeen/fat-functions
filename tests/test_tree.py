"""Tests for codemap.tree. Line counts are hand-checked against the sources."""

from pathlib import Path

from codemap.measure import FileRecord, FunctionRecord, measure, measure_source
from codemap.score import Thresholds, score
from codemap.tree import build_tree, own_lines

MIXED = Path(__file__).parent / "fixtures" / "mixed_project"


def assert_adds_up(node):
    """Every folder's and file's value is the sum of its children's."""
    if "children" in node:
        assert node["value"] == sum(child["value"] for child in node["children"])
        for child in node["children"]:
            assert child["value"] >= 0
            assert_adds_up(child)


def blocks(file_node):
    return [(child["name"], child["value"]) for child in file_node["children"]]


def test_mixed_project_map():
    files = measure(MIXED, MIXED.iterdir()).files
    score([f for file in files for f in file.functions], Thresholds())
    tree = build_tree(files)

    assert_adds_up(tree)
    assert (tree["type"], tree["name"], tree["path"]) == ("folder", "<root>", "")
    assert tree["value"] == 44
    assert [(f["name"], f["value"], blocks(f)) for f in tree["children"]] == [
        # The class line and closing brace are module-level code.
        ("Order.java", 11, [("Order::shipping", 9), ("<module>", 2)]),
        ("billing.py", 13, [("build", 10), ("round_money", 2), ("<module>", 1)]),
        ("cart.js", 8, [("applyDiscount", 7), ("total", 1)]),
        ("summary.py", 5, [("describe", 5)]),
        ("user.ts", 7, [("validate", 5), ("<module>", 2)]),
    ]
    build = tree["children"][1]["children"][0]
    assert build == {
        "type": "function",
        "id": "billing.py::build",
        "name": "build",
        "value": 10,
        "start_line": 2,
        "end_line": 11,
        "loc": 10,
        "complexity": 5,
        "params": 3,
        "forgiven": False,
        "status": "ok",
    }


def test_folders_nest_by_path_and_add_up():
    files = [
        FileRecord("src/app/main.py", "python", 10, []),
        FileRecord("src/app/util.py", "python", 5, []),
        FileRecord("src/cli.py", "python", 3, []),
        FileRecord("setup.py", "python", 2, []),
    ]
    tree = build_tree(reversed(files))  # order of input does not matter

    assert_adds_up(tree)
    assert tree["value"] == 20
    src = tree["children"][1]
    assert [(n["type"], n["name"], n["path"]) for n in tree["children"]] == [
        ("file", "setup.py", "setup.py"),
        ("folder", "src", "src"),
    ]
    assert [(n["name"], n["path"], n["value"]) for n in src["children"]] == [
        ("app", "src/app", 15),
        ("cli.py", "src/cli.py", 3),
    ]
    assert [n["path"] for n in src["children"][0]["children"]] == [
        "src/app/main.py",
        "src/app/util.py",
    ]


def test_nested_functions_give_up_the_line_they_share():
    source = (
        "def outer():\n"  # outer
        "    a = 1\n"  # outer
        "    def inner():\n"  # counted for both by lizard
        "        b = 2\n"  # inner
        "        return b\n"  # inner
        "    c = 3\n"  # outer
        "    return a + c\n"  # outer
    )
    record = measure_source("n.py", source)
    assert [(f.name, f.loc) for f in record.functions] == [
        ("outer", 5),
        ("outer.inner", 3),
    ]
    file_node = build_tree([record])["children"][0]
    assert_adds_up(file_node)
    assert blocks(file_node) == [("outer", 4), ("outer.inner", 3)]
    assert file_node["value"] == record.loc == 7


def test_two_levels_of_nesting_and_callbacks():
    two_levels = (
        "def a():\n"
        "    x = 1\n"
        "    def b():\n"
        "        y = 2\n"
        "        def c():\n"
        "            return 3\n"
        "        return c\n"
        "    return b\n"
    )
    callback = (
        "function f(xs) {\n"
        "  xs.forEach(function (x) {\n"
        "    log(x);\n"
        "  });\n"
        "  return 1;\n"
        "}\n"
    )
    python, js = measure_source("a.py", two_levels), measure_source("f.js", callback)
    tree = build_tree([python, js])
    assert_adds_up(tree)
    # lizard names the innermost function "a.a.b.c" (DESIGN.md section 4).
    assert blocks(tree["children"][0]) == [("a", 3), ("a.b", 3), ("a.a.b.c", 2)]
    assert blocks(tree["children"][1]) == [("f", 3), ("(anonymous)", 3)]
    assert tree["value"] == 8 + 6


def test_module_block_holds_code_outside_functions():
    source = (
        "import os\n"
        "\n"
        "class A:\n"
        "    X = 1\n"
        "\n"
        "    def m(self):\n"
        "        return 1\n"
        "\n"
        "    def n(self):\n"
        "        return 2\n"
        "\n"
        "print(A)\n"
    )
    file_node = build_tree([measure_source("c.py", source)])["children"][0]
    # import, class, X = 1 and print are the 4 module-level lines of code.
    assert blocks(file_node) == [("m", 2), ("n", 2), ("<module>", 4)]


def test_values_never_go_negative_and_still_add_up():
    # Inconsistent input: the outer function counts fewer lines than the
    # nested functions that start inside it. Its value stops at 0.
    def function(name, start, end, loc):
        return FunctionRecord(
            f"x.js::{name}", name, "x.js", start, end, loc, 1, 0, "javascript"
        )

    record = FileRecord(
        "x.js",
        "javascript",
        2,
        [function("outer", 1, 5, 1), function("a", 2, 2, 1), function("b", 4, 4, 1)],
    )
    assert own_lines(record.functions) == {"x.js::outer": 0, "x.js::a": 1, "x.js::b": 1}
    file_node = build_tree([record])["children"][0]
    assert_adds_up(file_node)
    assert blocks(file_node) == [("outer", 0), ("a", 1), ("b", 1)]


def test_functions_starting_on_the_same_line_share_it_once():
    # At line level the shorter one sits inside the longer one, so each gives
    # up the shared line once: 1 + 1 + 1 lines for a 3-line file.
    def function(name, start, end, loc):
        return FunctionRecord(
            f"x.js::{name}", name, "x.js", start, end, loc, 1, 0, "javascript"
        )

    functions = [function("f", 1, 4, 2), function("a", 3, 3, 1), function("b", 3, 4, 2)]
    assert own_lines(functions) == {"x.js::f": 1, "x.js::b": 1, "x.js::a": 1}


def test_empty_project_gives_an_empty_root():
    assert build_tree([]) == {
        "type": "folder",
        "name": "<root>",
        "path": "",
        "value": 0,
        "children": [],
    }
