# Fat Functions — Design Brief

This document captures every decision made while designing the tool, with the reasons. Treat it as the source of truth. If something here turns out to be wrong in practice, update this file in the same change.

## 1. Goal

Show which files, classes and functions in a workspace are too big and too complex, so they can be broken into smaller functions. Inspired by WinDirStat's treemap, applied to code instead of disk space.

Primary users: developers working mostly in Python, with some JavaScript, TypeScript and Java in the same workspaces.

**Pitch:** a beautiful code health map that runs locally, costs nothing, needs no account, and tells Copilot what to fix.

This is the niche, and the test for every future feature: anything that needs a server, an account, a subscription or a paid tier breaks the pitch.

### Why this is not reinventing the wheel

Every piece exists somewhere; the combination does not.

| Existing tool | What it lacks for this purpose |
|---|---|
| CodeScene (closest competitor: hotspot maps, code health, IDE extension, AI auto-refactor) | Commercial; full analysis needs their platform |
| CodeCharta (open-source treemap / code city) | Separate import pipeline, not in the editor, plain look, no AI handoff |
| SonarQube for IDE, CodeMetrics extension | Per-function warnings only, no overview map |
| radon, lizard, wily | Numbers only, no visuals, no AI |
| Copilot alone | Estimates instead of measuring |

We reuse lizard and ECharts rather than rebuilding parsing or charting.

## Name and identity

| Where | Form |
|---|---|
| GitHub repo | `AliMoeen/fat-functions` |
| Marketplace extension `name` | `fat-functions` |
| Marketplace display name | `Fat Functions` (consider `Fat Functions: Find Code to Split` for search) |
| Skill folder and `SKILL.md` `name` | `fat-functions` |
| PyPI package | `fat-functions` |
| Entry script | `fat_functions.py` |
| Engine package | `codemap/` (not `fat_functions/`, which would clash with the entry script on import) |
| Report folder in analyzed projects | `.fat-functions/` |

Before publishing, confirm the name is free on the VS Code Marketplace (name and display name must both be unique), Open VSX and PyPI. Marketplace names are permanent: never publish a placeholder you plan to delete.

## License

**Apache License 2.0**, with a `NOTICE` file crediting Ali Moeen. Chosen over MIT because redistributors must carry the NOTICE file, so credit travels with every copy. Compatible with the bundled code: ECharts is Apache-2.0, lizard is MIT, pygments is BSD-2-Clause, pathspec is MPL-2.0. Keep each vendored project's license file in `vendor/` (see section 5). The README politely asks users to mention or link the project.

## 2. Core principle

**Code measures. The LLM interprets.**

- Everything with one correct answer (file discovery, line counts, structure, complexity, ranking) is computed by deterministic Python. Never by an LLM.
- Everything that needs judgment (is this function actually bad, where are the natural seams, how to split it, writing the refactor) is done by Copilot, guided by `SKILL.md`, using the script's output.
- The script narrows a whole codebase down to the few functions that matter, so the LLM only reads those.

## 3. What gets built, in stages

Each stage builds on the previous one and never requires redoing it.

1. **Plain Python tool** (`fat_functions.py`). Useful on its own: `python fat_functions.py <path>` produces the report.
2. **Copilot skill**: add `SKILL.md` (about 30 lines) next to the script so Copilot can run it, read `report.json`, and propose or perform splits.
3. **VS Code extension** (later, only if the tool proves useful): report in a VS Code panel, click a function to open it in the editor, a command and toolbar button, refresh on save, Marketplace distribution.

Not planned: a custom Copilot agent. Revisit only if we want a full measure → refactor → re-measure loop; even then the agent would use the skill, not replace it.

## 4. Parsing: lizard for every language

Decision: use **lizard** for all languages, including Python. Do not use Python's `ast`, tree-sitter, or per-language native parsers for now.

Why: one dependency and one code path covers Python, JavaScript, TypeScript, Java, C#, C/C++, Go, Kotlin, Swift, Rust, PHP, Ruby and more. Language coverage becomes free instead of a per-language cost. Small precision losses do not change the answer to "which functions are fat."

