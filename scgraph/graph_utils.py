from typing import Literal


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
        self, destination_id: int, predecessor: list[int]
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

    def __connected_check__(self, origin_id: int = 0) -> bool:
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
            assert (
                self.__symmetric_check__()
            ), "The provided graph is not symmetric"
        if check_connected:
            assert (
                self.__connected_check__()
            ), "The provided graph is not fully connected"

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
        assert len(new_cache) == len(
            self.graph
        ), "Cache must be the same length as the graph"
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
    def add_node(
        self, node_dict: dict[int, int | float] = None, symmetric: bool = False
    ) -> int:
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

    def add_edge(
        self,
        origin_id: int,
        destination_id: int,
        distance: int | float,
        symmetric: bool = False,
    ) -> None:
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
        assert destination_id < len(
            self.graph
        ), "Destination node id is not in the graph"
        self.graph[origin_id][destination_id] = distance
        if symmetric:
            self.graph[destination_id][origin_id] = distance

    def remove_node(
        self, symmetric_node: bool = False
    ) -> dict[int, int | float]:
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

    def remove_edge(
        self, origin_id: int, destination_id: int, symmetric: bool = False
    ) -> int | float | None:
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
        assert destination_id < len(
            self.graph
        ), "Destination node id is not in the graph"
        if symmetric:
            self.graph[destination_id].pop(origin_id, None)
        return self.graph[origin_id].pop(destination_id, None)
