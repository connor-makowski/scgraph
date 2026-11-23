"""The warnings of a deprecated function or parameter of the former printing.

Each warning sends the user to the logging module. This module is internal.
"""

import warnings


def warn_deprecated(name: str, stacklevel: int = 3) -> None:
    """
    Warns that a function or a parameter of the former printing is deprecated. The
    message sends the user to the README section Logging.

    - `name`: the function or the parameter, as the message names it
    - `stacklevel`: the default points the warning at the caller of the function that
      calls this one
    """
    warnings.warn(
        f"{name} is deprecated. scgraph reports its messages through the logging"
        " module (README, section Logging)",
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
