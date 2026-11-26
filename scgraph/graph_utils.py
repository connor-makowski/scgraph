"""Helpers shared by `Graph`, `CHGraph` and `TNRGraph`.

`GraphUtils` holds the graph and its inverse, checks the inputs of a search, rebuilds a
path from its predecessors, validates a graph and keeps the cache of shortest path
trees. `GraphModifiers` adds and removes nodes and edges (`add_node`, `add_edge`,
`remove_node`, `remove_edge`). `normalize_node_input` turns an origin or a destination
into a dict of node ids and distances.
"""

import threading
from array import array
from typing import Literal
import math
import operator

from scgraph.errors import NegativeCycleError

# The number of node scans of the last search in each thread (see Graph._get_last_node_scans).
# None means that no search counted its node scans since the last reset.
_last_search_in_thread = threading.local()


def normalize_node_input(
    node_input: int | set[int] | dict[int, int | float],
) -> dict[int, float]:
    if isinstance(node_input, int):
        return {node_input: 0.0}
    elif isinstance(node_input, set):
        return {oid: 0.0 for oid in node_input}
    elif isinstance(node_input, dict):
        return {oid: float(dist) for oid, dist in node_input.items()}
    raise ValueError(
        "node_input must be an int, set of ints, or dict mapping int to float"
    )


def _as_plain_node_input(node_input: object) -> object:
    """Return an origin or a destination whose node ids are of type `int`.

    The C++ extension takes any integer with `__index__` as a node id, such as a numpy
    integer, and a `frozenset` as a set. In pure Python, this function turns such a
    node id into an `int`, and a `frozenset` into a `set`. It returns another value
    unchanged, so that `__input_check__` refuses it.
    """

    def _as_int(node_id):
        try:
            return operator.index(node_id)
        except TypeError:
            return node_id

    if isinstance(node_input, (set, frozenset)):
        return {_as_int(node_id) for node_id in node_input}
    if isinstance(node_input, dict):
        return {_as_int(node_id): dist for node_id, dist in node_input.items()}
    return _as_int(node_input)


