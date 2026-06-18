"""Pytest config for the minimalism-ladder eval.

The dir name is hyphenated (`minimalism-ladder`, the design's committed home),
which is not a valid dotted package path — so this conftest puts the harness dir
itself on sys.path. The harness modules (`loc`, `scorer`, `decision`, `tasks`)
are imported as top-level names. Fixture solution dirs are kept out of pytest
collection (they hold standalone solution.py / test_solution.py files that are
*inputs* to the scorer, not tests of this harness).
"""
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

collect_ignore_glob = ["fixtures/*"]
