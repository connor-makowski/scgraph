from .utils import haversine, distance_converter, get_line_path, cheap_ruler
import json
from heapq import heappop, heappush


class Graph:
    @staticmethod
    def validate_graph(
        graph: list[dict[int, int | float]],
        check_symmetry: bool = True,
        check_connected: bool = True,
    ) -> None:
        """
        Function:

        - Validate that a graph is properly formatted

        Required Arguments:

        - `graph`:
            - Type: list of dictionaries with integer keys and integer or float values
            - What: A list of dictionaries where the indicies are origin node ids and the values are dictionaries of destination node indices and graph weights
            - Note: All nodes must be included as origins in the graph regardless of if they have any connected destinations
            - EG:
            ```
                [
                    # From London (index 0)
                    {
                        # To Paris (index 1)
                        1: 311,
                    },
                    # From Paris (index 1)
                    {
                        # To London (index 0)
                        0: 311,
                        # To Berlin (index 2)
                        2: 878,
                        # To Rome (index 3)
                        3: 1439,
                        # To Madrid (index 4)
                        4: 1053
                    },
                    # From Berlin (index 2)
                    {
                        # To Paris (index 1)
                        1: 878,
                        # To Rome (index 3)
                        3: 1181,
                    },
                    # From Rome (index 3)
                    {
                        # To Paris (index 1)
                        1: 1439,
                        # To Berlin (index 2)
                        2: 1181,
                    },
                    # From Madrid (index 4)
                    {
                        # To Paris (index 1)
                        1: 1053,
                        # To Lisbon (index 5)
                        5: 623
                    },
                    # From Lisbon (index 5)
                    {
                        # To Madrid (index 4)
                        4: 623
                    }
                ]
            ```

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
            - Note: For computational efficiency, only symmetric graphs are checked for connectivity
            - Note: If this is True, `check_symmetry` is forced to True and the graph will be checked for symmetry prior to checking for connectivity
        """
        check_symmetry = check_symmetry or check_connected
        assert isinstance(graph, list), "Your graph must be a list"
        len_graph = len(graph)
        for origin_id, origin_dict in enumerate(graph):
            assert isinstance(
                origin_dict, dict
            ), f"Your graph must be a list of dictionaries but the value for origin {origin_id} is not a dictionary"
            destinations = list(origin_dict.keys())
            lengths = list(origin_dict.values())
            assert all(
                [
                    (isinstance(i, int) and i >= 0 and i < len_graph)
                    for i in destinations
                ]
            ), f"Destination ids must be non-negative integers and equivalent to an existing index, but graph[{origin_id}] has an error in the destination ids"
            assert all(
                [(isinstance(i, (int, float)) and i >= 0) for i in lengths]
            ), f"Distances must be integers or floats, but graph[{origin_id}] contains a non-integer or non-float distance"
            if check_symmetry:
                for destination_id, distance in origin_dict.items():
                    assert (
                        graph[destination_id].get(origin_id) == distance
                    ), f"Your graph is not symmetric, the distance from node {origin_id} to node {destination_id} is {distance} but the distance from node {destination_id} to node {origin_id} is {graph.get(destination_id, {}).get(origin_id)}"
        if check_connected:
            assert Graph.validate_connected(
                graph
            ), "Your graph is not fully connected"

    @staticmethod
    def validate_connected(
        graph: list[dict[int, int | float]], origin_id: int = 0
    ) -> bool:
        """
        Function:

        - Validate that a graph is fully connected
            - This means that every node in the graph has a path to every other node in the graph
            - Note: This assumes that the graph is symmetric
        - Return True if the graph is fully connected and False if it is not

        Required Arguments:

        - `graph`:
            - Type: list of dictionaries
            - See: https://connor-makowski.github.io/scgraph/scgraph/core.html#Graph.validate_graph

        Optional Arguments:

        - `origin_id`
            - Type: int
            - What: The id of the origin node from which to start the connectivity check
            - Default: 0
        """
        visited = [0] * len(graph)
        open_leaves = [origin_id]

        while open_leaves:
            current_id = open_leaves.pop()
            visited[current_id] = 1
            for connected_id, connected_distance in graph[current_id].items():
                if visited[connected_id] == 0:
                    open_leaves.append(connected_id)
        return min(visited) == 1

    @staticmethod
    def input_check(
        graph: list[dict[int, int | float]], origin_id: int, destination_id: int
    ) -> None:
        """
        Function:

        - Check that the inputs passed to the shortest path algorithm are valid
        - Raises an exception if the inputs passed are not valid

        Required Arguments:

        - `graph`:
            - Type: list of dictionaries
            - See: https://connor-makowski.github.io/scgraph/scgraph/core.html#Graph.validate_graph
        - `origin_id`
            - Type: int
            - What: The id of the origin node from the graph dictionary to start the shortest path from
        - `destination_id`
            - Type: int
            - What: The id of the destination node from the graph dictionary to end the shortest path at

        Optional Arguments:

        - None
        """
        if (
            not isinstance(origin_id, int)
            and origin_id < len(graph)
            and origin_id >= 0
        ):
            raise Exception(f"Origin node ({origin_id}) is not in the graph")
        if (
            not isinstance(destination_id, int)
            and origin_id < len(graph)
            and origin_id >= 0
        ):
            raise Exception(
                f"Destination node ({destination_id}) is not in the graph"
            )

    @staticmethod
    def dijkstra(
        graph: list[dict[int, int | float]], origin_id: int, destination_id: int
    ) -> dict:
        """
        Function:

        - Identify the shortest path between two nodes in a sparse network graph using a modified dijkstra algorithm
            - Modifications allow for a sparse distance matrix to be used instead of a dense distance matrix
            - This can dramatically reduce the memory and compute requirements of the algorithm
            - This algorithm runs in O(n^2) time where n is the number of nodes in the graph
        - Return a dictionary of various path information including:
            - `id_path`: A list of node ids in the order they are visited
            - `path`: A list of node dictionaries (lat + long) in the order they are visited

        Required Arguments:

        - `graph`:
            - Type: list of dictionaries
            - See: https://connor-makowski.github.io/scgraph/scgraph/core.html#Graph.validate_graph
        - `origin_id`
            - Type: int
            - What: The id of the origin node from the graph dictionary to start the shortest path from
        - `destination_id`
            - Type: int
            - What: The id of the destination node from the graph dictionary to end the shortest path at

        Optional Arguments:

        - None
        """
        Graph.input_check(
            graph=graph, origin_id=origin_id, destination_id=destination_id
        )
        distance_matrix = [float("inf")] * len(graph)
        branch_tip_distances = [float("inf")] * len(graph)
        predecessor = [-1] * len(graph)

        distance_matrix[origin_id] = 0
        branch_tip_distances[origin_id] = 0

        while True:
            current_distance = min(branch_tip_distances)
            if current_distance == float("inf"):
                raise Exception(
                    "Something went wrong, the origin and destination nodes are not connected."
                )
            current_id = branch_tip_distances.index(current_distance)
            branch_tip_distances[current_id] = float("inf")
            if current_id == destination_id:
                break
            for connected_id, connected_distance in graph[current_id].items():
                possible_distance = current_distance + connected_distance
                if possible_distance < distance_matrix[connected_id]:
                    distance_matrix[connected_id] = possible_distance
                    predecessor[connected_id] = current_id
                    branch_tip_distances[connected_id] = possible_distance

        output_path = [current_id]
        while predecessor[current_id] != -1:
            current_id = predecessor[current_id]
            output_path.append(current_id)

        output_path.reverse()

        return {
            "path": output_path,
            "length": distance_matrix[destination_id],
        }

    @staticmethod
    def dijkstra_makowski(
        graph: list[dict[int, int | float]], origin_id: int, destination_id: int
    ) -> dict:
        """
        Function:

        - Identify the shortest path between two nodes in a sparse network graph using Makowski's modified Dijkstra algorithm
            - Modifications allow for a sparse distance matrix to be used instead of a dense distance matrix
            - Improvements include only computing future potential nodes based on the open leaves for each branch
                - Open leaves are nodes that have not been visited yet but are adjacent to other visited nodes
            - This can dramatically reduce the memory and compute requirements of the algorithm
            - For particularly sparse graphs, this algorithm runs close to O(n log n) time
                - Where n is the number of nodes in the graph
            - For dense graphs, this algorithm runs closer to O(n^2) time (similar to the standard Dijkstra algorithm)
                - Where n is the number of nodes in the graph
        - Return a dictionary of various path information including:
            - `id_path`: A list of node ids in the order they are visited
            - `path`: A list of node dictionaries (lat + long) in the order they are visited

        Required Arguments:

        - `graph`:
            - Type: list of dictionaries
            - See: https://connor-makowski.github.io/scgraph/scgraph/core.html#Graph.validate_graph
        - `origin_id`
            - Type: int
            - What: The id of the origin node from the graph dictionary to start the shortest path from
        - `destination_id`
            - Type: int
            - What: The id of the destination node from the graph dictionary to end the shortest path at

        Optional Arguments:

        - None
        """
        # Input Validation
        Graph.input_check(
            graph=graph, origin_id=origin_id, destination_id=destination_id
        )
        # Variable Initialization
        distance_matrix = [float("inf")] * len(graph)
        distance_matrix[origin_id] = 0
        open_leaves = []
        heappush(open_leaves, (0, origin_id))
        predecessor = [-1] * len(graph)

        while open_leaves:
            current_distance, current_id = heappop(open_leaves)
            if current_id == destination_id:
                break
            for connected_id, connected_distance in graph[current_id].items():
                possible_distance = current_distance + connected_distance
                if possible_distance < distance_matrix[connected_id]:
                    distance_matrix[connected_id] = possible_distance
                    predecessor[connected_id] = current_id
                    heappush(open_leaves, (possible_distance, connected_id))
        if current_id != destination_id:
            raise Exception(
                "Something went wrong, the origin and destination nodes are not connected."
            )

        output_path = [current_id]
        while predecessor[current_id] != -1:
            current_id = predecessor[current_id]
            output_path.append(current_id)

        output_path.reverse()

        return {
            "path": output_path,
            "length": distance_matrix[destination_id],
        }

    @staticmethod
    def a_star(
        graph: list[dict[int, int | float]],
        origin_id: int,
        destination_id: int,
        heuristic_fn=None,
    ) -> dict:
        """
        Function:

        - Identify the shortest path between two nodes in a sparse network graph using an A* extension of Makowski's modified Dijkstra algorithm
        - Return a dictionary of various path information including:
            - `id_path`: A list of node ids in the order they are visited
            - `path`: A list of node dictionaries (lat + long) in the order they are visited

        Required Arguments:

        - `graph`:
            - Type: list of dictionaries
            - See: https://connor-makowski.github.io/scgraph/scgraph/core.html#Graph.validate_graph
        - `origin_id`
            - Type: int
            - What: The id of the origin node from the graph dictionary to start the shortest path from
        - `destination_id`
            - Type: int
            - What: The id of the destination node from the graph dictionary to end the shortest path at
        - `heuristic_fn`
            - Type: function
            - What: A heuristic function that takes two node ids and returns an estimated distance between them
            - Note: If None, returns the shortest path using Makowski's modified Dijkstra algorithm
            - Default: None

        Optional Arguments:

        - None
        """
        if heuristic_fn is None:
            return Graph.dijkstra_makowski(
                graph=graph,
                origin_id=origin_id,
                destination_id=destination_id,
            )
        # Input Validation
        Graph.input_check(
            graph=graph, origin_id=origin_id, destination_id=destination_id
        )
        # Variable Initialization
        distance_matrix = [float("inf")] * len(graph)
        distance_matrix[origin_id] = 0
        open_leaves = []
        heappush(open_leaves, (0, origin_id))
        predecessor = [-1] * len(graph)

        while open_leaves:
            current_id = heappop(open_leaves)[1]
            if current_id == destination_id:
                break
            current_distance = distance_matrix[current_id]
            for connected_id, connected_distance in graph[current_id].items():
                possible_distance = current_distance + connected_distance
                if possible_distance < distance_matrix[connected_id]:
                    distance_matrix[connected_id] = possible_distance
                    predecessor[connected_id] = current_id
                    heappush(
                        open_leaves,
                        (
                            possible_distance
                            + heuristic_fn(connected_id, destination_id),
                            connected_id,
                        ),
                    )
        if current_id != destination_id:
            raise Exception(
                "Something went wrong, the origin and destination nodes are not connected."
            )

        output_path = [current_id]
        while predecessor[current_id] != -1:
            current_id = predecessor[current_id]
            output_path.append(current_id)

        output_path.reverse()

        return {
            "path": output_path,
            "length": distance_matrix[destination_id],
        }


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
            - See: https://connor-makowski.github.io/scgraph/scgraph/core.html#Graph.validate_graph
        - `nodes`
            - Type: list of lists of ints or floats
            - What: A list of lists where the values are coordinates (latitude then longitude)
            - Note: The length of the nodes list must be the same as that of the graph list
            - EG Continuing off the example from https://connor-makowski.github.io/scgraph/scgraph/core.html#Graph.validate_graph
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
        return cheap_ruler(
            origin=self.nodes[origin_id],
            destination=self.nodes[destination_id],
            units="km",
            # Use a circuity factor of 0.95 to account for the fact that cheap_ruler can overestimate distances
            circuity=0.9,
        )

    def get_shortest_path(
        self,
        origin_node: dict[float | int],
        destination_node: dict[float | int],
        output_units: str = "km",
        algorithm_fn=Graph.dijkstra_makowski,
        algorithm_kwargs: dict = dict(),
        off_graph_circuity: [float | int] = 1,
        node_addition_type: str = "quadrant",
        node_addition_circuity: [float | int] = 4,
        geograph_units: str = "km",
        output_coordinate_path: str = "list_of_lists",
        output_path: bool = False,
        node_addition_lat_lon_bound: [float | int] = 5,
        node_addition_math: str = "euclidean",
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
                        - See: https://connor-makowski.github.io/scgraph/scgraph/core.html#Graph.validate_graph
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
            - Default: 'quadrant'
            - Options:
                - 'quadrant': Add the closest node in each quadrant (ne, nw, se, sw) to the distance matrix for this node
                - 'closest': Add only the closest node to the distance matrix for this node
                - 'all': Add all nodes to the distance matrix for this node
            - Notes:
                - `dijkstra_makowski` will operate substantially faster if the `node_addition_type` is set to 'quadrant' or 'closest'
                - `dijkstra` will operate at the similar speeds regardless of the `node_addition_type`
                - When using `all`, you should consider using `dijkstra` instead of `dijkstra_makowski` as it will be faster
                - The destination node is always added as 'all' regardless of the `node_addition_type` setting
                    - This guarantees that any destination node will be connected to any origin node regardless of how or where the origin node is added to the graph
                - If the passed graph is not a connected graph (meaning it is comprised of multiple disconnected networks)
                    - The entrypoints generated using the `node_addition_type` will determine which disconnected networks will be used to calculate the `optimal route`
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
            - Type: int | float
            - What: Forms a bounding box around the origin and destination nodes as they are added to graph
                - Only points on the current graph inside of this bounding box are considered when updating the distance matrix for the origin or destination nodes
            - Default: 5
            - Note: If no nodes are found within the bounding box, the bounding box is expanded to 180 degrees in all directions (all nodes are considered)
            - Note: This is only used when adding a new node (the specified origin and destination) to the graph
        - `node_addition_math`
            - Type: str
            - What: The math to use when calculating the distance between nodes when determining the closest node (or closest quadrant node) to add to the graph
            - Default: 'euclidean'
            - Options:
                - 'euclidean': Use the euclidean distance between nodes. This is much faster but is not as accurate (especially near the poles)
                - 'haversine': Use the haversine distance between nodes. This is slower but is an accurate representation of the surface distance between two points on the earth
            - Notes:
                - Only used if `node_addition_type` is set to 'quadrant' or 'closest'
        - `**kwargs`
            - Additional keyword arguments. These are included for forwards and backwards compatibility reasons, but are not currently used.
        """
        original_graph_length = len(self.graph)
        # Add the origin and destination nodes to the graph
        origin_id = self.add_node(
            node=origin_node,
            node_addition_type=node_addition_type,
            circuity=node_addition_circuity,
            lat_lon_bound=node_addition_lat_lon_bound,
            node_addition_math=node_addition_math,
        )
        destination_id = self.add_node(
            node=destination_node,
            node_addition_type="all",
            circuity=node_addition_circuity,
            lat_lon_bound=node_addition_lat_lon_bound,
            node_addition_math=node_addition_math,
        )
        try:
            output = algorithm_fn(
                graph=self.graph,
                origin_id=origin_id,
                destination_id=destination_id,
                **algorithm_kwargs,
            )
            output["coordinate_path"] = self.get_coordinate_path(output["path"])
            output["length"] = self.adujust_circuity_length(
                output=output,
                node_addition_circuity=node_addition_circuity,
                off_graph_circuity=off_graph_circuity,
            )
            output["length"] = distance_converter(
                output["length"],
                input_units=geograph_units,
                output_units=output_units,
            )
            if output_coordinate_path == "list_of_dicts":
                output["coordinate_path"] = [
                    {"latitude": i[0], "longitude": i[1]}
                    for i in output["coordinate_path"]
                ]
            elif output_coordinate_path == "list_of_lists_long_first":
                output["coordinate_path"] = [
                    [i[1], i[0]] for i in output["coordinate_path"]
                ]
                output["long_first"] = True
            if not output_path:
                del output["path"]
            while len(self.graph) > original_graph_length:
                self.remove_appended_node()
            return output
        except Exception as e:
            while len(self.graph) > original_graph_length:
                self.remove_appended_node()
            raise e

    def adujust_circuity_length(
        self,
        output: dict,
        node_addition_circuity: [float | int],
        off_graph_circuity: [float | int],
    ) -> [float | int]:
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

    def get_coordinate_path(self, path: list[int]) -> list[dict[float | int]]:
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
        circuity: [float | int],
        node_addition_type: str,
        node_addition_math: str,
        lat_lon_bound: [float | int],
    ) -> dict[float | int]:
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
                - 'quadrant': Add the closest node in each quadrant (ne, nw, se, sw) to the distance matrix for this node
                - 'closest': Add only the closest node to the distance matrix for this node
                - 'all': Add all nodes to the distance matrix for this node
            - Notes:
                - `dijkstra_makowski` will operate substantially faster if the `node_addition_type` is set to 'quadrant' or 'closest'
                - `dijkstra` will operate at the similar speeds regardless of the `node_addition_type`
                - When using `all`, you should consider using `dijkstra` instead of `dijkstra_makowski` as it will be faster
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
        """
        assert node_addition_type in [
            "quadrant",
            "all",
            "closest",
        ], f"Invalid node addition type provided ({node_addition_type}), valid options are: ['quadrant', 'all', 'closest']"
        assert node_addition_math in [
            "euclidean",
            "haversine",
        ], f"Invalid node addition math provided ({node_addition_math}), valid options are: ['euclidean', 'haversine']"
        # Get only bounded nodes
        nodes = {
            node_idx: node_i
            for node_idx, node_i in enumerate(self.nodes)
            if abs(node_i[0] - node[0]) < lat_lon_bound
            and abs(node_i[1] - node[1]) < lat_lon_bound
        }
        if len(nodes) == 0:
            # Default to all if the lat_lon_bound fails to find any nodes
            return self.get_node_distances(
                node=node,
                circuity=circuity,
                lat_lon_bound=180,
                node_addition_type=node_addition_type,
                node_addition_math=node_addition_math,
            )
        if node_addition_type == "all":
            return {
                node_idx: round(haversine(node, node_i, circuity=circuity), 4)
                for node_idx, node_i in nodes.items()
            }
        if node_addition_math == "haversine":
            dist_fn = lambda x: round(haversine(node, x, circuity=circuity), 4)
        else:
            dist_fn = lambda x: round(
                ((node[0] - x[0]) ** 2 + (node[1] - x[1]) ** 2) ** 0.5, 4
            )
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
            if dist < min_diffs.get(quadrant, 999999999):
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
        node: dict[float | int],
        circuity: [float | int],
        node_addition_type: str = "quadrant",
        node_addition_math: str = "euclidean",
        lat_lon_bound: [float | int] = 5,
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
            - Notes:
                - `dijkstra_makowski` will operate substantially faster if the `node_addition_type` is set to 'quadrant' or 'closest'
                - `dijkstra` will operate at the similar speeds regardless of the `node_addition_type`
                - When using `all`, you should consider using `dijkstra` instead of `dijkstra_makowski` as it will be faster
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
        # Get the distances to all other nodes
        distances = self.get_node_distances(
            node=node,
            circuity=circuity,
            node_addition_type=node_addition_type,
            node_addition_math=node_addition_math,
            lat_lon_bound=lat_lon_bound,
        )

        # Create the node
        new_node_id = len(self.graph)
        self.nodes.append(node)
        self.graph.append(distances)
        for node_idx, node_distance in distances.items():
            self.graph[node_idx][new_node_id] = node_distance
        return new_node_id

    def save_as_geojson(self, filename: str) -> None:
        """
        Function:

        - Save the current geograph object as a geojson file specifed by `filename`
        - This is useful for understanding the underlying geograph and for debugging purposes
        - Returns None

        Required Arguments:

        - `filename`
            - Type: str
            - What: The filename to save the geojson file as

        """
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
        self, latitude: [float | int], longitude: [float | int]
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


def load_geojson_as_geograph(geojson_filename: str) -> GeoGraph:
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
    """
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
    filename: [str, None] = None,
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
        [isinstance(i["origin"].get("latitude"), (int, float)) for i in routes]
    ), "All origins must have a 'latitude' key with a number"
    assert all(
        [isinstance(i["origin"].get("longitude"), (int, float)) for i in routes]
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
