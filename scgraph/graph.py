import math
from heapq import heappop, heappush
from typing import Any
from scgraph.graph_utils import GraphUtils, GraphModifiers
from scgraph.contraction_hierarchies import CHGraph
from bmsspy import Bmssp


class GraphTrees:
    def get_shortest_path_tree(self, origin_id: int | set[int]) -> dict:
        """
        Function:

        - Calculate the shortest path tree of a graph using Dijkstra's algorithm

        Required Arguments:

        - `origin_id`
            - Type: int | set[int]
            - What: The id(s) of the node(s) from which to calculate the shortest path tree

        Returns:

        - A dictionary with the following keys:
            - `origin_id`: The id of the node from which the shortest path tree was calculated
            - `predecessors`: A list of node ids referring to the predecessor of each node given the shortest path tree
                - Note: For disconnected graphs, nodes that are not connected to the origin node will have a predecessor of None
            - `distance_matrix`: A list of distances from the origin node to each node in the graph
                - Note: For disconnected graphs, nodes that are not connected to the origin node will have a distance of float("inf")

        """
        # Input Validation
        self.__input_check__(origin_id=origin_id, destination_id=0)
        origin_ids = {origin_id} if isinstance(origin_id, int) else origin_id

        # Variable Initialization
        distance_matrix = [float("inf")] * len(self.graph)
        open_leaves = []
        predecessor = [-1] * len(self.graph)

        for oid in origin_ids:
            distance_matrix[oid] = 0
            heappush(open_leaves, (0, oid))

        while open_leaves:
            current_distance, current_id = heappop(open_leaves)
            for connected_id, connected_distance in self.graph[
                current_id
            ].items():
                possible_distance = current_distance + connected_distance
                if possible_distance < distance_matrix[connected_id]:
                    distance_matrix[connected_id] = possible_distance
                    predecessor[connected_id] = current_id
                    heappush(open_leaves, (possible_distance, connected_id))

        return {
            "origin_id": origin_id,
            "predecessors": predecessor,
            "distance_matrix": distance_matrix,
        }

    def get_tree_path(
        self,
        origin_id: int,
        destination_id: int,
        tree_data: dict,
        length_only: bool = False,
    ) -> dict:
        """
        Function:

        - Get the path from the origin node to the destination node using the provided tree_data
        - Return a list of node ids in the order they are visited as well as the length of the path
        - If the destination node is not reachable from the origin node, return None

        Required Arguments:

        - `origin_id`
            - Type: int
            - What: The id of the origin node from the graph dictionary to start the shortest path from
            - Note: Since multiple origins are possible, if the origin_id is not a predecessor node of the destination node, the closest origin will be used.
        - `destination_id`
            - Type: int
            - What: The id of the destination node from the graph dictionary to end the shortest path at
        - `tree_data`
            - Type: dict
            - What: The output from a tree function

        Optional Arguments:

        - `length_only`
            - Type: bool
            - What: If True, only returns the length of the path
            - Default: False

        Returns:

        - A dictionary with the following keys:
            - `path`: A list of node ids in the order they are visited from the origin node to the destination node
            - `length`: The length of the path from the origin node to the destination node
        """
        if tree_data["origin_id"] != origin_id:
            raise Exception(
                "The origin node must be the same as the spanning node for this function to work."
            )
        destination_distance = tree_data["distance_matrix"][destination_id]
        if destination_distance == float("inf"):
            raise Exception(
                "Something went wrong, the origin and destination nodes are not connected."
            )
        if length_only:
            return {"length": destination_distance}
        current_id = destination_id
        current_path = [destination_id]
        while current_id != origin_id and current_id != -1:
            current_id = tree_data["predecessors"][current_id]
            current_path.append(current_id)
        current_path.reverse()
        return {
            "path": current_path,
            "length": destination_distance,
        }


