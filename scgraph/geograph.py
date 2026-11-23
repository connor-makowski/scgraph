"""Geographic graphs: a `Graph` whose nodes have a latitude and a longitude.

- `GeoGraphIO`, in `scgraph/geograph_io.py`, loads and saves networks (GeoJSON,
  graphjson, `.scgraph` files, OpenStreetMap, OSMnx), and loads or builds the networks
  of scgraph.
- `GeoGraphModifiers`, in `scgraph/geograph_modifiers.py`, adds and removes nodes and
  edges, by id or by coordinates.
- `GeoGraphEdges`, in `scgraph/geograph_edges.py`, holds the edge classes and the metrics,
  reads the arrays of the edges, and lists the edges of the network or of a path.
- `GeoGraphRouting`, `GeoGraphUtils` and `GeoGraphDistanceCalculations`, in
  `scgraph/geograph_routing.py`, answer `get_shortest_path` and `distance_matrix`, connect a
  point to nearby nodes, build the coordinates of a path, and give the haversine and
  cheap-ruler distances.
- `GeoGraph` joins these classes.
- `LazyGeoGraph` stands for a `GeoGraph` and loads it at its first use.

Users reach this module through `scgraph.GeoGraph`. `scgraph/networks.py` downloads
the released networks, and `scgraph/built_in_geographs.py` holds the seven networks
of scgraph 3.6.0.
"""

from scgraph.step_logs import log_step
from scgraph.edge_classes import EdgeClasses
from scgraph.node_snapping import SnapIndexes
from scgraph.metrics import Metric
from scgraph import array_views
from scgraph import geograph_io
from scgraph.geograph_io import GeoGraphIO
from scgraph.geograph_modifiers import GeoGraphModifiers
from scgraph.geograph_edges import GeoGraphEdges
from scgraph.geograph_routing import (
    GeoGraphUtils,
    GeoGraphDistanceCalculations,
    GeoGraphRouting,
)
import logging
import warnings
from array import array
from typing import TYPE_CHECKING, Literal
from scgraph import Graph

if (
    TYPE_CHECKING
):  # Only for annotations. A function that needs one of these modules imports it.
    from geokdtree import GeoKDTree
    from scgraph.helpers.snap_index import SnapIndex
    from scgraph.node_snapping import SortedSnapIndex

logger = logging.getLogger(__name__)


