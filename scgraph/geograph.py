"""Geographic graphs: a `Graph` whose nodes have a latitude and a longitude.

- `GeoGraphIO`, in `scgraph/geograph_files.py`, loads and saves networks (GeoJSON,
  graphjson, `.scgraph` files, OpenStreetMap, OSMnx), and loads or builds the networks
  of scgraph.
- `GeoGraphModifiers`, in `scgraph/geograph_edits.py`, adds and removes nodes and edges, by id
  or by coordinates.
- `GeoGraphUtils` connects a point to nearby nodes and builds the coordinates of a path.
- `GeoGraphDistanceCalculations` gives the haversine and cheap-ruler distances.
- `GeoGraph` joins these classes and answers `get_shortest_path` between two points.
- `LazyGeoGraph` stands for a `GeoGraph` and loads it at its first use.

Users reach this module through `scgraph.GeoGraph`. `scgraph/network_cache.py` downloads
the released networks, and `scgraph/built_in_geographs.py` holds the seven networks
of scgraph 3.6.0.
"""

from scgraph.utils import (
    haversine,
    distance_converter,
    cheap_ruler,
    get_lat_lon_bound_between_pts,
    get_units_per_km,
    earth_radius,
    radians_per_degree,
)
from scgraph._internal import warn_deprecated_parameter, log_step
from scgraph.edge_classes import EdgeClasses, find_edge_id
from scgraph.node_snapping import SnapIndexes
from scgraph.metrics import (
    Metric,
    parse_off_graph_weight_per_km,
    compute_weights_from_weighted_sum,
    compute_weights_from_function,
    build_default_description,
    resolve_weights_per_km,
    copy_with_edge_weights,
)
from scgraph import columns, network_file
from scgraph import geograph_files
from scgraph.geograph_files import GeoGraphIO
from scgraph.geograph_edits import GeoGraphModifiers
import logging
import warnings
import re
import types
from array import array
from itertools import zip_longest
from math import inf
from functools import partial
from typing import TYPE_CHECKING, Literal
from collections.abc import Callable, Iterable, Iterator, Sequence
from scgraph import Graph, PathNotFoundError

try:
    from scgraph.cpp import compute_weights_from_km
except ImportError:
    from scgraph.helpers.metric_weights import compute_weights_from_km

if (
    TYPE_CHECKING
):  # Only for annotations. A function that needs one of these modules imports it.
    from geokdtree import GeoKDTree
    from scgraph.helpers.snap_index import SnapIndex
    from scgraph.node_snapping import QuerySnapIndex, SortedSnapIndex

logger = logging.getLogger(__name__)


def _cut_legs(edges: list[dict]) -> list[dict]:
    """Cut the edges of a path into legs, and total each leg. A "leg" is a part of
    a route on one edge mode: consecutive edges whose classes have the same edge
    mode.

    Example, a path of four edges: a road of 2 km, two railways of 1 km and 90 km,
    and a road of 2 km. Its legs are a road leg of 2 km, a rail leg of 91 km and a
    road leg of 2 km: the two road legs stay two legs.

    Args:
        edges: The dict of each edge, in the order of the path (see
            `GeoGraph.get_path_edges`).

    Returns:
        One dict for each leg: its `mode`, its total `length`, its totals
        `metric_totals` by name, its lengths by class `class_lengths` and its node
        ids `path`. A leg starts at the node where the leg before it ends.
    """
    legs = []
    for edge in edges:
        if not legs or legs[-1]["mode"] != edge["edge_mode"]:
            legs.append(
                {
                    "mode": edge["edge_mode"],
                    "length": 0.0,
                    "metric_totals": dict.fromkeys(edge["metric_weights"], 0.0),
                    "class_lengths": {},
                    "path": [edge["origin_id"]],
                }
            )
        leg = legs[-1]
        leg["length"] += edge["length"]
        for name, weight in edge["metric_weights"].items():
            leg["metric_totals"][name] += weight
        class_lengths = leg["class_lengths"]
        class_lengths[edge["edge_class"]] = (
            class_lengths.get(edge["edge_class"], 0.0) + edge["length"]
        )
        leg["path"].append(edge["destination_id"])
    return legs