class GraphAlgorithms:
    def dijkstra(
        self,
        origin_id: int | set[int],
        destination_id: int,
    ) -> dict:
        """
        Function:

        - Identify the shortest path between two nodes in a sparse network graph using a modified Dijkstra algorithm

        - Return a dictionary of various path information including:
            - `path`: A list of node ids in the order they are visited
            - `length`: The length of the path from the origin node to the destination node

        Required Arguments:

        - `origin_id`
            - Type: int | set[int]
            - What: The id(s) of the origin node(s) from the graph dictionary to start the shortest path from
        - `destination_id`
            - Type: int
            - What: The id of the destination node from the graph dictionary to end the shortest path at

        Optional Arguments:

        - None
        """
        # Input Validation
        self.__input_check__(origin_id=origin_id, destination_id=destination_id)
        origin_ids = {origin_id} if isinstance(origin_id, int) else origin_id
        # Variable Initialization
        distance_matrix = [float("inf")] * len(self.graph)
        predecessor = [-1] * len(self.graph)
        open_leaves = []

        for oid in origin_ids:
            distance_matrix[oid] = 0
            heappush(open_leaves, (0, oid))

        while open_leaves:
            current_distance, current_id = heappop(open_leaves)
            if current_id == destination_id:
                break
            # Technically, the next line is not necessary but can help with performance
            if current_distance == distance_matrix[current_id]:
                for connected_id, connected_distance in self.graph[
                    current_id
                ].items():
                    possible_distance = current_distance + connected_distance
                    if possible_distance < distance_matrix[connected_id]:
                        distance_matrix[connected_id] = possible_distance
                        predecessor[connected_id] = current_id
                        heappush(open_leaves, (possible_distance, connected_id))
        if current_id != destination_id:
            raise Exception(
                "Something went wrong, the origin and destination nodes are not connected."
            )

        return {
            "path": self.__reconstruct_path__(destination_id, predecessor),
            "length": distance_matrix[destination_id],
        }

    def dijkstra_buckets(
        self,
        origin_id: int | set[int],
        destination_id: int,
        max_edge_weight: int | float | None = None,
    ) -> dict:
        """
        Function:

        - Identify the shortest path between two nodes in a sparse network graph using Dijkstra's algorithm with buckets (Dial's algorithm)
        - This is particularly efficient for graphs where most edge weights are >= 1 and the maximum edge weight is small
        - This implementation safely supports non-integer weights
        - Return a dictionary of various path information including:
            - `path`: A list of node ids in the order they are visited
            - `length`: The length of the path from the origin node to the destination node

        Required Arguments:

        - `origin_id`
            - Type: int | set[int]
            - What: The id(s) of the origin node(s) from the graph dictionary to start the shortest path from
        - `destination_id`
            - Type: int
            - What: The id of the destination node from the graph dictionary to end the shortest path at

        Optional Arguments:

        - `max_edge_weight`
            - Type: int | float | None
            - What: The maximum edge weight in the graph. If None, it will be calculated.
            - Default: None
        """
        # Input Validation
        self.__input_check__(origin_id=origin_id, destination_id=destination_id)
        origin_ids = {origin_id} if isinstance(origin_id, int) else origin_id

        if max_edge_weight is None:
            max_edge_weight = 0
            for node_edges in self.graph:
                if node_edges:
                    m = max(node_edges.values())
                    if m > max_edge_weight:
                        max_edge_weight = m
        max_edge_weight = math.ceil(max_edge_weight)

        # Variable Initialization
        distance_matrix = [float("inf")] * len(self.graph)
        predecessor = [-1] * len(self.graph)
        num_buckets = max_edge_weight + 1
        buckets = [[] for _ in range(num_buckets)]

        for oid in origin_ids:
            distance_matrix[oid] = 0
            buckets[0].append(oid)

        current_dist = 0
        nodes_in_buckets = len(origin_ids)

        while nodes_in_buckets > 0:
            bucket_idx = current_dist % num_buckets
            while not buckets[bucket_idx]:
                current_dist += 1
                bucket_idx = current_dist % num_buckets
                if nodes_in_buckets == 0:
                    break
                # If we've already found a path shorter than the current bucket minimum, we can exit
                if distance_matrix[destination_id] < current_dist:
                    break

            if (
                nodes_in_buckets == 0
                or distance_matrix[destination_id] < current_dist
            ):
                break

            current_id = buckets[bucket_idx].pop()
            nodes_in_buckets -= 1

            # Skip if we found a better path already (lazy removal)
            if distance_matrix[current_id] < current_dist:
                continue

            # Note: We do not break immediately if current_id == destination_id
            # because weights < 1 might allow a shorter path to be found within the same bucket.
            # The loop terminates when current_dist > distance_matrix[destination_id].

            for connected_id, connected_distance in self.graph[
                current_id
            ].items():
                possible_distance = (
                    distance_matrix[current_id] + connected_distance
                )
                if possible_distance < distance_matrix[connected_id]:
                    distance_matrix[connected_id] = possible_distance
                    predecessor[connected_id] = current_id
                    buckets[int(possible_distance) % num_buckets].append(
                        connected_id
                    )
                    nodes_in_buckets += 1

        if distance_matrix[destination_id] == float("inf"):
            raise Exception(
                "Something went wrong, the origin and destination nodes are not connected."
            )

        return {
            "path": self.__reconstruct_path__(destination_id, predecessor),
            "length": distance_matrix[destination_id],
        }

    def dijkstra_negative(
        self,
        origin_id: int | set[int],
        destination_id: int,
        cycle_check_iterations: int | None = None,
    ) -> dict:
        """
        Function:

        - Identify the shortest path between two nodes in a sparse network graph using a modified Dijkstra algorithm that catches negative cycles
            - Negative cycles raise an exception if they are detected
        - Note: This algorithm is guaranteed to find the shortest path or raise an exception if a negative cycle is detected
        - Note: This algorithm requires computing the entire shortest path tree of the graph and is therefore not able to be terminated early
            - For non negative weighted graphs, it is recommended to use the `dijkstra` algorithm instead
        - Note: This should be fairly performant in general, however it does have a higher worst-case time complexity than Bellman-Ford

        - Return a dictionary of various path information including:
            - `id_path`: A list of node ids in the order they are visited
            - `path`: A list of node dictionaries (lat + long) in the order they are visited

        Required Arguments:

        - `origin_id`
            - Type: int | set[int]
            - What: The id(s) of the origin node(s) from the graph dictionary to start the shortest path from
        - `destination_id`
            - Type: int
            - What: The id of the destination node from the graph dictionary to end the shortest path at

        Optional Arguments:

        - `cycle_check_iterations`
            - Type: int | None
            - What: The number of iterations to loop over before checking for negative cycles
            - Default: None (Then set to the number of nodes in the graph)
        """
        # Input Validation
        self.__input_check__(origin_id=origin_id, destination_id=destination_id)
        origin_ids = {origin_id} if isinstance(origin_id, int) else origin_id

        # Variable Initialization
        distance_matrix = [float("inf")] * len(self.graph)
        predecessor = [-1] * len(self.graph)
        open_leaves = []

        for oid in origin_ids:
            distance_matrix[oid] = 0
            heappush(open_leaves, (0, oid))

        # Cycle iteration Variables
        cycle_iteration = 0
        if cycle_check_iterations is None:
            cycle_check_iterations = len(self.graph)

        while open_leaves:
            current_distance, current_id = heappop(open_leaves)
            if current_distance == distance_matrix[current_id]:
                # Increment the cycle iteration counter and check for negative cycles if the iteration limit is reached
                cycle_iteration += 1
                if cycle_iteration >= cycle_check_iterations:
                    cycle_iteration = 0  # Reset the cycle iteration counter
                    self.__cycle_check__(
                        predecessor_matrix=predecessor, node_id=current_id
                    )
                for connected_id, connected_distance in self.graph[
                    current_id
                ].items():
                    possible_distance = current_distance + connected_distance
                    if possible_distance < distance_matrix[connected_id]:
                        distance_matrix[connected_id] = possible_distance
                        predecessor[connected_id] = current_id
                        heappush(open_leaves, (possible_distance, connected_id))

        if distance_matrix[destination_id] == float("inf"):
            raise Exception(
                "Something went wrong, the origin and destination nodes are not connected."
            )

        return {
            "path": self.__reconstruct_path__(destination_id, predecessor),
            "length": distance_matrix[destination_id],
        }

    def a_star(
        self,
        origin_id: int | set[int],
        destination_id: int,
        heuristic_fn: callable = None,
    ) -> dict:
        """
        Function:

        - Identify the shortest path between two nodes in a sparse network graph using an A* extension of Makowski's modified Dijkstra algorithm
        - Return a dictionary of various path information including:
            - `id_path`: A list of node ids in the order they are visited
            - `path`: A list of node dictionaries (lat + long) in the order they are visited

        Required Arguments:

        - `origin_id`
            - Type: int | set[int]
            - What: The id of the origin node from the graph dictionary to start the shortest path from
        - `destination_id`
            - Type: int
            - What: The id of the destination node from the graph dictionary to end the shortest path at
        - `heuristic_fn`
            - Type: function
            - What: A heuristic function that takes two node ids and returns an estimated distance between them
            - Note: If None, returns the shortest path using Dijkstra's algorithm
            - Default: None

        Optional Arguments:

        - None
        """
        if heuristic_fn is None:
            return self.dijkstra(
                origin_id=origin_id,
                destination_id=destination_id,
            )
        # Input Validation
        self.__input_check__(origin_id=origin_id, destination_id=destination_id)
        origin_ids = {origin_id} if isinstance(origin_id, int) else origin_id

        # Variable Initialization
        distance_matrix = [float("inf")] * len(self.graph)
        # Using a visited matrix does add a tad bit of overhead but avoids revisiting nodes
        # and does not require anything extra to be stored in the heap
        visited = [0] * len(self.graph)
        open_leaves = []
        predecessor = [-1] * len(self.graph)

        for oid in origin_ids:
            distance_matrix[oid] = 0
            heappush(open_leaves, (0, oid))

        while open_leaves:
            current_id = heappop(open_leaves)[1]
            if current_id == destination_id:
                break
            if visited[current_id] == 1:
                continue
            visited[current_id] = 1
            current_distance = distance_matrix[current_id]
            for connected_id, connected_distance in self.graph[
                current_id
            ].items():
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

        return {
            "path": self.__reconstruct_path__(destination_id, predecessor),
            "length": distance_matrix[destination_id],
        }

    def bellman_ford(
        self,
        origin_id: int | set[int],
        destination_id: int,
    ) -> dict:
        """
        Function:

        - Identify the shortest path between two nodes in a sparse network graph using the Bellman-Ford algorithm
        - Return a dictionary of various path information including:
            - `id_path`: A list of node ids in the order they are visited
            - `path`: A list of node dictionaries (lat + long) in the order they are visited

        Required Arguments:

        - `origin_id`
            - Type: int | set[int]
            - What: The id(s) of the origin node(s) from the graph dictionary to start the shortest path from
        - `destination_id`
            - Type: int
            - What: The id of the destination node from the graph dictionary to end the shortest path at

        Optional Arguments:

        - None
        """
        # Input Validation
        self.__input_check__(origin_id=origin_id, destination_id=destination_id)
        origin_ids = {origin_id} if isinstance(origin_id, int) else origin_id
        # Variable Initialization
        distance_matrix = [float("inf")] * len(self.graph)
        predecessor = [-1] * len(self.graph)

        for oid in origin_ids:
            distance_matrix[oid] = 0

        len_graph = len(self.graph)
        for i in range(len_graph):
            for current_id in range(len(self.graph)):
                current_distance = distance_matrix[current_id]
                for connected_id, connected_distance in self.graph[
                    current_id
                ].items():
                    possible_distance = current_distance + connected_distance
                    if possible_distance < distance_matrix[connected_id]:
                        distance_matrix[connected_id] = possible_distance
                        predecessor[connected_id] = current_id
                        if i == len_graph - 1:
                            raise Exception(
                                "Graph contains a negative weight cycle"
                            )
        # Check if destination is reachable
        if distance_matrix[destination_id] == float("inf"):
            raise Exception(
                "Something went wrong, the origin and destination nodes are not connected."
            )

        return {
            "path": self.__reconstruct_path__(destination_id, predecessor),
            "length": distance_matrix[destination_id],
        }

    def bmssp(
        self,
        origin_id: int | set[int],
        destination_id: int,
        use_constant_degree_graph: bool = True,
    ):
        """
        Function:

        - Identify the shortest path between two nodes in a sparse network graph using the BMSSPy package

        - This is now a wrapper for the BMSSPy package
            - https://github.com/connor-makowski/bmsspy
            - For backwards compatibility, this function wraps around the dijkstra function if BMSSPy is not installed

        - Return a dictionary of various path information including:
            - `id_path`: A list of node ids in the order they are visited
            - `path`: A list of node dictionaries (lat + long) in the order they are visited

        Required Arguments:

        - `origin_id`
            - Type: int | set[int]
            - What: The id(s) of the origin node(s) from the graph dictionary to start the shortest path from
        - `destination_id`
            - Type: int
            - What: The id of the destination node from the graph dictionary to end the shortest path at
        - `use_constant_degree_graph`
            - Type: bool
            - What: Whether to convert the graph to a constant degree 2 graph prior to running the BMSSPy algorithm
            - Default: True


        Optional Arguments:

        - None
        """
        bmssp_graph = Bmssp(
            graph=self.graph,
            use_constant_degree_graph=use_constant_degree_graph,
        )
        output = bmssp_graph.solve(
            origin_id=origin_id, destination_id=destination_id
        )
        return {
            "path": output["path"],
            "length": output["length"],
        }

    def cached_shortest_path(
        self,
        origin_id: int,
        destination_id: int,
        length_only: bool = False,
    ):
        """
        Function:

        - Get the shortest path between two nodes in the graph attempting to use a cached shortest path tree if available
        - If a cached shortest path tree is not available, it will compute the shortest path tree and cache it for future use if specified by `cache`
        - Uses the get_shortest_path_tree (Dijkstra) and get_tree_path functions internally
        - Stores cached shortest path trees in a list (self.__cache__) where the index corresponds to the origin node id
        - Note: If you modify this graph after caching shortest path trees, the cached trees may become invalid
            - You can reset the cache by calling self.reset_cache()
            - For efficiency, the cache is not automatically reset when the graph is modified
            - This logic must be handled by the user

        Requires:

        - origin_id: The id of the origin node
        - destination_id: The id of the destination node

        Optional:

        - length_only: If True, only returns the length of the path
        """
        shortest_path_tree = self.__cache__[origin_id]
        if shortest_path_tree == 0:
            shortest_path_tree = self.get_shortest_path_tree(
                origin_id=origin_id
            )
            self.__cache__[origin_id] = shortest_path_tree
        return self.get_tree_path(
            origin_id=origin_id,
            destination_id=destination_id,
            tree_data=shortest_path_tree,
            length_only=length_only,
        )

    def create_contraction_hierarchy(
        self, heuristic_fn=None, ch_graph_kwargs=None
    ) -> Any:
        """
        Function:

        - Create a Contraction Hierarchies (CH) graph from the current Graph object
        - The CH graph is stored as an instance variable `self.ch_graph`

        Optional Arguments:

        - `heuristic_fn`:
            - Type: function or None
            - What: A heuristic function for CH preprocessing
            - Default: None (uses default heuristic)
        """
        if not hasattr(self, "__ch_graph__"):
            ch_graph_kwargs = (
                ch_graph_kwargs if ch_graph_kwargs is not None else dict()
            )
            self.__ch_graph__ = CHGraph(
                graph=self.graph, heuristic_fn=heuristic_fn, **ch_graph_kwargs
            )

    def contraction_hierarchy(
        self, origin_id: int, destination_id: int, length_only: bool = False
    ) -> dict[str, Any]:
        """
        Function:

        - Get the shortest path between two nodes using the Contraction Hierarchies (CH) graph
        - Creates the CH graph if it doesn't exist

        Requires:

        - origin_id: The id of the origin node
        - destination_id: The id of the destination node

        Optional:

        - length_only: If True, only returns the length of the path (not implemented yet)

        Returns:

        - A dictionary with 'path' and 'length' keys containing the shortest path and its length
        """
        # Ensure that the CH graph is created and warmed up
        self.create_contraction_hierarchy()
        return self.__ch_graph__.search(origin_id, destination_id)


class Graph(GraphUtils, GraphModifiers, GraphTrees, GraphAlgorithms):
    def __init__(self, graph: list[dict[int, int | float]], validate=False):
        """
        Function:

        - Initialize a Graph object
        - Validate the input graph

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

        - `validate`:
            - Type: bool
            - What: Whether to validate the input graph upon initialization
            - Default: False
        """
        self.graph = graph
        self.reset_cache()
        if validate:
            self.validate()
