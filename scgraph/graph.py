from heapq import heappop, heappush
from typing import Literal

try:
    from bmsspy import Bmssp
except ImportError:
    Bmssp = None

class GraphUtils:
    def __input_check__(
        self,
        origin_id: int | set[int],
        destination_id: int,
    ) -> None:
        """
        Function:

        - Check that the inputs passed to the shortest path algorithm are valid
        - Raises an exception if the inputs passed are not valid

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
        origin_ids = {origin_id} if isinstance(origin_id, int) else origin_id
        assert isinstance(
            origin_ids, set
        ), "origin_id must be an integer or a set of integers"

        for oid in origin_ids:
            if not isinstance(oid, int) and oid < len(self.graph) and oid >= 0:
                raise Exception(f"Origin node ({oid}) is not in this graph")
        if (
            not isinstance(destination_id, int)
            and origin_id < len(self.graph)
            and origin_id >= 0
        ):
            raise Exception(
                f"Destination node ({destination_id}) is not in this graph"
            )

    def __reconstruct_path__(
        self,
        destination_id: int, 
        predecessor: list[int]
    ) -> list[int]:
        """
        Function:

        - Reconstruct the shortest path from the destination node to the origin node
        - Return the reconstructed path in the correct order
        - Given the predecessor list, this function reconstructs the path

        Required Arguments:

        - `destination_id`
            - Type: int
            - What: The id of the destination node from the graph dictionary to end the shortest path at
        - `predecessor`
            - Type: list[int]
            - What: The predecessor list that was used to compute the shortest path
            - This list is used to reconstruct the path from the destination node to the origin node
            - Note: Nodes with no predecessor should be -1

        Optional Arguments:

        - None
        """
        output_path = [destination_id]
        while predecessor[destination_id] != -1:
            destination_id = predecessor[destination_id]
            output_path.append(destination_id)
        output_path.reverse()
        return output_path

    def __cycle_check__(self, predecessor_matrix, node_id):
        """
        Function:

        - Check if a cycle exists in the predecessor matrix starting from the given node_id
        - Returns None if no cycle is detected
        - Raises an Exception if a cycle is detected

        Required Arguments:

        - `predecessor_matrix`:
            - Type: list[int]
            - What: A list where the index represents the node id and the value at that index is the predecessor node id
        - `node_id`:
            - Type: int
            - What: The node id to start checking for cycles from

        Optional Arguments:

        - None
        """
        cycle_id = node_id
        while True:
            cycle_id = predecessor_matrix[cycle_id]
            if cycle_id == -1:
                return
            if cycle_id == node_id:
                raise Exception(
                    f"Cycle detected in the graph at node {node_id}"
                )
            
    def __ensure_inverse_graph__(self) -> list[dict[int, int | float]]:
        """
        Function:

        - Ensure the inverse of the graph as self.inverse_graph is computed and stored
            - The inverse of the graph is a graph where all edges are reversed
            - This is useful for checking the connectivity of the graph and for algorithms that require the inverse graph
        """
        if not hasattr(self, "inverse_graph"):
            self.inverse_graph = [dict() for _ in range(len(self.graph))]
            for origin_id, origin_dict in enumerate(self.graph):
                for destination_id, distance in origin_dict.items():
                    self.inverse_graph[destination_id][origin_id] = distance

    def __connected_check__(
        self,
        origin_id: int = 0
    ) -> bool:
        """
        Function:

        - Return True if this graph is fully connected and False if it is not

        Optional Arguments:

        - `origin_id`
            - Type: int
            - What: The id of the origin node from which to start the connectivity check
            - Default: 0
        """
        self.__ensure_inverse_graph__()

        visited = [0] * len(self.graph)
        open_leaves = [origin_id]

        while open_leaves:
            current_id = open_leaves.pop()
            visited[current_id] = 1
            for connected_id in self.graph[current_id]:
                if visited[connected_id] == 0:
                    open_leaves.append(connected_id)
        
        inverse_visited = [0] * len(self.inverse_graph)
        inverse_open_leaves = [origin_id]
        while inverse_open_leaves:
            current_id = inverse_open_leaves.pop()
            inverse_visited[current_id] = 1
            for connected_id in self.inverse_graph[current_id]:
                if inverse_visited[connected_id] == 0:
                    inverse_open_leaves.append(connected_id)

        return min(visited) == 1 and min(inverse_visited) == 1
    
    def __symmetric_check__(self) -> bool:
        """
        Function:

        - Return True if this graph is symmetric and False if it is not
            - A graph is symmetric if for every edge from node A to node B, there is an edge from node B to node A with the same distance
        """
        for origin_id, origin_dict in enumerate(self.graph):
            for destination_id, distance in origin_dict.items():
                if distance != self.graph[destination_id].get(origin_id, None):
                    return False
        return True

    def validate(
        self,
        check_symmetry: bool = True,
        check_connected: bool = True,
    ) -> None:
        """
        Function:

        - Validate that this graph object is properly formatted

        Optional Arguments:

        - `check_symmetry`
            - Type: bool
            - What: Whether to check that the graph is symmetric
            - Default: True
        - `check_connected`
            - Type: bool
            - What: Whether to check that the graph is fully connected
            - Default: True
        """
        assert isinstance(self.graph, list), "Your graph must be a list"
        len_graph = len(self.graph)
        if len_graph == 0:
            raise Exception("The provided graph must contain at least one node")
        for origin_id, origin_dict in enumerate(self.graph):
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
            assert self.__symmetric_check__(), "The provided graph is not symmetric"
        if check_connected:
            assert self.__connected_check__(), "The provided graph is not fully connected"

    def reset_cache(self) -> None:
        """
        Function:

        - Reset the cached shortest path trees
            - This is useful if the graph has been modified and the cached shortest path trees are no longer valid
        """
        self.__cache__ = [0] * len(self.graph)

    def get_cache(self) -> list[dict | None]:
        """
        Function:

        - Get the cached shortest path trees
            - This is useful for saving the cache to disk or for inspecting the cache

        Returns:

        - A list of cached shortest path trees, where each tree is represented as a dictionary
            - If a tree is not cached for a specific node, the corresponding entry in the list will be 0
        """
        return self.__cache__
    
    def set_cache(self, new_cache: list[dict | Literal[0]]) -> None:
        """
        Function:

        - Set the cached shortest path trees
            - This is useful for loading a cache from disk or for manually setting the cache

        Required Arguments:

        - `new_cache`:
            - Type: list[dict | None]
            - What: A list of cached shortest path trees, where each tree is represented as a dictionary
                - If a tree is not cached for a specific node, the corresponding entry in the list should be 0
        """
        assert isinstance(new_cache, list), "Cache must be a list"
        assert len(new_cache) == len(self.graph), "Cache must be the same length as the graph"
        self.__cache__ = new_cache

    def __get__(self, idx: int) -> dict[int, int | float]:
        """
        Function:

        - Get the adjacency dictionary for a specific node in the graph

        Required Arguments:

        - `idx`:
            - Type: int
            - What: The id of the node to get the adjacency dictionary for
        
        Returns:
        
        - The adjacency dictionary for the specified node
        """
        return self.graph[idx]


class GraphModifiers:
    def add_node(self, node_dict: dict[int, int | float]=None, symmetric: bool = False) -> int:
        """
        Function:

        - Add a node to the graph

        Optional Arguments:

        - `node_dict`:
            - Type: dict[int, int | float]
            - What: Arcs leaving this node.
                - A dictionary where the keys are destination node ids and the values are the distances to those nodes
            - Default: An empty dictionary
        - `symmetric`:
            - Type: bool
            - What: Whether to add edges symmetrically (i.e., add edges from the new node to existing nodes and from existing nodes to the new node)
            - Default: False

        Returns:

        - The id of the newly added node
        """
        node_dict = node_dict if node_dict is not None else dict()
        self.graph.append(node_dict)
        new_node_id = len(self.graph) - 1
        if symmetric:
            for dest_id, distance in node_dict.items():
                self.graph[dest_id][new_node_id] = distance
        return new_node_id
    
    def add_edge(self, origin_id: int, destination_id: int, distance: int | float, symmetric: bool = False) -> None:
        """
        Function:

        - Add an edge to the graph

        Required Arguments:

        - `origin_id`:
            - Type: int
            - What: The id of the origin node
        - `destination_id`:
            - Type: int
            - What: The id of the destination node
        - `distance`:
            - Type: int | float
            - What: The distance between the origin and destination nodes
        - `symmetric`:
            - Type: bool
            - What: Whether to add the edge symmetrically (i.e., add an edge from destination to origin as well)
            - Default: False
        """
        assert origin_id < len(self.graph), "Origin node id is not in the graph"
        assert destination_id < len(self.graph), "Destination node id is not in the graph"
        self.graph[origin_id][destination_id] = distance
        if symmetric:
            self.graph[destination_id][origin_id] = distance

    def remove_node(self, symmetric_node: bool = False) -> dict[int, int | float]:
        """
        Function:

        - Removes the last node from the graph

        Optional Arguments:

        - `symmetric_node`:
            - Type: bool
            - What: Whether the node being removed has symmetric edges 
                - Specifically: This should be True only if all inbound edges to this node are also outbound edges from this node
            - Default: False
            - If True, only uses outbound edges from this node to identify inbound edges to remove from other nodes.

        Returns:

        - The dictionary of edges for this node that were removed from the graph
        """
        assert len(self.graph) > 0, "Graph is empty, cannot remove node"
        node_id = len(self.graph) - 1
        if symmetric_node:
            for dest_id in self.graph[node_id].keys():
                self.graph[dest_id].pop(node_id, None)
        else:
            for origin_dict in self.graph:
                if node_id in origin_dict:
                    origin_dict.pop(node_id)
        return self.graph.pop()

    def remove_edge(self, origin_id: int, destination_id: int, symmetric: bool = False) -> int | float | None:
        """
        Function:

        - Remove an edge from the graph

        Required Arguments:

        - `origin_id`:
            - Type: int
            - What: The id of the origin node
        - `destination_id`:
            - Type: int
            - What: The id of the destination node
        - `symmetric`:
            - Type: bool
            - What: Whether to remove the edge symmetrically (i.e., remove the edge from destination to origin as well)
            - Default: False

        Returns:

        - The distance of the removed edge from origin to destination, or None if the edge did not exist
        """
        assert origin_id < len(self.graph), "Origin node id is not in the graph"
        assert destination_id < len(self.graph), "Destination node id is not in the graph"
        if symmetric:
            self.graph[destination_id].pop(origin_id, None)
        return self.graph[origin_id].pop(destination_id, None)


class GraphTrees:
    def get_shortest_path_tree(
        self,
        origin_id: int | set[int]
    ) -> dict:
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
            for connected_id, connected_distance in self.graph[current_id].items():
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
        self.__input_check__(
            origin_id=origin_id, destination_id=destination_id
        )
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
        self.__input_check__(
            origin_id=origin_id, destination_id=destination_id
        )
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
        self.__input_check__(
            origin_id=origin_id, destination_id=destination_id
        )
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
            for connected_id, connected_distance in self.graph[current_id].items():
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
        self.__input_check__(
            origin_id=origin_id, destination_id=destination_id
        )
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
        constant_degree_graph: bool = True,
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
        - `constant_degree_graph`
            - Type: bool
            - What: Whether to convert the graph to a constant degree 2 graph prior to running the BMSSPy algorithm
            - Default: True


        Optional Arguments:

        - None
        """
        if Bmssp is None:
            print(
                "Warning: BMSSPy is not installed, falling back to dijkstra algorithm. To use the BMSSPy algorithm, please install the BMSSPy package."
            )
            return self.dijkstra(
                origin_id=origin_id,
                destination_id=destination_id,
            )
        else:
            bmssp_graph = Bmssp(
                graph=self.graph, use_constant_degree_graph=constant_degree_graph
            )
            output = bmssp_graph.solve(
                origin_id=origin_id, destination_id=destination_id
            )
            return {
                "path": output["path"],
                "length": output["length"],
            }

    def get_set_cached_shortest_path(
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
            shortest_path_tree = self.get_shortest_path_tree(origin_id=origin_id)
            self.__cache__[origin_id] = shortest_path_tree
        return self.get_tree_path(
            origin_id=origin_id,
            destination_id=destination_id,
            tree_data=shortest_path_tree,
            length_only=length_only,
        )


class Graph(GraphUtils, GraphModifiers, GraphTrees, GraphAlgorithms):
    def __init__(self, graph: list[dict[int, int | float]], validate = False):
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


try:
    from scgraph.cpp import Graph
    # TODO: Find way to notify users if they can use the C++ Implementation.
    # print("C++ Graph module found, using C++ implementation.")
except ImportError:
    # print("C++ Graph module not found, using Python implementation.")
    pass