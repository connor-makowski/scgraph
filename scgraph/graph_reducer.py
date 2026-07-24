from heapq import heappop, heappush
from functools import wraps


def use_reduced(func):
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        reduced_graph = getattr(self, "reduced_graph", None)
        if reduced_graph is None:
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
        self.is_reduced = [False] * len(self.graph)
        graph = self.graph
        inverse_graph = self.inverse_graph
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

        # 2. Build reduced graph and connections
        self.reduced_graph = [{} for _ in range(len(graph))]
        self.reduced_graph_connections = [None] * len(graph)
        reduced_graph = self.reduced_graph
        reduced_graph_connections = self.reduced_graph_connections

        for A in range(len(graph)):
            if is_reduced[A]:
                continue

            best_dist = {}
            open_leaves = [(0, A, [])]

            while open_leaves:
                dist, u, path = heappop(open_leaves)
                if u in best_dist and best_dist[u] <= dist:
                    continue
                best_dist[u] = dist

                if u != A and not is_reduced[u]:
                    # This is a boundary non-reduced node. Record connection.
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

    def __get_temp_connections__(
        self,
        start_node: int,
        direction: str = "out",
        target_nodes: set[int] = None,
    ) -> dict:
        """
        Function:

        - Find temporary connections into or out of a node by traversing pass-through nodes
          until a boundary node (non-reduced or target node) is reached.

        Required Arguments:

        - `start_node`
            - Type: int
            - What: The node to start traversing from

        Optional Arguments:

        - `direction`
            - Type: str
            - What: Direction of traversal ("out" for forward, "in" for backward)
            - Default: "out"
        - `target_nodes`
            - Type: set[int]
            - What: Nodes that must act as non-reduced boundaries even if they are reduced
            - Default: None

        Returns:

        - A dictionary of connection destination keys mapped to their shortest distances and intermediate path lists.
        """
        if target_nodes is None:
            target_nodes = set()

        adj_graph = self.graph if direction == "out" else self.inverse_graph
        is_reduced = self.is_reduced

        best_dist = {}
        open_leaves = [(0, start_node, [])]

        connections = {}

        while open_leaves:
            dist, u, path = heappop(open_leaves)
            if u in best_dist and best_dist[u] <= dist:
                continue
            best_dist[u] = dist

            if u != start_node and (not is_reduced[u] or u in target_nodes):
                connections[u] = (dist, path)
                continue

            for v, w in adj_graph[u].items():
                new_dist = dist + w
                if v not in best_dist or new_dist < best_dist[v]:
                    new_path = path if u == start_node else path + [u]
                    heappush(open_leaves, (new_dist, v, new_path))

        return connections

    def __run_with_reduced__(self, func, *args, **kwargs):
        """
        Function:

        - Run a graph routing function on the reduced graph.
        - Applies query-specific temporary modifications if the origin or destination is reduced,
          and automatically reconstructs the full path afterward.

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

        origin_ids = {origin_id} if isinstance(origin_id, int) else origin_id

        target_nodes = set(origin_ids)
        if destination_id is not None:
            target_nodes.add(destination_id)

        is_reduced = self.is_reduced
        nodes_to_process = set()
        for oid in origin_ids:
            if is_reduced[oid]:
                nodes_to_process.add(oid)
        if destination_id is not None and is_reduced[destination_id]:
            nodes_to_process.add(destination_id)

        restore_reduced_graph = {}
        restore_reduced_graph_connections = {}

        if nodes_to_process:
            self.__ensure_inverse_graph__()
            reduced_graph = self.reduced_graph
            reduced_graph_connections = self.reduced_graph_connections
            for node in nodes_to_process:
                # Outgoing
                outgoing = self.__get_temp_connections__(
                    node, direction="out", target_nodes=target_nodes
                )
                if node not in restore_reduced_graph:
                    restore_reduced_graph[node] = dict(reduced_graph[node])
                for v, (dist, path) in outgoing.items():
                    reduced_graph[node][v] = dist
                    if path:
                        if node not in restore_reduced_graph_connections:
                            restore_reduced_graph_connections[node] = (
                                dict(reduced_graph_connections[node])
                                if reduced_graph_connections[node] is not None
                                else None
                            )
                        if reduced_graph_connections[node] is None:
                            reduced_graph_connections[node] = {}
                        reduced_graph_connections[node][v] = path

                # Incoming
                incoming = self.__get_temp_connections__(
                    node, direction="in", target_nodes=target_nodes
                )
                for u, (dist, path) in incoming.items():
                    forward_path = list(reversed(path))
                    if u not in restore_reduced_graph:
                        restore_reduced_graph[u] = dict(reduced_graph[u])
                    reduced_graph[u][node] = dist
                    if forward_path:
                        if u not in restore_reduced_graph_connections:
                            restore_reduced_graph_connections[u] = (
                                dict(reduced_graph_connections[u])
                                if reduced_graph_connections[u] is not None
                                else None
                            )
                        if reduced_graph_connections[u] is None:
                            reduced_graph_connections[u] = {}
                        reduced_graph_connections[u][node] = forward_path

        original_graph = self.graph
        self.graph = self.reduced_graph
        try:
            if nodes_to_process and func.__name__ == "cached_shortest_path":
                length_only = (
                    kwargs.get("length_only", False)
                    if "length_only" in kwargs
                    else (args[2] if len(args) > 2 else False)
                )
                shortest_path_tree = self.get_shortest_path_tree(
                    origin_id=origin_id
                )
                res = self.get_tree_path(
                    origin_id=origin_id,
                    destination_id=destination_id,
                    tree_data=shortest_path_tree,
                    length_only=length_only,
                )
            elif nodes_to_process and func.__name__ in (
                "contraction_hierarchy",
                "tnr",
            ):
                length_only = (
                    kwargs.get("length_only", False)
                    if "length_only" in kwargs
                    else (args[2] if len(args) > 2 else False)
                )
                res = self.dijkstra(
                    origin_id=origin_id, destination_id=destination_id
                )
                if length_only:
                    res = {"length": res["length"]}
            else:
                res = func(self, *args, **kwargs)

            if isinstance(res, dict) and "path" in res:
                res["path"] = self.__expand_path__(res["path"])
        finally:
            self.graph = original_graph
            for u, val in restore_reduced_graph.items():
                self.reduced_graph[u] = val
            for u, val in restore_reduced_graph_connections.items():
                self.reduced_graph_connections[u] = val

        return res

    def __expand_path__(self, path: list[int]) -> list[int]:
        """
        Function:

        - Expand a path of non-pass-through nodes to restore all intermediate pass-through nodes.

        Required Arguments:

        - `path`
            - Type: list[int]
            - What: The path in the reduced graph

        Returns:

        - The fully expanded path matching the original graph
        """
        conns = getattr(self, "reduced_graph_connections", None)
        if conns is None:
            return path
        new_path = []
        append = new_path.append
        extend = new_path.extend
        for i in range(len(path) - 1):
            u = path[i]
            v = path[i + 1]
            append(u)
            u_conn = conns[u]
            if u_conn is not None:
                pass_throughs = u_conn.get(v)
                if pass_throughs:
                    extend(pass_throughs)
        if path:
            append(path[-1])
        return new_path
