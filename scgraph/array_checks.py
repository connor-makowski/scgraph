"""The checks of a sorted array: `is_sorted` and `is_sorted_from_zero`.

This module is internal.
"""

from collections.abc import Iterable, Sequence
from itertools import islice
from operator import le


def is_sorted(values: Iterable) -> bool:
    """Return whether no value is smaller than the value before it."""
    # `map` and `all` run the loop in C, not in Python.
    return all(map(le, values, islice(values, 1, None)))


def is_sorted_from_zero(values: Sequence) -> bool:
    """Return whether the first value is 0 and no value is smaller than the value
    before it, as in an array of offsets. `values` holds at least one value."""
    return values[0] == 0 and is_sorted(values)
