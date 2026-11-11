"""Tests for report.html: one self-contained page with the report inside."""

import json
import re
import shutil
import subprocess

import pytest

from codemap.render import ECHARTS, TEMPLATE, report_html, summary_text

HOSTILE = '<img src=x onerror="alert(1)"></script><script>alert(2)</script><!--'


def small_report(name="build", file="billing.py"):
    function = {
        "id": f"{file}::{name}",
        "name": name,
        "value": 10,
        "start_line": 2,
        "end_line": 11,
        "loc": 10,
        "complexity": 5,
        "params": 3,
        "forgiven": False,
        "status": "ok",
    }
    record = {**function, "file": file, "language": "python"}
    del record["value"]
    tree = {
        "type": "folder",
        "name": "<root>",
        "path": "",
        "value": 10,
        "children": [
            {
                "type": "file",
                "name": file,
                "path": file,
                "language": "python",
                "value": 10,
                "children": [{"type": "function", **function}],
            }
        ],
    }
    return {
        "summary": {"files": 1, "functions": 1, "loc": 10, "danger_zone": 0},
        "thresholds": {"max_loc": 50, "max_complexity": 10},
        "offenders": [record],
        "tree": tree,
        "errors": [{"file": file, "error": name}],
        "warnings": [{"file": file, "line": 3, "warning": name}],
        "skipped_generated": [{"file": file, "marker": name}],
    }


def scripts(html):
    """Return the text of each <script> element, in order."""
    return re.findall(r"<script[^>]*>(.*?)</script>", html, flags=re.DOTALL)


def embedded(html):
    """Return the JSON the page reads its data from."""
    match = re.search(
        r'<script type="application/json" id="report-data">(.*?)</script>',
        html,
        re.DOTALL,
    )
    return json.loads(match.group(1))


def test_the_page_carries_the_report_and_echarts_and_nothing_else():
    report = small_report()
    html = report_html(report, "shop")

    assert embedded(html) == {"project": "shop", "report": report}
    assert ECHARTS.read_text(encoding="utf-8") in html
    # Three scripts: the data, ECharts and the page's own code. Nothing is
    # loaded from elsewhere: no src or href, no stylesheets, no web fonts.
    assert len(scripts(html)) == html.count("<script") == 3
    assert not re.search(
        r"\b(src|href)\s*=", html.replace(ECHARTS.read_text(encoding="utf-8"), "")
    )
    assert "<link" not in html
    assert "{{" not in html


def test_names_from_the_code_cannot_end_the_data_block():
    report = small_report(name=HOSTILE, file=f"a/{HOSTILE}.py")
    html = report_html(report, HOSTILE)

    assert len(scripts(html)) == html.count("<script") == 3
    data = scripts(html)[0]
    assert "<" not in data
    assert embedded(html) == {"project": HOSTILE, "report": report}


def test_colors_come_only_from_css_variables():
    # So the VS Code extension can map every color to the editor theme.
    template = TEMPLATE.read_text(encoding="utf-8")
    for match in re.finditer(r"#[0-9a-fA-F]{3,8}\b|rgba?\(\s*\d", template):
        declaration = re.split(r"[;{\n]", template[: match.start()])[-1].strip()
        assert declaration.startswith("--"), template[match.start() - 40 : match.end()]


@pytest.mark.skipif(shutil.which("node") is None, reason="needs Node.js")
def test_page_script_is_valid_javascript(tmp_path):
    page_script = tmp_path / "page.js"
    page_script.write_text(
        scripts(report_html(small_report(), "shop"))[-1], encoding="utf-8"
    )
    result = subprocess.run(
        ["node", "--check", str(page_script)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_summary_names_the_first_five_of_each_kind_not_measured(tmp_path):
    report = small_report()
    report["skipped_generated"] = [
        {"file": f"gen{n}.py", "marker": "DO NOT EDIT"} for n in range(7)
    ]
    lines = summary_text(report, tmp_path / "r.html", tmp_path / "r.json").splitlines()
    skipped = [line for line in lines if line.startswith("  generated, skipped: ")]
    assert skipped[0] == '  generated, skipped: gen0.py ("DO NOT EDIT")'
    assert len(skipped) == 5
    assert "  ... and 2 more of this kind in the report" in lines
    assert (
        "  1. build: 10 lines of code, complexity 5, Simple (billing.py:2-11)" in lines
    )
