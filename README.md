# Fat Functions

Find the functions that are too big and too complex, see where they live, and fix the worst first.

A code health map that runs locally, costs nothing, needs no account, and tells Copilot what to fix. Works with Python, JavaScript, TypeScript, Java and more.

**Status:** in progress. The tool measures a folder and writes `report.json` with a short summary; the interactive HTML report comes next. See [`docs/DESIGN.md`](docs/DESIGN.md) for the full design and [`docs/report-prototype.html`](docs/report-prototype.html) for the report prototype (download and open it in a browser).

## Usage

You need Python 3.9 or newer, and nothing else: the tool brings its own copies of what it uses.

```bash
python skill/fat-functions/scripts/fat_functions.py path/to/project
```

It writes `path/to/project/.fat-functions/report.json` and prints the totals and the worst functions. Useful options:

* `--exclude tests "src/old/"` skips files and folders, written like `.gitignore` lines
* `--max-loc 50 --max-complexity 10` sets the danger zone: functions over both
* `--include-generated` measures files whose header says they were generated, which are skipped by default
* `--out folder` writes the report somewhere else

Run `python skill/fat-functions/scripts/fat_functions.py --help` for the full list.

## Development

You need Python 3.9 or newer. Dev tools (pytest, ruff) go in a virtual environment; the tool itself never needs them.

```bash
python -m venv .venv
.venv\Scripts\activate             # macOS/Linux: source .venv/bin/activate
python -m pip install --upgrade pip  # --group needs pip 25.1 or newer
python -m pip install --group dev
```

Run the checks before committing:

```bash
python -m pytest
ruff check .
ruff format --check .
```

Third-party code that ships with the tool lives in `skill/fat-functions/scripts/vendor/`, pinned in `VERSIONS.txt`. To change a version, edit its pin and run `python tools/update_vendor.py`.

## License

Apache License 2.0. See [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE).

If you use Fat Functions in your own project, a mention or a link back to this repository is appreciated.
