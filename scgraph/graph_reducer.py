from heapq import heappop, heappush
from functools import wraps


def use_reduced(func):
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        if getattr(self, "reduced_graph", None) is None:
            return func(self, *args, **kwargs)
        return self.__run_with_reduced__(func, *args, **kwargs)

    return wrapper


class GraphReducer:
    def reduce(self) -> None:
        """
        Function:

        - Reduce the graph by bypassing pass-through nodes and summing intermediate weights.
        - Sets self.reduced_graph, self.reduced_graph_connections, and self.is_reduced.

        Required Arguments:

        - None

        Returns:

        - None
        """
        self.reset_cache()
        self.__ensure_inverse_graph__()

        # 1. Identify pass-through nodes
        self.is_reduced = [False] * len(self.__graph__)
        graph = self.__graph__
        inverse_graph = self.__inverse_graph__
        is_reduced = self.is_reduced

        for u in range(len(graph)):
            out_dict = graph[u]
            in_dict = inverse_graph[u]

            out_len = len(out_dict) - (1 if u in out_dict else 0)
            if out_len == 1:
                in_len = len(in_dict) - (1 if u in in_dict else 0)
                if in_len >= 1:
                    is_reduced[u] = True
            elif out_len == 2:
                in_len = len(in_dict) - (1 if u in in_dict else 0)
                if in_len > 0:
                    outflows = {v for v in out_dict if v != u}
                    inflows = {v for v in in_dict if v != u}
                    if inflows.issubset(outflows):
                        is_reduced[u] = True

        # 2. Assign chain IDs to connected components of reduced nodes
        self.reduced_node_chain_ids = [None] * len(graph)
        reduced_node_chain_ids = self.reduced_node_chain_ids
        current_chain_id = 0
        for u in range(len(graph)):
            if is_reduced[u] and reduced_node_chain_ids[u] is None:
                queue = [u]
                reduced_node_chain_ids[u] = current_chain_id
                while queue:
                    curr = queue.pop()
                    for v in graph[curr]:
                        if (
                            v != curr
                            and is_reduced[v]
                            and reduced_node_chain_ids[v] is None
                        ):
                            reduced_node_chain_ids[v] = current_chain_id
                            queue.append(v)
                    for v in inverse_graph[curr]:
                        if (
                            v != curr
                            and is_reduced[v]
                            and reduced_node_chain_ids[v] is None
                        ):
                            reduced_node_chain_ids[v] = current_chain_id
                            queue.append(v)
                current_chain_id += 1

        # 3. Build reduced graph and connections (outbound from all nodes)
        self.reduced_graph = [{} for _ in range(len(graph))]
        self.reduced_graph_connections = [None] * len(graph)
        reduced_graph = self.reduced_graph
        reduced_graph_connections = self.reduced_graph_connections

        for A in range(len(graph)):
            best_dist = {}
            open_leaves = [(0, A, [])]

            while open_leaves:
                dist, u, path = heappop(open_leaves)
                if u in best_dist and best_dist[u] <= dist:
                    continue
                best_dist[u] = dist

                if u != A and not is_reduced[u]:
                    # Boundary non-reduced node. Record connection.
                    reduced_graph[A][u] = dist
                    if path:
                        if reduced_graph_connections[A] is None:
                            reduced_graph_connections[A] = {}
                        reduced_graph_connections[A][u] = path
                    continue

                for v, w in graph[u].items():
                    new_dist = dist + w
                    if v not in best_dist or new_dist < best_dist[v]:
                        new_path = path if u == A else path + [u]
                        heappush(open_leaves, (new_dist, v, new_path))

        # 4. Build reduced inverse graph and connections (inbound into all nodes)
        self.reduced_inverse_graph = [{} for _ in range(len(graph))]
        self.reduced_inverse_graph_connections = [None] * len(graph)
        reduced_inverse_graph = self.reduced_inverse_graph
        reduced_inverse_graph_connections = (
            self.reduced_inverse_graph_connections
        )

        for B in range(len(graph)):
            best_dist = {}
            open_leaves = [(0, B, [])]

            while open_leaves:
                dist, u, path = heappop(open_leaves)
                if u in best_dist and best_dist[u] <= dist:
                    continue
                best_dist[u] = dist

                if u != B and not is_reduced[u]:
                    # Boundary non-reduced node reaching B
                    reduced_inverse_graph[B][u] = dist
                    fwd_path = list(reversed(path))
                    if fwd_path:
                        if reduced_inverse_graph_connections[B] is None:
                            reduced_inverse_graph_connections[B] = {}
                        reduced_inverse_graph_connections[B][u] = fwd_path
                    continue

                for v, w in inverse_graph[u].items():
                    new_dist = dist + w
                    if v not in best_dist or new_dist < best_dist[v]:
                        new_path = path if u == B else path + [u]
                        heappush(open_leaves, (new_dist, v, new_path))

    def wrap_heuristic(self, heuristic_fn=None):
        """
        Function:

        - Wrap a CH/TNR heuristic function to contract reduced nodes before non-reduced nodes.
        """
        if not getattr(self, "is_reduced", None):
            return heuristic_fn
        if heuristic_fn is None:
            is_reduced = self.is_reduced
            return lambda ch, n: (
                0 if is_reduced[n] else 1000000
            ) + ch.default_heuristic(n)
        is_reduced = self.is_reduced
        return lambda ch, n: (0 if is_reduced[n] else 1000000) + heuristic_fn(
            ch, n
        )

    def __run_with_reduced__(self, func, *args, **kwargs):
        """
        Function:

        - Run a graph routing function on the reduced graph.
        - Same-chain queries route directly on the unreduced graph.
        - Bidirectional algorithms route on reduced_graph and reduced_inverse_graph.
        - One-sided algorithms with reduced destination solve via boundary entry nodes from reduced_inverse_graph.

        Required Arguments:

        - `func`
            - Type: function
            - What: The routing algorithm function to execute

        Returns:

        - The return value of the wrapped routing algorithm (typically a dict with 'path' and 'length')
        """
        origin_id = kwargs.get("origin_id")
        if origin_id is None and len(args) > 0:
            origin_id = args[0]

        destination_id = kwargs.get("destination_id")
        if destination_id is None and len(args) > 1:
            destination_id = args[1]

        # 1. Same-chain check: solve on unreduced graph with dijkstra
        if destination_id is not None and self.is_same_chain(
            origin_id, destination_id
        ):
            length_only = kwargs.get("length_only", False)
            res = self.__dijkstra_on_graph__(
                self.__graph__, origin_id, destination_id
            )
            if length_only:
                res.pop("path", None)
            return res

        is_reduced = self.is_reduced

        # 2. Bidirectional algorithms, Contraction Hierarchies, and Transit Node Routing
        if func.__name__ in (
            "bidirectional_dijkstra",
            "contraction_hierarchy",
            "tnr",
        ):
            res = func(self, *args, **kwargs)
            if isinstance(res, dict) and "path" in res:
                res["path"] = self.__expand_path__(res["path"])
            return res

        # 3. One-sided algorithms with unreduced destination (or None)
        if destination_id is None or not is_reduced[destination_id]:
            res = func(self, *args, **kwargs)
            if isinstance(res, dict) and "path" in res:
                res["path"] = self.__expand_path__(res["path"])
            return res

        # 4. One-sided algorithm with reduced destination
        entry_nodes = self.reduced_inverse_graph[destination_id]
        if not entry_nodes:
            raise Exception(
                "Something went wrong, the origin and destination nodes are not connected."
            )

        best_length = float("inf")
        best_res = None
        best_entry = None

        for entry_u, entry_dist in entry_nodes.items():
            try:
                call_kwargs = dict(kwargs)
                call_args = list(args)
                if "destination_id" in call_kwargs:
                    call_kwargs["destination_id"] = entry_u
                elif len(call_args) > 1:
                    call_args[1] = entry_u

                res_u = func(self, *call_args, **call_kwargs)
                total_dist = res_u["length"] + entry_dist
                if total_dist < best_length:
                    best_length = total_dist
                    best_res = res_u
                    best_entry = entry_u
            except Exception:
                continue

        if best_res is None or best_length == float("inf"):
            raise Exception(
                "Something went wrong, the origin and destination nodes are not connected."
            )

        if "path" in best_res:
            expanded_path = self.__expand_path__(best_res["path"])
            tail = []
            if (
                self.reduced_inverse_graph_connections is not None
                and self.reduced_inverse_graph_connections[destination_id]
                is not None
            ):
                tail = self.reduced_inverse_graph_connections[
                    destination_id
                ].get(best_entry, [])
            full_path = expanded_path + tail + [destination_id]
            return {
                "path": full_path,
                "length": best_length,
            }
        return {
            "length": best_length,
        }

    def __dijkstra_on_graph__(
        self,
        graph: list[dict[int, float]],
        origin_id: int | set[int],
        destination_id: int,
    ) -> dict:
        """
        Function:

        - Internal Dijkstra solver on a specified graph dictionary list (used for same-chain routing on unreduced graph).
        """
        origin_ids = {origin_id} if isinstance(origin_id, int) else origin_id
        distance_matrix = [float("inf")] * len(graph)
        predecessor = [-1] * len(graph)
        open_leaves = []

        for oid in origin_ids:
            distance_matrix[oid] = 0
            heappush(open_leaves, (0, oid))

        while open_leaves:
            current_distance, current_id = heappop(open_leaves)
            if current_id == destination_id:
                break
            if current_distance == distance_matrix[current_id]:
                for (
                    connected_id,
                    connected_distance,
                ) in graph[current_id].items():
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

    def __expand_path__(self, path: list[int]) -> list[int]:
        """
        Function:

        - Expand a path of reduced graph nodes to restore all intermediate pass-through nodes.

        Required Arguments:

        - `path`
            - Type: list[int]
            - What: The path in the reduced graph

        Returns:

        - The fully expanded path matching the original graph
        """
        fwd_conns = getattr(self, "reduced_graph_connections", None)
        inv_conns = getattr(self, "reduced_inverse_graph_connections", None)
        if fwd_conns is None and inv_conns is None:
            return path
        new_path = []
        append = new_path.append
        extend = new_path.extend
        for i in range(len(path) - 1):
            u = path[i]
            v = path[i + 1]
            append(u)
            expanded = False
            if fwd_conns is not None and fwd_conns[u] is not None:
                pass_throughs = fwd_conns[u].get(v)
                if pass_throughs:
                    extend(pass_throughs)
                    expanded = True
            if (
                not expanded
                and inv_conns is not None
                and inv_conns[v] is not None
            ):
                pass_throughs = inv_conns[v].get(u)
                if pass_throughs:
                    extend(pass_throughs)
        if path:
            append(path[-1])
        return new_path

    def is_same_chain(
        self,
        origin_id: int | set[int] | list[int],
        destination_id: int | None,
    ) -> bool:
        """
        Function:

        - Check whether any origin node and the destination node belong to the same reduced chain.

        Required Arguments:

        - `origin_id`
            - Type: int | set[int] | list[int]
            - What: The id(s) of the origin node(s)
        - `destination_id`
            - Type: int | None
            - What: The id of the destination node

        Returns:

        - True if both origin and destination are reduced nodes and share the same chain_id, False otherwise.
        """
        reduced_node_chain_ids = getattr(self, "reduced_node_chain_ids", None)
        if reduced_node_chain_ids is None or destination_id is None:
            return False
        if destination_id < 0 or destination_id >= len(reduced_node_chain_ids):
            return False
        dest_chain = reduced_node_chain_ids[destination_id]
        if dest_chain is None:
            return False
        if isinstance(origin_id, int):
            if 0 <= origin_id < len(reduced_node_chain_ids):
                return reduced_node_chain_ids[origin_id] == dest_chain
            return False
        for oid in origin_id:
            if (
                0 <= oid < len(reduced_node_chain_ids)
                and reduced_node_chain_ids[oid] == dest_chain
            ):
                return True
        return False
