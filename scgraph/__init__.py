"""Shortest paths on geographic and supply chain networks.

The README of the project is the entry page of this package. It is at
https://github.com/connor-makowski/scgraph#readme. Four guides, in `guides/`, each
cover one task, and `MIGRATING.md` lists the changes since release 3.6. The
documentation site shows them on this page: pdoc reads each line below and puts the
file in its place.

.. include:: ../README.md

.. include:: ../guides/routing.md

.. include:: ../guides/time_cost_co2.md

.. include:: ../guides/networks.md

.. include:: ../guides/custom_graphs.md

.. include:: ../MIGRATING.md
"""

import logging

from scgraph.graph import NegativeCycleError, PathNotFoundError
from scgraph.graph_reducer import algorithm

try:
    from scgraph.cpp import Graph, CHGraph, TNRGraph

    # Assign python methods to the cpp graph class
    Graph.algorithm = staticmethod(algorithm)
except ImportError:
    from scgraph.graph import Graph
    from scgraph.contraction_hierarchies import CHGraph
    from scgraph.transit_node_routing import TNRGraph

from scgraph.geograph import GeoGraph
from scgraph.grid import GridGraph

# The public names of the package (README, *Public API*)
__all__ = [
    "CHGraph",
    "GeoGraph",
    "Graph",
    "GridGraph",
    "NegativeCycleError",
    "PathNotFoundError",
    "TNRGraph",
]

# Messages go through logging; the application decides what is shown (Python Logging HOWTO)
logging.getLogger(__name__).addHandler(logging.NullHandler())
