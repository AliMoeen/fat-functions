"""Fat Functions engine: scan, measure, tree, score and render a workspace."""

import sys
from pathlib import Path

VENDOR = Path(__file__).resolve().parent.parent / "vendor"

# Bundled dependencies are imported straight from their wheels (docs/DESIGN.md
# section 5). Putting them first means every importer, the entry script and
# the tests alike, uses them rather than copies installed elsewhere.
sys.path[0:0] = [
    str(wheel) for wheel in sorted(VENDOR.glob("*.whl")) if str(wheel) not in sys.path
]
