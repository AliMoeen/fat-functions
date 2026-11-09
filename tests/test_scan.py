"""Tests for codemap.scan."""

import os
from pathlib import Path

from codemap.scan import scan

MIXED = Path(__file__).parent / "fixtures" / "mixed_project"


def make(root, *paths):
    """Create small files at the given /-separated paths under root."""
    for path in paths:
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("x = 1\n", encoding="utf-8")


def found(root, **kwargs):
    result = scan(root, **kwargs)
    assert result.errors == []
    return [path.relative_to(root).as_posix() for path in result.files]


def test_finds_the_mixed_project_sources_in_path_order():
    assert found(MIXED) == [
        "Order.java",
        "billing.py",
        "cart.js",
        "summary.py",
        "user.ts",
    ]


def test_keeps_only_file_types_lizard_reads(tmp_path):
    make(tmp_path, "a.py", "b.go", "README.md", "data.json", "Makefile", "c.tsx")
    assert found(tmp_path) == ["a.py", "b.go", "c.tsx"]


def test_skips_dependency_build_and_report_folders_at_any_depth(tmp_path):
    make(
        tmp_path,
        "app.py",
        "node_modules/lib/index.js",
        ".venv/lib/site.py",
        "src/build/out.py",
        "src/__pycache__/x.py",
        "web/dist/bundle.js",
        ".fat-functions/report.js",
        "src/target/Main.java",
        "src/main.py",
    )
    assert found(tmp_path) == ["app.py", "src/main.py"]


def test_skips_minified_javascript(tmp_path):
    make(tmp_path, "app.js", "app.min.js", "vendor/jquery.min.js")
    assert found(tmp_path) == ["app.js"]


def test_follows_gitignore_files_at_every_level(tmp_path):
    make(
        tmp_path,
        "keep.py",
        "scratch.py",
        "out/gen.py",
        "sub/local.py",
        "sub/keep.py",
        "sub/deeper/local.py",
        "local.py",
        "logs/keep_me.py",
        "logs/drop_me.py",
    )
    (tmp_path / ".gitignore").write_text(
        "# comment\nscratch.py\nout/\nlogs/*.py\n!logs/keep_me.py\n", encoding="utf-8"
    )
    (tmp_path / "sub" / ".gitignore").write_text("local.py\n", encoding="utf-8")
    assert found(tmp_path) == [
        "keep.py",
        "local.py",  # sub/.gitignore only applies inside sub/
        "logs/keep_me.py",
        "sub/keep.py",
    ]


def test_exclude_takes_gitignore_style_patterns(tmp_path):
    make(
        tmp_path,
        "app.py",
        "tests/test_app.py",
        "pkg/tests/test_pkg.py",
        "pkg/migrations/0001.py",
        "src/old/legacy.py",
        "src/old/keep/new.py",
        "src/core.py",
    )
    result = found(tmp_path, exclude=["tests", "migrations/", "src/old/*.py"])
    assert result == ["app.py", "src/core.py", "src/old/keep/new.py"]


def test_unreadable_folder_becomes_an_error_and_the_scan_continues(
    tmp_path, monkeypatch
):
    make(tmp_path, "a.py", "locked/b.py", "open/c.py")
    real_scandir = os.scandir

    def scandir(path="."):
        if Path(path).name == "locked":
            raise PermissionError(13, "Permission denied", str(path))
        return real_scandir(path)

    monkeypatch.setattr(os, "scandir", scandir)
    result = scan(tmp_path)

    assert [p.relative_to(tmp_path).as_posix() for p in result.files] == [
        "a.py",
        "open/c.py",
    ]
    assert [(e.file, e.error) for e in result.errors] == [
        ("locked", "cannot read folder: Permission denied")
    ]
