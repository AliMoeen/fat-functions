# Project instructions

This repository builds **Fat Functions**: a tool that measures function size and complexity across a workspace and shows which functions should be split, as a WinDirStat-style report. It ships first as a plain Python tool, then as a Copilot skill, later possibly as a VS Code extension.

**Read `docs/DESIGN.md` before making design decisions.** It records every decision and the reasons. If a change contradicts it, update `DESIGN.md` in the same change and say why.

## Rules

- **Code measures, the LLM interprets.** The engine is deterministic Python. Never add AI calls, network access, or anything that imports or runs the analyzed project. Never modify the analyzed project's code; only write into its `.fat-functions/` folder.
- **Runtime = Python 3 standard library + `skill/fat-functions/scripts/vendor/`.** Do not add runtime dependencies. Anything new that must ship gets vendored, pinned in `vendor/VERSIONS.txt`, and keeps its license file. Dev-only tools go in `pyproject.toml` as dev dependencies.
- **lizard is the only parser.** All lizard-specific code lives in the single conversion function in `codemap/measure.py`. Nothing else imports lizard.
- **Keep it simple.** Prefer the smallest change that works. Do not add abstractions, plugin systems or configuration for needs we do not have yet.
- **Never crash on one bad file.** Record it in `errors` and continue.
- **Paths** in records and reports are relative to the analyzed root and use `/` on every OS. Use `pathlib`.
- **Same input, same output.** Sort anything that would otherwise depend on filesystem order.

## Code style

- Python 3.9+ compatible. Type hints on public functions. Format and lint with ruff.
- Small modules with one job each: `scan`, `measure`, `tree`, `score`, `render`.
- Plain, descriptive names. Short docstrings that say what, not how.

## Testing

- Every behaviour change comes with a test. Run `pytest` before considering work done.
- Fixture numbers in `tests/fixtures/` are hand-checked. If a fixture's expected value changes, explain why in the change.
- Changes that affect output on real code: run `tools/run_corpus.py` and `tools/compare.py`, and describe the differences. Only accept a new baseline when the differences are intended.

## Working style

- Work in small steps that each leave the repo with passing tests.
- When finishing a step, summarise what changed and what the next step in `docs/DESIGN.md` section 14 is.
