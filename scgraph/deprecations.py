"""The warnings of a deprecated function or parameter.

Each warning says what to use in its place: by default, the logging module, which
replaces the former printing. This module is internal.
"""

import warnings


def warn_deprecated(
    name: str,
    stacklevel: int = 3,
    instead: str = "scgraph reports its messages through the logging module "
    "(README, section Logging)",
) -> None:
    """
    Warns that a function or a parameter is deprecated.

    - `name`: the function or the parameter, as the message names it
    - `stacklevel`: the default points the warning at the caller of the function that
      calls this one
    - `instead`: the sentence that says what to use in its place
    """
    warnings.warn(
        f"{name} is deprecated. {instead}",
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
