from array import array
from collections.abc import Callable
from heapq import heappop, heappush
from math import asin, ceil, cos, sin
from scgraph.graph_utils import (
    _last_search_in_thread,
    GraphUtils,
    GraphModifiers,
    normalize_node_input,
)
from scgraph.contraction_hierarchies import CHGraph
from scgraph.transit_node_routing import TNRGraph
from bmsspy import Bmssp
from scgraph.graph_reducer import GraphReducer, algorithm

try:
    from scgraph.cpp import PathNotFoundError
except ImportError:

    class PathNotFoundError(RuntimeError):
        """Raised when no path exists between origin and destination nodes."""


try:
    from scgraph.cpp import NegativeCycleError
except ImportError:

    class NegativeCycleError(RuntimeError):
        """Raised when a graph contains a negative weight cycle."""


# A* computes the heuristic of a node with one call of heuristic_fn per
# destination node. Above this number of destination nodes, A* is slower than
# Dijkstra on the built-in networks. The heuristic is then the smallest exit
# distance, and the search scans the nodes in the order of Dijkstra.
_MAX_DESTINATION_NODES_WITH_HEURISTIC = 4


class GraphTrees:
    def get_shortest_path_tree(
        self,
        origin_id: int | set[int] | dict[int, int | float],
    ) -> dict:
        """
        Function:

        - Calculate the shortest path tree of a graph using Dijkstra's algorithm

        Required Arguments:

        - `origin_id`
            - Type: int | set[int] | dict[int, int | float]
            - What: The id(s) of the node(s) (with optional starting distances) from which to calculate the shortest path tree

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
        return self._get_shortest_path_tree(self.graph, origin_id)

    def _get_shortest_path_tree(
        self,
        graph: list[dict[int, int | float]],
        origin_id: int | set[int] | dict[int, int | float],
    ) -> dict:
        """The shortest path tree of `get_shortest_path_tree`, on `graph`."""
        origin_dict = normalize_node_input(origin_id)

        # Variable Initialization
        distance_matrix = [float("inf")] * len(graph)
        open_leaves = []
        predecessor = [-1] * len(graph)

        for oid, odist in origin_dict.items():
            distance_matrix[oid] = odist
            heappush(open_leaves, (odist, oid))

        while open_leaves:
            current_distance, current_id = heappop(open_leaves)
            if current_distance > distance_matrix[current_id]:
                continue
            for connected_id, connected_distance in graph[current_id].items():
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
        origin_id: int | set[int] | dict[int, int | float],
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
            - Type: int | set[int] | dict[int, int | float]
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
        origin_dict = normalize_node_input(origin_id)
        tree_orig_dict = normalize_node_input(tree_data["origin_id"])

        start_dist = 0.0
        if len(tree_orig_dict) == 1:
            tree_root = next(iter(tree_orig_dict.keys()))
            if tree_root not in origin_dict:
                raise RuntimeError(
                    "The origin node must be the same as the spanning node for this function to work."
                )
            start_dist = origin_dict[tree_root] - tree_orig_dict[tree_root]

        dest_dict = normalize_node_input(destination_id)
        best_dist = float("inf")
        best_dest_node = -1
        for did, ddist in dest_dict.items():
            if tree_data["distance_matrix"][did] < float("inf"):
                tot = start_dist + tree_data["distance_matrix"][did] + ddist
                if tot < best_dist:
                    best_dist = tot
                    best_dest_node = did

        if best_dest_node == -1 or best_dist == float("inf"):
            raise PathNotFoundError(
                "Something went wrong, the origin and destination nodes are not connected."
            )
        if length_only:
            return {"path": [], "length": best_dist}
        current_id = best_dest_node
        current_path = [best_dest_node]
        while current_id != -1 and tree_data["predecessors"][current_id] != -1:
            current_id = tree_data["predecessors"][current_id]
            current_path.append(current_id)
        current_path.reverse()
        return {
            "path": current_path,
            "length": best_dist,
        }


class GraphAlgorithms:
    @algorithm
    def dijkstra(
        self,
        origin_id: int | set[int] | dict[int, int | float],
        destination_id: int | set[int] | dict[int, int | float],
    ) -> dict:
        """
        Function:

        - Identify the shortest path between two nodes in a sparse network graph using a modified Dijkstra algorithm

        - Return a dictionary of various path information including:
            - `path`: A list of node ids in the order they are visited
            - `length`: The length of the path from the origin node to the destination node

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
        # Input Validation
        self.__input_check__(origin_id=origin_id, destination_id=destination_id)
        origin_dict = normalize_node_input(origin_id)
        dest_dict = normalize_node_input(destination_id)

        # Variable Initialization
        graph = self.search_graph
        distance_matrix = [float("inf")] * len(graph)
        predecessor = [-1] * len(graph)
        open_leaves = []

        for oid, odist in origin_dict.items():
            distance_matrix[oid] = odist
            heappush(open_leaves, (odist, oid))

        best_dist = float("inf")
        best_dest_node = -1
        for did, ddist in dest_dict.items():
            if did in origin_dict:
                cand = origin_dict[did] + ddist
                if cand < best_dist:
                    best_dist = cand
                    best_dest_node = did

        node_scans = 0
        while open_leaves:
            current_distance, current_id = heappop(open_leaves)
            if current_distance >= best_dist:
                break
            if current_distance == distance_matrix[current_id]:
                if current_id in dest_dict:
                    cand = current_distance + dest_dict[current_id]
                    if cand < best_dist:
                        best_dist = cand
                        best_dest_node = current_id
                node_scans += 1
                for connected_id, connected_distance in graph[
                    current_id
                ].items():
                    possible_distance = current_distance + connected_distance
                    if possible_distance < distance_matrix[connected_id]:
                        distance_matrix[connected_id] = possible_distance
                        predecessor[connected_id] = current_id
                        if connected_id in dest_dict:
                            cand = possible_distance + dest_dict[connected_id]
                            if cand < best_dist:
                                best_dist = cand
                                best_dest_node = connected_id
                        if possible_distance < best_dist:
                            heappush(
                                open_leaves, (possible_distance, connected_id)
                            )

        _last_search_in_thread.node_scans = node_scans
        if best_dest_node == -1 or best_dist == float("inf"):
            raise PathNotFoundError(
                "Something went wrong, the origin and destination nodes are not connected."
            )

        return {
            "path": self.__reconstruct_path__(best_dest_node, predecessor),
            "length": best_dist,
        }

    @algorithm(bidirectional=True)
    def bidirectional_dijkstra(
        self,
        origin_id: int | set[int] | dict[int, int | float],
        destination_id: int | set[int] | dict[int, int | float],
    ) -> dict:
        """
        Function:

        - Identify the shortest path between two nodes in a sparse network graph using a bidirectional Dijkstra algorithm

        - Return a dictionary of various path information including:
            - `path`: A list of node ids in the order they are visited
            - `length`: The length of the path from the origin node to the destination node

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
        # Input Validation
        self.__input_check__(origin_id=origin_id, destination_id=destination_id)
        origin_dict = normalize_node_input(origin_id)
        dest_dict = normalize_node_input(destination_id)
        origin_ids = set(origin_dict.keys())
        dest_ids = set(dest_dict.keys())

        graph = self.search_graph
        inverse_graph = self.search_inverse_graph
        num_nodes = len(graph)

        forward_dist = [float("inf")] * num_nodes
        forward_pred = [-1] * num_nodes
        forward_open = []

        backward_dist = [float("inf")] * num_nodes
        backward_pred = [-1] * num_nodes
        backward_open = []

        best_dist = float("inf")
        meeting_node = -1
        inf = float("inf")

        for oid, odist in origin_dict.items():
            forward_dist[oid] = odist
            heappush(forward_open, (odist, oid))

        for did, ddist in dest_dict.items():
            backward_dist[did] = ddist
            heappush(backward_open, (ddist, did))
            if did in origin_dict:
                cand = origin_dict[did] + ddist
                if cand < best_dist:
                    best_dist = cand
                    meeting_node = did

        node_scans = 0
        while forward_open and backward_open:
            top_fwd = forward_open[0][0]
            top_bwd = backward_open[0][0]
            if top_fwd + top_bwd >= best_dist:
                break

            if top_fwd <= top_bwd:
                cur_d, u = heappop(forward_open)
                if cur_d > forward_dist[u]:
                    continue
                node_scans += 1
                for v, w in graph[u].items():
                    new_d = cur_d + w
                    if new_d < forward_dist[v]:
                        forward_dist[v] = new_d
                        forward_pred[v] = u
                        b_d = backward_dist[v]
                        if b_d < inf:
                            total_d = new_d + b_d
                            if total_d < best_dist:
                                best_dist = total_d
                                meeting_node = v
                        if new_d + top_bwd < best_dist:
                            heappush(forward_open, (new_d, v))
            else:
                cur_d, v = heappop(backward_open)
                if cur_d > backward_dist[v]:
                    continue
                node_scans += 1
                for u, w in inverse_graph[v].items():
                    new_d = cur_d + w
                    if new_d < backward_dist[u]:
                        backward_dist[u] = new_d
                        backward_pred[u] = v
                        f_d = forward_dist[u]
                        if f_d < inf:
                            total_d = f_d + new_d
                            if total_d < best_dist:
                                best_dist = total_d
                                meeting_node = u
                        if new_d + top_fwd < best_dist:
                            heappush(backward_open, (new_d, u))

        _last_search_in_thread.node_scans = node_scans
        if meeting_node == -1 or best_dist == float("inf"):
            raise PathNotFoundError(
                "Something went wrong, the origin and destination nodes are not connected."
            )

        forward_path = []
        curr = meeting_node
        while curr != -1:
            forward_path.append(curr)
            if curr in origin_ids and forward_pred[curr] == -1:
                break
            curr = forward_pred[curr]
        forward_path.reverse()

        backward_path = []
        curr = meeting_node
        while not (curr in dest_ids and backward_pred[curr] == -1):
            curr = backward_pred[curr]
            if curr != -1:
                backward_path.append(curr)
            else:
                break

        return {
            "path": forward_path + backward_path,
            "length": best_dist,
        }

    @algorithm
    def dijkstra_buckets(
        self,
        origin_id: int | set[int] | dict[int, int | float],
        destination_id: int | set[int] | dict[int, int | float],
        max_edge_weight: float | None = None,
        bucket_width: float | None = None,
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
            - Type: int | set[int] | dict[int, int | float]
            - What: The id(s) of the origin node(s) (with optional starting distances) from the graph dictionary to start the shortest path from
        - `destination_id`
            - Type: int | set[int] | dict[int, int | float]
            - What: The id(s) of the destination node(s) (with optional exit distances) from the graph dictionary to end the shortest path at

        Optional Arguments:

        - `max_edge_weight`
            - Type: int | float | None
            - What: The maximum edge weight in the graph. If None, it will be calculated.
            - Default: None
        - `bucket_width`
            - Type: int | float | None
            - What: The range of distances held by one bucket. If None, 8 times the median edge weight of the graph (1 if that median is 0). Raised if needed so that a ring holds at most 65,537 buckets. Must be a finite number greater than 0, else a ValueError is raised.
            - Default: None
        """
        # Input Validation
        self.__input_check__(origin_id=origin_id, destination_id=destination_id)
        origin_dict = normalize_node_input(origin_id)
        dest_dict = normalize_node_input(destination_id)
        graph = self.search_graph

        max_edge_weight = self.__get_max_edge_weight__(max_edge_weight)
        width = self._get_bucket_width(bucket_width, max_edge_weight)

        # Variable Initialization
        distance_matrix = [float("inf")] * len(graph)
        predecessor = [-1] * len(graph)
        num_buckets = ceil(max_edge_weight / width) + 1
        buckets = [[] for _ in range(num_buckets)]

        for oid, odist in origin_dict.items():
            distance_matrix[oid] = odist
            buckets[int(odist / width) % num_buckets].append(oid)

        current_dist = (
            min(int(odist / width) for odist in origin_dict.values())
            if origin_dict
            else 0
        )
        nodes_in_buckets = len(origin_dict)

        best_dist = float("inf")
        best_dest_node = -1
        for did, ddist in dest_dict.items():
            if did in origin_dict:
                cand = origin_dict[did] + ddist
                if cand < best_dist:
                    best_dist = cand
                    best_dest_node = did

        node_scans = 0
        while nodes_in_buckets > 0:
            bucket_idx = current_dist % num_buckets
            while not buckets[bucket_idx]:
                current_dist += 1
                bucket_idx = current_dist % num_buckets
                if nodes_in_buckets == 0:
                    break
                # If we've already found a path shorter than the current bucket minimum, we can exit
                if best_dist < current_dist * width:
                    break

            if nodes_in_buckets == 0 or best_dist < current_dist * width:
                break

            # The current bucket is relaxed as one batch; nodes re-inserted into it wait
            # for the next batch
            batch = buckets[bucket_idx]
            buckets[bucket_idx] = []
            nodes_in_buckets -= len(batch)

            for current_id in batch:
                # Skip if we found a better path already (lazy removal)
                if int(distance_matrix[current_id] / width) < current_dist:
                    continue

                if current_id in dest_dict:
                    cand = distance_matrix[current_id] + dest_dict[current_id]
                    if cand < best_dist:
                        best_dist = cand
                        best_dest_node = current_id

                node_scans += 1
                for connected_id, connected_distance in graph[
                    current_id
                ].items():
                    possible_distance = (
                        distance_matrix[current_id] + connected_distance
                    )
                    if possible_distance < distance_matrix[connected_id]:
                        distance_matrix[connected_id] = possible_distance
                        predecessor[connected_id] = current_id
                        if connected_id in dest_dict:
                            cand = possible_distance + dest_dict[connected_id]
                            if cand < best_dist:
                                best_dist = cand
                                best_dest_node = connected_id
                        buckets[
                            int(possible_distance / width) % num_buckets
                        ].append(connected_id)
                        nodes_in_buckets += 1

        _last_search_in_thread.node_scans = node_scans
        if best_dest_node == -1 or best_dist == float("inf"):
            raise PathNotFoundError(
                "Something went wrong, the origin and destination nodes are not connected."
            )

        return {
            "path": self.__reconstruct_path__(best_dest_node, predecessor),
            "length": best_dist,
        }

    @algorithm(bidirectional=True)
    def bidirectional_buckets(
        self,
        origin_id: int | set[int] | dict[int, int | float],
        destination_id: int | set[int] | dict[int, int | float],
        max_edge_weight: float | None = None,
        bucket_width: float | None = None,
    ) -> dict:
        """
        Function:

        - Identify the shortest path between two nodes in a sparse network graph using a bidirectional Dijkstra algorithm with buckets (Dial's algorithm)
        - This is particularly efficient for graphs where most edge weights are >= 1 and the maximum edge weight is small
        - This implementation safely supports non-integer weights
        - Return a dictionary of various path information including:
            - `path`: A list of node ids in the order they are visited
            - `length`: The length of the path from the origin node to the destination node

        Required Arguments:

        - `origin_id`
            - Type: int | set[int] | dict[int, int | float]
            - What: The id(s) of the origin node(s) (with optional starting distances) from the graph dictionary to start the shortest path from
        - `destination_id`
            - Type: int | set[int] | dict[int, int | float]
            - What: The id(s) of the destination node(s) (with optional exit distances) from the graph dictionary to end the shortest path at

        Optional Arguments:

        - `max_edge_weight`
            - Type: int | float | None
            - What: The maximum edge weight in the graph. If None, it will be calculated.
            - Default: None
        - `bucket_width`
            - Type: int | float | None
            - What: The range of distances held by one bucket. If None, 8 times the median edge weight of the graph (1 if that median is 0). Raised if needed so that a ring holds at most 65,537 buckets. Must be a finite number greater than 0, else a ValueError is raised.
            - Default: None
        """
        # Input Validation
        self.__input_check__(origin_id=origin_id, destination_id=destination_id)
        origin_dict = normalize_node_input(origin_id)
        dest_dict = normalize_node_input(destination_id)
        origin_ids = set(origin_dict.keys())
        dest_ids = set(dest_dict.keys())

        graph = self.search_graph
        inverse_graph = self.search_inverse_graph
        num_nodes = len(graph)

        max_edge_weight = self.__get_max_edge_weight__(max_edge_weight)
        width = self._get_bucket_width(bucket_width, max_edge_weight)

        num_buckets = ceil(max_edge_weight / width) + 1
        forward_dist = [float("inf")] * num_nodes
        forward_pred = [-1] * num_nodes
        forward_buckets = [[] for _ in range(num_buckets)]

        backward_dist = [float("inf")] * num_nodes
        backward_pred = [-1] * num_nodes
        backward_buckets = [[] for _ in range(num_buckets)]

        best_dist = float("inf")
        meeting_node = -1
        inf = float("inf")

        for oid, odist in origin_dict.items():
            forward_dist[oid] = odist
            forward_buckets[int(odist / width) % num_buckets].append(oid)

        for did, ddist in dest_dict.items():
            backward_dist[did] = ddist
            backward_buckets[int(ddist / width) % num_buckets].append(did)
            if did in origin_dict:
                cand = origin_dict[did] + ddist
                if cand < best_dist:
                    best_dist = cand
                    meeting_node = did

        fwd_current_dist = (
            min(int(odist / width) for odist in origin_dict.values())
            if origin_dict
            else 0
        )
        bwd_current_dist = (
            min(int(ddist / width) for ddist in dest_dict.values())
            if dest_dict
            else 0
        )
        fwd_nodes_in_buckets = len(origin_dict)
        bwd_nodes_in_buckets = len(dest_dict)

        node_scans = 0
        while fwd_nodes_in_buckets > 0 and bwd_nodes_in_buckets > 0:
            fwd_bucket_idx = fwd_current_dist % num_buckets
            while not forward_buckets[fwd_bucket_idx]:
                fwd_current_dist += 1
                fwd_bucket_idx = fwd_current_dist % num_buckets
                if fwd_nodes_in_buckets == 0:
                    break
                if (fwd_current_dist + bwd_current_dist) * width >= best_dist:
                    break

            bwd_bucket_idx = bwd_current_dist % num_buckets
            while not backward_buckets[bwd_bucket_idx]:
                bwd_current_dist += 1
                bwd_bucket_idx = bwd_current_dist % num_buckets
                if bwd_nodes_in_buckets == 0:
                    break
                if (fwd_current_dist + bwd_current_dist) * width >= best_dist:
                    break

            if (
                fwd_nodes_in_buckets == 0
                or bwd_nodes_in_buckets == 0
                or (fwd_current_dist + bwd_current_dist) * width >= best_dist
            ):
                break

            # The current bucket of the side with the lower cursor is relaxed as one
            # batch; nodes re-inserted into it wait for the next batch
            if fwd_current_dist <= bwd_current_dist:
                batch = forward_buckets[fwd_bucket_idx]
                forward_buckets[fwd_bucket_idx] = []
                fwd_nodes_in_buckets -= len(batch)

                for u in batch:
                    if int(forward_dist[u] / width) < fwd_current_dist:
                        continue

                    cur_d = forward_dist[u]
                    node_scans += 1
                    for v, w in graph[u].items():
                        new_d = cur_d + w
                        if new_d < forward_dist[v]:
                            forward_dist[v] = new_d
                            forward_pred[v] = u
                            b_d = backward_dist[v]
                            if b_d < inf:
                                total_d = new_d + b_d
                                if total_d < best_dist:
                                    best_dist = total_d
                                    meeting_node = v
                            if new_d + bwd_current_dist * width < best_dist:
                                forward_buckets[
                                    int(new_d / width) % num_buckets
                                ].append(v)
                                fwd_nodes_in_buckets += 1
            else:
                batch = backward_buckets[bwd_bucket_idx]
                backward_buckets[bwd_bucket_idx] = []
                bwd_nodes_in_buckets -= len(batch)

                for v in batch:
                    if int(backward_dist[v] / width) < bwd_current_dist:
                        continue

                    cur_d = backward_dist[v]
                    node_scans += 1
                    for u, w in inverse_graph[v].items():
                        new_d = cur_d + w
                        if new_d < backward_dist[u]:
                            backward_dist[u] = new_d
                            backward_pred[u] = v
                            f_d = forward_dist[u]
                            if f_d < inf:
                                total_d = f_d + new_d
                                if total_d < best_dist:
                                    best_dist = total_d
                                    meeting_node = u
                            if new_d + fwd_current_dist * width < best_dist:
                                backward_buckets[
                                    int(new_d / width) % num_buckets
                                ].append(u)
                                bwd_nodes_in_buckets += 1

        _last_search_in_thread.node_scans = node_scans
        if meeting_node == -1 or best_dist == float("inf"):
            raise PathNotFoundError(
                "Something went wrong, the origin and destination nodes are not connected."
            )

        forward_path = []
        curr = meeting_node
        while curr != -1:
            forward_path.append(curr)
            if curr in origin_ids and forward_pred[curr] == -1:
                break
            curr = forward_pred[curr]
        forward_path.reverse()

        backward_path = []
        curr = meeting_node
        while not (curr in dest_ids and backward_pred[curr] == -1):
            curr = backward_pred[curr]
            if curr != -1:
                backward_path.append(curr)
            else:
                break

        return {
            "path": forward_path + backward_path,
            "length": best_dist,
        }

    @algorithm
    def dijkstra_negative(
        self,
        origin_id: int | set[int] | dict[int, int | float],
        destination_id: int | set[int] | dict[int, int | float],
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
            - Type: int | set[int] | dict[int, int | float]
            - What: The id(s) of the origin node(s) (with optional starting distances) from the graph dictionary to start the shortest path from
        - `destination_id`
            - Type: int | set[int] | dict[int, int | float]
            - What: The id(s) of the destination node(s) (with optional exit distances) from the graph dictionary to end the shortest path at

        Optional Arguments:

        - `cycle_check_iterations`
            - Type: int | None
            - What: The number of iterations to loop over before checking for negative cycles
            - Default: None (Then set to the number of nodes in the graph)
        """
        # Input Validation
        self.__input_check__(origin_id=origin_id, destination_id=destination_id)
        origin_dict = normalize_node_input(origin_id)
        dest_dict = normalize_node_input(destination_id)
        graph = self.search_graph

        # Variable Initialization
        distance_matrix = [float("inf")] * len(graph)
        predecessor = [-1] * len(graph)
        open_leaves = []

        for oid, odist in origin_dict.items():
            distance_matrix[oid] = odist
            heappush(open_leaves, (odist, oid))

        # Cycle iteration Variables
        cycle_iteration = 0
        if cycle_check_iterations is None:
            cycle_check_iterations = len(graph)

        while open_leaves:
            current_distance, current_id = heappop(open_leaves)
            if current_distance == distance_matrix[current_id]:
                # Increment the cycle iteration counter and check for negative cycles if the iteration limit is reached
                cycle_iteration += 1
                if cycle_iteration >= cycle_check_iterations:
                    cycle_iteration = 0  # Reset the cycle iteration counter
                    self.__check_predecessor_loop__(
                        predecessor_matrix=predecessor, node_id=current_id
                    )
                for connected_id, connected_distance in graph[
                    current_id
                ].items():
                    possible_distance = current_distance + connected_distance
                    if possible_distance < distance_matrix[connected_id]:
                        distance_matrix[connected_id] = possible_distance
                        predecessor[connected_id] = current_id
                        heappush(open_leaves, (possible_distance, connected_id))

        best_dist = float("inf")
        best_dest_node = -1
        for did, ddist in dest_dict.items():
            cand = distance_matrix[did] + ddist
            if cand < best_dist:
                best_dist = cand
                best_dest_node = did

        if best_dest_node == -1 or best_dist == float("inf"):
            raise PathNotFoundError(
                "Something went wrong, the origin and destination nodes are not connected."
            )

        return {
            "path": self.__reconstruct_path__(best_dest_node, predecessor),
            "length": best_dist,
        }

    @algorithm
    def a_star(
        self,
        origin_id: int | set[int] | dict[int, int | float],
        destination_id: int | set[int] | dict[int, int | float],
        heuristic_fn: Callable[[int, int], int | float] | None = None,
    ) -> dict:
        """
        Function:

        - Identify the shortest path between two nodes in a sparse network graph using an A* extension of Makowski's modified Dijkstra algorithm
        - Return a dictionary of various path information including:
            - `id_path`: A list of node ids in the order they are visited
            - `path`: A list of node dictionaries (lat + long) in the order they are visited

        Required Arguments:

        - `origin_id`
            - Type: int | set[int] | dict[int, int | float]
            - What: The id of the origin node (or nodes with starting distances) from the graph dictionary to start the shortest path from
        - `destination_id`
            - Type: int | set[int] | dict[int, int | float]
            - What: The id of the destination node (or nodes with exit distances) from the graph dictionary to end the shortest path at
        - `heuristic_fn`
            - Type: function
            - What: A heuristic function that takes two node ids and returns an estimated distance between them
            - Note: If None, returns the shortest path using Dijkstra's algorithm
            - Note: The path is the shortest one if the heuristic never exceeds the real distance between the two nodes
            - Note: With more than 4 destination nodes, the heuristic is not called and the search scans the nodes as Dijkstra's algorithm does
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
        origin_dict = normalize_node_input(origin_id)
        dest_dict = normalize_node_input(destination_id)

        # Variable Initialization
        graph = self.search_graph
        distance_matrix = [float("inf")] * len(graph)
        open_leaves = []
        predecessor = [-1] * len(graph)

        best_dist = float("inf")
        best_dest_node = -1
        for did, ddist in dest_dict.items():
            if did in origin_dict:
                cand = origin_dict[did] + ddist
                if cand < best_dist:
                    best_dist = cand
                    best_dest_node = did

        # The heuristic of a node estimates its distance to the destination
        # point. It is the smallest sum of the estimate to a destination node
        # and the exit distance of that node.
        smallest_exit_distance = min(dest_dict.values())

        def _h(node):
            if isinstance(destination_id, int):
                return heuristic_fn(node, destination_id)
            if len(dest_dict) > _MAX_DESTINATION_NODES_WITH_HEURISTIC:
                return smallest_exit_distance
            return min(
                heuristic_fn(node, did) + ddist
                for did, ddist in dest_dict.items()
            )

        # A queue entry holds the key of a node (its distance from the origin
        # plus its heuristic), this distance, and the node.
        for oid, odist in origin_dict.items():
            distance_matrix[oid] = odist
            heappush(open_leaves, (odist + _h(oid), odist, oid))

        node_scans = 0
        while open_leaves:
            key, current_distance, current_id = heappop(open_leaves)
            # No route through a node left in the queue is shorter than its key.
            if key >= best_dist:
                break
            # A shorter distance to this node was found after this entry.
            if current_distance > distance_matrix[current_id]:
                continue
            if current_id in dest_dict:
                cand = current_distance + dest_dict[current_id]
                if cand < best_dist:
                    best_dist = cand
                    best_dest_node = current_id
            node_scans += 1
            for connected_id, connected_distance in graph[current_id].items():
                possible_distance = current_distance + connected_distance
                if possible_distance < distance_matrix[connected_id]:
                    distance_matrix[connected_id] = possible_distance
                    predecessor[connected_id] = current_id
                    if connected_id in dest_dict:
                        cand = possible_distance + dest_dict[connected_id]
                        if cand < best_dist:
                            best_dist = cand
                            best_dest_node = connected_id
                    connected_key = possible_distance + _h(connected_id)
                    if connected_key < best_dist:
                        heappush(
                            open_leaves,
                            (connected_key, possible_distance, connected_id),
                        )
        _last_search_in_thread.node_scans = node_scans
        if best_dest_node == -1 or best_dist == float("inf"):
            raise PathNotFoundError(
                "Something went wrong, the origin and destination nodes are not connected."
            )

        return {
            "path": self.__reconstruct_path__(best_dest_node, predecessor),
            "length": best_dist,
        }

    def a_star_great_circle(
        self,
        origin_id: int | set[int] | dict[int, int | float],
        destination_id: int | set[int] | dict[int, int | float],
        latitudes: array | memoryview,
        longitudes: array | memoryview,
        radius: float,
    ) -> dict:
        """
        Function:

        - A* with the great-circle (haversine) distance between nodes as its heuristic
        - Same result as `a_star` with `GeoGraph.haversine`; the C++ build computes the heuristic natively
        - Called by `GeoGraph.get_shortest_path` when `heuristic_fn` is `GeoGraph.haversine`

        Required Arguments:

        - `origin_id`
            - Type: int | set[int] | dict[int, int | float]
            - What: The id of the origin node (or nodes with starting distances)
        - `destination_id`
            - Type: int | set[int] | dict[int, int | float]
            - What: The id of the destination node (or nodes with exit distances)
        - `latitudes`
            - Type: C-contiguous float64 buffer (e.g. `array("d")`)
            - What: The latitude of each node, in radians (at least one entry per graph node)
        - `longitudes`
            - Type: C-contiguous float64 buffer (e.g. `array("d")`)
            - What: The longitude of each node, in radians (at least one entry per graph node)
        - `radius`
            - Type: float
            - What: The earth radius in the units of the graph weights

        Optional Arguments:

        - None
        """
        if len(latitudes) < len(self.graph) or len(longitudes) < len(
            self.graph
        ):
            raise ValueError(
                "latitudes and longitudes must have an entry for every graph node"
            )

        def heuristic_fn(origin, destination):
            a = (
                sin((latitudes[destination] - latitudes[origin]) / 2) ** 2
                + cos(latitudes[origin])
                * cos(latitudes[destination])
                * sin((longitudes[destination] - longitudes[origin]) / 2) ** 2
            )
            return 2 * asin(a**0.5) * radius

        return self.a_star(
            origin_id=origin_id,
            destination_id=destination_id,
            heuristic_fn=heuristic_fn,
        )

    @algorithm
    def bellman_ford(
        self,
        origin_id: int | set[int] | dict[int, int | float],
        destination_id: int | set[int] | dict[int, int | float],
    ) -> dict:
        """
        Function:

        - Identify the shortest path between two nodes in a sparse network graph using the Bellman-Ford algorithm
        - Return a dictionary of various path information including:
            - `id_path`: A list of node ids in the order they are visited
            - `path`: A list of node dictionaries (lat + long) in the order they are visited

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
        # Input Validation
        self.__input_check__(origin_id=origin_id, destination_id=destination_id)
        origin_dict = normalize_node_input(origin_id)
        dest_dict = normalize_node_input(destination_id)
        graph = self.search_graph

        # Variable Initialization
        distance_matrix = [float("inf")] * len(graph)
        predecessor = [-1] * len(graph)

        for oid, odist in origin_dict.items():
            distance_matrix[oid] = odist

        len_graph = len(graph)
        for i in range(len_graph):
            updated = False
            for current_id in range(len(graph)):
                current_distance = distance_matrix[current_id]
                if current_distance == float("inf"):
                    continue
                for connected_id, connected_distance in graph[
                    current_id
                ].items():
                    possible_distance = current_distance + connected_distance
                    if possible_distance < distance_matrix[connected_id]:
                        distance_matrix[connected_id] = possible_distance
                        predecessor[connected_id] = current_id
                        updated = True
                        if i == len_graph - 1:
                            raise NegativeCycleError(
                                "Graph contains a negative weight cycle"
                            )
            if not updated:
                break
        best_dist = float("inf")
        best_dest_node = -1
        for did, ddist in dest_dict.items():
            cand = distance_matrix[did] + ddist
            if cand < best_dist:
                best_dist = cand
                best_dest_node = did

        if best_dest_node == -1 or best_dist == float("inf"):
            raise PathNotFoundError(
                "Something went wrong, the origin and destination nodes are not connected."
            )

        return {
            "path": self.__reconstruct_path__(best_dest_node, predecessor),
            "length": best_dist,
        }

    @algorithm
    def bmssp(
        self,
        origin_id: int | set[int] | dict[int, int | float],
        destination_id: int | set[int] | dict[int, int | float],
        use_constant_degree_graph: bool = True,
    ) -> dict:
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
        if isinstance(origin_id, (set, dict)) or isinstance(
            destination_id, (set, dict)
        ):
            return self.dijkstra(
                origin_id=origin_id, destination_id=destination_id
            )
        if not hasattr(self, "__bmssp_graph__"):
            self.__bmssp_graph__ = Bmssp(
                graph=self.search_graph,
                use_constant_degree_graph=use_constant_degree_graph,
            )
        output = self.__bmssp_graph__.solve(
            origin_id=origin_id, destination_id=destination_id
        )
        return {
            "path": output["path"],
            "length": output["length"],
        }

    @algorithm
    def cached_shortest_path(
        self,
        origin_id: int | set[int] | dict[int, int | float],
        destination_id: int | set[int] | dict[int, int | float],
        length_only: bool = False,
    ) -> dict:
        """
        Function:

        - Get the shortest path between two nodes in the graph attempting to use a cached shortest path tree if available
        - If a cached shortest path tree is not available, it will compute the shortest path tree and cache it for future use if specified by `cache`
        - Builds each tree with Dijkstra on the searched graph and reads it with get_tree_path: after `reduce()`, the cached trees are those of the reduced graph (`inf` on contracted nodes), in both builds
        - Stores cached shortest path trees in a list (self.__cache__) where the index corresponds to the origin node id
        - Note: If you modify this graph after caching shortest path trees, the cached trees may become invalid

        Required Arguments:

        - `origin_id`
            - Type: int | set[int] | dict[int, int | float]
            - What: The id(s) of the origin node(s) (with optional starting distances) from the graph dictionary to start the shortest path from
        - `destination_id`
            - Type: int | set[int] | dict[int, int | float]
            - What: The id(s) of the destination node(s) (with optional exit distances) from the graph dictionary to end the shortest path at

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
        # Input Validation
        self.__input_check__(origin_id=origin_id, destination_id=destination_id)

        # Main function
        if isinstance(origin_id, int):
            orig_node = origin_id
            is_single_origin = True
        elif isinstance(origin_id, set) and len(origin_id) == 1:
            orig_node = next(iter(origin_id))
            is_single_origin = True
        elif isinstance(origin_id, dict) and len(origin_id) == 1:
            orig_node = next(iter(origin_id.keys()))
            is_single_origin = True
        else:
            is_single_origin = False

        if is_single_origin:
            if self.__cache__[orig_node] == 0:
                self.__cache__[orig_node] = self._get_shortest_path_tree(
                    self.search_graph, orig_node
                )
            return self.get_tree_path(
                origin_id=origin_id,
                destination_id=destination_id,
                tree_data=self.__cache__[orig_node],
                length_only=length_only,
            )

        res = self.dijkstra(
            origin_id=origin_id,
            destination_id=destination_id,
        )
        if length_only:
            res["path"] = []
        return res

    def create_contraction_hierarchy(
        self,
        heuristic_fn: Callable[[CHGraph, int], int | float] | None = None,
        ch_graph_kwargs: dict | None = None,
        settled_limit: int = 50,
    ) -> CHGraph:
        """
        Function:

        - Create a Contraction Hierarchies (CH) graph from the current Graph object
        - The CH graph is stored as an instance variable `self.__ch_graph__`

        Optional Arguments:

        - `heuristic_fn`:
            - Type: function or None
            - What: A heuristic function for CH preprocessing
            - Default: None (uses default heuristic)

        - `settled_limit`:
            - Type: int
            - What: The settled count limit for witness search
            - Default: 50
        """
        if not hasattr(self, "__ch_graph__"):
            ch_graph_kwargs = (
                ch_graph_kwargs if ch_graph_kwargs is not None else dict()
            )
            self.__ch_graph__ = CHGraph(
                graph=self.search_graph,
                inverse_graph=self.search_inverse_graph,
                settled_limit=settled_limit,
                heuristic_fn=self.wrap_heuristic(heuristic_fn),
                **ch_graph_kwargs,
            )
        return self.__ch_graph__

    def create_tnr_hierarchy(
        self,
        num_transit_nodes: int = 100,
        tnr_graph_kwargs: dict | None = None,
        settled_limit: int = 50,
        heuristic_fn: Callable[[CHGraph, int], int | float] | None = None,
    ) -> TNRGraph:
        """
        Function:

        - Create a Transit Node Routing (TNR) graph from the current Graph object
        - The TNR graph is stored as an instance variable `self.__tnr_graph__`

        Optional Arguments:

        - `num_transit_nodes`:
            - Type: int
            - What: The number of transit nodes to use
                - On a reduced graph, at most the number of nodes left
            - Default: 100

        - `settled_limit`:
            - Type: int
            - What: The settled count limit for witness search
            - Default: 50

        - `heuristic_fn`:
            - Type: function or None
            - What: A heuristic function for TNR/CH preprocessing
            - Default: None
        """
        if not hasattr(self, "__tnr_graph__"):
            tnr_graph_kwargs = (
                tnr_graph_kwargs if tnr_graph_kwargs is not None else dict()
            )
            is_reduced = getattr(self, "is_reduced", None)
            if is_reduced is not None:
                # Transit nodes are the last contracted, and reduced nodes are
                # contracted first: no more transit nodes than nodes left
                num_transit_nodes = min(
                    num_transit_nodes, max(1, is_reduced.count(False))
                )
            self.__tnr_graph__ = TNRGraph(
                graph=self.search_graph,
                inverse_graph=self.search_inverse_graph,
                settled_limit=settled_limit,
                num_transit_nodes=num_transit_nodes,
                heuristic_fn=self.wrap_heuristic(heuristic_fn),
                **tnr_graph_kwargs,
            )
        return self.__tnr_graph__

    @algorithm(bidirectional=True)
    def tnr(
        self,
        origin_id: int | set[int] | dict[int, int | float],
        destination_id: int | set[int] | dict[int, int | float],
        length_only: bool = False,
        **kwargs,
    ) -> dict:
        """
        Function:

        - Perform a Transit Node Routing (TNR) search on the graph
        - Automatically creates the TNR hierarchy if it doesn't exist

        Required Arguments:

        - `origin_id`
            - Type: int | set[int] | dict[int, int | float]
            - What: The id(s) of the origin node(s) (with optional starting distances)
        - `destination_id`
            - Type: int | set[int] | dict[int, int | float]
            - What: The id(s) of the destination node(s) (with optional exit distances)

        Optional Arguments:

        - `length_only`
            - Type: bool
            - What: If True, only returns the length of the path
            - Default: False
        """
        self.create_tnr_hierarchy(50)
        return self.__tnr_graph__.search(
            origin_id, destination_id, length_only=length_only
        )

    @algorithm(bidirectional=True)
    def contraction_hierarchy(
        self,
        origin_id: int | set[int] | dict[int, int | float],
        destination_id: int | set[int] | dict[int, int | float],
        length_only: bool = False,
    ) -> dict:
        """
        Function:

        - Get the shortest path between two nodes using the Contraction Hierarchies (CH) graph
        - Creates the CH graph if it doesn't exist

        Requires:

        - origin_id: The id(s) of the origin node(s) (with optional starting distances)
        - destination_id: The id(s) of the destination node(s) (with optional exit distances)

        Optional:

        - length_only: If True, only returns the length of the path

        Returns:

        - A dictionary with 'path' and 'length' keys containing the shortest path and its length
        """
        self.create_contraction_hierarchy()
        return self.__ch_graph__.search(
            origin_id, destination_id, length_only=length_only
        )


class Graph(
    GraphUtils, GraphModifiers, GraphTrees, GraphAlgorithms, GraphReducer
):
    algorithm = staticmethod(algorithm)

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
            - Note: The Graph may keep and modify this list instead of copying it; do not modify it afterwards (use methods such as `add_edge` instead)
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

    @staticmethod
    def from_csr(
        offsets: array | memoryview,
        heads: array | memoryview,
        weights: array | memoryview,
    ) -> "Graph":
        """
        Function:

        - Create a Graph from its arcs stored by origin (compressed sparse rows), as in a `.scgraph` network file
        - The arcs of node `u` go to `heads[offsets[u]:offsets[u + 1]]`, with the same slice of `weights`

        Required Arguments:

        - `offsets`
            - Type: sequence of ints (int32 array in the C++ backend), one per node plus one
        - `heads`
            - Type: sequence of ints (int32 array in the C++ backend), one per arc
        - `weights`
            - Type: sequence of floats (float64 array in the C++ backend), one per arc
        """
        n = len(offsets) - 1
        if (
            n < 0
            or offsets[0] != 0
            or offsets[-1] != len(heads)
            or len(weights) != len(heads)
        ):
            raise ValueError(
                "expected offsets from 0 to the number of arcs and one weight per arc"
            )
        if len(heads) and (min(heads) < 0 or max(heads) >= n):
            raise ValueError("an arc goes to a node that is not in the graph")
        return Graph(
            [
                dict(zip(heads[start:end], weights[start:end]))
                for start, end in zip(offsets, offsets[1:])
            ]
        )

    @staticmethod
    def _reset_node_scans() -> None:
        """
        Forgets the number of node scans of the last search in this thread.
        """
        _last_search_in_thread.node_scans = None

    @staticmethod
    def _get_last_node_scans() -> int | None:
        """
        Returns the number of node scans of the last search in this thread.

        - A node scan is one pass over the arcs of one node. A bidirectional or bucket
          search can scan a node more than once
        - Dijkstra, A* and bucket searches count their node scans. Returns None if no
          such search ran since `_reset_node_scans`
        """
        return getattr(_last_search_in_thread, "node_scans", None)

    def reset_cache(self) -> None:
        super().reset_cache()
        if hasattr(self, "__ch_graph__"):
            delattr(self, "__ch_graph__")
        if hasattr(self, "__tnr_graph__"):
            delattr(self, "__tnr_graph__")
        if hasattr(self, "__bmssp_graph__"):
            delattr(self, "__bmssp_graph__")
        if hasattr(self, "__max_edge_weight__"):
            delattr(self, "__max_edge_weight__")
        if hasattr(self, "__bucket_width__"):
            delattr(self, "__bucket_width__")
        self.reduced_graph = None
        self.reduced_graph_connections = None
        self.reduced_inverse_graph = None
        self.reduced_inverse_graph_connections = None
        self.__hidden_next__ = None
        self.__hidden_previous__ = None
        self.is_reduced = None
        self.reduced_node_chain_ids = None