class GeoGraph(
    GeoGraphIO,
    GeoGraphModifiers,
    GeoGraphEdges,
    GeoGraphRouting,
    GeoGraphUtils,
    GeoGraphDistanceCalculations,
):
    def __init__(
        self,
        graph: list[dict[int, int | float]],
        nodes: list[list[float]],
        validate: bool = False,
        intermediate_nodes: list[dict[int, list[list[float]]]] | None = None,
        default_off_graph_circuity: float = 1,
        default_node_addition_circuity: float = 4,
        geograph_units: Literal["km", "m", "mi", "ft"] = "km",
        source_node_ids: list[int] | None = None,
        node_mode_ids: list[int] | None = None,
        node_modes: list[dict] | None = None,
        coordinate_dtype: Literal["float64", "int32"] = "float64",
        classes: list[dict] | None = None,
        edge_classes: list[dict[int, str]] | None = None,
    ) -> None:
        """
        Function:

        - Create a GeoGraph object
        - The attribute `graph_object` is the `Graph` of the edges. Change its edges only with `add_edge`, `remove_edge`, `add_node` and `remove_node`, of the geograph or of `graph_object`: `create_metric` and `save_as_scgraph` raise a ValueError when the count of the edges changed otherwise. In the C++ build, `graph_object.graph` is a copy: a write into it changes nothing
        - The attribute `default_metric` is the name of the metric that a call without `metric` uses (`get_shortest_path`, `distance_matrix`, `get_path_weight`, `get_graph_object`). It is 'length', until a loader or the caller sets it to another name of `metrics`
        - A call fails with a ValueError while `default_metric` names a metric that the geograph does not have, for example after an edit of the network, which removes the metrics other than 'length'

        Required Arguments:

        - `graph`
            - Type: list of dictionaries
            - See: https://connor-makowski.github.io/scgraph/scgraph/graph.html#Graph
            - Note: May be kept and modified instead of copied (pure-Python backend; the C++ backend copies it); do not modify it afterwards
        - `nodes`
            - Type: list of lists of ints or floats
            - What: A list of lists where the values are coordinates (latitude then longitude)
            - Note: The length of the nodes list must be the same as that of the graph list
            - Note: Kept without copying and may be modified by the GeoGraph; do not modify it afterwards
            - Example:
            ```
                [
                    # London (index 0)
                    [51.5074, 0.1278],
                    # Paris (index 1)
                    [48.8566, 2.3522],
                    # Berlin (index 2)
                    [52.5200, 13.4050],
                    # Rome (index 3)
                    [41.9028, 12.4964],
                    # Madrid (index 4)
                    [40.4168, 3.7038],
                    # Lisbon (index 5)
                    [38.7223, 9.1393]
                ]
            ```

        Optional Arguments:

        - `validate`
            - Type: bool
            - What: Whether to validate the graph upon initialization
            - Default: False
        - `intermediate_nodes`
            - Type: list of dicts of lists of [float, float]
            - What: One dict per node, {destination: [[latitude, longitude], ...]}: the coordinates of each edge's shape, between its two nodes (not repeated), from origin to destination
            - Note: Allows for more detailed path plotting along edges without needing to increase the number of nodes in the graph
            - Default: None
        - `source_node_ids`
            - Type: list of ints | None
            - What: The stable id of each node, for example its id in the source the network was built from; read back as `source_node_ids`
            - Note: Node ids in paths and graph methods stay positions; `[geograph.source_node_ids[p] for p in path]` translates a path
            - Note: Nodes added later (`add_coord_node`, merges) get negative ids, below all the others; extend `nodes` in place (replacing it leaves `source_node_ids` counting the former list)
            - Default: None (each node's id is its position)
        - `node_mode_ids`
            - Type: list of ints | None
            - What: The node mode of each node (road, sea, port, ...), as its position in `node_modes`; read back as `node_mode_ids`
            - Note: `(node mode, node id)` identifies a node: node ids of different node modes may come from different sources
            - Default: None (every node in the first node mode)
        - `node_modes`
            - Type: list of dicts | None
            - What: The node modes, each a dict with its `name` (str or None) and, optionally, the `source` of its node ids (the name of an entry of the network's sources); read back as `node_modes`
            - Note: At most 256 node modes; two node modes may have the same name (two sea networks merged)
            - Default: None (one node mode, without a name: `[{"name": None}]`)
        - `coordinate_dtype`
            - Type: str
            - What: The coordinate dtype `save_as_scgraph` uses by default, 'float64' or 'int32' (see there); loaders that round to 7 decimals or fewer, and int32 network files, give 'int32'
            - Default: 'float64'
        - `classes`
            - Type: list of dicts | None
            - What: The classes of the edges, each a dict with its `name` (str) and the `edge_mode` of its edges; read back as `classes`
            - Note: At most 255 classes; more raise a ValueError
            - Example: `[{"name": "motorway", "edge_mode": "road"}, {"name": "ferry", "edge_mode": "sea"}]`
            - Default: None (a geograph without classes)
        - `edge_classes`
            - Type: list of dicts | None
            - What: One dict per node, {destination: name of a class}: the class of each edge, as a name of `classes`; `get_edges` reads it back as `edge_class`
            - Note: An edge that is not in its dict has no class
            - Note: A name that is not in `classes`, a destination that is no edge of `graph`, a list that has not one dict per node, or `edge_classes` without `classes` raises a ValueError
            - Example: `[{1: "motorway"}, {0: "motorway", 2: "ferry"}, {1: "ferry"}]`
            - Default: None (no edge has a class)
        - `default_off_graph_circuity`
            - Type: float | int
            - What: The physical distance multiplier applied to final off-graph access legs (origin -> entrance node and exit node -> destination) after the route is solved
            - Purpose: Accounts for the real-world winding of local roads or converts spatial distances to different graph units (e.g. time)
                - EG: For distance routing, 1.0 represents straight-line (great-circle) access distance, while 1.2 models average local street circuity
                - EG: For travel time in seconds with an assumed off-graph speed of 30 km/h, set circuity to 3600 / 30 = 120
                - EG: Set to 0 if off-graph travel should not contribute to the reported route length/time
            - Default: 1
        - `default_node_addition_circuity`
            - Type: float | int
            - What: The algorithmic search penalty applied to candidate off-graph connection legs *during* shortest path finding
            - Purpose: Prevents the pathfinding algorithm from "flying" off-network across impassable geographic barriers (e.g. crossing land in a maritime graph or crossing water without bridges)
                - When connecting origins/destinations with multiple candidate entry points (`node_addition_type="quadrant"` or `"all"`), this factor artificially inflates the cost of traveling off-graph during the search
                - A higher penalty (default: 4) forces the search to enter the graph at a nearby node rather than shortcutting off-graph towards the destination
                - Once the optimal route sequence is determined, the actual reported path length uses `default_off_graph_circuity` instead of this penalty factor
            - Default: 4
        - `geograph_units`
            - Type: str
            - What: The units in which the geograph is represented
            - Default: 'km'
            - Options:
                - 'km': Kilometers
                - 'm': Meters
                - 'mi': Miles
                - 'ft': Feet
        """
        if isinstance(graph, Graph) or (
            hasattr(graph, "get_shortest_path") and not isinstance(graph, list)
        ):
            self.graph_object = graph
            self.graph = None  # built from the graph object on first use
        else:
            self.graph_object = Graph(graph=graph, validate=validate)
            self.graph = graph
        self.nodes = nodes
        if source_node_ids is not None and len(source_node_ids) != len(nodes):
            raise ValueError("source_node_ids must give one id per node")
        self.source_node_ids = array_views.SourceNodeIds(
            range(len(nodes)) if source_node_ids is None else source_node_ids,
            nodes,
        )
        if coordinate_dtype not in ("float64", "int32"):
            raise ValueError("coordinate_dtype must be 'float64' or 'int32'")
        self.coordinate_dtype = coordinate_dtype
        # How the network was built, as read from a network file (see save_as_scgraph)
        self.metadata = {}
        # The network file that the geograph was read from, if any (load_from_scgraph)
        self.scgraph_file = None
        # The class of each edge (`scgraph/edge_classes.py`)
        self._edge_classes = EdgeClasses()
        # The metrics other than `length`, by name (`scgraph/metrics.py`). A
        # method reads them with `_read_metrics`: an edit of `graph_object`
        # removes them.
        self._metrics = {}
        # The offsets, the heads and the lengths of the edges of `graph_object`
        # (`Graph.get_edge_arrays`), as `_read_edge_arrays` last read them. The id of an edge
        # is its position in the heads. The graph and its count of edits at that
        # time show whether the graph was edited since.
        self._edge_arrays = None
        self._edge_arrays_graph = None
        self._edge_arrays_edit_count = None
        # The class id of each of these edges, by edge id, as
        # `_read_edge_class_ids` computed it. None before the first call and
        # after an edit.
        self._edge_class_ids = None
        if classes is not None or edge_classes is not None:
            offsets, heads, _ = self._read_edge_arrays()
            self._edge_classes = EdgeClasses.build_from_class_names(
                classes, edge_classes, offsets, heads
            )
        # The argument of the last `reduce`, for the graph of each metric
        self._reduce_iterations = None
        self.node_modes = (
            [dict(mode) for mode in node_modes]
            if node_modes
            else [{"name": None}]
        )
        self.node_mode_ids = array(
            "B", bytes(len(nodes) if node_mode_ids is None else node_mode_ids)
        )
        if node_mode_ids is not None and (
            len(self.node_mode_ids) != len(nodes)
            or max(self.node_mode_ids, default=0) >= len(self.node_modes)
        ):
            raise ValueError(
                "node_mode_ids must give each node the position of a row of "
                "node_modes"
            )
        self.intermediate_nodes = intermediate_nodes
        self.default_off_graph_circuity = default_off_graph_circuity
        self.default_node_addition_circuity = default_node_addition_circuity
        self.default_get_intermediate_nodes = (
            True if intermediate_nodes is not None else False
        )
        self.geograph_units = geograph_units
        # The name of the metric that a call without `metric` uses
        self.default_metric = "length"
        # Built at the first snap, not here: a GeoGraph that never snaps never pays for it
        self.snap_index = None
        # len(nodes), not len(graph): a C++ graph would be copied to Python to count it
        self.__original_graph_length__ = len(self.nodes)

    @classmethod
    def _build_from_edge_arrays(
        cls,
        edge_arrays: tuple[array | memoryview, ...],
        edge_class_ids: array | memoryview | None = None,
        metrics: dict[str, Metric] | None = None,
        classes: list[dict] | None = None,
        edge_classes: list[dict[int, str]] | None = None,
        **kwargs,
    ) -> "GeoGraph":
        # Create a geograph from what a loader read, with the other arguments of
        # the constructor. `edge_arrays` are the offsets, the heads and the
        # lengths of the edges of the graph, in the order of
        # `Graph.get_edge_arrays`. The geograph keeps them without a copy.
        # `edge_class_ids` is the class id of each edge, by edge id, when a
        # network file holds it. `metrics` are the metrics other than `length`.
        geograph = cls(**kwargs)
        geograph._set_edge_arrays(edge_arrays, edge_class_ids)
        offsets, heads, _ = edge_arrays
        if edge_class_ids is not None:
            geograph._edge_classes = EdgeClasses(
                classes, offsets, heads, edge_class_ids
            )
        elif classes is not None or edge_classes is not None:
            geograph._edge_classes = EdgeClasses.build_from_class_names(
                classes, edge_classes, offsets, heads
            )
        geograph._metrics = dict(metrics or {})
        return geograph

    def _read_node_mode_ids(self) -> array:
        # Return the node mode id of each node. A node appended to `nodes`
        # directly has no id in `node_mode_ids`: it is in the first node mode, as
        # a node of the constructor without `node_mode_ids`. The attribute does
        # not change.
        missing = len(self.nodes) - len(self.node_mode_ids)
        if missing <= 0:
            return self.node_mode_ids
        return self.node_mode_ids + array("B", bytes(missing))

    @property
    def graph(self) -> list[dict[int, int | float]]:
        if self._graph is None:
            # The original graph, whether or not it has been reduced
            self._graph = self.graph_object.unreduced_graph
        return self._graph

    @graph.setter
    def graph(self, graph: list[dict[int, int | float]] | None) -> None:
        self._graph = graph

    @property
    def snap_index(self) -> "SnapIndex | SortedSnapIndex | GeoKDTree":
        """
        The index that snaps coordinates to their closest nodes (`closest_idx(point)`,
        `closest_idx_per_quadrant(point)`), built when a network file is loaded or else at
        the first snap, and again after nodes were added or removed.

        - Nodes too scattered for the index (a graph built from a list, or many nodes added
          to a network file) are indexed in Hilbert order, sorted in Python at each build:
          an exact tie between two places then goes to the node earlier on the curve
        """
        return self._snap_indexes.get_index_of_every_node(self)

    @snap_index.setter
    def snap_index(
        self, snap_index: "SnapIndex | SortedSnapIndex | GeoKDTree | None"
    ) -> None:
        # Set to None by add_coord_node, remove_coord_node and merge_with_other_geograph
        # (merge keeps the index of the networks before the merge while it connects
        # them); direct edits of nodes are not detected. The new `SnapIndexes` has no
        # index of a node mode: they are rebuilt with the index.
        self._snap_indexes = SnapIndexes(snap_index)
        # Node coordinates in radians for the native A* heuristic, rebuilt with the index
        self.__node_radians__ = None
        if snap_index is None:
            self.__geokdtree__ = None

    @property
    def geokdtree(self) -> "GeoKDTree":
        """
        A `geokdtree.GeoKDTree` of the nodes.
        Interchangeable with `snap_index`, sharing the same `closest_idx` and
        `closest_idx_per_quadrant` methods.
        """
        if self.__geokdtree__ is None:
            from geokdtree import GeoKDTree

            self.__geokdtree__ = GeoKDTree(points=self.nodes)
        return self.__geokdtree__

    @geokdtree.setter
    def geokdtree(self, geokdtree: "GeoKDTree | None") -> None:
        self.__geokdtree__ = geokdtree
        self.snap_index = geokdtree

    def reduce(self, iterations: int = -1) -> None:
        """
        Function:

        - Reduce the graph by bypassing pass-through nodes and summing intermediate weights.
        - Precomputes and sets reduced graph structures on self.graph_object for faster queries.
        - The graph of each metric is reduced the same way (see `get_graph_object`).

        Optional Arguments:

        - `iterations`:
            - Type: int
            - What: Number of reduction iterations to perform. If -1, reduces iteratively until convergence. If 0, no reduction is done.
            - Default: -1

        Returns:

        - None
        """
        if iterations == 0:
            return
        with log_step(
            logger, "reduce the graph", {"iterations": iterations}
        ) as indicators:
            self.graph_object.reduce(iterations)
            is_reduced = self.graph_object.is_reduced or []
            indicators["nodes"] = len(is_reduced)
            indicators["kept_nodes"] = len(is_reduced) - sum(is_reduced)
        self._reduce_iterations = iterations
        for metric_record in self._metrics.values():
            if metric_record.graph_object is not None:
                metric_record.graph_object.reduce(iterations)

    def validate_nodes(self) -> None:
        """

        Function:

        - Validate that self.nodes is properly formatted (see GeoGraph.__init__ docs for more details)
        - Raises an exception if the nodes are invalid
        - Returns None if the nodes are valid

        Required Arguments:

        - None

        Optional Arguments:

        - None
        """
        if not (isinstance(self.nodes, (list, array_views.NodePoints))):
            raise ValueError("Your nodes must be a list")
        if not (all([isinstance(i, list) for i in self.nodes])):
            raise ValueError("Your nodes must be a list of lists")
        if not (all([len(i) == 2 for i in self.nodes])):
            raise ValueError(
                "Your nodes must be a list of lists where each sub list has a length of 2"
            )
        if not (
            all(
                [
                    (
                        isinstance(i[0], (int, float))
                        and isinstance(i[1], (int, float))
                    )
                    for i in self.nodes
                ]
            )
        ):
            raise ValueError(
                "Your nodes must be a list of lists where each sub list has a numeric latitude and longitude value"
            )
        if not (
            all(
                [
                    (
                        i[0] >= -90
                        and i[0] <= 90
                        and i[1] >= -180
                        and i[1] <= 180
                    )
                    for i in self.nodes
                ]
            )
        ):
            raise ValueError(
                "Your nodes must be a list of lists where each sub list has a length of 2 with a latitude [-90,90] and longitude [-180,180] value"
            )

    def __get_node_addition_type__(self, node_addition_type):
        if node_addition_type in ("kdclosest", "kdquadrant"):
            current = node_addition_type.removeprefix("kd")
            warnings.warn(
                f"The node addition type '{node_addition_type}' is deprecated. "
                f"Use '{current}', which gives the same result.",
                DeprecationWarning,
                stacklevel=3,
            )
            return current
        if node_addition_type not in ["closest", "quadrant", "all"]:
            raise ValueError(
                "node_addition_type must be one of 'kdclosest', 'kdquadrant', 'closest', 'quadrant', or 'all'"
            )
        return node_addition_type


