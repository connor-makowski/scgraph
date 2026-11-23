"""The log of a step: how long it took, with the indicators of its work.

The step writes one record at DEBUG, under the logger of the calling module. This
module is internal.
"""

import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager


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
