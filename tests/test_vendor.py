"""Checks that the bundled vendor/ folder matches VERSIONS.txt and imports."""

import os
import subprocess
import sys
import zipfile

import pytest

from update_vendor import (
    ECHARTS,
    ECHARTS_FILES,
    PURE_PYTHON_TAG,
    VENDOR,
    VERSIONS_FILE,
    license_files,
    read_pins,
    vendored_python_packages,
    wheels,
)

PINS = read_pins()


def test_read_pins_skips_comments_and_normalizes_names(tmp_path):
    pins_file = tmp_path / "VERSIONS.txt"
    pins_file.write_text(
        "# header\n\nPygments==2.21.0  # BSD\nsome_pkg == 1.0\n", encoding="utf-8"
    )
    assert read_pins(pins_file) == {"pygments": "2.21.0", "some-pkg": "1.0"}


def test_read_pins_rejects_unpinned_lines(tmp_path):
    pins_file = tmp_path / "VERSIONS.txt"
    pins_file.write_text("lizard>=1.0\n", encoding="utf-8")
    with pytest.raises(ValueError, match="line 1"):
        read_pins(pins_file)


def test_license_files_takes_dist_info_licenses_only(tmp_path):
    wheel = tmp_path / "Some_Pkg-1.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("some_pkg/__init__.py", "")
        archive.writestr("some_pkg-1.0.dist-info/METADATA", "")
        archive.writestr("some_pkg-1.0.dist-info/licenses/LICENSE", "MIT")
        archive.writestr("some_pkg-1.0.dist-info/licenses/AUTHORS.md", "Ann")
        archive.writestr("some_pkg-1.0.dist-info/licenses/sub/NOTICE", "N")
    assert license_files(wheel) == {
        "some-pkg-AUTHORS.md": b"Ann",
        "some-pkg-LICENSE.txt": b"MIT",
        "some-pkg-sub-NOTICE.txt": b"N",
    }


def test_vendor_holds_only_expected_files():
    expected = {VERSIONS_FILE.name, *ECHARTS_FILES.values()}
    for wheel in wheels():
        expected.add(wheel.name)
        expected.update(license_files(wheel))
    assert {entry.name for entry in VENDOR.iterdir()} == expected


def test_vendored_python_packages_match_pins():
    expected = {name: version for name, version in PINS.items() if name != ECHARTS}
    assert vendored_python_packages() == expected


def test_wheels_are_pure_python():
    assert wheels()
    for wheel in wheels():
        assert wheel.name.endswith(PURE_PYTHON_TAG), wheel.name


def test_wheels_hold_only_python_code():
    # Importing from a zip only works for code that never needs a real file on
    # disk, so no C extensions, data files or .data/ install folders.
    # py.typed is a marker that only type checkers read.
    for wheel in wheels():
        with zipfile.ZipFile(wheel) as archive:
            for name in archive.namelist():
                top = name.split("/", 1)[0]
                if top.endswith(".dist-info"):
                    continue
                assert not top.endswith(".data"), f"{wheel.name}: {name}"
                assert name.endswith((".py", "/py.typed")), f"{wheel.name}: {name}"


def test_license_files_sit_next_to_their_wheels():
    for wheel in wheels():
        copies = license_files(wheel)
        assert any("LICENSE" in n or "COPYING" in n for n in copies), wheel.name
        for name, content in copies.items():
            assert (VENDOR / name).read_bytes() == content, name


def test_echarts_matches_pin_and_keeps_its_license():
    for name in ECHARTS_FILES.values():
        assert (VENDOR / name).stat().st_size > 0, name
    script = (VENDOR / "echarts.min.js").read_text(encoding="utf-8")
    assert f'"{PINS[ECHARTS]}"' in script


def test_packages_import_from_the_wheels():
    # A fresh, isolated interpreter with only the wheels added to sys.path, as
    # fat_functions.py will run, so packages from the dev venv cannot leak in.
    code = (
        "import sys; sys.path[0:0] = sys.argv[1:]; "
        "import lizard, pathspec, pygments; "
        "print('\\n'.join(m.__file__ for m in (lizard, pathspec, pygments)))"
    )
    wheel_paths = [str(wheel) for wheel in wheels()]
    result = subprocess.run(
        [sys.executable, "-I", "-c", code, *wheel_paths],
        capture_output=True,
        text=True,
        check=True,
    )
    module_files = result.stdout.splitlines()
    assert len(module_files) == 3
    for module_file in module_files:
        assert any(module_file.startswith(w + os.sep) for w in wheel_paths), module_file
