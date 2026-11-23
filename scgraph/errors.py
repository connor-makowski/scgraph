"""The two errors that a search raises.

This module is internal. `PathNotFoundError` means that no path joins the origin to
the destination. `NegativeCycleError` means that the graph has a cycle of negative
length. With the C++ extension, the two names are the exceptions that the extension
raises, so that one `except` catches the error of both builds. Users import them from
`scgraph`.
"""

try:
    from scgraph.cpp import PathNotFoundError
except ImportError:

    class PathNotFoundError(RuntimeError):
        """Raised when no path exists between origin and destination nodes."""


try:
    from scgraph.cpp import NegativeCycleError
except ImportError:

    class NegativeCycleError(RuntimeError):
        """Raised when a graph contains a negative weight cycle."""


__all__ = ["NegativeCycleError", "PathNotFoundError"]