class GraphUtils:
    @property
    def graph(self) -> list[dict[int, int | float]]:
        """The graph as given (or as modified), also after `reduce()`."""
        return getattr(self, "__graph__", None)

    @graph.setter
    def graph(self, value: list[dict[int, int | float]]) -> None:
        self.__graph__ = value

    @property
    def unreduced_graph(self) -> list[dict[int, int | float]]:
        """Same as `graph`."""
        return self.graph

    def _get_edge_arrays(
        self, order: list[int] | None = None
    ) -> tuple[array, array, array]:
        """The graph (unreduced) as edges by origin: int32 node_first_edge_ids and edge_destination_node_ids, float64
        weights, in the order in which searches visit the edges (the C++ backend gives
        views of its own arrays). The id of an edge is its position in these arrays.
        With `order` (order[new] = old), the rows of the nodes in that order, their
        edge_destination_node_ids renumbered. `Graph.from_edge_arrays` builds a graph from the three
        arrays. `GeoGraph` calls this method.
        """
        rows, new_id = self.graph, None
        if order is not None:
            new_id = array("i", [-1]) * len(rows)
            if len(order) != len(rows):
                raise IndexError("order must list every node once")
            for new, old in enumerate(order):
                if not 0 <= old < len(rows) or new_id[old] != -1:
                    raise IndexError("order must list every node once")
                new_id[old] = new
            rows = map(rows.__getitem__, order)
        node_first_edge_ids, edge_destination_node_ids, weights = (
            array("i", [0]),
            array("i"),
            array("d"),
        )
        for row in rows:
            edge_destination_node_ids.extend(
                row if new_id is None else map(new_id.__getitem__, row)
            )
            weights.extend(row.values())
            node_first_edge_ids.append(len(edge_destination_node_ids))
        return node_first_edge_ids, edge_destination_node_ids, weights

    @property
    def inverse_graph(self) -> list[dict[int, int | float]]:
        """The inverse of `graph`: every edge reversed."""
        self.__ensure_inverse_graph__()
        return self.__inverse_graph__

    @inverse_graph.setter
    def inverse_graph(self, value: list[dict[int, int | float]] | None) -> None:
        self.__inverse_graph__ = value

    @property
    def search_graph(self) -> list[dict[int, int | float]]:
        """The graph searched by the algorithms: `reduced_graph` after `reduce()`, else
        `graph`."""
        if getattr(self, "reduced_graph", None) is not None:
            return self.reduced_graph
        return self.graph

    @property
    def search_inverse_graph(self) -> list[dict[int, int | float]]:
        """The inverse searched by the bidirectional algorithms: `reduced_inverse_graph`
        after `reduce()`, else `inverse_graph`."""
        if getattr(self, "reduced_inverse_graph", None) is not None:
            return self.reduced_inverse_graph
        return self.inverse_graph

    def __input_check__(
        self,
        origin_id: int | set[int] | dict[int, int | float],
        destination_id: int | set[int] | dict[int, int | float],
    ) -> None:
        """
        Function:

        - Check that the inputs passed to the shortest path algorithm are valid
        - Raises an exception if the inputs passed are not valid

        Required Arguments:

        - `origin_id`
            - Type: int | set[int] | dict[int, int | float]
            - What: The id(s) of the origin node(s) (with optional starting distances) from the graph dictionary to start the shortest path from
        - `destination_id`
            - Type: int | set[int] | dict[int, int | float]
            - What: The id(s) of the destination node(s) (with optional exit distances) from the graph dictionary to end the shortest path at

        Optional Arguments:

        - None
        """
        num_nodes = len(self.graph)

        # A node id of the wrong type raises TypeError, as the C++ extension
        # does. A node id out of range raises ValueError.
        def _validate_node_id(node_id, name):
            if not isinstance(node_id, int):
                raise TypeError(f"{name} node ({node_id!r}) is not an integer")
            if not (0 <= node_id < num_nodes):
                raise ValueError(
                    f"{name} node ({node_id}) is not in this graph"
                )

        def _validate_node_arg(arg, name):
            if isinstance(arg, int):
                _validate_node_id(arg, name)
            elif isinstance(arg, set):
                if len(arg) == 0:
                    raise ValueError(f"{name} set cannot be empty")
                for oid in arg:
                    _validate_node_id(oid, name)
            elif isinstance(arg, dict):
                if len(arg) == 0:
                    raise ValueError(f"{name} dictionary cannot be empty")
                for oid, dist in arg.items():
                    _validate_node_id(oid, name)
                    # A number is a value with `__float__`, as the C++ extension
                    # takes it: an int, a float, a Decimal, a numpy number.
                    if not hasattr(dist, "__float__"):
                        raise TypeError(
                            f"{name} distance for node ({oid}) must be a number, not {dist!r}"
                        )
                    # A NaN distance fails this test too.
                    if not dist >= 0:
                        raise ValueError(
                            f"{name} distance for node ({oid}) must be a non-negative number"
                        )
            else:
                raise TypeError(
                    f"{name} must be an integer, a set of integers, or a dict mapping node integers to distances"
                )

        _validate_node_arg(origin_id, "Origin")
        _validate_node_arg(destination_id, "Destination")

    def get_path_weight(self, path: list[int]) -> int | float:
        """
        Function:

        - Sum the graph weights along a sequence of node ids

        Required Arguments:

        - `path`
            - Type: list[int]
            - What: An ordered list of node ids representing a path through the graph

        Returns:

        - The total weight of the path as an int or float
        """
        total = 0
        for origin, destination in zip(path, path[1:]):
            try:
                total += self.__graph__[origin][destination]
            except KeyError:
                raise ValueError(
                    f"No edge from node {origin} to node {destination}"
                ) from None
        return total

    @staticmethod
    def __reconstruct_path__(
        destination_id: int, predecessor: list[int]
    ) -> list[int]:
        """
        Function:

        - Reconstruct the path from the origin node to the destination node using the predecessor matrix
        - Returns a list of node ids in the order they are visited

        Required Arguments:

        - `destination_id`:
            - Type: int
            - What: The id of the destination node from the graph dictionary to end the shortest path at
        - `predecessor`:
            - Type: list[int]
            - What: A list where the index represents the node id and the value at that index is the predecessor node id

        Optional Arguments:

        - None
        """
        current_id = destination_id
        path = [destination_id]
        while predecessor[current_id] != -1:
            current_id = predecessor[current_id]
            path.append(current_id)
        path.reverse()
        return path

    def __check_predecessor_loop__(
        self, predecessor_matrix: list[int], node_id: int
    ) -> None:
        """
        Function:

        - Check if a cycle exists in the predecessor matrix starting from the given node_id
        - Returns None if no cycle is detected
        - Raises a NegativeCycleError if a cycle is detected. The predecessors of a search form a cycle only when the graph has a cycle of negative weight

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
                raise NegativeCycleError(
                    f"Cycle detected in the graph at node {node_id}"
                )

    def __ensure_inverse_graph__(self) -> None:
        """
        Function:

        - Ensure the inverse of the graph as self.__inverse_graph__ is computed and stored
            - The inverse of the graph is a graph where all edges are reversed
            - This is useful for checking the connectivity of the graph and for algorithms that require the inverse graph
        """
        if getattr(self, "__inverse_graph__", None) is None:
            self.__inverse_graph__ = [
                dict() for _ in range(len(self.__graph__))
            ]
            for origin_id, origin_dict in enumerate(self.__graph__):
                for destination_id, distance in origin_dict.items():
                    self.__inverse_graph__[destination_id][origin_id] = distance

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

        graph = self.__graph__
        inverse_graph = self.__inverse_graph__

        visited = [0] * len(graph)
        open_leaves = [origin_id]

        while open_leaves:
            current_id = open_leaves.pop()
            visited[current_id] = 1
            for connected_id in graph[current_id]:
                if visited[connected_id] == 0:
                    open_leaves.append(connected_id)

        inverse_visited = [0] * len(inverse_graph)
        inverse_open_leaves = [origin_id]
        while inverse_open_leaves:
            current_id = inverse_open_leaves.pop()
            inverse_visited[current_id] = 1
            for connected_id in inverse_graph[current_id]:
                if inverse_visited[connected_id] == 0:
                    inverse_open_leaves.append(connected_id)

        return min(visited) == 1 and min(inverse_visited) == 1

    def __symmetric_check__(self) -> bool:
        """
        Function:

        - Return True if this graph is symmetric and False if it is not
            - A graph is symmetric if for every edge from node A to node B, there is an edge from node B to node A with the same distance
        """
        graph = self.__graph__
        for origin_id, origin_dict in enumerate(graph):
            for destination_id, distance in origin_dict.items():
                if distance != graph[destination_id].get(origin_id, None):
                    return False
        return True

    def __get_max_edge_weight__(
        self,
        max_edge_weight: float | None,
    ) -> int:
        """Infer and round up the maximum edge weight for bucket allocation. An infinite
        weight closes its edge, so the maximum is that of the finite weights."""
        if max_edge_weight is not None:
            return math.ceil(max_edge_weight)
        cached_max_edge_weight = getattr(self, "__max_edge_weight__", None)
        if cached_max_edge_weight is None:
            graph = self.search_graph
            max_edge_weight = max(
                0,
                max(
                    (
                        weight
                        for edges in graph
                        for weight in edges.values()
                        if math.isfinite(weight)
                    ),
                    default=0,
                ),
            )
            cached_max_edge_weight = math.ceil(max_edge_weight)
            self.__max_edge_weight__ = cached_max_edge_weight
        return cached_max_edge_weight

    def _get_bucket_width(
        self,
        bucket_width: float | None,
        max_edge_weight: int,
    ) -> float:
        """Width of the buckets of the bucket algorithms: the given width, else 8 times the
        median finite edge weight of the graph (1 if that median is 0), never so small that a
        bucket ring would exceed 2^16 + 1 buckets. Same rule as Graph::resolve_bucket_width
        (C++).
        """
        if bucket_width is not None:
            if not (math.isfinite(bucket_width) and bucket_width > 0):
                raise ValueError(
                    "bucket_width must be a finite number greater than 0."
                )
            width = float(bucket_width)
        else:
            width = getattr(self, "__bucket_width__", None)
            if width is None:
                weights = sorted(
                    w
                    for edges in self.search_graph
                    if edges
                    for w in edges.values()
                    if math.isfinite(w)
                )
                median = weights[len(weights) // 2] if weights else 0
                width = 8.0 * median if median > 0 else 1.0
                self.__bucket_width__ = width
        return max(width, max_edge_weight / 65536)

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

        Raises:

        - `TypeError`: The graph is not a list of dictionaries, a destination id is not an integer, or a distance is not a number
        - `ValueError`: The graph is empty, a destination id is not in the graph, a distance is negative or NaN, or the graph is not symmetric
        - `RuntimeError`: The graph is not fully connected
        """
        graph = self.__graph__
        if not isinstance(graph, list):
            raise TypeError("Your graph must be a list")
        len_graph = len(graph)
        if len_graph == 0:
            raise ValueError(
                "The provided graph must contain at least one node"
            )
        for origin_id, origin_dict in enumerate(graph):
            if not isinstance(origin_dict, dict):
                raise TypeError(
                    f"Your graph must be a list of dictionaries but the value for origin {origin_id} is not a dictionary"
                )
            destinations = list(origin_dict.keys())
            lengths = list(origin_dict.values())
            # A value of the wrong type raises TypeError, as the C++
            # extension does. A value out of range raises ValueError.
            if not all(
                [
                    (isinstance(i, int) and i >= 0 and i < len_graph)
                    for i in destinations
                ]
            ):
                if all([isinstance(i, int) for i in destinations]):
                    raise ValueError(
                        f"Destination ids must be existing indexes, but graph[{origin_id}] has a destination id that is not in the graph"
                    )
                raise TypeError(
                    f"Destination ids must be non-negative integers and equivalent to an existing index, but graph[{origin_id}] has an error in the destination ids"
                )
            if not all(
                [(isinstance(i, (int, float)) and i >= 0) for i in lengths]
            ):
                if all([isinstance(i, (int, float)) for i in lengths]):
                    raise ValueError(
                        f"Distances must be non-negative, but graph[{origin_id}] contains a negative or NaN distance"
                    )
                raise TypeError(
                    f"Distances must be integers or floats, but graph[{origin_id}] contains a non-integer or non-float distance"
                )

        if check_symmetry:
            if not self.__symmetric_check__():
                raise ValueError("The provided graph is not symmetric")
        if check_connected:
            if not self.__connected_check__():
                raise RuntimeError("The provided graph is not fully connected")

    def reset_cache(self) -> None:
        """
        Function:

        - Reset the cached shortest path trees
            - This is useful if the graph has been modified and the cached shortest path trees are no longer valid
        """
        self.__cache__ = [0] * len(self.__graph__)

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

        Raises:

        - `TypeError`: The cache is not a list
        - `ValueError`: The cache does not have one entry per node of the graph
        """
        if not isinstance(new_cache, list):
            raise TypeError("Cache must be a list")
        if len(new_cache) != len(self.__graph__):
            raise ValueError("Cache must be the same length as the graph")
        self.__cache__ = new_cache

    def get(self, idx: int) -> dict[int, int | float]:
        """
        Function:

        - Get the adjacency dictionary for a specific node in the graph

        Required Arguments:

        - `idx`:
            - Type: int
            - What: The id of the node to get the adjacency dictionary for

        Returns:

        - The adjacency dictionary for the specified node: the weight of each edge by the id of its destination node
        - Note: The pure-Python build returns the graph's own dictionary, with the weights as they were given; the C++ build returns a copy with float weights. Do not modify the result

        Raises:

        - IndexError if `idx` is not the id of a node of the graph
        """
        if not 0 <= idx < len(self.__graph__):
            raise IndexError("Index out of range")
        return self.__graph__[idx]


class GraphModifiers:
    @property
    def _edit_count(self) -> int:
        """The number of calls of `add_node`, `add_edge`, `remove_node` and
        `remove_edge` that changed the graph. A GeoGraph reads it to know that its
        graph was edited. An assignment into `graph` does not change it."""
        return getattr(self, "_edit_counter", 0)

    def add_node(
        self,
        node_dict: dict[int, int | float] | None = None,
        symmetric: bool = False,
    ) -> int:
        """
        Function:

        - Add a node to the graph

        Optional Arguments:

        - `node_dict`:
            - Type: dict[int, int | float]
            - What: Edges leaving this node.
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
        self.__graph__.append(node_dict)
        new_node_id = len(self.__graph__) - 1
        if symmetric:
            for dest_id, distance in node_dict.items():
                self.__graph__[dest_id][new_node_id] = distance
        self.__inverse_graph__ = None
        self._edit_counter = self._edit_count + 1
        self.reset_cache()
        return new_node_id

    def add_edge(
        self,
        origin_id: int,
        destination_id: int,
        distance: float,
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

        Raises:

        - `TypeError`: A node id is not an integer, or the distance is not a number
        - `IndexError`: The origin id or the destination id is not in the graph
        - `ValueError`: The distance is NaN
        """
        try:
            origin_id = operator.index(origin_id)
            destination_id = operator.index(destination_id)
        except TypeError:
            raise TypeError(
                f"Node ids must be integers, not {origin_id!r} and {destination_id!r}"
            ) from None
        if not hasattr(distance, "__float__"):
            raise TypeError(f"distance must be a number, not {distance!r}")
        if not isinstance(distance, (int, float)):
            # A Decimal or a numpy number: the searches add floats to it
            distance = float(distance)
        if origin_id < 0 or origin_id >= len(self.__graph__):
            raise IndexError(
                f"Origin node id ({origin_id}) is not in the graph"
            )
        if destination_id < 0 or destination_id >= len(self.__graph__):
            raise IndexError(
                f"Destination node id ({destination_id}) is not in the graph"
            )
        if math.isnan(distance):
            raise ValueError("distance must not be NaN")
        if origin_id == destination_id:
            return
        self.__graph__[origin_id][destination_id] = distance
        if symmetric:
            self.__graph__[destination_id][origin_id] = distance
        self.__inverse_graph__ = None
        self._edit_counter = self._edit_count + 1
        self.reset_cache()

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

        Raises:

        - `RuntimeError`: The graph has no node
        """
        if len(self.__graph__) == 0:
            raise RuntimeError("Graph is empty, cannot remove node")
        node_id = len(self.__graph__) - 1
        if symmetric_node:
            for dest_id in self.__graph__[node_id].keys():
                self.__graph__[dest_id].pop(node_id, None)
        else:
            for origin_dict in self.__graph__:
                if node_id in origin_dict:
                    origin_dict.pop(node_id)
        removed_node = self.__graph__.pop()
        self.__inverse_graph__ = None
        self._edit_counter = self._edit_count + 1
        self.reset_cache()
        return removed_node

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

        Raises:

        - `IndexError`: The origin id or the destination id is not in the graph
        """
        if origin_id < 0 or origin_id >= len(self.__graph__):
            raise IndexError("Origin node id is not in the graph")
        if destination_id < 0 or destination_id >= len(self.__graph__):
            raise IndexError("Destination node id is not in the graph")
        if symmetric:
            self.__graph__[destination_id].pop(origin_id, None)
        res = self.__graph__[origin_id].pop(destination_id, None)
        self.__inverse_graph__ = None
        self._edit_counter = self._edit_count + 1
        self.reset_cache()
        return res
