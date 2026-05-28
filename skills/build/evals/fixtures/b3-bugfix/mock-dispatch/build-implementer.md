# Receipt — build-implementer (mocked, refactor mode)

VERDICT: PASS
CLAIMS:
- files-touched: 1
- tests-passing: 1 (tests/test_tax.py)
WITNESS: kind=exec; ran=TRACE#3
TRACE:
  1: ran pytest tests/test_tax.py → RED (existing failure)
  2: edited src/tax.py: return (amount - discount) * rate
  3: ran pytest tests/test_tax.py → GREEN
EDIT: src/tax.py:1-12:taxfix
TRIPWIRE: claims-touch(src/tax.py), wrote(src/tax.py)
SUPERSEDES:

Fixed compute_tax to subtract discount before applying rate. Single-file targeted fix; no new files.