class LazyGeoGraph(GeoGraph):
    """
    A lazy-loading proxy for GeoGraph that delays loading/fetching the graph
    until its first attribute access or method invocation.
    """

    def __init__(self, loader_fn) -> None:
        object.__setattr__(self, "_loader_fn", loader_fn)
        object.__setattr__(self, "_initialized", False)

    def _load(self) -> "GeoGraph":
        if not object.__getattribute__(self, "_initialized"):
            loader_fn = object.__getattribute__(self, "_loader_fn")
            real_geo = loader_fn()
            object.__setattr__(self, "_initialized", True)
            object.__getattribute__(self, "__dict__").update(real_geo.__dict__)
        return self

    def load(self) -> "GeoGraph":
        """Explicitly load the underlying GeoGraph if not already loaded."""
        return self._load()

    def __getattribute__(self, name: str):
        if name in (
            "_loader_fn",
            "_initialized",
            "_load",
            "load",
            "__class__",
        ):
            return object.__getattribute__(self, name)
        if not object.__getattribute__(self, "_initialized"):
            object.__getattribute__(self, "_load")()
        return object.__getattribute__(self, name)

    def __setattr__(self, name: str, value) -> None:
        if name in ("_loader_fn", "_initialized"):
            object.__setattr__(self, name, value)
        else:
            if not object.__getattribute__(self, "_initialized"):
                object.__getattribute__(self, "_load")()
            super().__setattr__(name, value)

    def __delattr__(self, name: str) -> None:
        if name in ("_loader_fn", "_initialized"):
            object.__delattr__(self, name)
        else:
            if not object.__getattribute__(self, "_initialized"):
                object.__getattribute__(self, "_load")()
            super().__delattr__(name)

    def __repr__(self) -> str:
        if not object.__getattribute__(self, "_initialized"):
            return f"<LazyGeoGraph (not loaded) at {hex(id(self))}>"
        return f"<LazyGeoGraph (loaded) at {hex(id(self))}>"

    def __dir__(self) -> list[str]:
        self._load()
        return super().__dir__()


# The methods of `GeoGraphIO` annotate their result as "GeoGraph". `geograph_io` cannot
# import the class at the top, so `typing.get_type_hints` finds it through this name.
geograph_io.GeoGraph = GeoGraph
