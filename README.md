# Fat Functions

Find the functions that are too big and too complex, see where they live, and fix the worst first.

A code health map that runs locally, costs nothing, needs no account, and tells Copilot what to fix. Works with Python, JavaScript, TypeScript, Java and more.

**Status:** design complete, implementation starting. See [`docs/DESIGN.md`](docs/DESIGN.md) for the full design and [`docs/report-prototype.html`](docs/report-prototype.html) for the report prototype (download and open it in a browser).

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
