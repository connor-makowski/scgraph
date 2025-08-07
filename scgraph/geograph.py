from scgraph.utils import (
    haversine,
    distance_converter,
    get_line_path,
    cheap_ruler,
    print_console,
    get_lat_lon_bound_between_pts,
)
from scgraph.cache import CacheGraph
from scgraph.helpers.geojson import parse_geojson
from scgraph.helpers.kd_tree import GeoKDTree
import json
from copy import deepcopy
from typing import Literal

from scgraph.graph import Graph


class GeoGraph:
    def __init__(
        self,
        graph: list[dict[int, int | float]],
        nodes: list[list[float | int]],
    ) -> None:
        """
        Function:

        - Create a GeoGraph object

        Required Arguments:

        - `graph`
            - Type: list of dictionaries
            - See: https://connor-makowski.github.io/scgraph/scgraph/graph.html#Graph.validate_graph
        - `nodes`
            - Type: list of lists of ints or floats
            - What: A list of lists where the values are coordinates (latitude then longitude)
            - Note: The length of the nodes list must be the same as that of the graph list
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
        """
        self.graph = graph
        self.nodes = nodes
        self.geokdtree = GeoKDTree(points=self.nodes)
        self.cacheGraph = CacheGraph(graph=self.graph, validate_graph=False)

        self.__original_graph_length__ = len(graph)

    def validate_graph(
        self, check_symmetry: bool = True, check_connected: bool = True
    ) -> None:
        """
        Function:

        - Validate that self.graph is properly formatted (see Graph.validate_graph)
        - Raises an exception if the graph is invalid
        - Returns None if the graph is valid

        Required Arguments:

        - None

        Optional Arguments:

        - `check_symmetry`
            - Type: bool
            - What: Whether to check that the graph is symmetric
            - Default: True
            - Note: This is forced to True if `check_connected` is True
        - `check_connected`
            - Type: bool
            - What: Whether to check that the graph is fully connected
            - Default: True
            - Note: For computational efficiency, graphs are validated for symmetry prior to checking for connectivity
        """
        Graph.validate_graph(
            self.graph,
            check_symmetry=check_symmetry,
            check_connected=check_connected,
        )

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
        assert isinstance(self.nodes, list), "Your nodes must be a dictionary"
        assert all(
            [isinstance(i, list) for i in self.nodes]
        ), "Your nodes must be a list of lists"
        assert all(
            [len(i) == 2 for i in self.nodes]
        ), "Your nodes must be a list of lists where each sub list has a length of 2"
        assert all(
            [
                (
                    isinstance(i[0], (int, float))
                    and isinstance(i[1], (int, float))
                )
                for i in self.nodes
            ]
        ), "Your nodes must be a list of lists where each sub list has a numeric latitude and longitude value"
        assert all(
            [
                (i[0] >= -90 and i[0] <= 90 and i[1] >= -180 and i[1] <= 180)
                for i in self.nodes
            ]
        ), "Your nodes must be a list of lists where each sub list has a length of 2 with a latitude [-90,90] and longitude [-180,180] value"

    def haversine(
        self,
        origin_id: int,
        destination_id: int,
    ):
        """
        Function:

        - Calculate the haversine distance between two points on the Earth.

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
            units="km",
            circuity=1,
        )

    def cheap_ruler(
        self,
        origin_id: int,
        destination_id: int,
    ):
        """
        Function:

        - Calculate the distance between two points on the Earth using the cheap ruler algorithm.
        - This is based off of Mapbox's cheap ruler algorithm which is a fast approximation of the haversine distance
        - It has modifications to support distances across the antimeridian

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
            units="km",
            # Use a circuity factor of 0.95 to account for the fact that cheap_ruler can overestimate distances
            circuity=0.9,
        )

    def format_coordinates(
        self,
        coordinate_path: list[list[float | int]],
        output_format: str = "list_of_lists",
    ) -> list:
        """
        Function:

        Arguments:

        - `coordinate_path`
            - Type: list of lists
            - What: A list of lists where each sublist is a coordinate [latitude, longitude]
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

    def format_output(
        self,
        output: dict,
        output_coordinate_path: str = "list_of_lists",
        output_units: str = "km",
        geograph_units: str = "km",
        output_path: bool = False,
        adj_circuity: bool = True,
        node_addition_circuity: float | int = 4,
        off_graph_circuity: float | int = 1,
        length_only: bool = False,
    ):
        """
        Function:

        - Format the output of the shortest path algorithm to include:

        Arguments:

        - `output`
            - Type: dict
            - What: The output from the shortest path algorithm
            - Expected Keys:
                - 'length': The length of the path in the units specified by `geograph_units`
                - 'path': (optional) A list of node ids in the order they are visited
                - 'coordinate_path': (optional) A list of coordinates (latitude, longitude) in the order they are visited
        - `output_coordinate_path`:
            - Type: str
            - What: The format of the output coordinate path
            - Options:
                - 'list_of_dicts': A list of dictionaries with keys 'latitude' and 'longitude'
                - 'list_of_lists': A list of lists with the first value being latitude and the second being longitude
                - 'list_of_lists_long_first': A list of lists with the first value being longitude and the second being latitude
            - Default: 'list_of_lists'
        - `output_units`:
            - Type: str
            - What: The units in which to return the length of the path
            - Default: 'km'
            - Options:
                - 'km': Kilometers
                - 'm': Meters
                - 'mi': Miles
                - 'ft': Feet
        - `geograph_units`:
            - Type: str
            - What: The units of measurement in the geograph data
            - Default: 'km'
            - Options:
                - 'km': Kilometers
                - 'm': Meters
                - 'mi': Miles
                - 'ft': Feet
        - `output_path`:
            - Type: bool
            - What: Whether to output the path as a list of geograph node ids (for debugging and other advanced uses)
            - Default: False
        - `adj_circuity`:
            - Type: bool
            - What: Whether to adjust the length for node addition type circuity factors (this needs the coordinate path)
            - Default: True
        - `node_addition_circuity`:
            - Type: float | int
            - What: The circuity factor that was applied when adding your origin and destination nodes to the distance matrix
            - Default: 4
        - `off_graph_circuity`:
            - Type: float | int
            - What: The circuity factor that was applied when the path goes off the graph
            - Default: 1
        - `length_only`:
            - Type: bool
            - What: If True, only returns the length of the path
            - Default: False

        Returns:

        - A dictionary with the following keys:
            - 'length': The length of the path in the units specified by `output_units`
            - 'path': (optional) A list of node ids in the order they are visited
            - 'coordinate_path': (optional) A list of coordinates (latitude, longitude) in the order they are visited
            - 'long_first': (optional) A boolean indicating if the coordinate path is in longitude-first format
        """

        # If only the length is requested, return early if no circuity adjustment is needed
        if length_only and not adj_circuity:
            return {
                "length": distance_converter(
                    output["length"],
                    input_units=geograph_units,
                    output_units=output_units,
                )
            }

        # Get the coordinate path
        if "coordinate_path" not in output:
            output["coordinate_path"] = self.get_coordinate_path(output["path"])
        # If the output path is not requested, remove it from the output
        if not output_path:
            if "path" in output:
                del output["path"]

        # Adjust the length for circuity factors if needed (this needs the coordinate path)
        # This adjusts for the difference between node addition circuity and off graph circuity
        if adj_circuity:
            output["length"] = self.adjust_circuity_length(
                output=output,
                node_addition_circuity=node_addition_circuity,
                off_graph_circuity=off_graph_circuity,
            )

        # Format the length
        output["length"] = distance_converter(
            output["length"],
            input_units=geograph_units,
            output_units=output_units,
        )

        if length_only:
            return {"length": output["length"]}

        # Format the coordinate path to the desired output format
        output["coordinate_path"] = self.format_coordinates(
            coordinate_path=output["coordinate_path"],
            output_format=output_coordinate_path,
        )
        if output_coordinate_path == "list_of_lists_long_first":
            output["long_first"] = True

        return output

    def cleanup_temp_nodes(self):
        # Cleanup temp nodes from the graph
        while len(self.graph) > self.__original_graph_length__:
            self.remove_appended_node()

    def get_shortest_path(
        self,
        origin_node: dict[str, float | int],
        destination_node: dict[str, float | int],
        output_units: str = "km",
        algorithm_fn=Graph.dijkstra_makowski,
        algorithm_kwargs: dict = dict(),
        off_graph_circuity: float | int = 1,
        node_addition_type: str = "kdclosest",
        node_addition_circuity: float | int = 4,
        geograph_units: str = "km",
        output_coordinate_path: str = "list_of_lists",
        output_path: bool = False,
        node_addition_lat_lon_bound: float | int | Literal["auto"] = "auto",
        node_addition_math: str = "euclidean",
        destination_node_addition_type: str = "kdclosest",
        auto_lat_lon_bound_max: float | int = 2,
        silent: bool = False,
        cache: bool = False,
        length_only: bool = False,
        **kwargs,
    ) -> dict:
        """
        Function:

        - Identify the shortest path between two nodes in a sparse network graph

        - Return a dictionary of various path information including:
            - `id_path`: A list of node ids in the order they are visited
            - `path`: A list of nodes  (list of lat then long) in the order they are visited
            - `length`: The length of the path

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
            - Type: function | method
            - What: The algorithm function to identify the shortest path
            - Default: 'Graph.dijkstra_makowski'
            - Options:
                - 'Graph.dijkstra': A modified dijkstra algorithm that uses a sparse distance matrix to identify the shortest path
                - 'Graph.dijkstra_makowski': A modified dijkstra algorithm that uses a sparse distance matrix to identify the shortest path
                - Any user defined algorithm that takes the arguments:
                    - `graph`: A dictionary of dictionaries where the keys are origin node ids and the values are dictionaries of destination node ids and distances
                        - See: https://connor-makowski.github.io/scgraph/scgraph/graph.html#Graph.validate_graph
                    - `origin`: The id of the origin node from the graph dictionary to start the shortest path from
                    - `destination`: The id of the destination node from the graph dictionary to end the shortest path at
        - `algorithm_kwargs`
            - Type: dict
            - What: Additional keyword arguments to pass to the algorithm function assuming it accepts them
        - `off_graph_circuity`
            - Type: int | float
            - What: The circuity factor to apply to any distance calculations between your origin and destination nodes and their connecting nodes in the graph
            - Default: 1
            - Notes:
                - For alogrithmic solving purposes, the node_addition_circuity is applied to the origin and destination nodes when they are added to the graph
                - This is only applied after an `optimal solution` using the `node_addition_circuity` has been found when it is then adjusted to equal the `off_graph_circuity`
        - `node_addition_type`
            - Type: str
            - What: The type of node addition to use when adding your origin node to the distance matrix
            - Default: 'kdclosest' (was 'quadrant' prior to v2.10.0)
            - Options:
                - 'kdclosest': Add the closest node using a KD-Tree
                - 'quadrant': Add the closest node in each quadrant (ne, nw, se, sw) to the distance matrix for this node
                - 'closest': Add only the closest node to the distance matrix for this node
                - 'all': Add all nodes within the bounding box to the distance matrix for this node
        - `node_addition_circuity`
            - Type: int | float
            - What: The circuity factor to apply when adding your origin and destination nodes to the distance matrix
            - Default: 4
            - Note:
                - This defaults to 4 to prevent the algorithm from taking a direct route in direction of the destination over some impassible terrain (EG: a maritime network that goes through land)
                - A higher value will push the algorithm to join the network at a closer node to avoid the extra distance from the circuity factor
                - This is only relevant if `node_addition_type` is set to 'quadrant' or 'all' as it affects the choice on where to enter the graph network
                - This factor is used to calculate the node sequence for the `optimal route`, however the reported `length` of the path will be calculated using the `off_graph_circuity` factor
        - `geograph_units`
            - Type: str
            - What: The units of measurement in the geograph data
            - Default: 'km'
            - Options:
                - 'km': Kilometers
                - 'm': Meters
                - 'mi': Miles
                - 'ft': Feet
            - Note: In general, all scgraph provided geographs be in kilometers
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
                - Only points on the current graph inside of this bounding box are considered when updating the distance matrix for the origin or destination nodes
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
            - What: The math to use when calculating the distance between nodes when determining the closest node (or closest quadrant node) to add to the graph
            - Default: 'euclidean'
            - Options:
                - 'euclidean': Use the euclidean distance between nodes. This is much faster but is not as accurate (especially near the poles)
                - 'haversine': Use the haversine distance between nodes. This is slower but is an accurate representation of the surface distance between two points on the earth
            - Notes:
                - Only used if `node_addition_type` is set to 'quadrant' or 'closest'
        - `destination_node_addition_type`
            - Type: str
            - What: The method to use when adding the destination node to the graph
            - Default: 'kdclosest' (was 'all' in functionality prior to v2.10.0)
            - Options:
                - 'kdclosest': Add the closest node using a KD-Tree
                - 'closest': Add the node to the closest point in the graph
                - 'quadrant': Add the node to the quadrant it belongs to
                - 'all': Add the node to all points in the graph within the bounding box
        - `silent`
            - Type: bool
            - What: If True, suppresses all output from the function
            - Default: False
        - `cache`
            - Type: bool
            - What: Whether to cache the spanning tree for future use
                - Note: If true, the initial call will likely be slower than a non-cached call, but subsequent calls will be much faster
                - Note: If true, this requires that both the node_addition_type and destination_node_addition_type are set to 'kdclosest' or 'closest'
                - Note: Only the origin node is cached
            - Default: False
        - `length_only`
            - Type: bool
            - What: If True, only returns the length of the path
            - Default: False
        - `**kwargs`
            - Additional keyword arguments. These are included for forwards and backwards compatibility reasons, but are not currently used.
        """
        # Handle auto bounding boxes
        if node_addition_lat_lon_bound == "auto":
            node_addition_lat_lon_bound_origin = 180
            node_addition_lat_lon_bound_destination = 180
            if not (
                node_addition_type == "kdclosest"
                and destination_node_addition_type == "kdclosest"
            ):
                node_addition_lat_lon_bound_destination = (
                    get_lat_lon_bound_between_pts(origin_node, destination_node)
                    * 1.01
                )
                node_addition_lat_lon_bound_origin = min(
                    node_addition_lat_lon_bound_destination,
                    auto_lat_lon_bound_max,
                )
        else:
            node_addition_lat_lon_bound_origin = node_addition_lat_lon_bound
            node_addition_lat_lon_bound_destination = (
                node_addition_lat_lon_bound
            )
        try:
            # Handle Cache based shortest path calculations
            if cache:
                assert node_addition_type in [
                    "kdclosest",
                    "closest",
                ], "When caching, origin_node_addition_type must be 'kdclosest' or 'closest'"
                assert destination_node_addition_type in [
                    "kdclosest",
                    "closest",
                ], "When caching, destination_node_addition_type must be 'kdclosest' or 'closest'"
                origin = [
                    origin_node.get("latitude"),
                    origin_node.get("longitude"),
                ]
                destination = [
                    destination_node.get("latitude"),
                    destination_node.get("longitude"),
                ]
                entry_id, entry_length = list(
                    self.get_node_distances(
                        node=origin,
                        circuity=off_graph_circuity,
                        node_addition_type=node_addition_type,
                        node_addition_math=node_addition_math,
                        lat_lon_bound=node_addition_lat_lon_bound_origin,
                        silent=silent,
                    ).items()
                )[0]
                exit_id, exit_length = list(
                    self.get_node_distances(
                        node=destination,
                        circuity=off_graph_circuity,
                        node_addition_type=destination_node_addition_type,
                        node_addition_math=node_addition_math,
                        lat_lon_bound=node_addition_lat_lon_bound_destination,
                        silent=silent,
                    ).items()
                )[0]
                output = self.cacheGraph.get_shortest_path(
                    origin_id=entry_id,
                    destination_id=exit_id,
                    length_only=length_only,
                )
                # Modify the output to include the origin and destination nodes
                output["length"] += entry_length + exit_length
                # Make modifications to the output if the request is not just for length
                if not length_only:
                    output["coordinate_path"] = (
                        [origin]
                        + self.get_coordinate_path(output["path"])
                        + [destination]
                    )
                    # Add the origin and destination nodes to the id path
                    output["path"] = [entry_id] + output["path"] + [exit_id]
            # Handle non-cache based shortest path calculations
            else:
                origin_id = self.add_node(
                    node=origin_node,
                    node_addition_type=node_addition_type,
                    circuity=node_addition_circuity,
                    lat_lon_bound=node_addition_lat_lon_bound_origin,
                    node_addition_math=node_addition_math,
                    silent=silent,
                )
                destination_id = self.add_node(
                    node=destination_node,
                    node_addition_type=destination_node_addition_type,
                    circuity=node_addition_circuity,
                    lat_lon_bound=node_addition_lat_lon_bound_destination,
                    node_addition_math=node_addition_math,
                    silent=silent,
                )
                output = algorithm_fn(
                    graph=self.graph,
                    origin_id=origin_id,
                    destination_id=destination_id,
                    **algorithm_kwargs,
                )
            # Format the output
            output = self.format_output(
                output=output,
                output_coordinate_path=output_coordinate_path,
                output_units=output_units,
                geograph_units=geograph_units,
                output_path=output_path,
                # No need to adjust for node addition circuity here if the request is cached since
                # the off_graph_circuity is applied for node addition when caching is used.
                adj_circuity=not cache,
                node_addition_circuity=node_addition_circuity,
                off_graph_circuity=off_graph_circuity,
                length_only=length_only,
            )
            self.cleanup_temp_nodes()
            return output
        except Exception as e:
            # Cleanup temp nodes from the graph
            self.cleanup_temp_nodes()
            print("An error occurred while calculating the shortest path:")
            print("This is likely caused by a disconnect in the graph.")
            print(
                "You can ensure a solution by setting destination_node_addition_type='all' and setting your lat_lon_bound=180."
            )
            print(
                "This will, however, result in a much longer runtime per shortest path query."
            )
            print("See the stacktrace below for more details:")
            raise e

    def adjust_circuity_length(
        self,
        output: dict,
        node_addition_circuity: float | int,
        off_graph_circuity: float | int,
    ) -> float | int:
        """
        Function:

        - Adjust the length of the path to account for the circuity factors applied to the origin and destination nodes

        Required Arguments:

        - `output`
            - Type: dict
            - What: The output from the algorithm function
        - `node_addition_circuity`
            - Type: int | float
            - What: The circuity factor that was applied when adding your origin and destination nodes to the distance matrix
        - `off_graph_circuity`
            - Type: int | float
            - What: The circuity factor to apply to any distance calculations between your origin and destination nodes and their connecting nodes in the graph
        """
        coordinate_path = output["coordinate_path"]
        # If the path does not enter the graph, undo the node_addition_circuity and apply the off_graph_circuity
        if len(output["coordinate_path"]) == 2:
            return (
                output["length"] / node_addition_circuity
            ) * off_graph_circuity
        else:
            direct_off_graph_length = haversine(
                coordinate_path[0], coordinate_path[1], circuity=1
            ) + haversine(coordinate_path[-2], coordinate_path[-1], circuity=1)
            return round(
                output["length"]
                + direct_off_graph_length
                * (off_graph_circuity - node_addition_circuity),
                4,
            )

    def adujust_circuity_length(self, *args, **kwargs):
        """
        Maintain backwards compatibility with the old method that had a typo.

        This is now just an alias for `adjust_circuity_length`.
        """
        # TODO: Remove in next major release
        return self.adjust_circuity_length(*args, **kwargs)

    def get_coordinate_path(self, path: list[int]) -> list[list[float | int]]:
        """
        Function:

        - Return a list of node dictionaries (lat + long) in the order they are visited

        Required Arguments:

        - `path`
            - Type: list
            - What: A list of node ids in the order they are visited

        Optional Arguments:

        - None
        """
        return [self.nodes[node_id] for node_id in path]

    def remove_appended_node(self) -> None:
        """
        Function:

        - Remove the last node that was appended to the graph
        - Assumes that this node has symmetric flows
            - EG: If node A has a distance of 10 to node B, then node B has a distance of 10 to node A
        - Return None

        Required Arguments:

        - None

        Optional Arguments:

        - None
        """
        node_id = len(self.graph) - 1
        for reverse_connection in [i for i in self.graph[node_id].keys()]:
            del self.graph[reverse_connection][node_id]
        self.graph = self.graph[:node_id]
        self.nodes = self.nodes[:node_id]

    def get_node_distances(
        self,
        node: list,
        circuity: float | int,
        node_addition_type: str,
        node_addition_math: str,
        lat_lon_bound: float | int,
        silent: bool = False,
    ) -> dict[int, float]:
        """
        Function:

        - Get the distances between a node and all other nodes in the graph
        - This is used to determine the closest node to add to the graph when adding a new node

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
                - 'kdclosest': Add the closest node using a KD-Tree
                - 'quadrant': Add the closest node in each quadrant (ne, nw, se, sw) to the distance matrix for this node
                - 'closest': Add only the closest node to the distance matrix for this node
                - 'all': Add all nodes to the distance matrix for this node
            - Notes:
                - If you are using 'kdclosest', the lat_lon_bound is ignored as the KD-Tree is globally built
        - `node_addition_math`
            - Type: str
            - What: The math to use when calculating the distance between nodes when determining the closest node (or closest quadrant node) to add to the graph
            - Default: 'euclidean'
            - Options:
                - 'euclidean': Use the euclidean distance between nodes. This is much faster but is not accurate (especially near the poles)
                - 'haversine': Use the haversine distance between nodes. This is slower but is an accurate representation of the surface distance between two points on the earth
            - Notes:
                - Once the closest node (or closest quadrant node) is determined, the haversine distance (with circuity) is used to calculate the distance between the nodes when adding it to the graph.
        - `lat_lon_bound`
            - Type: int | float
            - What: Forms a bounding box around the node that is to be added to graph. Only selects graph nodes to consider joining that are within this bounding box.

        Optional Arguments:

        - `silent`
            - Type: bool
            - What: Whether to suppress output messages
            - Default: False
        """
        if node_addition_type == "kdclosest":
            closest_idx = self.geokdtree.closest_idx(point=node)
            closest_point = self.nodes[closest_idx]
            return {
                closest_idx: haversine(node, closest_point, circuity=circuity),
            }
        assert node_addition_type in [
            "quadrant",
            "all",
            "closest",
            "kdclosest",
        ], f"Invalid node addition type provided ({node_addition_type}), valid options are: ['quadrant', 'all', 'closest', 'kdclosest']"
        assert node_addition_math in [
            "euclidean",
            "haversine",
        ], f"Invalid node addition math provided ({node_addition_math}), valid options are: ['euclidean', 'haversine']"
        # Get only bounded nodes
        # Find the only keep nodes that are within the bounding latitude
        top_lat = node[0] + lat_lon_bound
        bottom_lat = node[0] - lat_lon_bound
        top_lon = node[1] + lat_lon_bound
        bottom_lon = node[1] - lat_lon_bound
        nodes = {
            node_idx: node_i
            for node_idx, node_i in enumerate(self.nodes)
            if node_i[0] >= bottom_lat
            and node_i[0] <= top_lat
            and node_i[1] >= bottom_lon
            and node_i[1] <= top_lon
        }
        if len(nodes) == 0:
            print_console(
                f"When adding your origin or destination node to the graph, no nodes found within the bounding box of {lat_lon_bound} degrees around the node {node}.",
                silent=silent,
            )
            print_console(
                "Using KD-Tree to find closest node instead.", silent=silent
            )
            closest_idx = self.geokdtree.closest_idx(point=node)
            closest_point = self.nodes[closest_idx]
            return {
                closest_idx: round(
                    haversine(node, closest_point, circuity=circuity), 4
                )
            }
        if node_addition_type == "all":
            return {
                node_idx: round(haversine(node, node_i, circuity=circuity), 4)
                for node_idx, node_i in nodes.items()
            }
        if node_addition_math == "haversine":
            dist_fn = lambda x: haversine(node, x, circuity=circuity)
        elif node_addition_math == "euclidean":
            # Note this is squared euclidean distance since it is not used except for comparison
            dist_fn = lambda x: (node[0] - x[0]) ** 2 + (node[1] - x[1]) ** 2
        if node_addition_type == "closest":
            quadrant_fn = lambda x, y: "all"
        else:
            quadrant_fn = lambda x, y: ("n" if x[0] - y[0] > 0 else "s") + (
                "e" if x[1] - y[1] > 0 else "w"
            )
        min_diffs = {}
        min_diffs_idx = {}
        for node_idx, node_i in nodes.items():
            quadrant = quadrant_fn(node_i, node)
            dist = dist_fn(node_i)
            if dist < min_diffs.get(quadrant, float("inf")):
                min_diffs[quadrant] = dist
                min_diffs_idx[quadrant] = node_idx
        return {
            node_idx: round(
                haversine(node, self.nodes[node_idx], circuity=circuity), 4
            )
            for node_idx in min_diffs_idx.values()
        }

    def add_node(
        self,
        node: dict[str, float | int],
        circuity: float | int,
        node_addition_type: str = "quadrant",
        node_addition_math: str = "euclidean",
        lat_lon_bound: float | int = 5,
        silent: bool = False,
    ) -> int:
        """
        Function:

        - Add a node to the network
        - Returns the id of the new node

        Required Arguments:

        - `node`
            - Type: dict
            - What: A dictionary with the keys 'latitude' and 'longitude'

        Optional Arguments:

        - `circuity`
            - Type: int | float
            - What: The circuity to apply to any distance calculations
            - Default: 4
            - Note: This defaults to 4 to prevent the algorithm from taking a direct route in direction of the destination over some impassible terrain (EG: a maritime network that goes through land)
        - `node_addition_type`
            - Type: str
            - What: The type of node addition to use
            - Default: 'quadrant'
            - Options:
                - 'quadrant': Add the closest node in each quadrant (ne, nw, se, sw) to the distance matrix for this node
                - 'closest': Add only the closest node to the distance matrix for this node
                - 'all': Add all nodes to the distance matrix for this node
                - 'kdclosest': Add the closest node using a KD-Tree
        - `node_addition_math`
            - Type: str
            - What: The math to use when calculating the distance between nodes when determining the closest node (or closest quadrant node) to add to the graph
            - Default: 'euclidean'
            - Options:
                - 'euclidean': Use the euclidean distance between nodes. This is much faster but is not accurate (especially near the poles)
                - 'haversine': Use the haversine distance between nodes. This is slower but is an accurate representation of the surface distance between two points on the earth
            - Notes:
                - Once the closest node (or closest quadrant node) is determined, the haversine distance (with circuity) is used to calculate the distance between the nodes when adding it to the graph.
        - `lat_lon_bound`
            - Type: int | float
            - What: Forms a bounding box around the node that is to be added to graph. Only selects graph nodes to consider joining that are within this bounding box.
            - Default: 5
        - `silent`
            - Type: bool
            - What: If True, suppresses all output from the function
            - Default: False

        """
        # Validate the inputs
        assert isinstance(node, dict), "Node must be a dictionary"
        assert "latitude" in node.keys(), "Node must have a latitude"
        assert "longitude" in node.keys(), "Node must have a longitude"
        assert (
            node["latitude"] >= -90 and node["latitude"] <= 90
        ), "Latitude must be between -90 and 90"
        assert (
            node["longitude"] >= -180 and node["longitude"] <= 180
        ), "Longitude must be between -180 and 180"
        assert circuity > 0, "Circuity must be greater than 0"
        assert node_addition_type in [
            "quadrant",
            "all",
            "closest",
            "kdclosest",
        ], f"Invalid node addition type provided ({node_addition_type}), valid options are: ['quadrant', 'all', 'closest']"
        assert node_addition_math in [
            "euclidean",
            "haversine",
        ], f"Invalid node addition math provided ({node_addition_math}), valid options are: ['euclidean', 'haversine']"
        assert isinstance(
            lat_lon_bound, (int, float)
        ), "Lat_lon_bound must be a number"
        assert lat_lon_bound > 0, "Lat_lon_bound must be greater than 0"
        node = [node["latitude"], node["longitude"]]
        # Get the distances to all relevant nodes
        distances = self.get_node_distances(
            node=node,
            circuity=circuity,
            node_addition_type=node_addition_type,
            node_addition_math=node_addition_math,
            lat_lon_bound=lat_lon_bound,
            silent=silent,
        )

        # Create the node
        new_node_id = len(self.graph)
        self.nodes.append(node)
        self.graph.append(distances)
        for node_idx, node_distance in distances.items():
            self.graph[node_idx][new_node_id] = node_distance
        return new_node_id

    def save_as_geojson(self, filename: str, compact: bool = False) -> None:
        """
        Function:

        - Save the current geograph object as a geojson file specifed by `filename`
        - This is useful for understanding the underlying geograph and for debugging purposes
        - Returns None

        Required Arguments:

        - `filename`
            - Type: str
            - What: The filename to save the geojson file as

        Optional Arguments:

        - `compact`
            - Type: bool
            - What:
                - If True, saves the geojson as a compact multiline string without distances or properties
                - If False, saves the geojson as a feature collection with each line as a separate feature
                    - Note: If False, the resulting file can be loaded with the legacy load_geojson_as_geograph function
            - Default: False

        """
        if compact:
            multiline = []
            for origin_idx, destinations in enumerate(self.graph):
                for destination_idx, distance in destinations.items():
                    multiline.append(
                        [
                            [
                                self.nodes[origin_idx][1],
                                self.nodes[origin_idx][0],
                            ],
                            [
                                self.nodes[destination_idx][1],
                                self.nodes[destination_idx][0],
                            ],
                        ]
                    )
            out_dict = {
                "type": "GeometryCollection",
                "geometries": [
                    {
                        "type": "MultiLineString",
                        "coordinates": multiline,
                    }
                ],
            }

        else:
            features = []
            for origin_idx, destinations in enumerate(self.graph):
                for destination_idx, distance in destinations.items():
                    # Create an undirected graph for geojson purposes
                    if origin_idx > destination_idx:
                        continue
                    origin = self.nodes[origin_idx]
                    destination = self.nodes[destination_idx]
                    features.append(
                        {
                            "type": "Feature",
                            "properties": {
                                "origin_idx": origin_idx,
                                "destination_idx": destination_idx,
                                "distance": distance,
                            },
                            "geometry": {
                                "type": "LineString",
                                "coordinates": [
                                    [origin[1], origin[0]],
                                    [
                                        destination[1],
                                        destination[0],
                                    ],
                                ],
                            },
                        }
                    )
            out_dict = {"type": "FeatureCollection", "features": features}
        with open(filename, "w") as f:
            json.dump(out_dict, f)

    def merge_with_other_geograph(
        self,
        other_geograph,
        connection_nodes: list[list[int | float]],
        circuity_to_current_geograph: float | int = 1.2,
        circuity_to_other_geograph: float | int = 1.2,
        node_addition_type_current_geograph: str = "closest",
        node_addition_type_other_geograph: str = "closest",
        node_addition_math: str = "euclidean",
    ) -> None:
        """
        Function:

        - Merge the current geograph with another geograph
        - This is useful for combining multiple geographs into one
        - This modifies the current geograph in place

        Required Arguments:

        - `other_geograph`
            - Type: GeoGraph
            - What: The other geograph to merge with
        - `connection_nodes`
            - Type: list of tuples
            - What: A list of [latitude, longitude] pairs that represent the nodes to connect between the two geographs
            - The only connections between the two graphs will be those specified in this list

        Optional Arguments:

        - `circuity_to_current_geograph`
            - Type: int | float
            - What: The circuity factor to apply to the distance calculations between the connection nodes and the current geograph
            - Default: 1.2
        - `circuity_to_other_geograph`
            - Type: int | float
            - What: The circuity factor to apply to the distance calculations between the connection nodes and the other geograph
            - Default: 1.2
        - `node_addition_type_current_geograph`
            - Type: str
            - What: The type of node addition to use when adding the connection nodes to the current geograph
            - Default: 'closest'
            - Options:
                - 'closest': Add the closest node to the connection node in the current geograph
                - 'quadrant': Add the closest node in each quadrant (ne, nw, se, sw) to the connection node in the current geograph
        - `node_addition_type_other_geograph`
            - Type: str
            - What: The type of node addition to use when adding the connection nodes to the other geograph
            - Default: 'closest'
            - Options:
                - 'closest': Add the closest node to the connection node in the other geograph
                - 'quadrant': Add the closest node in each quadrant (ne, nw, se, sw) to the connection node in the other geograph
        - `node_addition_math`
            - Type: str
            - What: The math to use when calculating the distance between nodes in determining which nodes to connect into when applying node addition
            - Note: Haversine distance is used to calculate the distance between the added connection nodes and the existing nodes in the geographs once they are chosen
            - Default: 'euclidean'
            - Options:
                - 'euclidean': Use the euclidean distance between nodes. This is much faster but is not accurate (especially near the poles)
                - 'haversine': Use the haversine distance between nodes. This is slower but is an accurate representation of the surface distance between two points
        """
        node_connection_mapper = {}
        original_other_graph_length = len(other_geograph.graph)
        for idx, node in enumerate(connection_nodes):
            node_dict = {
                "latitude": node[0],
                "longitude": node[1],
            }
            # Add the connection node to the current geograph
            new_node_id = self.add_node(
                node=node_dict,
                circuity=circuity_to_current_geograph,
                node_addition_type=node_addition_type_current_geograph,
                node_addition_math=node_addition_math,
            )
            # Add the connection node to the other geograph
            other_node_id = other_geograph.add_node(
                node=node_dict,
                circuity=circuity_to_other_geograph,
                node_addition_type=node_addition_type_other_geograph,
                node_addition_math=node_addition_math,
            )
            node_connection_mapper[other_node_id] = new_node_id

        # Store the modified other geograph graph that include the connection nodes
        other_graph = deepcopy(other_geograph.graph)
        # Add the other graph nodes to the current geograph (removing the connection nodes since they are already added to the current geograph)
        self.nodes += deepcopy(other_geograph.nodes)[
            :original_other_graph_length
        ]

        # Clean up the other geograph to remove any appended nodes
        while len(other_geograph.graph) > original_other_graph_length:
            other_geograph.remove_appended_node()

        graph_length = len(self.graph)

        # Create a list based connection map to map the merging nodes into the current graph
        node_connection_map = [
            i + graph_length for i in range(len(other_graph))
        ]
        # Adjust the added nodes to match the nodes added to the current graph
        for idx, node in node_connection_mapper.items():
            node_connection_map[idx] = node

        # Fill the current graph with empty dictionaries to match the length of the other graph
        self.graph.extend(
            [{} for _ in range(len(other_graph) - len(connection_nodes))]
        )
        # Populate the new connections
        for origin_idx, destinations in enumerate(other_graph):
            for destination_idx, distance in destinations.items():
                self.graph[node_connection_map[origin_idx]][
                    node_connection_map[destination_idx]
                ] = distance

    def save_as_geograph(self, name: str) -> None:
        """
        Function:

        - Save the current geograph as an importable python file

        Required Arguments:

        - `name`
            - Type: str
            - What: The name of the geograph and file
            - EG: 'custom'
                - Stored as: 'custom.py'
                    - In your current directory
                - Import as: 'from .custom import custom_geograph'
        """
        self.validate_nodes()
        self.validate_graph(check_symmetry=True, check_connected=False)
        out_string = f"""from scgraph.core import GeoGraph\ngraph={str(self.graph)}\nnodes={str(self.nodes)}\n{name}_geograph = GeoGraph(graph=graph, nodes=nodes)"""
        with open(name + ".py", "w") as f:
            f.write(out_string)

    def save_as_graphjson(self, filename: str) -> None:
        """
        Function:

        - Save the current geograph as a JSON file that can be used to recreate the geograph later
        - This is particularly useful for larger geographs that you want to save and load later without having to recreate them from scratch
        - Only the graph and nodes are saved, not the methods or any other attributes of the GeoGraph class

        Required Arguments:

        - `filename`
            - Type: str
            - What: The filename to save the JSON file as
            - EG: 'custom.graphjson'
                - Stored as: 'custom.graphjson'
                    - In your current directory
            - Note: The filename must end with .graphjson
        """
        if not filename.endswith(".graphjson"):
            raise ValueError("Filename must end with .graphjson")
        with open(filename, "w") as f:
            json.dump(
                {
                    "type": "GeoGraph",
                    "graph": self.graph,
                    "nodes": self.nodes,
                },
                f,
            )

    @staticmethod
    def load_from_graphjson(filename: str) -> "GeoGraph":
        """
        Function:

        - Load a GeoGraph from a JSON file that was saved using the `save_as_graphjson` method

        Required Arguments:

        - `filename`
            - Type: str
            - What: The filename of the JSON file to load
            - EG: 'custom.json'
                - Stored as: 'custom.json'
                    - In your current directory

        Returns:

        - A GeoGraph object with the graph and nodes loaded from the JSON file
        """
        if not filename.endswith(".graphjson"):
            raise ValueError("Filename must end with .graphjson")
        with open(filename, "r") as f:
            data = json.load(f)
        if data.get("type", None) != "GeoGraph":
            raise ValueError(
                "JSON file is not a valid GeoGraph. Ensure it was saved using the save_as_graphjson method."
            )
        return GeoGraph(
            graph=[
                {int(k): v for k, v in item.items()} for item in data["graph"]
            ],
            nodes=data["nodes"],
        )

    @staticmethod
    def load_from_geojson(
        filename: str,
        precision: int = 3,
        pct_to_keep: int | float = 100,
        min_points=3,
        silent: bool = False,
    ):
        """
        Function:

        - Load a GeoGraph from an arbitrary geojson file (GeometryCollection or FeatureCollection)
        - This function
            - Merges all LineStrings and MultiLineStrings into a single MultiLineString
            - Simplifies the MultiLineString to reduce the number of points using a percentage based Visvalengam simplification algorithm
            - Rounds the coordinates to the specified precision
            - Merges lines that start and end at the same location after rounding
            - Converts the MultiLineString into a GeoGraph object
        - Note:
            - All arcs read in will be undirected


        Required Arguments:

        - `filename`
            - Type: str
            - What: The filename of the geojson file to load
            - EG: 'custom.geojson'
                - Stored as: 'custom.geojson'
                    - In your current directory

        Optional Arguments:

        - `precision`
            - Type: int
            - What: Decimal places to round coordinates when loading and simplifying the lines
            - Default: 4
        - `pct_to_keep`
            - Type: int|float
            - What: Percentage of the interior line points to keep (note the ends are always kept)
            - Default: 100
        - `min_points`
            - Type: int
            - What: Minimum number of points to keep in the simplified line (The ends are always kept but should be included in this count)
            - Default: 3
        - `silent`
            - Type: bool
            - What: Whether to suppress progress output to the console when loading the geojson
            - Default: False
        """
        data = parse_geojson(
            filename_in=filename,
            precision=precision,
            pct_to_keep=pct_to_keep,
            min_points=min_points,
            silent=silent,
        )
        return GeoGraph(
            graph=data["graph"],
            nodes=data["nodes"],
        )

    def mod_remove_arc(
        self, origin_idx: int, destination_idx: int, undirected: bool = True
    ) -> None:
        """
        Function:

        - Remove an arc from the graph

        Required Arguments:

        - `origin_idx`
            - Type: int
            - What: The index of the origin node
        - `destination_idx`
            - Type: int
            - What: The index of the destination node

        Optional Arguments:

        - `undirected`
            - Type: bool
            - What: Whether to remove the arc in both directions
            - Default: True
        """
        assert origin_idx < len(self.graph), "Origin node does not exist"
        assert destination_idx < len(
            self.graph
        ), "Destination node does not exist"
        assert destination_idx in self.graph[origin_idx], "Arc does not exist"
        del self.graph[origin_idx][destination_idx]
        if undirected:
            if origin_idx in self.graph[destination_idx]:
                del self.graph[destination_idx][origin_idx]

    def mod_add_node(
        self, latitude: float | int, longitude: float | int
    ) -> int:
        """
        Function:

        - Add a node to the graph

        Required Arguments:

        - `latitude`
            - Type: int | float
            - What: The latitude of the node
        - `longitude`
            - Type: int | float
            - What: The longitude of the node

        Returns:

        - The index of the new node
        """
        self.nodes.append([latitude, longitude])
        self.graph.append({})
        return len(self.graph) - 1

    def mod_add_arc(
        self,
        origin_idx: int,
        destination_idx: int,
        distance: [float | int] = 0,
        use_haversine_distance=True,
        undirected: bool = True,
    ) -> None:
        """
        Function:

        - Add an arc to the graph

        Required Arguments:

        - `origin_idx`
            - Type: int
            - What: The index of the origin node
        - `destination_idx`
            - Type: int
            - What: The index of the destination node

        Optional Arguments:

        - `distance`
            - Type: int | float
            - What: The distance between the origin and destination nodes in terms of the graph distance (normally km)
            - Default: 0
        - `use_haversine_distance`
            - Type: bool
            - What: Whether to calculate the haversine distance (km) between the nodes when calculating the distance
            - Default: True
            - Note: If true, overrides the `distance` argument
        - `undirected`
            - Type: bool
            - What: Whether to add the arc in both directions
            - Default: True
        """
        assert origin_idx < len(self.graph), "Origin node does not exist"
        assert destination_idx < len(
            self.graph
        ), "Destination node does not exist"
        if use_haversine_distance:
            distance = haversine(
                self.nodes[origin_idx], self.nodes[destination_idx]
            )
        self.graph[origin_idx][destination_idx] = distance
        if undirected:
            self.graph[destination_idx][origin_idx] = distance

    @staticmethod
    def get_multi_path_geojson(
        routes: list[dict],
        filename: str | None = None,
        show_progress: bool = False,
    ) -> dict:
        """
        Creates a GeoJSON file with the shortest path between the origin and destination of each route.

        Required Parameters:

        - `routes`: list[dict]
            - List of dictionaries with the following keys:
                - geograph: GeoGraph
                    - Geograph object to use for the shortest path calculation.
                - origin: dict[float|float]
                    - Origin coordinates
                    - EG: {"latitude":39.2904, "longitude":-76.6122}
                - destination: dict[float|int]
                    - Destination coordinates
                    - EG: {"latitude":39.2904, "longitude":-76.6122}
                - properties: dict
                    - Dictionary with the properties of the route
                    - Everything in this dictionary will be included in the output GeoJSON file as properties of the route.
                    - EG: {"id":"route_1", "name":"Route 1", "color":"#ff0000"}

        Optional Parameters:

        - `filename`: str | None
            - Name of the output GeoJSON file.
            - If None, the function will not save the file
            - Default: None
        - `show_progress`: bool
            - Whether to show basic progress information
            - Default: False
        - `silent`: bool
            - Whether to suppress console output
            - Default: False

        Returns

        - `output`: dict
            - Dictionary with the GeoJSON file content.
        """
        assert isinstance(routes, list), "Routes must be a list"
        assert all(
            [isinstance(i, dict) for i in routes]
        ), "Routes must be a list of dictionaries"
        assert all(
            [isinstance(i.get("geograph"), GeoGraph) for i in routes]
        ), "All routes must have a 'geograph' key with a GeoGraph object"
        assert all(
            [isinstance(i.get("origin"), dict) for i in routes]
        ), "All routes must have an 'origin' key with a dictionary"
        assert all(
            [isinstance(i.get("destination"), dict) for i in routes]
        ), "All routes must have a 'destination' key with a dictionary"
        assert all(
            [isinstance(i.get("properties"), dict) for i in routes]
        ), "All routes must have a 'properties' key with a dictionary"
        assert all(
            [
                isinstance(i["origin"].get("latitude"), (int, float))
                for i in routes
            ]
        ), "All origins must have a 'latitude' key with a number"
        assert all(
            [
                isinstance(i["origin"].get("longitude"), (int, float))
                for i in routes
            ]
        ), "All origins must have a 'longitude' key with a number"
        assert all(
            [
                isinstance(i["destination"].get("latitude"), (int, float))
                for i in routes
            ]
        ), "All destinations must have a 'latitude' key with a number"
        assert all(
            [
                isinstance(i["destination"].get("longitude"), (int, float))
                for i in routes
            ]
        ), "All destinations must have a 'longitude' key with a number"
        assert all(
            [
                (
                    i["origin"].get("latitude") >= -90
                    and i["origin"].get("latitude") <= 90
                )
                for i in routes
            ]
        ), "All origin latitudes must be between -90 and 90"
        assert all(
            [
                (
                    i["origin"].get("longitude") >= -180
                    and i["origin"].get("longitude") <= 180
                )
                for i in routes
            ]
        ), "All origin longitudes must be between -180 and 180"
        assert all(
            [
                (
                    i["destination"].get("latitude") >= -90
                    and i["destination"].get("latitude") <= 90
                )
                for i in routes
            ]
        ), "All destination latitudes must be between -90 and 90"
        assert all(
            [
                (
                    i["destination"].get("longitude") >= -180
                    and i["destination"].get("longitude") <= 180
                )
                for i in routes
            ]
        ), "All destination longitudes must be between -180 and 180"

        output = {"type": "FeatureCollection", "features": []}
        len_routes = len(routes)
        for idx, route in enumerate(routes):
            shortest_path = route["geograph"].get_shortest_path(
                route["origin"], route["destination"]
            )
            shortest_line_path = get_line_path(shortest_path)
            output["features"].append(
                {
                    "type": "Feature",
                    "properties": route["properties"],
                    "geometry": shortest_line_path,
                }
            )
            if show_progress:
                print(
                    f"[{'='*(int((idx+1)/len_routes*20))}>{' '*(20-int((idx+1)/len_routes*20))}] {idx+1}/{len_routes}",
                    end="\r",
                )
        if show_progress:
            print()
        if filename is not None:
            json.dump(output, open(filename, "w"))
        return output

    def distance_matrix(
        self,
        nodes: list[dict[str, float | int]],
        off_graph_circuity: float | int = 1,
        geograph_units: str = "km",
        output_units: str = "km",
        silent: bool = False,
    ) -> list[list[float | int | None]]:
        """
        Function:

        - Calculate the distance matrix for a list of nodes in a very efficient way using cached spanning trees and cached node addition distances
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
        - `geograph_units`
            - Type: str
            - What: The units of the distances in the graph
            - Default: 'km'
            - Options: 'km', 'miles', 'meters', 'feet'
        - `output_units`
            - Type: str
            - What: The units of the output distance matrix
            - Default: 'km'
            - Options: 'km', 'miles', 'meters', 'feet'

        Returns:

        - A list of lists representing the distance matrix between the nodes
        - The distance matrix is a square matrix where the entry at (i, j) is the distance between node i and node j
        - The distances are in the units specified by `output_units`
        - EG:
        ```
        [
            [0.0, 0.1, ...],
            [0.1, 0.0, ...],
            ...
        ]
        """
        output_matrix = [[None] * len(nodes) for _ in range(len(nodes))]
        dist_multiplier = distance_converter(
            distance=1, input_units=geograph_units, output_units=output_units
        )
        node_addition_multiplier = distance_converter(
            distance=1, input_units="km", output_units=output_units
        )
        # Get the entry idx for each node as well as the distance to that node given the off-graph circuity
        # [(entry_idx, distance), ...]
        entry_idx_and_distance = []
        for node in nodes:
            node_idx, distance = list(
                self.get_node_distances(
                    node=[node["latitude"], node["longitude"]],
                    circuity=off_graph_circuity,
                    node_addition_type="kdclosest",
                    node_addition_math="haversine",
                    lat_lon_bound=0,
                    silent=True,
                ).items()
            )[0]
            entry_idx_and_distance.append(
                (node_idx, distance * node_addition_multiplier)
            )

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
                    length = self.cacheGraph.get_shortest_path(
                        origin_id=entry_idx_start,
                        destination_id=entry_idx_end,
                        length_only=True,
                    )["length"]
                    output_matrix[node_idx_start][node_idx_end] = (
                        (length * dist_multiplier)
                        + entry_length_start
                        + entry_length_end
                    )
                except Exception as e:
                    print_console(
                        f"Error calculating distance between nodes {node_idx_start} and {node_idx_end} with entry indices {entry_idx_start} and {entry_idx_end}.",
                        silent=silent,
                    )

        return output_matrix


def load_geojson_as_geograph(geojson_filename: str, silent=False) -> GeoGraph:
    """
    Function:

    - Create a CustomGeoGraph object loaded from a geojson file

    Required Arguments:

    - `geojson_filename`
        - Type: str
        - What: The filename of the geojson file to load
        - Note: All arcs read in will be undirected
        - Note: This geojson file must be formatted in a specific way
            - The geojson file must be a FeatureCollection
            - Each feature must be a LineString with two coordinate pairs
                - The first coordinate pair must be the origin node
                - The second coordinate pair must be the destination node
                - The properties of the feature must include the distance between the origin and destination nodes
                - The properties of the feature must include the origin and destination node idxs
                - Origin and destination node idxs must be integers between 0 and n-1 where n is the number of nodes in the graph
            - EG:
            ```
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {
                            "origin_idx": 0,
                            "destination_idx": 1,
                            "distance": 10
                        },
                        "geometry": {
                            "type": "LineString",
                            "coordinates": [
                                [121.47, 31.23],
                                [121.48, 31.24]
                            ]
                        }
                    }
                ]
            }
            ```

    Optional Arguments:

    - `silent`
        - Type: bool
        - What: Whether to suppress output to the console when loading the geojson
        - Default: False
    """
    # TODO: Remove this function in a future release
    print_console(
        "This function is deprecated and will be removed in a future release. Please use `GeoGraph.load_from_geojson` instead.",
        silent=silent,
    )
    print_console(
        "Note: `GeoGraph.load_from_geojson` is not an equivalent function so see the documentation there for details.",
        silent=silent,
    )
    print_console(
        "Note: Use silent when calling this function to suppress this message.",
        silent=silent,
    )
    with open(geojson_filename, "r") as f:
        geojson_features = json.load(f).get("features", [])

    nodes_dict = {}
    graph_dict = {}
    for feature in geojson_features:
        properties = feature.get("properties", {})
        origin_idx = properties.get("origin_idx")
        destination_idx = properties.get("destination_idx")
        distance = properties.get("distance")
        geometry = feature.get("geometry", {})
        coordinates = geometry.get("coordinates", [])

        # Validations
        assert (
            feature.get("type") == "Feature"
        ), "All features must be of type 'Feature'"
        assert (
            geometry.get("type") == "LineString"
        ), "All geometries must be of type 'LineString'"
        assert (
            len(coordinates) == 2
        ), "All LineStrings must have exactly 2 coordinates"
        assert isinstance(
            origin_idx, int
        ), "All features must have an 'origin_idx' property that is an integer"
        assert isinstance(
            destination_idx, int
        ), "All features must have a 'destination_idx' property that is an integer"
        assert isinstance(
            distance, (int, float)
        ), "All features must have a 'distance' property that is a number"
        assert (
            origin_idx >= 0
        ), "All origin_idxs must be greater than or equal to 0"
        assert (
            destination_idx >= 0
        ), "All destination_idxs must be greater than or equal to 0"
        assert distance >= 0, "All distances must be greater than or equal to 0"
        origin = coordinates[0]
        destination = coordinates[1]
        assert isinstance(origin, list), "All coordinates must be lists"
        assert isinstance(destination, list), "All coordinates must be lists"
        assert len(origin) == 2, "All coordinates must have a length of 2"
        assert len(destination) == 2, "All coordinates must have a length of 2"
        assert all(
            [isinstance(i, (int, float)) for i in origin]
        ), "All coordinates must be numeric"
        assert all(
            [isinstance(i, (int, float)) for i in destination]
        ), "All coordinates must be numeric"
        # assert all([origin[0] >= -90, origin[0] <= 90, origin[1] >= -180, origin[1] <= 180]), "All coordinates must be valid latitudes and longitudes"
        # assert all([destination[0] >= -90, destination[0] <= 90, destination[1] >= -180, destination[1] <= 180]), "All coordinates must be valid latitudes and longitudes"

        # Update the data
        nodes_dict[origin_idx] = origin
        nodes_dict[destination_idx] = destination
        graph_dict[origin_idx] = {
            **graph_dict.get(origin_idx, {}),
            destination_idx: distance,
        }
        graph_dict[destination_idx] = {
            **graph_dict.get(destination_idx, {}),
            origin_idx: distance,
        }
    assert len(nodes_dict) == len(
        graph_dict
    ), "All nodes must be included as origins in the graph dictionary"
    nodes = [
        [i[1][1], i[1][0]]
        for i in sorted(nodes_dict.items(), key=lambda x: x[0])
    ]
    ordered_graph_tuple = sorted(graph_dict.items(), key=lambda x: x[0])
    graph_map = {i[0]: idx for idx, i in enumerate(ordered_graph_tuple)}
    graph = [
        {graph_map[k]: v for k, v in i[1].items()} for i in ordered_graph_tuple
    ]
    return GeoGraph(graph=graph, nodes=nodes)


def get_multi_path_geojson(
    routes: list[dict],
    filename: str | None = None,
    show_progress: bool = False,
) -> dict:
    """
    This function is deprecated and will be removed in a future release.
    See `GeoGraph.get_multi_path_geojson` instead.
    """
    return GeoGraph.get_multi_path_geojson(
        routes=routes,
        filename=filename,
        show_progress=show_progress,
    )
