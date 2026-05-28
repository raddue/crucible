"""Failing test exercising the b3 bug. build should fix src/tax.py so this passes."""
from src.tax import compute_tax


def test_compute_tax_with_discount():
    # (amount - discount) * rate == 90 * 0.1 == 9
    assert compute_tax(100, 0.1, discount=10) == 9
