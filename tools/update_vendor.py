"""Re-create skill/fat-functions/scripts/vendor/ from the pins in its VERSIONS.txt.

Python packages are kept as the wheel files pip downloads, unmodified, and the
tool imports straight from them. Each wheel's license files are copied out next
to it so they can be read without unzipping. pip uses your pip configuration,
so the wheels come from the package index you normally use. ECharts comes from
jsDelivr's copy of the npm package. Run from the dev virtual environment:

    python tools/update_vendor.py
"""

import importlib.metadata
import re
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent.parent
VENDOR = ROOT / "skill" / "fat-functions" / "scripts" / "vendor"
VERSIONS_FILE = VENDOR / "VERSIONS.txt"

# Oldest Python the tool supports; pip refuses pins that need a newer one.
MIN_PYTHON = "3.9"

ECHARTS = "echarts"
ECHARTS_URL = "https://cdn.jsdelivr.net/npm/echarts@{version}/{path}"
# Path inside the npm package -> file name in vendor/.
ECHARTS_FILES = {
    "dist/echarts.min.js": "echarts.min.js",
    "LICENSE": "echarts-LICENSE.txt",
    "NOTICE": "echarts-NOTICE.txt",
}

# Wheels with this ending hold only Python code, so they run on every OS and
# can be imported straight from the zip.
PURE_PYTHON_TAG = "-none-any.whl"


def normalize(name: str) -> str:
    """Return a package name in PEP 503 normalized form."""
    return re.sub(r"[-_.]+", "-", name).lower()


def read_pins(path: Path = VERSIONS_FILE) -> dict[str, str]:
    """Return {normalized name: version} for every `name==version` line."""
    pins = {}
    lines = path.read_text(encoding="utf-8").splitlines()
    for number, raw in enumerate(lines, start=1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        name, separator, version = line.partition("==")
        name, version = normalize(name.strip()), version.strip()
        if not (name and separator and version):
            raise ValueError(f"{path.name} line {number}: expected name==version")
        pins[name] = version
    return pins


def wheels(vendor: Path = VENDOR) -> list[Path]:
    """Return the wheel files in vendor/, sorted by name."""
    return sorted(vendor.glob("*.whl"))


def vendored_python_packages(vendor: Path = VENDOR) -> dict[str, str]:
    """Return {normalized name: version} for the wheels in vendor/."""
    paths = [str(wheel) for wheel in wheels(vendor)]
    return {
        normalize(dist.metadata["Name"]): dist.version
        for dist in importlib.metadata.distributions(path=paths)
    }


def license_files(wheel: Path) -> dict[str, bytes]:
    """Return {vendor/ file name: content} for the license files inside a wheel.

    Reads `*.dist-info/licenses/`; `pygments-2.21.0.dist-info/licenses/AUTHORS`
    becomes `pygments-AUTHORS.txt`.
    """
    package = normalize(wheel.name.split("-", 1)[0])
    copies = {}
    with zipfile.ZipFile(wheel) as archive:
        for member in sorted(archive.namelist()):
            _, marker, relative = member.partition(".dist-info/licenses/")
            if not marker or not relative or member.endswith("/"):
                continue
            name = f"{package}-{relative.replace('/', '-')}"
            if not PurePosixPath(name).suffix:
                name += ".txt"
            copies[name] = archive.read(member)
    return copies


def clear_vendor() -> None:
    """Delete everything in vendor/ except VERSIONS.txt."""
    for entry in VENDOR.iterdir():
        if entry == VERSIONS_FILE:
            continue
        if entry.is_dir():
            shutil.rmtree(entry)
        else:
            entry.unlink()


def download_python_packages(pins: dict[str, str]) -> None:
    """Download the pinned packages, and any they depend on, into vendor/."""
    requirements = [f"{name}=={version}" for name, version in sorted(pins.items())]
    command = [
        sys.executable,
        "-m",
        "pip",
        "download",
        "--dest",
        str(VENDOR),
        "--python-version",
        MIN_PYTHON,
        "--only-binary=:all:",
        "--disable-pip-version-check",
        *requirements,
    ]
    subprocess.run(command, check=True)


def copy_license_files() -> None:
    """Write each wheel's license files into vendor/ next to the wheel."""
    for wheel in wheels():
        copies = license_files(wheel)
        if not copies:
            sys.exit(f"{wheel.name} has no .dist-info/licenses/ files to copy")
        for name, content in copies.items():
            (VENDOR / name).write_bytes(content)


def download_echarts(version: str) -> None:
    """Download echarts.min.js and its LICENSE and NOTICE into vendor/."""
    for source, target in ECHARTS_FILES.items():
        url = ECHARTS_URL.format(version=version, path=source)
        print(f"Downloading {url}")
        with urllib.request.urlopen(url, timeout=60) as response:
            (VENDOR / target).write_bytes(response.read())


def main() -> int:
    pins = read_pins()
    if ECHARTS not in pins:
        sys.exit(f"{VERSIONS_FILE.name} must pin {ECHARTS}")
    python_pins = {name: v for name, v in pins.items() if name != ECHARTS}

    clear_vendor()
    download_python_packages(python_pins)
    download_echarts(pins[ECHARTS])

    not_pure = [w.name for w in wheels() if not w.name.endswith(PURE_PYTHON_TAG)]
    if not_pure:
        sys.exit(f"Not pure-Python, so cannot ship: {', '.join(not_pure)}")
    downloaded = vendored_python_packages()
    if downloaded != python_pins:
        sys.exit(
            f"pip downloaded {downloaded}, but {VERSIONS_FILE.name} pins "
            f"{python_pins}. Pin every package pip downloads."
        )
    copy_license_files()
    size = sum(f.stat().st_size for f in VENDOR.iterdir())
    print(f"Vendored {', '.join(f'{n}=={v}' for n, v in sorted(pins.items()))}")
    print(f"vendor/ is {size / 1_000_000:.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