class GeoGraphUtils:
    def __get_quadrant_node_indices__(
        self,
        node: list,
        snap_index: "QuerySnapIndex",
    ) -> set[int]:
        indices = snap_index.closest_idx_per_quadrant(point=node)
        node_indices = {idx for idx in indices.values() if idx is not None}
        if not node_indices:
            node_indices.add(snap_index.closest_idx(point=node))
        return node_indices

    def __get_node_distances__(
        self,
        node: list,
        circuity: float,
        node_addition_type: str,
        lat_lon_bound: float,
        snap_index: "QuerySnapIndex",
    ) -> dict[int, float]:
        """
        Function:

        - Get distances from a new node to graph nodes selected for connection

        Required Arguments:

        - `node`
            - Type: list
            - What: A list of the latitude and longitude of the node
            - EG: [latitude, longitude] -> [31.23, 121.47]
        - `circuity`
            - Type: int | float
            - What: The circuity to apply to any distance calculations
            - Note: This defaults to 4 to prevent the algorithm from taking a direct route in direction of the destination over some impassible terrain (EG: a maritime network that goes through land)
        - `node_addition_type`
            - Type: str
            - What: The type of node addition to use
            - Options:
                - 'closest' / 'kdclosest': Connect to the closest node with the snapping index (`snap_index`)
                - 'quadrant' / 'kdquadrant': Connect to closest nodes in each quadrant with the snapping index (`snap_index`)
                - 'all': Connect to every node inside the latitude/longitude bound
            - Notes:
                - The snapping index searches the full graph; the bound applies only to 'all'
        - `lat_lon_bound`
            - Type: int | float
            - What: Forms a bounding box around the node that is to be added to graph. Only selects graph nodes to consider joining that are within this bounding box.
        - `snap_index`
            - Type: QuerySnapIndex
            - What: The snapping index of the nodes that may be selected (see `scgraph/node_snapping.py`)

        """
        if node_addition_type in ["kdclosest", "closest"]:
            closest_idx = snap_index.closest_idx(point=node)
            closest_point = self.nodes[closest_idx]
            return {
                closest_idx: haversine(
                    node,
                    closest_point,
                    circuity=circuity,
                    units=self.geograph_units,
                ),
            }
        if node_addition_type in ["kdquadrant", "quadrant"]:
            return {
                idx: haversine(
                    node,
                    self.nodes[idx],
                    circuity=circuity,
                    units=self.geograph_units,
                )
                for idx in self.__get_quadrant_node_indices__(node, snap_index)
            }
        if not (node_addition_type == "all"):
            raise ValueError(
                f"Invalid node addition type provided ({node_addition_type})"
            )
        # Get only bounded nodes
        # Find the only keep nodes that are within the bounding latitude
        top_lat = node[0] + lat_lon_bound
        bottom_lat = node[0] - lat_lon_bound
        top_lon = node[1] + lat_lon_bound
        bottom_lon = node[1] - lat_lon_bound
        nodes = {
            node_idx: node_i
            for node_idx, node_i in snap_index.list_nodes()
            if node_i[0] >= bottom_lat
            and node_i[0] <= top_lat
            and node_i[1] >= bottom_lon
            and node_i[1] <= top_lon
        }
        if len(nodes) == 0:
            logger.debug(
                "No node within %s degrees of %s; the closest node is used",
                lat_lon_bound,
                node,
            )
            closest_idx = snap_index.closest_idx(point=node)
            closest_point = self.nodes[closest_idx]
            return {
                closest_idx: haversine(
                    node,
                    closest_point,
                    circuity=circuity,
                    units=self.geograph_units,
                )
            }
        return {
            node_idx: haversine(
                node,
                node_i,
                circuity=circuity,
                units=self.geograph_units,
            )
            for node_idx, node_i in nodes.items()
        }

    def __get_intermediate_nodes__(
        self, origin_idx: int, destination_idx: int, sequence: str = "lat_lon"
    ) -> list[list[float]]:
        """
        Function:

        - Get the intermediate nodes between two nodes if they exist in the graph object
        - Note: Not as performant so not used in __get_coordinate_path__, but can be used in post processing of the path if desired

        Required Arguments:

        - `origin_idx`
            - Type: int
            - What: The index of the origin node
        - `destination_idx`
            - Type: int
            - What: The index of the destination node
        - `sequence`
            - Type: str
            - What: The sequence of coordinates to return, either "lat_lon" or "lon_lat"
            - Default: "lat_lon"
        """
        if self.intermediate_nodes is not None:
            if sequence not in [
                "lat_lon",
                "lon_lat",
            ]:
                raise ValueError(
                    f"Invalid sequence provided ({sequence}), valid options are: ['lat_lon', 'lon_lat']"
                )
            out = self.intermediate_nodes[origin_idx].get(destination_idx, [])
            if sequence == "lon_lat":
                out = [[point[1], point[0]] for point in out]
            return out
        else:
            return []

    def __format_coordinates__(
        self,
        coordinate_path: list[list[int | float]],
        output_format: str = "list_of_lists",
    ) -> list:
        """
        Function:

        Arguments:

        - `coordinate_path`
            - Type: list of lists
            - What: A list of lists where each sublist is a point [latitude, longitude]
        - `output_format`
            - Type: str
            - What: The format to return the coordinates in
            - Options:
                - 'list_of_lists': A list of lists with the first value being latitude and the second being longitude
                - 'list_of_lists_long_first': A list of lists with the first value being longitude and the second being latitude
                - 'list_of_dicts': A list of dictionaries with keys 'latitude' and 'longitude'
            - Default: 'list_of_lists'

        """
        if output_format == "list_of_lists":
            return coordinate_path
        elif output_format == "list_of_lists_long_first":
            return [[i[1], i[0]] for i in coordinate_path]
        elif output_format == "list_of_dicts":
            return [
                {"latitude": i[0], "longitude": i[1]} for i in coordinate_path
            ]
        else:
            raise ValueError(
                "Invalid output_format. Must be one of 'list_of_lists', 'list_of_lists_long_first', or 'list_of_dicts'"
            )

    def __get_coordinate_path__(
        self, path: list[int], get_intermediate_nodes: bool = False
    ) -> list[list[float]]:
        """
        Function:

        - Return a list of node dictionaries (lat + long) in the order they are visited

        Required Arguments:

        - `path`
            - Type: list
            - What: A list of node ids in the order they are visited

        Optional Arguments:

        - `get_intermediate_nodes`
            - Type: bool
            - What: If True, returns the intermediate nodes in the path (if they exist for each segment)
            - Default: False
        """
        nodes = self.nodes
        coordinates = (
            nodes.take(path)
            if isinstance(nodes, columns.NodePoints)
            else [nodes[node_id] for node_id in path]
        )
        if (
            get_intermediate_nodes
            and self.intermediate_nodes is not None
            and path
        ):
            if isinstance(self.intermediate_nodes, columns.EdgeShapes):
                return self.intermediate_nodes.coordinate_path(
                    path, coordinates
                )
            # Start with the origin node
            coordinate_path = [coordinates[0]]
            for i in range(len(path) - 1):
                origin_id = path[i]
                destination_id = path[i + 1]
                # Nodes added after loading (add_coord_node) have no shapes
                shapes = (
                    self.intermediate_nodes[origin_id]
                    if origin_id < len(self.intermediate_nodes)
                    else {}
                )
                intermediate_nodes = shapes.get(destination_id, [])
                coordinate_path.extend(intermediate_nodes)
                # Add the destination node
                coordinate_path.append(coordinates[i + 1])
            return coordinate_path
        return coordinates

    def get_path_weight(
        self,
        path_result: dict,
        off_graph_circuity: float | None = None,
        output_units: str = "km",
        *,
        metric: str | None = None,
    ) -> float:
        """
        Function:

        - Compute the total weight of a pre-computed path in this geograph's units
        - With `metric`, compute the total of this metric along the path: `geograph.get_path_weight(result, metric="hours")`

        - This allows computing the weight of a path optimized for one metric
          (e.g., time) using a different geograph's weights (e.g., distance),
          including the off-graph entry and exit segments using this geograph's
          circuity.

        Required Arguments:

        - `path_result`
            - Type: dict
            - What: The output from `get_shortest_path` called with `output_path=True`
            - Must contain both a `path` key (list of on-graph node ids) and a
              `coordinate_path` key (list of [lat, lon] pairs)

        Optional Arguments:

        - `off_graph_circuity`
            - Type: float | int | None
            - What: Circuity to apply to the off-graph entry and exit haversine
              distances. Defaults to `self.default_off_graph_circuity`.
            - Default: None

        - `output_units`
            - Type: str
            - What: Units for the returned weight value
            - Default: 'km'

        - `metric`
            - Type: str
            - What: The name of a metric of `metrics`. The total is the weight in
              this metric of the edges of the path, plus the weight of the two
              off-graph legs: their km times `off_graph_circuity` times the
              weight of 1 km of an off-graph leg in the metric
            - Note: The total of a metric other than 'length' is not converted to
              `output_units`. An unknown name raises a ValueError
            - Default: None (the `default_metric` of the geograph, which is
              'length' unless a loader or the caller set it)

        Returns:

        - The total weight of the path in this geograph's edge units, converted
          to `output_units`
        """
        if off_graph_circuity is None:
            off_graph_circuity = self.default_off_graph_circuity
        if metric is None:
            metric = self.default_metric
        path = path_result.get("path")
        coordinate_path = path_result.get("coordinate_path")
        if not (path is not None):
            raise ValueError(
                "path_result must contain a 'path' key; call get_shortest_path with output_path=True"
            )
        if not (coordinate_path is not None):
            raise ValueError("path_result must contain a 'coordinate_path' key")

        origin = coordinate_path[0]
        destination = coordinate_path[-1]

        if metric != "length":
            off_graph_km = off_graph_circuity * self._get_off_graph_km(
                path, origin, destination
            )
            return (
                self._get_path_total(path, metric)
                + off_graph_km
                * self._read_metric(metric).off_graph_weight_per_km
            )
        if len(path) == 0:
            # Edge case: origin and destination map to the same graph node
            total = haversine(
                origin,
                destination,
                circuity=off_graph_circuity,
                units=self.geograph_units,
            )
        else:
            on_graph_weight = self.graph_object.get_path_weight(path)
            origin_off = haversine(
                origin,
                self.nodes[path[0]],
                circuity=off_graph_circuity,
                units=self.geograph_units,
            )
            destination_off = haversine(
                self.nodes[path[-1]],
                destination,
                circuity=off_graph_circuity,
                units=self.geograph_units,
            )
            total = on_graph_weight + origin_off + destination_off

        return distance_converter(
            total,
            input_units=self.geograph_units,
            output_units=output_units,
        )

    def validate(
        self,
        check_symmetry: bool = True,
        check_connected: bool = True,
    ) -> None:
        return self.graph_object.validate(
            check_symmetry=check_symmetry,
            check_connected=check_connected,
        )


class GeoGraphDistanceCalculations:
    def haversine(
        self,
        origin_id: int,
        destination_id: int,
    ) -> float:
        """
        Function:

        - Calculate the haversine distance between two points on the Earth, in the units of the GeoGraph (`geograph_units`).
        - Passed as `heuristic_fn` to `get_shortest_path` with `algorithm_fn='a_star'`, the same bound is computed natively (C++ build) from a cache of the node coordinates, rebuilt when nodes are added or removed; edit nodes through the GeoGraph methods rather than in place.

        Required Arguments:

        - `origin_id`
            - Type: int
            - What: The id of the origin node in the graph
        - `destination_id`
            - Type: int
            - What: The id of the destination node in the graph

        Optional Arguments:

        - None
        """
        return haversine(
            origin=self.nodes[origin_id],
            destination=self.nodes[destination_id],
            units=self.geograph_units,
            circuity=1,
        )

    def cheap_ruler(
        self,
        origin_id: int,
        destination_id: int,
    ) -> float:
        """
        Function:

        - Calculate the distance between two points on the Earth using the cheap ruler algorithm.
        - This is based off of Mapbox's cheap ruler algorithm which is a fast approximation of the haversine distance
        - It has modifications to support distances across the antimeridian
        - The distance is in the units of the GeoGraph (`geograph_units`).

        Required Arguments:

        - `origin_id`
            - Type: int
            - What: The id of the origin node in the graph
        - `destination_id`
            - Type: int
            - What: The id of the destination node in the graph

        Optional Arguments:

        - None
        """
        return cheap_ruler(
            origin=self.nodes[origin_id],
            destination=self.nodes[destination_id],
            units=self.geograph_units,
            # Use a circuity factor of 0.95 to account for the fact that cheap_ruler can overestimate distances
            circuity=0.9,
        )


