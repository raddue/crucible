"""Tiny inventory module for the delve eval fixture (#373). Hermetic, stdlib-only.

Contains deliberately PLANTED defects at known lines — see ground-truth-bugs.json.
Do not "fix" these in place; they are the eval substrate.
"""


def last_n(items, n):
    # PLANTED b1 (line 11): off-by-one slice — drops the final element. Should be
    # items[-n:]; items[-n:-1] omits the last item entirely.
    return items[-n:-1]


def total_price(cart, discounts=[]):
    # PLANTED b2 (lines 15-17): mutable default argument — `discounts` is shared across
    # calls, so an append in one call leaks into the next.
    discounts.append(0)
    return sum(cart) - sum(discounts)


def is_in_stock(quantity):
    # PLANTED b3 (line 24): wrong comparison operator — treats a quantity of exactly
    # 0 as in stock (should be `> 0`, not `>= 0`).
    return quantity >= 0


def restock(levels, sku, amount):
    # PLANTED b4 (line 30): missing key guard — a KeyError is raised for an
    # unknown sku instead of initializing it.
    levels[sku] = levels[sku] + amount
    return levels
