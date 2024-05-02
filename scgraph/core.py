from .utils import haversine, hard_round, distance_converter
import json


class Graph:
    @staticmethod
    def validate_graph(
        graph: list[dict],
        check_symmetry: bool = True,
        check_connected: bool = True,
    ) -> None:
        """
        Function:

        - Validate that a graph is properly formatted

        Required Arguments:

        - `graph`
            - Type: list of dictionaries
            - What: A list of dictionaries where the indicies are origin node ids and the values are dictionaries of destination node indices and distances
            - Note: All nodes must be included as origins in the graph regardless of if they have any connected destinations

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
            ), f"Your graph must be a dictionary of dictionaries but the value for origin {origin_id} is not a dictionary"
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
    def validate_connected(graph: list[dict]) -> bool:
        """
        Function:

        - Validate that a graph is fully connected
            - This means that every node in the graph has a path to every other node in the graph
            - Note: This assumes that the graph is symmetric
        - Return True if the graph is fully connected and False if it is not

        Required Arguments:

        - `graph`
            - Type: list of dictionaries
            - What: A list of dictionaries where the indicies are origin node ids and the values are dictionaries of destination node ids and distances
            - Note: All nodes must be included as origins in the graph regardless of if they have any connected destinations

        Optional Arguments:

        - None
        """
        origin_id = 0
        destination_id = len(graph) + 1

        distance_matrix = [float("inf") for i in graph]
        open_leaves = {}
        predecessor = [None for i in graph]

        distance_matrix[origin_id] = 0
        open_leaves[origin_id] = 0

        while True:
            if len(open_leaves) == 0:
                return max(distance_matrix) != float("inf")
            current_id = min(open_leaves, key=open_leaves.get)
            open_leaves.pop(current_id)
            if current_id == destination_id:
                break
            current_distance = distance_matrix[current_id]
            for connected_id, connected_distance in graph[current_id].items():
                possible_distance = current_distance + connected_distance
                if possible_distance < distance_matrix[connected_id]:
                    distance_matrix[connected_id] = possible_distance
                    predecessor[connected_id] = current_id
                    open_leaves[connected_id] = possible_distance

    @staticmethod
    def input_check(
        graph: list[dict], origin_id: int, destination_id: int
    ) -> None:
        """
        Function:

        - Check that the inputs passed to the shortest path algorithm are valid
        - Raises an exception if the inputs passed are not valid

        Required Arguments:

        - `graph`
            - Type: list[dict]
            - What: A list of dictionaries where the indicies are origin node ids and the values are dictionaries of destination node ids and distances
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
        graph: list[dict], origin_id: int, destination_id: int
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

        - `graph`
            - Type: list[dict]
            - What: A list of dictionaries where the indicies are origin node ids and the values are dictionaries of destination node ids and distances
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
        distance_matrix = [float("inf") for i in graph]
        branch_tip_distances = [float("inf") for i in graph]
        predecessor = [None for i in graph]

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
        while predecessor[current_id] is not None:
            current_id = predecessor[current_id]
            output_path.append(current_id)

        output_path.reverse()

        return {
            "path": output_path,
            "length": hard_round(4, distance_matrix[destination_id]),
        }

    @staticmethod
    def dijkstra_makowski(
        graph: list[dict], origin_id: int, destination_id: int
    ) -> dict:
        """
        Function:

        - Identify the shortest path between two nodes in a sparse network graph using Makowski's modified Dijkstra algorithm
            - Modifications allow for a sparse distance matrix to be used instead of a dense distance matrix
            - Improvements include only computing future potential nodes based on the open leaves for each branch
                - Open leaves are nodes that have not been visited yet but are adjacent to other visited nodes
            - This can dramatically reduce the memory and compute requirements of the algorithm
            - For particularly sparse graphs, this algorithm runs close to O(n) time
                - Where n is the number of nodes in the graph
            - For dense graphs, this algorithm runs in O(n^2) time
                - Where n is the number of nodes in the graph
        - Return a dictionary of various path information including:
            - `id_path`: A list of node ids in the order they are visited
            - `path`: A list of node dictionaries (lat + long) in the order they are visited

        Required Arguments:

        - `graph`
            - Type: list[dict]
            - What: A list of dictionaries where the indicies are origin node ids and the values are dictionaries of destination node ids and distances
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
        distance_matrix = [float("inf") for i in graph]
        open_leaves = {}
        predecessor = [None for i in graph]

        distance_matrix[origin_id] = 0
        open_leaves[origin_id] = 0

        while True:
            if len(open_leaves) == 0:
                raise Exception(
                    "Something went wrong, the origin and destination nodes are not connected."
                )
            current_id = min(open_leaves, key=open_leaves.get)
            open_leaves.pop(current_id)
            if current_id == destination_id:
                break
            current_distance = distance_matrix[current_id]
            for connected_id, connected_distance in graph[current_id].items():
                possible_distance = current_distance + connected_distance
                if possible_distance < distance_matrix[connected_id]:
                    distance_matrix[connected_id] = possible_distance
                    predecessor[connected_id] = current_id
                    open_leaves[connected_id] = possible_distance

        output_path = [current_id]
        while predecessor[current_id] is not None:
            current_id = predecessor[current_id]
            output_path.append(current_id)

        output_path.reverse()

        return {
            "path": output_path,
            "length": hard_round(4, distance_matrix[destination_id]),
        }


class GeoGraph:
    def __init__(
        self, graph: list[dict], nodes: list[list[int, float]]
    ) -> None:
        """
        Function:

        - Create a GeoGraph object

        Required Arguments:

        - `graph`
            - Type: list of dictionaries
            - What: A list of dictionaries where the indicies are origin node ids and the values are dictionaries of destination node indices and distances
            - Note: All nodes must be included as origins in the graph regardless of if they have any connected destinations
        - `nodes`
            - Type: list of lists
            - What: A list of lists where the values are coordinates (latitude then longitude)
            - Note: The length of the nodes list must be the same as that of the graph list

        Optional Arguments:

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

    def get_shortest_path(
        self,
        origin_node: dict[int, float],
        destination_node: dict[int, float],
        output_units: str = "km",
        algorithm_fn=Graph.dijkstra_makowski,
        off_graph_circuity: [int, float] = 1,
        node_addition_type: str = "quadrant",
        node_addition_circuity: [int, float] = 4,
        geograph_units: str = "km",
        output_coordinate_path: str = "list_of_lists",
        output_path: bool = False,
        node_addition_lat_lon_bound: [int, float] = 5,
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
                    - `origin`: The id of the origin node from the graph dictionary to start the shortest path from
                    - `destination`: The id of the destination node from the graph dictionary to end the shortest path at
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
        node_addition_circuity: [float, int],
        off_graph_circuity: [float, int],
    ) -> [float, int]:
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

    def get_coordinate_path(self, path: list[int]) -> list[dict[int, float]]:
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
        circuity: [int, float],
        node_addition_type: str,
        node_addition_math: str,
        lat_lon_bound: [int, float],
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
        node: dict[int, float],
        circuity: [int, float],
        node_addition_type: str = "quadrant",
        node_addition_math: str = "euclidean",
        lat_lon_bound: [int, float] = 5,
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
        for origin_idx, destinations in self.graph.items():
            for destination_idx, distance in destinations.items():
                # Create an undirected graph for geojson purposes
                if origin_idx > destination_idx:
                    continue
                origin = self.nodes.get(origin_idx)
                destination = self.nodes.get(destination_idx)
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
                                [origin["longitude"], origin["latitude"]],
                                [
                                    destination["longitude"],
                                    destination["latitude"],
                                ],
                            ],
                        },
                    }
                )

        out_dict = {"type": "FeatureCollection", "features": features}
        with open(filename, "w") as f:
            json.dump(out_dict, f)
