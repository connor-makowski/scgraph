"""Helpers that scgraph uses inside: the deprecation warnings, the log of a step, and
the checks of a sorted array.

This module is internal. `scgraph.utils` holds the helpers that a user calls.
"""

import logging
import time
import warnings
from collections.abc import Iterable, Iterator, Sequence
from contextlib import contextmanager
from itertools import islice
from operator import le


def warn_deprecated(name: str, stacklevel: int = 3) -> None:
    """
    Warns that a function or a parameter of the former printing is deprecated. The
    message sends the user to the section Logging of `guides/routing.md`.

    - `name`: the function or the parameter, as the message names it
    - `stacklevel`: the default points the warning at the caller of the function that
      calls this one
    """
    warnings.warn(
        f"{name} is deprecated. scgraph reports its messages through the logging"
        " module (guides/routing.md, section Logging)",
        DeprecationWarning,
        stacklevel=stacklevel,
    )


def warn_deprecated_parameter(name: str, value: object) -> None:
    """
    Warns that the parameter `name`, which controlled printing, is deprecated, if the
    caller gave it.

    - `value`: the value of the parameter; None means that the caller did not give it
    """
    if value is not None:
        warn_deprecated(f"The parameter `{name}`", stacklevel=4)


@contextmanager
def log_step(
    step_logger: logging.Logger, step: str, indicators: dict
) -> Iterator[dict]:
    """
    Logs at DEBUG how long a step took, with indicators of its work.

    - `step_logger`: the logger of the calling module
    - `step`: what the step does, in a few words, such as "reduce the graph"
    - `indicators`: values known before the step, such as a number of nodes
    - Yields a copy of `indicators`, which the step completes with the values it knows
      at its end
    - The log message shows the indicators and `duration_ms`. The log record keeps them
      with `step` in its attribute `scgraph`, for a handler of the application
    """
    indicators = dict(indicators)
    start = time.perf_counter()
    yield indicators
    indicators["duration_ms"] = round((time.perf_counter() - start) * 1000, 3)
    step_logger.debug(
        "%s: %s",
        step,
        indicators,
        extra={"scgraph": {"step": step, **indicators}},
    )


def is_sorted(values: Iterable) -> bool:
    """Return whether no value is smaller than the value before it."""
    # `map` and `all` run the loop in C, not in Python.
    return all(map(le, values, islice(values, 1, None)))


def is_sorted_from_zero(values: Sequence) -> bool:
    """Return whether the first value is 0 and no value is smaller than the value
    before it, as in an array of offsets. `values` holds at least one value."""
    return values[0] == 0 and is_sorted(values)
