"""The log of a step: how long it took, with the values of its work.

The step writes one record at DEBUG, under the logger of the calling module. This
module is internal.
"""

import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager


@contextmanager
def log_step(
    step_logger: logging.Logger, step: str, values: dict
) -> Iterator[dict]:
    """
    Logs at DEBUG how long a step took, with the values of its work.

    - `step_logger`: the logger of the calling module
    - `step`: what the step does, in a few words, such as "reduce the graph"
    - `values`: what the step knows before it starts, such as a number of nodes
    - Yields a copy of `values`, which the step completes with the values it knows
      at its end
    - The log message shows the values and `duration_ms`. The log record keeps them
      with `step` in its attribute `scgraph`, for a handler of the application
    """
    values = dict(values)
    start = time.perf_counter()
    yield values
    values["duration_ms"] = round((time.perf_counter() - start) * 1000, 3)
    step_logger.debug(
        "%s: %s",
        step,
        values,
        extra={"scgraph": {"step": step, **values}},
    )
