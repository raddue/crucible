"""Make the parent package importable when pytest is run from any cwd.

Also exclude fixtures/ from pytest collection — fixture seeds contain intentionally
buggy tests (e.g. b3-bugfix's seed/tests/test_tax.py is RED by design) that must
not be run as part of the harness's own self-tests.
"""
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parents[2]  # skills/build/evals -> repo root
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

collect_ignore_glob = ["fixtures/*"]