class GeoGraph(
    GeoGraphIO, GeoGraphModifiers, GeoGraphUtils, GeoGraphDistanceCalculations
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
        *,
        _edge_arrays: tuple[array | memoryview, ...] | None = None,
        _edge_class_ids: array | memoryview | None = None,
        _metrics: dict[str, Metric] | None = None,
    ) -> None:
        """
        Function:

        - Create a GeoGraph object
        - The arguments that start with `_` are internal: a loader of scgraph passes the arrays of the edges of `graph`, the class id of each edge and the metrics with them
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
        self.source_node_ids = columns.SourceNodeIds(
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
        self._metrics = dict(_metrics or {})
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
        if _edge_arrays is not None:
            self._set_edge_arrays(_edge_arrays, _edge_class_ids)
        if _edge_arrays is not None and _edge_class_ids is not None:
            self._edge_classes = EdgeClasses(
                classes, _edge_arrays[0], _edge_arrays[1], _edge_class_ids
            )
        elif classes is not None or edge_classes is not None:
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

    @property
    def classes(self) -> list[dict]:
        """
        The classes of the edges, as rows `{"name": ..., "edge_mode": ...}`. A class
        is the category of an edge, such as `motorway`. Its edge mode is the kind of
        transport of its edges, such as `road`. A loader, the arguments `classes` and
        `edge_classes` of the constructor, or a merge gives classes to a geograph.
        Without them, the list is empty. `get_edges` gives the class of each edge.
        """
        return self._edge_classes.classes

    def _read_edge_arrays(
        self, check_edge_count: bool = False
    ) -> tuple[array | memoryview, ...]:
        # Return the offsets, the heads and the lengths of the edges of
        # `graph_object`. The method reads them again when the graph or its count
        # of edits has changed: the caller may have edited `graph_object` itself.
        # It then removes the metrics: a metric has the weight of each edge at the
        # id that the edge had before the edit.
        graph = self.graph_object
        # A pure-Python graph keeps its edges in the list `__graph__`, which a
        # caller can change without a counted edit. A C++ graph has no such list.
        # The count reads every node, so only a call that computes or writes one
        # value for each edge asks for it: a query does not.
        rows = getattr(graph, "__graph__", None) if check_edge_count else None
        if (
            graph is not self._edge_arrays_graph
            or graph.edit_count != self._edge_arrays_edit_count
        ):
            self._remove_metrics()
            self._set_edge_arrays(graph.get_edge_arrays())
        elif rows is not None and sum(map(len, rows)) != len(
            self._edge_arrays[1]
        ):
            raise ValueError(
                "The edges of graph_object changed without add_edge, "
                "remove_edge, add_node or remove_node. Edit the edges with "
                "these methods of the geograph or of graph_object."
            )
        return self._edge_arrays

    def _set_edge_arrays(
        self,
        edge_arrays: tuple[array | memoryview, ...],
        edge_class_ids: array | memoryview | None = None,
    ) -> None:
        # Keep the offsets, the heads and the lengths of the edges of
        # `graph_object`, for `_read_edge_arrays`. `edge_class_ids` gives the
        # class id of each of these edges when a network file holds it. With
        # None, `_read_edge_class_ids` computes it.
        self._edge_arrays = edge_arrays
        self._edge_arrays_graph = self.graph_object
        self._edge_arrays_edit_count = self.graph_object.edit_count
        self._edge_class_ids = edge_class_ids

    def _read_edge_class_ids(self) -> array | memoryview | None:
        # Return the class id of each edge of `graph_object`, by edge id: 255 for
        # an edge without a class. Return None for a geograph without classes.
        # The array is computed at the first call, and again after an edit.
        offsets, heads, _ = self._read_edge_arrays()
        if self._edge_class_ids is None:
            self._edge_class_ids = self._edge_classes.list_edge_class_ids(
                offsets, heads
            )
        return self._edge_class_ids

    def _remove_metrics(self) -> None:
        # Remove every metric other than `length`, at an edit of the network, and
        # warn with their names.
        if self._metrics:
            warnings.warn(
                "An edit of the network removed its metrics "
                f"{list(self._metrics)}. Create them again with `create_metric`.",
                stacklevel=3,
            )
            self._metrics = {}

    def _read_metrics(self) -> dict[str, Metric]:
        # Return the metrics other than `length`, by name. A geograph with
        # metrics first reads its edges: an edit made on `graph_object` removes
        # the metrics here.
        if self._metrics:
            self._read_edge_arrays()
        return self._metrics

    def _read_metric(self, metric: str) -> Metric:
        # Return the record of a metric other than `length`, as `_read_metrics`
        # reads it.
        metrics = self._read_metrics()
        if metric not in metrics:
            raise ValueError(
                f"Unknown metric {metric!r}: the metrics of this geograph are "
                f"{['length', *metrics]}. An edit of the network removes the "
                "metrics other than 'length'"
                + (
                    f". {metric!r} is the `default_metric` of this geograph: "
                    "create this metric again, or set `default_metric`"
                    if metric == self.default_metric
                    else ""
                )
            )
        return metrics[metric]

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

    def _get_node_radians(self) -> tuple[array, array]:
        # Also rebuilt when nodes were appended or removed directly; in-place edits of
        # existing nodes are not detected (as for the snapping index)
        if self.__node_radians__ is None or len(
            self.__node_radians__[0]
        ) != len(self.nodes):
            self.__node_radians__ = (
                array(
                    "d", (radians_per_degree * node[0] for node in self.nodes)
                ),
                array(
                    "d", (radians_per_degree * node[1] for node in self.nodes)
                ),
            )
        return self.__node_radians__

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

    @property
    def metrics(self) -> list[dict]:
        """
        The info of each metric (see `create_metric`): what describes the metric,
        without the weights of its edges. The first one is `length`, with its unit:
        `geograph_units`. The info of another metric has its `name`, its `unit` and
        `description` if it has them, and `off_graph_weight_per_km`: the weight of
        1 km of an off-graph leg.
        """
        return [{"name": "length", "unit": self.geograph_units}] + [
            metric_record.get_info()
            for metric_record in self._read_metrics().values()
        ]

    def create_metric(
        self,
        name: str,
        *,
        weight_per_km: float | dict | None = None,
        class_weight_per_km: dict | None = None,
        weight_at_hub: dict | None = None,
        weighted_sum_of: dict[str, float] | None = None,
        edge_weight_fn: Callable | None = None,
        off_graph_weight_per_km: float | None = None,
        edge_weights: dict | None = None,
        unit: str | None = None,
        description: str | None = None,
    ) -> None:
        """
        Function:

        - Create a metric: one weight for each edge, under a name. `get_shortest_path(metric=name)` then finds the route with the smallest total of these weights
        - Every optional argument is None by default. A call gives exactly one of `weight_per_km`, `weighted_sum_of` and `edge_weight_fn`. A weight is a number of zero or more. None in place of a weight closes its edges: no route by this metric takes them
        - The weights are computed at the call. A metric of the same name is replaced, and no other metric changes. An edit of the network removes the metric (see `add_edge`)
        - Example: `geograph.create_metric("hours", weight_per_km={"road": 1 / 60, "rail": 1 / 40, "off_graph": 1 / 30}, class_weight_per_km={"motorway": 1 / 90}, weight_at_hub={"rail_terminal": {"rail": 4}}, unit="h")`

        Required Arguments:

        - `name`: The name of the metric: small letters, digits and `_`, starting with a letter; not `length`

        Optional Arguments:

        - `weight_per_km`: The weight of 1 km: the weight of an edge is its weight per km times its km. The lengths of the geograph must be in km
            - A number is the weight per km of every edge, and of the off-graph legs: the straight lines between the points of a query and their nodes
            - A dict is `{mode of a leg: weight of 1 km}`. Its keys are the edge modes (see `classes`) and `"off_graph"`, for the off-graph legs. The dict must have `"off_graph"`, and the edge mode of each class that has an edge and that `class_weight_per_km` does not name. None closes an edge mode
            - With a dict, an edge without a class has the weight of an off-graph leg: its km times the weight of `"off_graph"`. `weight_at_hub` adds nothing to it
        - `class_weight_per_km`: With `weight_per_km`, `{name of a class: weight of 1 km}`: the weight per km of the edges of this class, in place of the weight per km of their edge mode. None closes a class
        - `weight_at_hub`: With `weight_per_km`, `{node mode of a hub: {edge mode: weight}}`: the weight that is added to an edge of this edge mode when it leaves a node of this node mode, and when it enters one. `{"port": {"sea": 12}}` adds 12 to each sea edge that enters a port, and to each sea edge that leaves a port
        - `weighted_sum_of`: `{name of a metric: coefficient}`: the weight of an edge is the sum of its weight in each metric times the coefficient, a finite number above zero. `length` may be one of the metrics. An edge that is closed in one of these metrics is closed in the sum. The sum keeps its weights when one of these metrics is created again
        - `edge_weight_fn`: A function that takes the dictionary of an edge (see `get_edges`) and returns its weight. It is called once for each edge, and for the edges only. It needs `off_graph_weight_per_km`
        - `off_graph_weight_per_km`: With `edge_weight_fn`, the weight of 1 km of an off-graph leg, a finite number of zero or more. The other ways refuse it: a number of `weight_per_km` is also the weight per km of the off-graph legs, a dict of `weight_per_km` has the key `"off_graph"`, and a sum adds the weights per km of the off-graph legs of its metrics
        - `edge_weights`: `{(origin_id, destination_id): weight}`: the weight of these edges, in place of the weight computed above
        - `unit`: The unit of the weights, as free text
        - `description`: Where the weights come from, as free text; the text of this call when None

        Raises:

        - `ValueError`: An argument breaks a rule above. The message names the argument, or the two nodes of the first edge with a weight below zero or not a number
        """
        if (
            not (
                isinstance(name, str) and re.fullmatch("[a-z][a-z0-9_]*", name)
            )
            or name == "length"
        ):
            raise ValueError(
                "The name of a metric has small letters, digits and '_', starts "
                f"with a letter and is not 'length': got {name!r}"
            )
        if [weight_per_km, weighted_sum_of, edge_weight_fn].count(None) != 2:
            raise ValueError(
                "create_metric takes exactly one of weight_per_km, "
                "weighted_sum_of and edge_weight_fn"
            )
        if weight_per_km is None:
            if class_weight_per_km is not None:
                raise ValueError(
                    "class_weight_per_km needs weight_per_km: it replaces the "
                    "weight per km of the edge mode of a class"
                )
            if weight_at_hub is not None:
                raise ValueError(
                    "weight_at_hub needs weight_per_km: a hub weight is added "
                    "to the weight that a weight per km gives"
                )
        elif self.geograph_units != "km":
            raise ValueError(
                "weight_per_km needs lengths in km: the lengths of this "
                f"geograph are in {self.geograph_units!r}"
            )
        if edge_weight_fn is None:
            if off_graph_weight_per_km is not None:
                raise ValueError(
                    "off_graph_weight_per_km needs edge_weight_fn: weight_per_km "
                    "and weighted_sum_of give the weight of 1 km of an off-graph "
                    "leg themselves"
                )
        elif off_graph_weight_per_km is None:
            raise ValueError(
                "edge_weight_fn needs off_graph_weight_per_km: the weight of 1 km "
                "of an off-graph leg. The function is called for the edges only"
            )
        description = description or build_default_description(
            weight_per_km=weight_per_km,
            class_weight_per_km=class_weight_per_km,
            weight_at_hub=weight_at_hub,
            weighted_sum_of=weighted_sum_of,
            edge_weight_fn=edge_weight_fn,
            off_graph_weight_per_km=off_graph_weight_per_km,
            edge_weights=edge_weights,
        )
        offsets, heads, lengths = self._read_edge_arrays(check_edge_count=True)
        units_per_km = get_units_per_km(self.geograph_units)
        if weight_per_km is not None:
            edge_class_ids = self._read_edge_class_ids()
            if edge_class_ids is None:
                # No edge has a class: `weight_per_km` is one weight per km for
                # every edge
                edge_class_ids = array(
                    "B", bytes([network_file.NO_CLASS_ID]) * len(heads)
                )
            # Nodes appended to `nodes` directly are in the first node mode
            node_mode_ids = self.node_mode_ids + array(
                "B", bytes(len(offsets) - 1 - len(self.node_mode_ids))
            )
            class_weights_per_km, hub_weights, off_graph_weight_per_km = (
                resolve_weights_per_km(
                    weight_per_km,
                    class_weight_per_km,
                    weight_at_hub,
                    self.classes,
                    self.node_modes,
                    edge_class_ids,
                )
            )
            weights = compute_weights_from_km(
                offsets,
                heads,
                lengths,
                edge_class_ids,
                node_mode_ids,
                class_weights_per_km,
                hub_weights,
            )
        elif weighted_sum_of is not None:
            weights, off_graph_weight_per_km = (
                compute_weights_from_weighted_sum(
                    weighted_sum_of, self._metrics, lengths, units_per_km
                )
            )
        else:
            weights = compute_weights_from_function(
                edge_weight_fn, self._iter_edge_dicts(self._iter_edges())
            )
        if edge_weights:
            weights = copy_with_edge_weights(
                weights, edge_weights, offsets, heads
            )
        # The metric is kept when every check has passed
        self._metrics[name] = Metric(
            name,
            unit,
            description,
            weights,
            parse_off_graph_weight_per_km(name, off_graph_weight_per_km),
        )

    def remove_metric(self, name: str) -> None:
        """
        Function:

        - Remove a metric that `create_metric` made, or that a loader read
        - Example: `geograph.remove_metric("hours")`

        Required Arguments:

        - `name`: The name of a metric of `metrics`, other than `length`; an unknown name raises a ValueError
        """
        self._read_metric(name)
        del self._metrics[name]

    def get_graph_object(self, metric: str | None = None) -> Graph:
        """
        Function:

        - Get the `Graph` that a search by a metric runs on: the edges of the geograph, with the weights of the metric. A search called on it returns the total of the metric under the key `length`
        - For `length`, it is `graph_object`. For another metric, the graph is built at the first call and kept until the metric is created again or removed. It is reduced when `graph_object` is reduced (see `reduce`)
        - Example: `geograph.get_graph_object("hours").dijkstra(origin_id=0, destination_id=2)`

        Optional Arguments:

        - `metric`: The name of a metric of `metrics`; an unknown name raises a ValueError. None is the `default_metric` of the geograph, which is 'length' unless a loader or the caller set it
        """
        if metric is None:
            metric = self.default_metric
        if metric == "length":
            return self.graph_object
        metric_record = self._read_metric(metric)
        if metric_record.graph_object is None:
            offsets, heads, _ = self._read_edge_arrays()
            # The graph reads the three arrays in place and keeps them alive
            graph = Graph.from_csr(
                offsets, heads, metric_record.weights, copy=False
            )
            if self.graph_object.is_reduced is not None:
                graph.reduce(
                    -1
                    if self._reduce_iterations is None
                    else self._reduce_iterations
                )
            metric_record.graph_object = graph
        return metric_record.graph_object

    def get_nodes(
        self,
        node_mode: str | None = None,
        bbox: Sequence[float] | None = None,
    ) -> list[dict]:
        """
        Function:

        - Get the nodes of the geograph, or those of one node mode or inside a bounding box

        Optional Arguments:

        - `node_mode`: The name of a node mode of `node_modes`: only the nodes of this node mode are returned; an unknown name raises a ValueError
        - `bbox`: A bounding box `(south, west, north, east)` in degrees: only the nodes with `south <= latitude <= north` and `west <= longitude <= east` are returned

        Returns:

        - A list with one dictionary for each node, in the order of the node ids: `{"node_id", "latitude", "longitude", "node_mode"}`. `node_mode` is the name of the node mode of the node (None on a geograph without named node modes)
        """
        node_mode_names = [row.get("name") for row in self.node_modes]
        if node_mode is not None and node_mode not in node_mode_names:
            raise ValueError(
                f"Unknown node mode {node_mode!r}: the node modes of this "
                f"geograph are {node_mode_names}"
            )
        south, west, north, east = (
            (-inf, -inf, inf, inf) if bbox is None else bbox
        )
        nodes = []
        # A node appended to `nodes` directly is in the first node mode
        for node_id, (point, node_mode_id) in enumerate(
            zip_longest(self.nodes, self.node_mode_ids, fillvalue=0)
        ):
            if (
                node_mode in (None, node_mode_names[node_mode_id])
                and south <= point[0] <= north
                and west <= point[1] <= east
            ):
                nodes.append(
                    {
                        "node_id": node_id,
                        "latitude": point[0],
                        "longitude": point[1],
                        "node_mode": node_mode_names[node_mode_id],
                    }
                )
        return nodes

    def get_edges(
        self,
        origin_id: int | None = None,
        edge_class: str | None = None,
    ) -> list[dict]:
        """
        Function:

        - Get the edges of the geograph, or those of one node or of one class. With both arguments, only the edges that fit both are returned

        Optional Arguments:

        - `origin_id`: The id of a node: only the edges that leave this node are returned; an id that is not in the geograph raises a ValueError
        - `edge_class`: The name of a class of `classes`: only the edges of this class are returned; an unknown name raises a ValueError

        Returns:

        - A list with one dictionary for each edge, in the order of the origins: `{"origin_id", "destination_id", "length", "edge_class", "edge_mode", "metric_weights"}`
        - `length` is in `geograph_units`. `edge_class` is the name of the class of the edge and `edge_mode` is the edge mode of that class; both are None for an edge without a class
        - `metric_weights` is a dictionary `{name: weight}`: the weight of the edge in each metric other than `length`; infinity for an edge that is closed in the metric
        """
        offsets, heads, _ = self._read_edge_arrays()
        if origin_id is not None and not 0 <= origin_id < len(offsets) - 1:
            raise ValueError(f"Node {origin_id} is not in the geograph")
        self._edge_classes.check_class(edge_class)
        edges = self._iter_edges(origin_id)
        if edge_class is not None:
            find_class = self._edge_classes.find_class
            edges = (
                (origin_id, edge_id)
                for origin_id, edge_id in edges
                if find_class(origin_id, heads[edge_id])["name"] == edge_class
            )
        return list(self._iter_edge_dicts(edges))

    def _iter_edges(
        self, origin_id: int | None = None
    ) -> Iterator[tuple[int, int]]:
        """Return each edge of one node, or every edge for None, as (origin id,
        edge id), in the order of the edges."""
        offsets = self._read_edge_arrays()[0]
        origin_ids = (
            range(len(offsets) - 1) if origin_id is None else (origin_id,)
        )
        return (
            (origin_id, edge_id)
            for origin_id in origin_ids
            for edge_id in range(offsets[origin_id], offsets[origin_id + 1])
        )

    def _iter_edge_dicts(
        self, edges: Iterable[tuple[int, int]]
    ) -> Iterator[dict]:
        """Yield the dictionary of each edge, as `get_edges` returns it. `edges`
        gives each edge as (origin id, edge id)."""
        _, heads, lengths = self._read_edge_arrays()
        find_class = self._edge_classes.find_class
        weights_of_metrics = [
            (name, metric_record.weights)
            for name, metric_record in self._metrics.items()
        ]
        for origin_id, edge_id in edges:
            destination_id = heads[edge_id]
            class_row = find_class(origin_id, destination_id)
            yield {
                "origin_id": origin_id,
                "destination_id": destination_id,
                "length": lengths[edge_id],
                "edge_class": class_row["name"],
                "edge_mode": class_row["edge_mode"],
                "metric_weights": {
                    name: weights[edge_id]
                    for name, weights in weights_of_metrics
                },
            }

    def _find_path_edge_ids(self, path: list[int]) -> list[int]:
        # The id of each edge of a path
        offsets, heads, _ = self._read_edge_arrays()
        edge_ids = []
        for origin_id, destination_id in zip(path, path[1:]):
            edge_id = find_edge_id(offsets, heads, origin_id, destination_id)
            if edge_id is None:
                raise ValueError(
                    f"The geograph has no edge from node {origin_id} to node "
                    f"{destination_id}"
                )
            edge_ids.append(edge_id)
        return edge_ids

    def _get_path_total(self, path: list[int], metric: str) -> float:
        # The total of a metric along the edges of a path. The metric may be
        # `length`.
        lengths = self._read_edge_arrays()[2]
        weights = (
            lengths if metric == "length" else self._read_metric(metric).weights
        )
        return sum(
            weights[edge_id] for edge_id in self._find_path_edge_ids(path)
        )

    def get_path_edges(self, path: list[int]) -> list[dict]:
        """
        Function:

        - Get the edges of a path, in the order of the path

        Required Arguments:

        - `path`: The node ids of a path, as the `path` of `get_shortest_path` with `output_path=True`; two consecutive nodes without an edge raise a ValueError

        Returns:

        - A list with one dictionary for each pair of consecutive nodes of the path (see `get_edges`)
        """
        return list(
            self._iter_edge_dicts(zip(path, self._find_path_edge_ids(path)))
        )

    def _get_metric_totals(
        self,
        path: list[int],
        origin: Sequence[float],
        destination: Sequence[float],
        off_graph_circuity: float,
    ) -> dict[str, float]:
        """Return the total of each metric other than `length` along a route: the
        weight of each edge of `path`, plus the off-graph legs from the points
        `origin` and `destination` of the query. The weight of an off-graph leg is
        its km, times `off_graph_circuity`, times `off_graph_weight_per_km` of the
        metric."""
        off_graph_km = off_graph_circuity * self._get_off_graph_km(
            path, origin, destination
        )
        edge_ids = self._find_path_edge_ids(path)
        return {
            name: sum(metric_record.weights[edge_id] for edge_id in edge_ids)
            + off_graph_km * metric_record.off_graph_weight_per_km
            for name, metric_record in self._metrics.items()
        }

    def _get_off_graph_km(
        self,
        path: list[int],
        origin: Sequence[float],
        destination: Sequence[float],
    ) -> float:
        # The km of the two off-graph legs of a route, without circuity. A route
        # without a node is one off-graph leg from the origin to the destination.
        if not path:
            return haversine(origin, destination)
        return haversine(origin, self.nodes[path[0]]) + haversine(
            self.nodes[path[-1]], destination
        )

    def _get_legs(
        self,
        path: list[int],
        origin: Sequence[float],
        destination: Sequence[float],
        off_graph_circuity: float,
        get_intermediate_nodes: bool,
    ) -> tuple[list[dict], list[dict]]:
        """Return the legs and the transfers of a route, as `get_shortest_path`
        describes them. `_cut_legs` makes the legs on the network from the edges of
        `path`. An off-graph leg joins each point of the query to its node
        (`_get_off_graph_legs`). The lengths are in the units of the geograph, and
        each coordinate path is a list of [latitude, longitude]. `_format_leg` then
        gives a leg the units and the format that the query asks for."""
        legs = _cut_legs(self.get_path_edges(path))
        transfers = self._get_transfers(legs)
        for leg in legs:
            leg["coordinate_path"] = self.__get_coordinate_path__(
                leg.pop("path"), get_intermediate_nodes=get_intermediate_nodes
            )
        off_graph_legs = self._get_off_graph_legs(
            path, origin, destination, off_graph_circuity
        )
        return [off_graph_legs[0], *legs, *off_graph_legs[1:]], transfers

    def _get_transfers(self, legs: list[dict]) -> list[dict]:
        """Return the transfers of a route: each node where a leg on the network
        ends and the next one starts. `legs` are the legs of `_cut_legs`, which
        still have the node ids of their `path`."""
        transfers = []
        for leg in legs[1:]:
            node_id = leg["path"][0]
            node_mode = self.node_modes[self.node_mode_ids[node_id]]
            transfers.append(
                {"node_id": node_id, "node_mode": node_mode.get("name")}
            )
        return transfers

    def _get_off_graph_legs(
        self,
        path: list[int],
        origin: Sequence[float],
        destination: Sequence[float],
        off_graph_circuity: float,
    ) -> list[dict]:
        """Return the off-graph legs of a route, with the keys of a leg of
        `_cut_legs` and a `coordinate_path` in place of `path`. A route with an
        edge has two: from `origin` to the first node of `path`, and from its last
        node to `destination`. A route without an edge is one off-graph leg,
        through the node of its path if it has one. An off-graph leg has the
        weight that `_get_metric_totals` gives it in the totals of the route."""
        if len(path) > 1:
            off_graph_paths = [
                [origin, self.nodes[path[0]]],
                [self.nodes[path[-1]], destination],
            ]
        else:
            off_graph_paths = [
                [
                    origin,
                    *(self.nodes[node_id] for node_id in path),
                    destination,
                ]
            ]
        off_graph_legs = []
        for points in off_graph_paths:
            hops = list(zip(points, points[1:]))
            off_graph_km = off_graph_circuity * sum(
                haversine(start, end) for start, end in hops
            )
            off_graph_legs.append(
                {
                    "mode": "off_graph",
                    "length": sum(
                        haversine(
                            start,
                            end,
                            circuity=off_graph_circuity,
                            units=self.geograph_units,
                        )
                        for start, end in hops
                    ),
                    "metric_totals": {
                        name: off_graph_km
                        * metric_record.off_graph_weight_per_km
                        for name, metric_record in self._metrics.items()
                    },
                    "class_lengths": {},
                    "coordinate_path": points,
                }
            )
        return off_graph_legs

    def _format_leg(
        self, leg: dict, output_units: str, output_coordinate_path: str
    ) -> None:
        """Give a leg of `_get_legs` the form that a query asks for: its lengths in
        `output_units`, and its coordinate path in the format
        `output_coordinate_path`. A geograph without a metric gives no
        `metric_totals`. The leg is changed in place."""
        leg["length"] = distance_converter(
            leg["length"],
            input_units=self.geograph_units,
            output_units=output_units,
        )
        leg["class_lengths"] = {
            name: distance_converter(
                length,
                input_units=self.geograph_units,
                output_units=output_units,
            )
            for name, length in leg["class_lengths"].items()
        }
        leg["coordinate_path"] = self.__format_coordinates__(
            coordinate_path=leg["coordinate_path"],
            output_format=output_coordinate_path,
        )
        if not self._metrics:
            del leg["metric_totals"]

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
        if not (isinstance(self.nodes, (list, columns.NodePoints))):
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

    def get_shortest_path(
        self,
        origin_node: dict[str, float],
        destination_node: dict[str, float],
        *,
        output_units: str = "km",
        algorithm_fn: str | Callable = "bidirectional_buckets",
        algorithm_kwargs: dict | None = None,
        off_graph_circuity: float = 1,
        node_addition_type: str = "closest",
        node_addition_circuity: float = 4,
        output_coordinate_path: str = "list_of_lists",
        output_path: bool = False,
        node_addition_lat_lon_bound: float | Literal["auto"] = "auto",
        node_addition_math: str = "euclidean",
        destination_node_addition_type: str = "closest",
        auto_lat_lon_bound_max: float = 2,
        silent: bool | None = None,
        length_only: bool = False,
        get_intermediate_nodes: bool | None = None,
        metric: str | None = None,
        snap_to_node_modes: list[str] | None = None,
        output_legs: bool = False,
        **kwargs,
    ) -> dict:
        """
        Function:

        - Identify the shortest path between two nodes in a sparse network graph

        - Return a dictionary of various path information including:
            - `path`: With `output_path=True`, a list of node ids in the order they are visited
            - `coordinate_path`: A list of coordinates (latitude then longitude) in the order they are visited, in the format of `output_coordinate_path`
            - `length`: The length of the path
            - `metric_totals`: On a geograph that has metrics other than `length` (see `metrics`), a dictionary `{name: total}` with the total of each of these metrics along the path
            - `legs`: With `output_legs=True`, the legs of the path in their order. A leg is a part of the path on one mode, as a dictionary `{"mode", "length", "metric_totals", "class_lengths", "coordinate_path"}`
                - `mode` is the edge mode of the edges of the leg (see `classes`). A new leg starts where this edge mode changes. The edges of a geograph without classes make one leg of the mode None
                - The first and the last leg are the off-graph legs, of the mode 'off_graph': the straight lines from the origin to the first node of the path, and from its last node to the destination. A path without an edge is one leg of the mode 'off_graph'
                - `length` and `metric_totals` are the totals of the leg, as those of the path. The length of the path is the sum of the lengths of its legs, and so is each total of `metric_totals`. A leg has the key `metric_totals` only when the path has it
                - `class_lengths` is a dictionary `{class name: length}`: the length of the leg on each class of edges, in `output_units`. It is empty for an off-graph leg
                - `coordinate_path` holds the coordinates of the leg, in the format of `output_coordinate_path`
            - `transfers`: With `output_legs=True`, a list of dictionaries `{"node_id", "node_mode"}`: each node where the path goes from a leg of one edge mode to a leg of another, with the node mode of this node (see `node_modes`). The two nodes where an off-graph leg meets the network are not transfers

         Required Arguments:

        - `origin_node`
            - Type: dict of int | float
            - What: A dictionary with the keys 'latitude' and 'longitude'
        - `destination_node`
            - Type: dict of int | float
            - What: A dictionary with the keys 'latitude' and 'longitude'

        Optional Arguments:

        - `output_units`
            - Type: str
            - What: The units in which to return the length of the path
            - Default: 'km'
            - Options:
                - 'km': Kilometers
                - 'm': Meters
                - 'mi': Miles
                - 'ft': Feet
        - `algorithm_fn`
            - Type: str | callable
            - What: The algorithm to use for shortest path calculation. Can be a string name of a method on the underlying Graph object, or any callable.
            - Default: 'bidirectional_buckets'
            - Options:
                - 'bidirectional_buckets' -> GraphAlgorithms.bidirectional_buckets
                    - Bidirectional Dijkstra with buckets (Dial's algorithm); default algorithm for GeoGraphs, very fast for sparse spatial networks
                - 'dijkstra' -> GraphAlgorithms.dijkstra
                    - Standard Dijkstra's algorithm; general purpose for non-negative edge weights
                - 'bidirectional_dijkstra' -> GraphAlgorithms.bidirectional_dijkstra
                    - Bidirectional Dijkstra's algorithm; searches from both origin and destination simultaneously
                - 'dijkstra_buckets' -> GraphAlgorithms.dijkstra_buckets
                    - Dijkstra with buckets (Dial's algorithm); efficient for non-negative weights
                - 'dijkstra_negative' -> GraphAlgorithms.dijkstra_negative
                    - Modified Dijkstra supporting negative edge weights; detects negative cycles
                - 'a_star' -> GraphAlgorithms.a_star
                    - A* algorithm; requires a heuristic_fn passed via algorithm_kwargs for speedup
                - 'bellman_ford' -> GraphAlgorithms.bellman_ford
                    - Bellman-Ford algorithm; supports negative weights but slower than dijkstra
                - 'bmssp' -> GraphAlgorithms.bmssp
                    - BMSSP algorithm; not actually faster in practice than dijkstra but included for completeness
                - 'cached_shortest_path' -> GraphAlgorithms.cached_shortest_path
                    - Computes and caches the full shortest path tree from the origin on the first call;
                      subsequent calls from the same origin node are near-instant
                    - Only the origin graph node is cached (not the off-graph origin point)
                    - Note: Requires that both node_addition_type and destination_node_addition_type are 'kdclosest'
                - 'contraction_hierarchy' -> GraphAlgorithms.contraction_hierarchy
                    - Bidirectional Dijkstra on a preprocessed Contraction Hierarchy graph
                    - Requires one-time preprocessing via graph_object.create_contraction_hierarchy()
                      (called automatically on first use if not already done)
                    - Very fast for arbitrary origin-destination queries on large graphs
                    - Note: Requires that both node_addition_type and destination_node_addition_type are 'kdclosest'
                - 'tnr' -> TNRGraph.search
                    - Transit Node Routing; extremely fast for global queries on large graphs
                    - Requires preprocessing via TNRGraph initialization or create_tnr_hierarchy()
                    - Note: Requires that both node_addition_type and destination_node_addition_type are 'kdclosest'
                - Any callable that accepts:
                    - `graph`: The graph (list[dict[int, int | float]]) to perform the shortest path on
                    - `origin_id`: The id of the origin node
                    - `destination_id`: The id of the destination node
                    - `**algorithm_kwargs`: Additional keyword arguments
        - `algorithm_kwargs`
            - Type: dict
            - What: Additional keyword arguments to pass to the algorithm function assuming it accepts them
        - `off_graph_circuity`
            - Type: int | float
            - What: The physical distance multiplier applied to final off-graph access legs (origin -> entrance node and exit node -> destination) after the route is solved
            - Default: 1 (more specifically `self.default_off_graph_circuity`)
            - Notes:
                - During pathfinding, `node_addition_circuity` is used to penalize off-graph travel and select the entry/exit nodes
                - Once the optimal route sequence is determined, the actual reported `length` scales the access distance by `off_graph_circuity`
                - Set to 0 if access legs should not contribute to total route length/time
        - `node_addition_type`
            - Type: str
            - What: The snapping strategy used to connect off-graph origin and destination coordinates to the network
            - Default: 'closest'
            - Options:
                - 'kdclosest' / 'closest': Snap to the single closest node using `snap_index`
                - 'kdquadrant' / 'quadrant': Snap to the closest node in each spatial quadrant (up to 4 candidates)
                - 'all': Snap to all nodes within the spatial bounding box
        - `node_addition_circuity`
            - Type: int | float
            - What: The algorithmic search penalty applied to candidate off-graph connection legs *during* pathfinding
            - Default: 4 (more specifically `self.default_node_addition_circuity`)
            - Notes:
                - Penalizes off-network travel relative to on-network routing to prevent shortcuts across impassable terrain (e.g. crossing land in a maritime graph)
                - A higher penalty pushes the route to enter the network at a closer node rather than traveling off-graph towards the destination
                - Active when `node_addition_type` is 'quadrant' or 'all' (not needed for 'closest' where only one entry node exists)
                - Only influences route selection; final reported `length` uses `off_graph_circuity`
        - `output_coordinate_path`
            - Type: str
            - What: The format of the output coordinate path
            - Default: 'list_of_lists'
            - Options:
                - 'list_of_dicts': A list of dictionaries with keys 'latitude' and 'longitude'
                - 'list_of_lists': A list of lists with the first value being latitude and the second being longitude
                - 'list_of_lists_long_first': A list of lists with the first value being longitude and the second being latitude
        - `output_path`
            - Type: bool
            - What: Whether to output the path as a list of geograph node ids (for debugging and other advanced uses)
            - Default: False
        - `node_addition_lat_lon_bound`
            - Type: int | float | Literal["auto"]
            - What: Forms a bounding box around the origin and destination nodes as they are added to graph
                - The bound filters candidates only when node_addition_type is 'all'
            - Default: 'auto'
            - If set to 'auto', the bounding box is set based on the distance between the origin and destination nodes capped at `auto_lat_lon_bound_max` for the origin node
            - Note: This is only used when adding a new node (the specified origin and destination) to the graph
        - `auto_lat_lon_bound_max`
            - Type: int | float
            - What: The maximum value for the automatic latitude/longitude bounding box used only for the origin node when `node_addition_lat_lon_bound` is set to 'auto'
            - Default: 2
            - Note: Only used if `node_addition_lat_lon_bound` is set to 'auto'
        - `node_addition_math`
            - Type: str
            - What: Deprecated but kept for backwards compatibility.
        - `destination_node_addition_type`
            - Type: str
            - What: The method to use when adding the destination node to the graph
            - Default: 'closest'
            - Options:
                - 'kdclosest' / 'closest': Add the closest node with the snapping index (`snap_index`)
                - 'kdquadrant' / 'quadrant': Add the closest node in each quadrant with the snapping index (`snap_index`)
                - 'all': Add the node to all points in the graph within the bounding box
        - `silent`
            - Deprecated and without effect. scgraph reports its messages through `logging`.
        - `length_only`
            - Type: bool
            - What: If True, only returns the length of the path
            - Note: With a `metric` other than 'length', only returns the total of this metric: `{"metric_totals": {metric: total}}`
            - Note: `output_legs` is then ignored, as `output_path` is
            - Default: False
        - `get_intermediate_nodes`
            - Type: bool
            - What: If True, returns the intermediate nodes in the path (if they exist for each segment)
            - Default: self.default_get_intermediate_nodes
        - `metric`
            - Type: str
            - What: The name of the metric to minimise, a name of `metrics`: the path is the one with the smallest total of this metric. `length` in the result stays the length of the path
            - Default: None (the `default_metric` of the geograph, which is 'length' unless a loader or the caller set it)
            - Notes:
                - EG: `geograph.get_shortest_path(origin_node, destination_node, metric="hours")`
                - The search runs on `get_graph_object(metric)`. An unknown name raises a ValueError
                - When no route by the metric joins the two points, the PathNotFoundError names the metric: an edge that is closed in the metric cannot be taken
                - With `algorithm_fn='a_star'`, the bound of `geograph.haversine` or of `geograph.cheap_ruler` is a length: the geograph multiplies it by the smallest weight of 1 km of an edge in the metric. Another `heuristic_fn` is used as it is: it must give a lower bound of the total of the metric between two nodes
                - The weight of an off-graph leg is its km times the weight of 1 km in the metric (`off_graph_weight_per_km` in `metrics`), with `node_addition_circuity` during pathfinding and with `off_graph_circuity` in the reported totals
        - `snap_to_node_modes`
            - Type: list of str | None
            - What: The names of the node modes (see `node_modes`) that the origin and the destination may snap to: each one is connected only to nodes of these node modes, for every `node_addition_type`
            - Default: None (the road nodes when the geograph has a node of the node mode `road`, and the nodes that `add_coord_node` added without `node_mode`; every node otherwise)
            - Notes:
                - EG: `geograph.get_shortest_path(origin_node, destination_node, snap_to_node_modes=["road"])` starts and ends the path on a road, also when a railway or a sea lane is closer
                - An empty list, a name that is not in `node_modes`, or node modes that no node has, raise a ValueError
                - The first query that snaps to a node mode builds the snapping index of its nodes. The geograph keeps it until its nodes change
        - `output_legs`
            - Type: bool
            - What: Whether to output the legs of the path and its transfers, under the keys `legs` and `transfers` described above
            - Default: False
        - `**kwargs`
            - Additional keyword arguments. These are included for forwards and backwards compatibility reasons, but are not currently used.
        """
        warn_deprecated_parameter("silent", silent)
        algorithm_name = (
            algorithm_fn if isinstance(algorithm_fn, str) else "custom"
        )
        get_intermediate_nodes = (
            get_intermediate_nodes
            if get_intermediate_nodes is not None
            else self.default_get_intermediate_nodes
        )
        off_graph_circuity = (
            off_graph_circuity
            if off_graph_circuity is not None
            else self.default_off_graph_circuity
        )
        node_addition_circuity = (
            node_addition_circuity
            if node_addition_circuity is not None
            else self.default_node_addition_circuity
        )
        algorithm_kwargs = (
            dict(algorithm_kwargs) if algorithm_kwargs is not None else dict()
        )
        if metric is None:
            metric = self.default_metric
        # The graph whose weights are those of the metric
        graph_object = self.get_graph_object(metric)
        is_metric_other_than_length = metric != "length"
        if callable(algorithm_fn):
            algorithm_kwargs["graph"] = graph_object.unreduced_graph
        elif isinstance(algorithm_fn, str):
            heuristic_fn = algorithm_kwargs.get("heuristic_fn")
            # The methods `haversine` and `cheap_ruler` of scgraph, for this
            # geograph: each gives a length between two of its nodes. The function
            # of the caller is equal to one of them only when the caller passed
            # this method of this geograph. A subclass that defines its own
            # `haversine` passes another function, which is used as it is.
            haversine_of_scgraph = types.MethodType(
                GeoGraphDistanceCalculations.haversine, self
            )
            cheap_ruler_of_scgraph = types.MethodType(
                GeoGraphDistanceCalculations.cheap_ruler, self
            )
            if (
                algorithm_fn == "a_star"
                and hasattr(graph_object, "a_star_great_circle")
                and heuristic_fn == haversine_of_scgraph
            ):
                # The built-in haversine heuristic is computed natively in the C++ build
                latitudes, longitudes = self._get_node_radians()
                algorithm_kwargs.pop("heuristic_fn")
                radius = earth_radius.get(self.geograph_units, 6371)
                if is_metric_other_than_length:
                    # The total of a route of the length d is at least d times
                    # `min_weight_per_length_unit`: the radius times it is the bound.
                    radius *= self._read_metric(
                        metric
                    ).get_min_weight_per_length_unit(
                        self._read_edge_arrays()[2]
                    )
                algorithm_fn = partial(
                    graph_object.a_star_great_circle,
                    latitudes=latitudes,
                    longitudes=longitudes,
                    radius=radius,
                )
            elif hasattr(graph_object, algorithm_fn):
                if (
                    is_metric_other_than_length
                    and algorithm_fn == "a_star"
                    and heuristic_fn == cheap_ruler_of_scgraph
                ):
                    # `cheap_ruler` gives a length. The bound of the metric is this
                    # length times `min_weight_per_length_unit`, as for `haversine`.
                    min_weight_per_length_unit = self._read_metric(
                        metric
                    ).get_min_weight_per_length_unit(
                        self._read_edge_arrays()[2]
                    )
                    algorithm_kwargs["heuristic_fn"] = (
                        lambda origin_id, destination_id: min_weight_per_length_unit
                        * heuristic_fn(origin_id, destination_id)
                    )
                algorithm_fn = getattr(graph_object, algorithm_fn)
            else:
                raise ValueError("algorithm_fn must be a string or callable")
        else:
            raise ValueError("algorithm_fn must be a string or callable")

        node_addition_type = self.__get_node_addition_type__(node_addition_type)
        destination_node_addition_type = self.__get_node_addition_type__(
            destination_node_addition_type
        )
        snap_index = self._snap_indexes.get_index(self, snap_to_node_modes)

        # If auto lat lon bounds are needed, then calculate them.
        if "all" in [node_addition_type, destination_node_addition_type]:
            if node_addition_lat_lon_bound == "auto":
                node_addition_lat_lon_bound = min(
                    get_lat_lon_bound_between_pts(origin_node, destination_node)
                    * 1.01,
                    auto_lat_lon_bound_max,
                )
        try:
            # Parse origin and destination
            origin = [
                origin_node.get("latitude"),
                origin_node.get("longitude"),
            ]
            destination = [
                destination_node.get("latitude"),
                destination_node.get("longitude"),
            ]
            if len(origin) < 1 or len(destination) < 1:
                raise ValueError(
                    "Origin and destination must have valid latitude and longitude"
                )

            # Get the node addition direct distance between origin and destination
            direct_node_addition_length = haversine(
                origin,
                destination,
                circuity=node_addition_circuity,
                units=self.geograph_units,
            )

            # Snap the origin and destination to their closest nodes in the graph
            origin_id = self.__get_node_distances__(
                node=origin,
                circuity=node_addition_circuity,
                node_addition_type=node_addition_type,
                lat_lon_bound=node_addition_lat_lon_bound,
                snap_index=snap_index,
            )
            destination_id = self.__get_node_distances__(
                node=destination,
                circuity=node_addition_circuity,
                node_addition_type=destination_node_addition_type,
                lat_lon_bound=node_addition_lat_lon_bound,
                snap_index=snap_index,
            )

            # Calculate the circuity ratio for the node addition
            circuity_ratio = (
                off_graph_circuity / node_addition_circuity
                if node_addition_circuity != 0
                else 1.0
            )

            # If direct distance is better than any entry or exit distance, bypass graph search
            min_entry_exit = min(
                min(origin_id.values()), min(destination_id.values())
            )
            is_direct = direct_node_addition_length <= min_entry_exit
            if is_metric_other_than_length:
                # In the search, the weight of an off-graph leg is its km times the
                # weight of 1 km. The test above compares lengths: a metric whose
                # off-graph legs have a weight of zero must not make every route direct.
                off_graph_weight_per_unit = self._read_metric(
                    metric
                ).off_graph_weight_per_km / get_units_per_km(
                    self.geograph_units
                )
                direct_node_addition_length *= off_graph_weight_per_unit
                origin_id = {
                    node_id: length * off_graph_weight_per_unit
                    for node_id, length in origin_id.items()
                }
                destination_id = {
                    node_id: length * off_graph_weight_per_unit
                    for node_id, length in destination_id.items()
                }

            if logger.isEnabledFor(logging.DEBUG):
                self.graph_object.reset_node_scans()
            if is_direct:
                output = {
                    "path": [],
                    "length": direct_node_addition_length * circuity_ratio,
                }
            else:
                output = algorithm_fn(
                    origin_id=origin_id,
                    destination_id=destination_id,
                    **algorithm_kwargs,
                )
                if circuity_ratio != 1.0:
                    entry_node = (
                        output["path"][0]
                        if output.get("path")
                        else next(iter(origin_id.keys()))
                    )
                    exit_node = (
                        output["path"][-1]
                        if output.get("path")
                        else next(iter(destination_id.keys()))
                    )
                    output["length"] += (
                        origin_id[entry_node] + destination_id[exit_node]
                    ) * (circuity_ratio - 1.0)
            if logger.isEnabledFor(logging.DEBUG):
                self._log_query_indicators(
                    algorithm_name,
                    origin,
                    destination,
                    origin_id,
                    destination_id,
                )

            if is_metric_other_than_length:
                # The search returned the total of the metric. `length` stays the
                # length of the route.
                metric_total = output["length"]
                if length_only:
                    return {"metric_totals": {metric: metric_total}}
                output["length"] = self.get_path_weight(
                    {
                        "path": output["path"],
                        "coordinate_path": [origin, destination],
                    },
                    off_graph_circuity=off_graph_circuity,
                    output_units=self.geograph_units,
                    metric="length",
                )
            # Convert the length to the desired output units
            output["length"] = distance_converter(
                output["length"],
                input_units=self.geograph_units,
                output_units=output_units,
            )
            # Early return if only length is needed
            if length_only:
                return {"length": output["length"]}
            if self._read_metrics():
                output["metric_totals"] = self._get_metric_totals(
                    output["path"], origin, destination, off_graph_circuity
                )
                if is_metric_other_than_length:
                    output["metric_totals"][metric] = metric_total

            # Get the coordinate path
            output["coordinate_path"] = (
                [origin]
                + self.__get_coordinate_path__(
                    output["path"],
                    get_intermediate_nodes=get_intermediate_nodes,
                )
                + [destination]
            )

            # Format the coordinate path to the desired output format
            if output_coordinate_path != "list_of_lists":
                output["coordinate_path"] = self.__format_coordinates__(
                    coordinate_path=output["coordinate_path"],
                    output_format=output_coordinate_path,
                )
                if output_coordinate_path == "list_of_lists_long_first":
                    output["long_first"] = True

            if output_legs:
                output["legs"], output["transfers"] = self._get_legs(
                    output["path"],
                    origin,
                    destination,
                    off_graph_circuity,
                    get_intermediate_nodes,
                )
                for leg in output["legs"]:
                    self._format_leg(leg, output_units, output_coordinate_path)
            if not output_path:
                del output["path"]
            return output

        except PathNotFoundError as error:
            if is_metric_other_than_length:
                raise PathNotFoundError(
                    f"No route by the metric {metric!r} joins the two points. An "
                    "edge that is closed in this metric cannot be taken: check the "
                    "weights of the metric, and `snap_to_node_modes`, which names "
                    "the node modes that the points snap to."
                ) from error
            error.add_note(
                "This is likely caused by a disconnect in the graph. Setting"
                " destination_node_addition_type='all' and"
                " node_addition_lat_lon_bound=180 ensures a solution, at a much"
                " longer runtime per query."
            )
            raise

    def _log_query_indicators(
        self,
        algorithm_name: str,
        origin: Sequence[float],
        destination: Sequence[float],
        origin_entries: dict[int, int | float],
        destination_entries: dict[int, int | float],
    ) -> None:
        """
        Logs at DEBUG the indicators of a shortest-path query: what the query did, which
        its result does not show.

        - `algorithm_name`: the name of the search, or "custom" for a search function
        - `origin`, `destination`: the [latitude, longitude] of the two ends of the query
        - `origin_entries`, `destination_entries`: the graph nodes that each end was
          joined to, with the cost to reach each node
        - The snapping distance of an end is the great-circle distance to its closest
          entry node, in the units of the geograph, without circuity
        - `node_scans` is present only if the query ran a search that counts them
        - A query builds this record only when DEBUG is on, and does not use `log_step`:
          a query must pay nothing for logging when DEBUG is off. It logs no duration,
          which the caller can measure around its own call
        """
        origin_node = min(origin_entries, key=origin_entries.__getitem__)
        destination_node = min(
            destination_entries, key=destination_entries.__getitem__
        )
        step = "find the shortest path"
        indicators = {
            "algorithm": algorithm_name,
            "distance_units": self.geograph_units,
            "origin_snap_distance": round(
                haversine(
                    origin, self.nodes[origin_node], units=self.geograph_units
                ),
                3,
            ),
            "destination_snap_distance": round(
                haversine(
                    destination,
                    self.nodes[destination_node],
                    units=self.geograph_units,
                ),
                3,
            ),
        }
        node_scans = self.graph_object.get_last_node_scans()
        if node_scans is not None:
            indicators["node_scans"] = node_scans
        logger.debug(
            "%s: %s",
            step,
            indicators,
            extra={"scgraph": {"step": step, **indicators}},
        )

    def distance_matrix(
        self,
        nodes: list[dict[str, float]],
        off_graph_circuity: float = 1,
        output_units: str = "km",
        silent: bool | None = None,
        *,
        metric: str | None = None,
        output_metric: str | None = None,
        snap_to_node_modes: list[str] | None = None,
    ) -> list[list[int | float | None]]:
        """
        Function:

        - Calculate the distance matrix for a list of nodes in a very efficient way using cached shortest path trees and cached node addition distances
        - This should run in O(((n+m)*log(n)*i) + (i*i)) time where i is the number of nodes in the distance matrix, n is the number of nodes in the graph, and m is the number of edges in the graph
           - Compare this to a naive matrix implementation time of O(((n+m)*log(n)*(i*i)) where paths are fetched for each pair of nodes in the distance matrix without caching
        - This is useful for calculating the distance between multiple nodes at the same time

        Required Arguments:

        - `nodes`
            - Type: list[dict[str, float | int]]
            - What: A list of dictionaries with the keys 'latitude' and 'longitude'
            - EG: [{"latitude": 39.2904, "longitude": -76.6122}, {"latitude": 39.2905, "longitude": -76.6123}]

        Optional Arguments:

        - `off_graph_circuity`
            - Type: float | int
            - What: The circuity to apply to the distance calculations for nodes that are not in the graph
            - Default: 1
        - `output_units`
            - Type: str
            - What: The units of the output distance matrix
            - Default: 'km'
            - Options: 'km', 'm', 'mi', 'ft'
            - Note: Ignored when the matrix holds the totals of a metric other than 'length'
        - `silent`
            - Deprecated and without effect. scgraph reports its messages through `logging`.
        - `metric`
            - Type: str
            - What: The name of the metric to minimise, a name of `metrics`: the path between two nodes is the one with the smallest total of this metric
            - Default: None (the `default_metric` of the geograph, which is 'length' unless a loader or the caller set it)
        - `output_metric`
            - Type: str | None
            - What: The name of the metric that the matrix holds: the entry at (i, j) is the total of this metric along the path between node i and node j
            - Default: None (the metric of `metric`)
            - Notes:
                - EG: `geograph.distance_matrix(nodes, metric="hours", output_metric="length")` gives the lengths of the fastest paths
                - With an `output_metric` other than `metric`, the call is slower: it reads the path of each pair, where it otherwise reads only its total
        - `snap_to_node_modes`
            - Type: list of str | None
            - What: The names of the node modes (see `node_modes`) that the nodes of the matrix may snap to, as in `get_shortest_path`
            - Default: None (as in `get_shortest_path`)

        Returns:

        - A list of lists representing the distance matrix between the nodes
        - The distance matrix is a square matrix where the entry at (i, j) is the distance between node i and node j
        - A pair of nodes without a path has the distance None, and the call warns once with the number of such pairs
        - The distances are in the units specified by `output_units`
        - An unknown `metric` or `output_metric` raises a ValueError
        - EG:
        ```
        [
            [0.0, 0.1, ...],
            [0.1, 0.0, ...],
            ...
        ]
        """
        warn_deprecated_parameter("silent", silent)
        failed_pairs = 0
        output_matrix = [[None] * len(nodes) for _ in range(len(nodes))]
        if metric is None:
            metric = self.default_metric
        graph_object = self.get_graph_object(metric)
        if output_metric is None:
            output_metric = metric
        if output_metric == "length":
            dist_multiplier = distance_converter(
                distance=1,
                input_units=self.geograph_units,
                output_units=output_units,
            )
            off_graph_units, off_graph_weight_per_unit = output_units, 1
        else:
            # The total of a metric is not converted. The weight of an off-graph leg
            # is its km times the weight of 1 km in the metric.
            dist_multiplier, off_graph_units = 1, "km"
            off_graph_weight_per_unit = self._read_metric(
                output_metric
            ).off_graph_weight_per_km
        snap_index = self._snap_indexes.get_index(self, snap_to_node_modes)
        # Get the entry idx for each node as well as the distance to that node given the off-graph circuity
        # [(entry_idx, distance), ...]
        entry_idx_and_distance = []
        for node in nodes:
            node_idx = snap_index.closest_idx(
                point=[node["latitude"], node["longitude"]]
            )
            distance = (
                haversine(
                    [node["latitude"], node["longitude"]],
                    self.nodes[node_idx],
                    circuity=off_graph_circuity,
                    units=off_graph_units,  # Store directly as output units since this is a post processing step
                )
                * off_graph_weight_per_unit
            )
            entry_idx_and_distance.append((node_idx, distance))

        for node_idx_start, (entry_idx_start, entry_length_start) in enumerate(
            entry_idx_and_distance
        ):
            for node_idx_end, (entry_idx_end, entry_length_end) in enumerate(
                entry_idx_and_distance
            ):
                if entry_idx_start == entry_idx_end:
                    output_matrix[node_idx_start][node_idx_end] = 0.0
                    continue
                try:
                    if output_metric == metric:
                        length = graph_object.cached_shortest_path(
                            origin_id=entry_idx_start,
                            destination_id=entry_idx_end,
                            length_only=True,
                        )["length"]
                    else:
                        path = graph_object.cached_shortest_path(
                            origin_id=entry_idx_start,
                            destination_id=entry_idx_end,
                        )["path"]
                        length = self._get_path_total(path, output_metric)
                    output_matrix[node_idx_start][node_idx_end] = (
                        (length * dist_multiplier)
                        + entry_length_start
                        + entry_length_end
                    )
                except PathNotFoundError:
                    failed_pairs += 1
        if failed_pairs:
            warnings.warn(
                f"{failed_pairs} pair(s) of nodes have no path between them:"
                " their distance is None",
                stacklevel=2,
            )
        return output_matrix


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


# The methods of `GeoGraphIO` annotate their result as "GeoGraph". `geograph_files` cannot
# import the class at the top, so `typing.get_type_hints` finds it through this name.
geograph_files.GeoGraph = GeoGraph