Keep exactly **one conversion function** in `measure.py` that turns lizard output into our own record shape. That is the only place that knows about lizard, so a future swap (tree-sitter for one language, `ast` for Python docstrings) touches one place.

Upgrade only when a real problem appears:

| If this happens | Then |
|---|---|
| lizard misreads files we care about | Swap that one language to tree-sitter |
| Neither | Keep it simple |

Excluding docstrings from Python line counts was once on this list. It is not needed: `loc` is lizard's code-line count (section 6), which already skips docstrings, comments and blank lines (checked in build step 3).

### Verified lizard behaviour (tested with lizard 1.25.0, re-checked on 1.24.3)

Tested by vendoring lizard into a folder (no pip install) and running it on small Python, JS, TS and Java files. Vendoring works; all four languages parsed with correct line ranges; complexity numbers were hand-checked and correct.

**Vendored version is 1.24.3, not 1.25.0.** 1.25.0 was not yet on the package feed used to build `vendor/` (build step 2), and 1.24.3 is 314 commits older. Build step 3 re-checked everything below on 1.24.3, with the same hand-checked numbers. Moving to a newer lizard later is a pin change in `VERSIONS.txt`.

Known quirks the code must handle:

- **Python and TypeScript methods lose their class name.** Python reports `build`, not `InvoiceBuilder.build`. Java reports `Order::shipping`. Nested Python functions are named `outer.inner`. Functions still group correctly under their file. Class grouping is a later nice-to-have. Two classes with a method of the same name give two functions with the same name in one file, so `measure.py` numbers repeated ids (section 6).
- **A callback on the same line as its function shares its line range.** In `const total = (c) => c.items.reduce((s, i) => s + i.price, 0);` lizard reports `total` and, for the inner arrow, `(anonymous)`, both on line 8 to 8. (An earlier reading took this for one arrow function reported twice; a one-line arrow without a callback is reported once.) Counting both would count the line twice, so `measure.py` keeps one function per file + start line + end line: a named one over `(anonymous)`, then the outermost. A callback on its own line has its own range and is kept. lizard counts 0 parameters for arrow callbacks like `(s, i) => …`.
- **Syntax errors are not reported.** lizard returns no error, and a broken Python file can lose every function, even valid ones after the error.
- **lizard reads files with the OS default encoding and hides read errors**, and reports a `RecursionError` (for example, thousands of nested braces) only on stderr, returning partial results. So `measure.py` reads each file itself as UTF-8 (BOM allowed, bad bytes replaced, any line endings), and turns anything lizard writes to stderr into an `errors` entry.
- **A comment containing `GENERATED CODE` makes lizard stop reading the file.** Every function after it is lost, and in Python the one just before it too; a generated-file header gives zero functions. `#lizard forgive` comments hide a function (in Python, the one before the comment). `scan.py` should skip generated files on purpose, so this never happens silently (build step 4).
- **Deeply nested functions are slow.** Time doubles with each level of nested Python functions: 0.09 s at 25 levels, so a minute or more past 35. Real code does not nest that deep; add a per-file time limit only if the corpus shows a need.
- **Language names come from lizard's readers:** `python`, `javascript`, `typescript`, `java`; `.jsx` files are `tsx` and `.c` files are `cpp`.
- **Bundle size is about 6.2 MB.** lizard pulls in `pygments` (most of the size) and `pathspec`. All pure Python, so bundling works on every OS. Kept as wheels (section 5), the whole `vendor/` folder, ECharts included, is 2.5 MB.

Not yet verified: Windows paths, speed on very large repositories, behaviour when Python is missing (extension stage).

## 5. Dependencies and vendoring

