"""Tax computation.

BUG (intentional, for b3 fixture): compute_tax ignores the discount kwarg.
The seed test in tests/test_tax.py asserts compute_tax(100, 0.1, discount=10) == 9
which fails until build's bugfix lands.
"""


def compute_tax(amount, rate, discount=0):
    # FIXME: should subtract discount before applying rate
    return amount * rate
