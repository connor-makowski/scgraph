"""The queries of a `GeoGraph`: paths between points, their legs and totals, and matrices.

This module is internal. `GeoGraphUtils` and `GeoGraphDistanceCalculations` are mixins of
release 3.6.0. `GeoGraphRouting` is the mixin of `GeoGraph` that answers `get_shortest_path`
and `distance_matrix`.
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
from scgraph.deprecations import warn_deprecated, warn_deprecated_parameter
from scgraph import array_views
import logging
import warnings
import types
from array import array
from functools import partial
from typing import TYPE_CHECKING, Literal
from collections.abc import Callable, Sequence
from scgraph.errors import PathNotFoundError
from scgraph.turn_restrictions import (
    connect_to_nodes_of_junctions,
    find_route_end_at_junction,
    find_nodes_of_junction,
    has_turn_restrictions,
)

if TYPE_CHECKING:  # Only for annotations.
    from scgraph import Graph
    from scgraph.node_snapping import QuerySnapIndex

# The records keep the logger name that they had in `scgraph.geograph`: the documents
# show this name, and a user filters on it.
logger = logging.getLogger("scgraph.geograph")


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
        One dict for each leg: its `edge_mode`, its total `length`, its totals
        `metric_totals` by name, its lengths by class `class_lengths` and its node
        ids `path`. A leg starts at the node where the leg before it ends.
    """
    legs = []
    for edge in edges:
        if not legs or legs[-1]["edge_mode"] != edge["edge_mode"]:
            legs.append(
                {
                    "edge_mode": edge["edge_mode"],
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
    def _get_quadrant_node_indices(
        self,
        node: list,
        snap_index: "QuerySnapIndex",
    ) -> set[int]:
        indices = snap_index.closest_idx_per_quadrant(point=node)
        node_indices = {idx for idx in indices.values() if idx is not None}
        if not node_indices:
            node_indices.add(snap_index.closest_idx(point=node))
        return node_indices

    def _get_node_distances(
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
                for idx in self._get_quadrant_node_indices(node, snap_index)
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

    def _get_intermediate_nodes(
        self, origin_idx: int, destination_idx: int, sequence: str = "lat_lon"
    ) -> list[list[float]]:
        """
        Function:

        - Get the intermediate nodes between two nodes if they exist in the graph object
        - Note: Not as performant so not used in _get_coordinate_path, but can be used in post processing of the path if desired

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

    def _format_coordinates(
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

    def _get_coordinate_path(
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
            - What: If True, returns the intermediate nodes in the path (if they exist for each edge)
            - Default: False
        """
        nodes = self.nodes
        coordinates = (
            nodes.take(path)
            if isinstance(nodes, array_views.NodePoints)
            else [nodes[node_id] for node_id in path]
        )
        if (
            get_intermediate_nodes
            and self.intermediate_nodes is not None
            and path
        ):
            if isinstance(self.intermediate_nodes, array_views.EdgeShapes):
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
          including the two off-graph legs using this geograph's
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

        off_graph_km = off_graph_circuity * self._get_off_graph_km(
            path, origin, destination
        )
        total = (
            self.get_graph_object(metric).get_path_weight(path)
            + off_graph_km * self._read_metric(metric).off_graph_weight_per_km
        )
        return self._read_metric(metric).convert_total(total, output_units)

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


class GeoGraphRouting:
    """The queries of a `GeoGraph`: paths between points, their legs and totals, and matrices."""

    def _get_node_radians(self) -> tuple[array, array]:
        # Also rebuilt when nodes were appended or removed directly; in-place edits of
        # existing nodes are not detected (as for the snapping index)
        if self._node_radians is None or len(self._node_radians[0]) != len(
            self.nodes
        ):
            self._node_radians = (
                array(
                    "d", (radians_per_degree * node[0] for node in self.nodes)
                ),
                array(
                    "d", (radians_per_degree * node[1] for node in self.nodes)
                ),
            )
        return self._node_radians

    def _get_path_total(self, path: list[int], metric: str) -> float:
        # The total of a metric along the edges of a path. The metric may be
        # `length`, whose record has no weights: they are the lengths.
        weights = self._read_metric(metric).weights
        if weights is None:
            weights = self._read_edge_arrays()[2]
        return sum(
            weights[edge_id] for edge_id in self._find_path_edge_ids(path)
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
            for name, metric_record in self._read_metrics().items()
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
            leg["coordinate_path"] = self._get_coordinate_path(
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
        node_mode_ids = self._read_node_mode_ids()
        for leg in legs[1:]:
            node_id = leg["path"][0]
            node_mode = self.node_modes[node_mode_ids[node_id]]
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
        units_per_km = get_units_per_km(self.geograph_units)
        off_graph_legs = []
        for points in off_graph_paths:
            # One sum of km gives both the length and the totals of the leg.
            # `_get_off_graph_km` computes the km of the route in the same way.
            off_graph_km = off_graph_circuity * sum(
                haversine(start, end) for start, end in zip(points, points[1:])
            )
            off_graph_legs.append(
                {
                    "edge_mode": "off_graph",
                    "length": off_graph_km * units_per_km,
                    "metric_totals": {
                        name: off_graph_km
                        * metric_record.off_graph_weight_per_km
                        for name, metric_record in self._read_metrics().items()
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
        `output_coordinate_path`. Its `metric_totals` get its length. The leg is
        changed in place."""
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
        leg["coordinate_path"] = self._format_coordinates(
            coordinate_path=leg["coordinate_path"],
            output_format=output_coordinate_path,
        )
        leg["metric_totals"] = {"length": leg["length"], **leg["metric_totals"]}

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
        totals_only: bool = False,
        **kwargs,
    ) -> dict:
        """
        Function:

        - Identify the shortest path between two nodes in a sparse network graph

        - Return a dictionary of various path information including:
            - `path`: With `output_path=True`, a list of node ids in the order they are visited
            - `coordinate_path`: A list of coordinates (latitude then longitude) in the order they are visited, in the format of `output_coordinate_path`
            - `length`: The length of the path, in `output_units`
            - `metric_totals`: A dictionary `{name: total}` with the total of each metric of `metrics` along the path. `metric_totals["length"]` is `length`. The total of another metric is in the unit of this metric
            - `legs`: With `output_legs=True`, the legs of the path in their order. A leg is a part of the path on one mode, as a dictionary `{"edge_mode", "length", "metric_totals", "class_lengths", "coordinate_path"}`
                - `edge_mode` is the edge mode of the edges of the leg (see `classes`). A new leg starts where this edge mode changes. The edges of a geograph without classes make one leg of the mode None
                - The first and the last leg are the off-graph legs, of the mode 'off_graph': the straight lines from the origin to the first node of the path, and from its last node to the destination. A path without an edge is one leg of the mode 'off_graph'
                - `length` and `metric_totals` are the totals of the leg, as those of the path. The length of the path is the sum of the lengths of its legs, and so is each total of `metric_totals`
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
            - Deprecated: use `totals_only`. If True, only returns the length of a path by length: `{"length": length}`
            - Note: With a `metric` other than 'length', it raises a ValueError
            - Default: False
        - `get_intermediate_nodes`
            - Type: bool
            - What: If True, returns the intermediate nodes in the path (if they exist for each edge)
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
        - `totals_only`
            - Type: bool
            - What: If True, only returns the total of the metric of the search: `{"metric_totals": {metric: total}}`. With `output_path` or `output_legs`, it raises a ValueError
            - Default: False
        - `**kwargs`
            - Additional keyword arguments. These are included for forwards and backwards compatibility reasons, but are not currently used.
        """
        warn_deprecated_parameter("silent", silent)
        algorithm_name = (
            algorithm_fn if isinstance(algorithm_fn, str) else "custom"
        )
        if get_intermediate_nodes is None:
            get_intermediate_nodes = self.default_get_intermediate_nodes
        if off_graph_circuity is None:
            off_graph_circuity = self.default_off_graph_circuity
        if node_addition_circuity is None:
            node_addition_circuity = self.default_node_addition_circuity
        algorithm_kwargs = (
            dict(algorithm_kwargs) if algorithm_kwargs is not None else dict()
        )
        if metric is None:
            metric = self.default_metric
        if length_only or totals_only:
            self._check_totals_arguments(
                metric, length_only, totals_only, output_path, output_legs
            )
        # The graph whose weights are those of the metric
        graph_object = self.get_graph_object(metric)
        search_function = self._build_search_function(
            algorithm_fn, algorithm_kwargs, graph_object, metric
        )
        node_addition_type = self._get_node_addition_type(node_addition_type)
        destination_node_addition_type = self._get_node_addition_type(
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
        # Parse origin and destination
        origin = [origin_node.get("latitude"), origin_node.get("longitude")]
        destination = [
            destination_node.get("latitude"),
            destination_node.get("longitude"),
        ]
        if len(origin) < 1 or len(destination) < 1:
            raise ValueError(
                "Origin and destination must have valid latitude and longitude"
            )
        # Get the node addition direct distance between origin and destination
        direct_length = haversine(
            origin,
            destination,
            circuity=node_addition_circuity,
            units=self.geograph_units,
        )
        # Snap the origin and destination to their closest nodes in the graph
        origin_id = connect_to_nodes_of_junctions(
            self,
            self._get_node_distances(
                node=origin,
                circuity=node_addition_circuity,
                node_addition_type=node_addition_type,
                lat_lon_bound=node_addition_lat_lon_bound,
                snap_index=snap_index,
            ),
        )
        destination_id = connect_to_nodes_of_junctions(
            self,
            self._get_node_distances(
                node=destination,
                circuity=node_addition_circuity,
                node_addition_type=destination_node_addition_type,
                lat_lon_bound=node_addition_lat_lon_bound,
                snap_index=snap_index,
            ),
        )
        # Calculate the circuity ratio for the node addition
        circuity_ratio = (
            off_graph_circuity / node_addition_circuity
            if node_addition_circuity != 0
            else 1.0
        )
        # If direct distance is better than any entry or exit distance, bypass graph search
        is_direct = direct_length <= min(
            min(origin_id.values()), min(destination_id.values())
        )
        # In the search, the weight of an off-graph leg is its km times the
        # weight of 1 km. The test above compares lengths: a metric whose
        # off-graph legs have a weight of zero must not make every route direct.
        direct_length, origin_id, destination_id = self._convert_to_metric(
            metric, direct_length, origin_id, destination_id
        )
        if logger.isEnabledFor(logging.DEBUG):
            graph_object._reset_node_scans()
        if is_direct:
            output = {"path": [], "length": direct_length * circuity_ratio}
        else:
            output = self._find_route(
                search_function,
                algorithm_kwargs,
                origin_id,
                destination_id,
                metric,
            )
            if circuity_ratio != 1.0:
                path = output.get("path")
                entry_node = path[0] if path else next(iter(origin_id))
                exit_node = path[-1] if path else next(iter(destination_id))
                output["length"] += (
                    origin_id[entry_node] + destination_id[exit_node]
                ) * (circuity_ratio - 1.0)
        if logger.isEnabledFor(logging.DEBUG):
            self._log_query_values(
                algorithm_name,
                graph_object,
                origin,
                destination,
                origin_id,
                destination_id,
            )
        # The search returned the total of the metric
        metric_total = self._read_metric(metric).convert_total(
            output["length"], output_units
        )
        if totals_only:
            return {"metric_totals": {metric: metric_total}}
        if length_only:
            return {"length": metric_total}
        # The key `length` of release 3.6.0 holds the length of the route, which
        # `get_path_weight` computes for a search by another metric
        if metric == "length":
            length = metric_total
        else:
            length = self.get_path_weight(
                {
                    "path": output["path"],
                    "coordinate_path": [origin, destination],
                },
                off_graph_circuity=off_graph_circuity,
                output_units=output_units,
                metric="length",
            )
        output["length"] = length
        output["metric_totals"] = {"length": length}
        if self._read_metrics():
            output["metric_totals"].update(
                self._get_metric_totals(
                    output["path"], origin, destination, off_graph_circuity
                )
            )
            output["metric_totals"][metric] = metric_total
        # Get the coordinate path
        output["coordinate_path"] = (
            [origin]
            + self._get_coordinate_path(
                output["path"], get_intermediate_nodes=get_intermediate_nodes
            )
            + [destination]
        )
        # Format the coordinate path to the desired output format
        if output_coordinate_path != "list_of_lists":
            output["coordinate_path"] = self._format_coordinates(
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

    def _build_search_function(
        self,
        algorithm_fn: str | Callable,
        algorithm_kwargs: dict,
        graph_object: "Graph",
        metric: str,
    ) -> Callable:
        """Return the function that searches a route on `graph_object`, the graph
        of `metric`, for the argument `algorithm_fn` of `get_shortest_path`. The
        method sets in `algorithm_kwargs` what this function needs: the graph for
        a function of the caller, or the A* bound of the metric."""
        if callable(algorithm_fn):
            algorithm_kwargs["graph"] = graph_object.unreduced_graph
            return algorithm_fn
        if not isinstance(algorithm_fn, str):
            raise ValueError("algorithm_fn must be a string or callable")
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
        if algorithm_fn == "a_star" and heuristic_fn == haversine_of_scgraph:
            # The built-in haversine heuristic is computed natively in the C++ build
            latitudes, longitudes = self._get_node_radians()
            algorithm_kwargs.pop("heuristic_fn")
            # The total of a route of the length d is at least d times
            # `min_weight_per_length_unit`: the radius times it is the bound.
            radius = earth_radius[self.geograph_units] * self._read_metric(
                metric
            ).get_min_weight_per_length_unit(
                lambda: self._read_edge_arrays()[2]
            )
            return partial(
                graph_object._a_star_great_circle,
                latitudes=latitudes,
                longitudes=longitudes,
                radius=radius,
            )
        if not hasattr(graph_object, algorithm_fn):
            raise ValueError("algorithm_fn must be a string or callable")
        if algorithm_fn == "a_star" and heuristic_fn == cheap_ruler_of_scgraph:
            # `cheap_ruler` gives a length. The bound of the metric is this
            # length times `min_weight_per_length_unit`, as for `haversine`.
            min_weight_per_length_unit = self._read_metric(
                metric
            ).get_min_weight_per_length_unit(
                lambda: self._read_edge_arrays()[2]
            )
            # A weight of 1 per length unit, as for `length`, keeps the function
            if min_weight_per_length_unit != 1.0:
                algorithm_kwargs["heuristic_fn"] = (
                    lambda origin_id, destination_id: min_weight_per_length_unit
                    * heuristic_fn(origin_id, destination_id)
                )
        return getattr(graph_object, algorithm_fn)

    def _convert_to_metric(
        self,
        metric: str,
        direct_length: float,
        origin_id: dict[int, float],
        destination_id: dict[int, float],
    ) -> tuple[float, dict[int, float], dict[int, float]]:
        """Return the length of the direct line and the lengths from each query
        point to its nodes as weights of `metric`: in the search, the weight of
        an off-graph leg is its length times the weight of 1 length unit of an
        off-graph leg in the metric. A weight of 1 per length unit, as for
        `length`, returns the arguments without a copy."""
        off_graph_weight_per_unit = self._read_metric(
            metric
        ).off_graph_weight_per_km / get_units_per_km(self.geograph_units)
        if off_graph_weight_per_unit == 1.0:
            return direct_length, origin_id, destination_id
        return (
            direct_length * off_graph_weight_per_unit,
            {
                node_id: length * off_graph_weight_per_unit
                for node_id, length in origin_id.items()
            },
            {
                node_id: length * off_graph_weight_per_unit
                for node_id, length in destination_id.items()
            },
        )

    def _check_totals_arguments(
        self,
        metric: str,
        length_only: bool,
        totals_only: bool,
        output_path: bool,
        output_legs: bool,
    ) -> None:
        """Raise a ValueError when `totals_only` comes with an argument that needs
        the path, or when `length_only` comes with a metric other than `length`.
        Warn that `length_only` is deprecated."""
        if totals_only and (output_path or output_legs):
            raise ValueError(
                "totals_only=True returns no path: it cannot be used with "
                f"{'output_path' if output_path else 'output_legs'}=True"
            )
        if length_only:
            # `length_only` of release 3.6.0 gives a length, and no other total
            if metric != "length":
                raise ValueError(
                    "length_only=True gives the length of a route by length. "
                    f"For the metric {metric!r}, use totals_only=True"
                )
            warn_deprecated(
                "The parameter `length_only`",
                stacklevel=4,
                instead="Use `totals_only=True`: it returns "
                "{'metric_totals': {metric: total}}",
            )

    def _find_route(
        self,
        search_function: Callable,
        algorithm_kwargs: dict,
        origin_id: dict[int, float],
        destination_id: dict[int, float],
        metric: str,
    ) -> dict:
        """Return the result of the search between the nodes of the two query
        points: `{"path": node ids, "length": total of the metric}`. When no route
        joins them, the PathNotFoundError names the metric, or gets a note on a
        disconnected graph."""
        try:
            return search_function(
                origin_id=origin_id,
                destination_id=destination_id,
                **algorithm_kwargs,
            )
        except PathNotFoundError as error:
            # A search by length raises the error of release 3.6.0, with a note
            if metric != "length":
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

    def _log_query_values(
        self,
        algorithm_name: str,
        graph_object: "Graph",
        origin: Sequence[float],
        destination: Sequence[float],
        origin_entries: dict[int, int | float],
        destination_entries: dict[int, int | float],
    ) -> None:
        """
        Logs at DEBUG the values of a shortest-path query: what the query did, which
        its result does not show.

        - `algorithm_name`: the name of the search, or "custom" for a search function
        - `graph_object`: the graph that the query searched, which counts the node scans
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
        values = {
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
        node_scans = graph_object._get_last_node_scans()
        if node_scans is not None:
            values["node_scans"] = node_scans
        logger.debug(
            "%s: %s",
            step,
            values,
            extra={"scgraph": {"step": step, **values}},
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
        output_metric_record = self._read_metric(output_metric)
        dist_multiplier = output_metric_record.convert_total(1, output_units)
        # The weight of an off-graph leg is its km times the weight of 1 km
        off_graph_weight_per_km = (
            output_metric_record.off_graph_weight_per_km * dist_multiplier
        )
        snap_index = self._snap_indexes.get_index(self, snap_to_node_modes)
        follows_turn_restrictions = has_turn_restrictions(self)
        # Get the entry idx for each node as well as the distance to that node given the off-graph circuity
        # [(entry_idx, distance), ...]
        entry_idx_and_distance = []
        for node in nodes:
            node_idx = snap_index.closest_idx(
                point=[node["latitude"], node["longitude"]]
            )
            if follows_turn_restrictions:
                # A route starts at the first node of a junction, which has an
                # edge along every street that leaves the junction
                # (`scgraph/turn_restrictions.py`)
                node_idx = find_nodes_of_junction(self, node_idx).start
            distance = (
                haversine(
                    [node["latitude"], node["longitude"]],
                    self.nodes[node_idx],
                    circuity=off_graph_circuity,
                )
                * off_graph_weight_per_km
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
                if follows_turn_restrictions:
                    entry_idx_end = find_route_end_at_junction(
                        self, graph_object, entry_idx_start, entry_idx_end
                    )
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