- **Runtime needs only Python 3 plus the bundled `vendor/` folder.** No `pip install` for users, no network.
- lizard, pygments and pathspec ship as the unmodified wheel files (`*.whl`) from `pip download`, committed to `scripts/vendor/`. Python imports pure-Python packages straight from a zip. `codemap/__init__.py` puts each wheel first on `sys.path`, so every importer (`fat_functions.py`, the tests, later the extension) gets the bundled copies, not ones installed elsewhere. One exception: pytest imports its own pygments at startup, so inside a test run pygments comes from the dev environment (it only matters for Erlang). A test checks the real setup in a fresh interpreter.
- Why wheels instead of an unpacked folder (decided in build step 2): 11 files and 2.5 MB in `vendor/` instead of about 500 files and 6.2 MB; a version bump replaces one wheel; the wheels are byte-identical to the ones on PyPI; and Python never writes `__pycache__` into the analyzed project, where the skill may live. The cost is about 0.14 s extra startup per run, because Python cannot cache compiled code inside a zip. Tested on Python 3.9, 3.11 and 3.12 with identical lizard results.
- The wheel spec discourages importing from wheels in general: skipping installation hides packages from tools that track dependencies for security updates, and code that assumes it was installed (C extensions, files opened via `__file__`) fails in obscure ways. Neither applies here. All three wheels hold only `.py` files (plus pathspec's `py.typed` marker), with no C extensions and no `.data` directory, and `tests/test_vendor.py` checks this on every CI run. Security updates are tracked by hand through `VERSIONS.txt`.
- `update_vendor.py` uses the developer's pip configuration, so private package feeds work. It resolves for Python 3.9 (every pin must support it), refuses wheels that are not pure Python (they would not run on every OS), and fails if pip downloads anything not pinned.
- `.gitattributes` marks the third-party files in `vendor/` as `-text`, so git never changes their line endings and every checkout stays byte-identical to upstream.
- ECharts (`echarts.min.js`) is downloaded once into `scripts/vendor/` and pasted into the generated HTML, so reports work offline, on locked-down networks, and as a single file that can be emailed. It comes from jsDelivr's copy of the npm package, because some corporate networks block the npm registry. Its `LICENSE` and `NOTICE` are saved next to it as `echarts-LICENSE.txt` and `echarts-NOTICE.txt`.
- Keep each bundled project's license file as a plain file in `vendor/`, so people and license scanners see it without unzipping anything. `update_vendor.py` copies each wheel's `*.dist-info/licenses/` files out next to it (`lizard-LICENSE.txt`, `pathspec-LICENSE.txt`, `pygments-LICENSE.txt`, `pygments-AUTHORS.txt`), and a test checks they still match the copies inside the wheels. pygments' `AUTHORS` is kept because its license names the copyright holders by pointing to it. lizard is MIT (its `lizard.py` also carries an Apache-2.0 header; both are compatible), pygments is BSD-2-Clause, pathspec is MPL-2.0 (ship its files unmodified), ECharts is Apache-2.0 (its NOTICE travels with every copy).
- Pinned versions live in `scripts/vendor/VERSIONS.txt`. `tools/update_vendor.py` re-creates the folder from those pins, and `tests/test_vendor.py` checks the folder still matches them.
- Dev tools (pytest, ruff) are dev dependencies in `pyproject.toml` and never ship.

## 6. Responsibilities of the engine

`fat_functions.py` is the entry point; it parses arguments and calls the engine. The engine is split by job:

| Module | Job |
|---|---|
| `scan.py` | Walk the target folder and collect source files. Skip `.git`, `.venv`, `venv`, `__pycache__`, `site-packages`, `node_modules`, `build`, `dist`, `target`, `*.min.js`, generated code, and anything in `.gitignore`. Exclusions are configurable. |
| `measure.py` | Run lizard on each file and convert results to records. Files it cannot read, file types lizard does not know, and lizard failures go in an `errors` list, and the run keeps going; never crash on one bad file. |
| `tree.py` | Build folder → file → function, rolling sizes up so each parent equals the sum of its children. Code at module level that is not in any function becomes a `<module>` block (like WinDirStat's `<Files>`). Nested functions are separate records, and the line that starts a nested function counts in both (outer 5 + inner 3 lines of code in a 7-line file), so `tree.py` must nest or subtract them rather than add them up. |
| `score.py` | Apply thresholds, assign a status to each function, rank the worst offenders. |
| `render.py` | Write `report.json` and the HTML report, and print a short summary to stdout. |

What the engine never does: call an AI, suggest refactors, modify the analyzed code, use the network, import or run the analyzed project. Same input always gives the same output.

### Record shape (one per function)

```
{id, name, file, start_line, end_line, loc, complexity, params, language, status}
```

`id` is `"<relative file path>::<function name>"`. When a file has several functions with the same name (methods of different classes, anonymous callbacks), the second and later get `#2`, `#3`… in source order, so ids are unique and the first one's id does not change when another is added. `file` paths are relative to the analyzed root and always use `/`.

`loc` is **lines of code**: lizard's code-line count, without blank lines, comments or docstrings. It is not `end_line - start_line + 1`, which counts every line the function spans. Chosen in build step 3 because comments and spacing should not make a function look fatter, and it is what lizard and most metrics tools mean by lines of code. `status` is filled in by `score.py`.

`measure.py` also returns each file's language and code-line count (the `<module>` block in `tree.py` is what is left after the functions), and an `errors` list. Results are sorted by file path, then by start line.

## 7. Scoring

Status by cyclomatic complexity:

| Complexity | Status | Label |
|---|---|---|
| 1–5 | `ok` | Simple |
| 6–10 | `watch` | Watch |
| 11–20 | `soon` | Split soon |
| 21+ | `now` | Split now |

- **Danger zone**: functions with 50+ lines of code **and** complexity 11+.
- **Ranking**: worst offenders sorted by `loc × complexity`.
- These defaults are placeholders. Calibrate them against the test corpus (section 11) so that only a few percent of functions land in the danger zone. Allow per-language overrides later; a 50-line Java method is not the same as 50 lines of Python.

## 8. Outputs

Written into the analyzed project, in `.fat-functions/` (never into the tool's own folder):

- `report.html`: self-contained interactive report.
- `report.json`: structured data for Copilot and other tools.

```json
{
  "summary": {"files": 14, "functions": 31, "loc": 1645, "danger_zone": 3},
  "thresholds": {"danger_loc": 50, "danger_complexity": 11},
  "offenders": [
    {"id": "services/billing.py::calculate_invoice", "name": "calculate_invoice",
     "file": "services/billing.py", "start_line": 42, "end_line": 253,
     "loc": 187, "complexity": 34, "status": "now"}
  ],
  "tree": {"name": "<root>", "children": ["..."]},
  "errors": [{"file": "legacy/old.py", "error": "..."}]
}
```

stdout: a few lines with totals and the top 5 offenders, so Copilot often does not need to open the JSON.

### Command line

```
python fat_functions.py [path] --out .fat-functions/ --exclude tests migrations
                         --max-loc 50 --max-complexity 10 --no-open
```

## 9. The report page

A working prototype is in `docs/report-prototype.html`. It becomes `scripts/templates/report.html`, with the hard-coded sample data replaced by a placeholder that `render.py` fills with the real data.

Three linked views, each with one job:

1. **Diagnose — scatter plot.** Each dot is a function; lines of code across, complexity up. Shaded top-right danger zone labelled "Split these", dashed lines at the thresholds, worst offenders labelled by name. This answers the core question most directly, because position is judged more precisely than color.
2. **Act — ranked list** of worst offenders with a status chip.
3. **Navigate — treemap.** Folder → file → function, block size = lines of code, color = complexity. Click to zoom; path bar to zoom out.

Selecting a function in any view highlights it in the other two (dot highlighted, row highlighted, treemap zooms to its file).

Visual rules (these are what make it look polished, unlike the classic D3 Flare treemap):

- Calm neutral blocks; color reserved for complexity, with red only for real problems.
- Labels only where they fit; details on hover.
- Clear folder and file headers with totals; gaps and soft corners between blocks instead of thin lines.
- Real units everywhere ("187 lines of code · complexity 34"), never bare numbers. Where there is room (tooltips, details), show the span too: "187 lines of code (lines 42–253)", so a function that is long mostly because of comments is easy to spot. Keep the span out of the ranked-list rows, where numbers must never be cut off.
- Light and dark mode.

Library: **ECharts 5.5.0**. Chosen over D3 (more polish possible, but zoom, breadcrumbs and transitions must be hand-built) and Plotly (large and dated-looking). ECharts gives built-in drill-down, breadcrumbs, tooltips and good defaults for little code.

Known issues in the prototype to fix when turning it into the template (seen in dark mode at desktop width):

- Scatter labels collide when dots are close (`main`/`build`, `InvoiceTable`/`render_pdf`, `submitOrder`/`apply_discounts`).
- The label of the right-most dot (`calculate_invoice`) is cut off at the chart edge.
- Ranked list rows truncate the numbers ("144 …", "cc …") on long paths. Numbers must never be the truncated part; truncate the path instead.
- Small top-level folders in the treemap (`utils/`, `models/customer.py`) shrink to unreadable slivers. Consider a minimum size or an "other" group.
- File headers get cut ("InvoiceTable.tsx 1"): drop the loc count before cutting the name.

Later ideas: treemap/sunburst switch, color-by toggle (complexity, git churn, coverage), search box, `vscode://file/...:line` links.


### Ready for the VS Code extension (stage 3)

Build the report so the extension can reuse it unchanged:

- **Self-contained page.** All data and scripts are inside the HTML. No
  outside files, fonts from the web or network requests at runtime.
- **One click handler.** Every "go to this function" action calls a single
  `openFunction(file, line)` in the page. In a browser it shows the path
  and line. In the extension it is replaced to open the file in the editor.
- **Colors only through CSS variables.** No hard-coded colors in components
  or chart options; read them from the variables, so the extension can map
  them to the VS Code theme.
- **Stable command line.** The extension runs `fat_functions.py` with its
  arguments, so treat the options in section 8 and the `report.json` shape
  as a public contract: add options freely, but don't rename or remove them
  without a major version change.

## 10. Repository structure

```
fat-functions/
├── README.md
├── LICENSE                     # Apache-2.0
├── NOTICE                      # attribution, must travel with copies
├── pyproject.toml              # dev tools only
├── .gitignore                  # .fat-functions/ .corpus/ .corpus-out/
├── .gitattributes              # keep vendor/ byte-identical on every OS
├── .github/
│   ├── copilot-instructions.md
│   └── workflows/ci.yml        # tests on Windows, macOS, Linux
├── docs/
│   ├── DESIGN.md               # this file
│   └── report-prototype.html
├── skill/
│   └── fat-functions/           # the shippable unit: copy this folder anywhere
│       ├── SKILL.md            # stage 2
│       └── scripts/
│           ├── fat_functions.py
│           ├── codemap/        # scan, measure, tree, score, render
│           ├── templates/report.html
│           └── vendor/         # lizard, pygments, pathspec wheels; echarts + licenses; VERSIONS.txt
├── tests/
│   ├── fixtures/mixed_project/ # provided: small .py .js .ts .java files with hand-checked numbers
│   ├── fixtures/edge_cases/    # syntax error, empty file, arrow duplicate, non-English names, huge file
│   └── test_*.py
├── corpus/
│   ├── repos.toml              # real repos pinned to exact commits
│   └── baseline.json           # last accepted corpus results
├── tools/
│   ├── update_vendor.py
│   ├── fetch_corpus.py
│   ├── run_corpus.py
│   └── compare.py
└── extension/                  # stage 3
```

## 11. Testing

Three levels, fastest first:

| Level | Checks | When |
|---|---|---|
| Unit tests on fixtures | Numbers are exactly right | Every change |
| Corpus run | No crashes, sensible output, speed on real code | After meaningful changes |
| Looking at reports | It looks and feels right | When output changes |

**First fixture** is already in `tests/fixtures/mixed_project/` (the exact files lizard was tested on; numbers hand-checked):

- Python `InvoiceBuilder.build`: a `for`, an `if` with `and`, an `elif` → complexity 5. `round_money` → 1.
- JavaScript `applyDiscount`: `if`, `for`, `if` with `||` → 5. Arrow function `total` → 1; its inner callback `(s, i) => …` on the same line is reported as `(anonymous)` with the same line range and dropped (dedupe test).
- TypeScript `UserService.validate`: two `if`s, `&&`, `||` → 5.
- Java `Order::shipping`: two `case`s, a ternary, an `if` → 5.
- Python `describe` in `summary.py` (added in build step 3): a docstring, comments and blank lines. It spans lines 4–15 (12 lines) but has 5 lines of code; one `if` → complexity 2. The file has 5 lines of code; its module docstring does not count.

**Corpus**: 8–10 real repositories pinned to commits, cloned into `.corpus/` (gitignored). Suggested mix: `psf/requests` and `pallets/flask` (normal Python), `django/django` (large, stress test), `expressjs/express` (JavaScript), `colinhacks/zod` (TypeScript), `spring-projects/spring-petclinic` (Java), one messy legacy repo, plus private work repos listed in an uncommitted local file.

- `run_corpus.py` runs the tool on every repo in parallel, writes reports to `.corpus-out/<repo>/`, an `index.html` linking them, and a summary table (files, functions, danger zone, errors, time).
- `compare.py` diffs a run against `corpus/baseline.json` and shows only what changed; `--accept` makes the run the new baseline.
- Tweak loop: change → pytest → `run_corpus --only <a,b>` → compare → look at changed reports → accept.
- Use the corpus distribution to choose default thresholds.
- CI: unit tests on every push on three OSes. Corpus run on demand or weekly, with a small subset.

## 12. Copilot skill (stage 2)

Location: `.github/skills/fat-functions/` in a project (shared with the team) or `~/.copilot/skills/fat-functions/` (personal, all workspaces). The repo keeps the source in `skill/fat-functions/`.

`SKILL.md` frontmatter: `name: fat-functions` (must match the folder name: lowercase letters, numbers, hyphens only), and a `description` that says what it does and when to use it, for example "Measure function size and complexity across the workspace and find functions that should be split. Use when asked about large, complex or hard-to-maintain code, or what to refactor first."

Body tells Copilot to:

1. Run `scripts/fat_functions.py` on the workspace with the bundled Python path.
2. Read the stdout summary, and `report.json` if needed.
3. Point the user to `report.html`.
4. For the top offenders, read only those functions and judge whether each is genuinely a problem (a long but simple lookup table is fine).
5. When asked, propose how to split a function, write the refactor, run the tests, and re-run the tool to confirm the improvement.

## 13. Distribution

1. **Now**: one GitHub repo; the `skill/fat-functions/` folder is self-contained. Users copy it into `.github/skills/` or `~/.copilot/skills/`, or install it through VS Code's Customization Marketplace. Version with git tags.
2. **Later**: VS Code extension published to the VS Code Marketplace and Open VSX (for Cursor and VSCodium). It ships the same skill folder through the `chatSkills` contribution point in `package.json`, plus the in-editor panel. It finds Python through the Python extension's selected interpreter, falling back to `python3`/`python`, and shows a clear message if none is found.
3. **Optional**: an agent plugin bundling related skills for a team; the engine on PyPI for CI use.

Because Agent Skills is an open standard, the same skill folder also works in Copilot CLI, Claude Code (`.claude/skills/`) and Codex.

## 14. Build order

1. Repo setup (LICENSE, Python .gitignore and README already exist; extend, don't replace), dev virtual environment, pytest, ruff, CI skeleton.
2. `tools/update_vendor.py`; vendor lizard and ECharts.
3. `measure.py` + tests against `fixtures/mixed_project`, including arrow-function dedupe.
4. `scan.py` with exclusions + tests.
5. `tree.py` and `score.py` + tests; output `report.json`.
6. Turn `docs/report-prototype.html` into `templates/report.html`; implement `render.py`.
7. Corpus tools; run on the corpus; calibrate thresholds; commit the baseline.
8. `SKILL.md`; try it in Copilot on a real project.
9. Extension, if wanted.
