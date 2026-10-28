from heapq import heappop, heappush
from functools import wraps


def algorithm(
    func=None,
    *,
    bidirectional: bool = False,
    name: str | None = None,
):
    """
    Function:

    - Decorator and registration helper for graph shortest path algorithms.
    - Transparently enables graph reduction support (same-chain handling, boundary entry solving, path expansion).
    - Can be used as a method decorator `@Graph.algorithm` or `@Graph.algorithm(bidirectional=True)`.
    - Can register external algorithms onto Graph via `@Graph.algorithm(name="custom_algo")`.
    """

    def decorator(fn):
        @wraps(fn)
        def wrapper(self, *args, **kwargs):
            if getattr(self, "reduced_graph", None) is None:
                return fn(self, *args, **kwargs)
            return GraphReducer.run_with_reduced(
                self, fn, *args, is_bidirectional=bidirectional, **kwargs
            )

        wrapper.__is_graph_algorithm__ = True
        wrapper.__bidirectional__ = bidirectional

        if name is not None:
            import scgraph.graph as _graph_mod

            if hasattr(_graph_mod, "Graph"):
                setattr(_graph_mod.Graph, name, wrapper)

        return wrapper

    if func is not None and callable(func):
        return decorator(func)
    return decorator


def hidden_nodes(pointers, node: int, root: int, inverse: bool) -> list[int]:
    """
    Function:

    - Hidden nodes of the reduced edge node -> root (root -> node if `inverse`),
      in path order.
    - `pointers[x][root]` is the node after x on the path from x to the
      non-reduced node root (before x on the path from root to x if `inverse`).
      The pointers toward one root come from one shortest path tree, so
      following them always ends.
    """
    path = []
    step = pointers[node]
    while step is not None and root in step:
        node = step[root]
        path.append(node)
        step = pointers[node]
    if inverse:
        path.reverse()
    return path


def connections(pointers, inverse: bool) -> list[dict[int, list[int]] | None]:
    """
    Function:

    - reduced_graph_connections (reduced_inverse_graph_connections if
      `inverse`) as a list built from the pointers: each node's entry is None
      or {b: [hidden nodes]} for the reduced edge a -> b (b -> a if `inverse`).
    """
    return [
        (
            None
            if roots is None
            else {
                root: hidden_nodes(pointers, node, root, inverse)
                for root in roots
            }
        )
        for node, roots in enumerate(pointers)
    ]


class GraphReducer:
    # The two connection lists are built on first read and kept until the next
    # reduce(): scgraph itself reads the pointers (see hidden_nodes)
    @property
    def reduced_graph_connections(
        self,
    ) -> list[dict[int, list[int]] | None] | None:
        if getattr(self, "__reduced_graph_connections__", None) is None:
            pointers = getattr(self, "__hidden_next__", None)
            if pointers is None:
                return None
            self.__reduced_graph_connections__ = connections(pointers, False)
        return self.__reduced_graph_connections__

    @reduced_graph_connections.setter
    def reduced_graph_connections(self, value) -> None:
        self.__reduced_graph_connections__ = value

    @property
    def reduced_inverse_graph_connections(
        self,
    ) -> list[dict[int, list[int]] | None] | None:
        if getattr(self, "__reduced_inverse_graph_connections__", None) is None:
            pointers = getattr(self, "__hidden_previous__", None)
            if pointers is None:
                return None
            self.__reduced_inverse_graph_connections__ = connections(
                pointers, True
            )
        return self.__reduced_inverse_graph_connections__

    @reduced_inverse_graph_connections.setter
    def reduced_inverse_graph_connections(self, value) -> None:
        self.__reduced_inverse_graph_connections__ = value

    def reduce(self, iterations: int = 1) -> None:
        """
        Function:

        - Reduce the graph by bypassing pass-through nodes and summing intermediate weights.
        - Supports iterative reduction passes.
        - Sets self.reduced_graph, self.reduced_graph_connections, self.reduced_inverse_graph,
          self.reduced_inverse_graph_connections, self.reduced_node_chain_ids, and self.is_reduced.

        Optional Arguments:

        - `iterations`:
            - Type: int
            - What: Number of reduction iterations to perform.
              - `0`: No reduction is done.
              - `-1`: Reduce iteratively until convergence (no new nodes can be reduced).
              - `> 0`: Reduce iteratively up to the minimum of convergence and the specified count.
            - Default: 1

        Returns:

        - None
        """
        self.reset_cache()
        if iterations == 0:
            return

        self.__ensure_inverse_graph__()

        # 1. Identify pass-through nodes iteratively
        graph = self.__graph__
        inverse_graph = self.__inverse_graph__
        n = len(graph)
        is_reduced = [False] * n

        current_iter = 0
        while True:
            newly_reduced_count = 0
            if current_iter == 0:
                for u in range(n):
                    out_dict = graph[u]
                    in_dict = inverse_graph[u]

                    out_len = len(out_dict) - (1 if u in out_dict else 0)
                    if out_len == 1:
                        in_len = len(in_dict) - (1 if u in in_dict else 0)
                        if in_len >= 1:
                            is_reduced[u] = True
                            newly_reduced_count += 1
                    elif out_len == 2:
                        in_len = len(in_dict) - (1 if u in in_dict else 0)
                        if in_len > 0:
                            outflows = {v for v in out_dict if v != u}
                            inflows = {v for v in in_dict if v != u}
                            if inflows.issubset(outflows):
                                is_reduced[u] = True
                                newly_reduced_count += 1
            else:
                # Subsequent iterations: find pass-through nodes on current reduced topology
                for u in range(n):
                    if is_reduced[u]:
                        continue

                    # Outflows from u through is_reduced nodes
                    outflows = set()
                    queue = [u]
                    visited = {u}
                    while queue:
                        curr = queue.pop()
                        if curr != u and not is_reduced[curr]:
                            outflows.add(curr)
                            continue
                        for v in graph[curr]:
                            if v not in visited:
                                visited.add(v)
                                queue.append(v)

                    # Inflows to u through is_reduced nodes
                    inflows = set()
                    queue = [u]
                    visited = {u}
                    while queue:
                        curr = queue.pop()
                        if curr != u and not is_reduced[curr]:
                            inflows.add(curr)
                            continue
                        for v in inverse_graph[curr]:
                            if v not in visited:
                                visited.add(v)
                                queue.append(v)

                    out_len = len(outflows)
                    in_len = len(inflows)
                    if out_len == 1:
                        if in_len >= 1:
                            is_reduced[u] = True
                            newly_reduced_count += 1
                    elif out_len == 2:
                        if in_len > 0:
                            if inflows.issubset(outflows):
                                is_reduced[u] = True
                                newly_reduced_count += 1

            current_iter += 1

            if newly_reduced_count == 0:
                break
            if iterations != -1 and current_iter >= iterations:
                break

        self.is_reduced = is_reduced

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

        # 3. Build reduced graph (outbound from all nodes). Hidden nodes are
        # stored as pointers from the searches rooted at non-reduced nodes (see
        # hidden_nodes): the search from a non-reduced node A gives those of the
        # reduced_inverse_graph edges A -> B.
        self.reduced_graph = [{} for _ in range(len(graph))]
        self.__hidden_previous__ = [None] * len(graph)
        self.reduced_inverse_graph_connections = None  # rebuilt on first read
        reduced_graph = self.reduced_graph
        previous_nodes = self.__hidden_previous__

        for A in range(len(graph)):
            best_dist = {A: 0}
            predecessor = {}
            open_leaves = [(0, A)]
            is_root = not is_reduced[A]

            while open_leaves:
                dist, u = heappop(open_leaves)
                if dist > best_dist[u]:
                    continue

                if is_root and u != A and predecessor[u] != A:
                    if previous_nodes[u] is None:
                        previous_nodes[u] = {}
                    previous_nodes[u][A] = predecessor[u]

                if u != A and not is_reduced[u]:
                    # Boundary non-reduced node. Record connection.
                    reduced_graph[A][u] = dist
                    continue

                for v, w in graph[u].items():
                    new_dist = dist + w
                    if v not in best_dist or new_dist < best_dist[v]:
                        best_dist[v] = new_dist
                        predecessor[v] = u
                        heappush(open_leaves, (new_dist, v))

        # 4. Build reduced inverse graph (inbound into all nodes). The search
        # from a non-reduced node B gives the hidden nodes of the reduced_graph
        # edges A -> B.
        self.reduced_inverse_graph = [{} for _ in range(len(graph))]
        self.__hidden_next__ = [None] * len(graph)
        self.reduced_graph_connections = None  # rebuilt on first read
        reduced_inverse_graph = self.reduced_inverse_graph
        next_nodes = self.__hidden_next__

        for B in range(len(graph)):
            best_dist = {B: 0}
            predecessor = {}
            open_leaves = [(0, B)]
            is_root = not is_reduced[B]

            while open_leaves:
                dist, u = heappop(open_leaves)
                if dist > best_dist[u]:
                    continue

                if is_root and u != B and predecessor[u] != B:
                    if next_nodes[u] is None:
                        next_nodes[u] = {}
                    next_nodes[u][B] = predecessor[u]

                if u != B and not is_reduced[u]:
                    # Boundary non-reduced node reaching B
                    reduced_inverse_graph[B][u] = dist
                    continue

                for v, w in inverse_graph[u].items():
                    new_dist = dist + w
                    if v not in best_dist or new_dist < best_dist[v]:
                        best_dist[v] = new_dist
                        predecessor[v] = u
                        heappush(open_leaves, (new_dist, v))

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

    def run_with_reduced(
        self, func, *args, is_bidirectional: bool = False, **kwargs
    ):
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
            res = GraphReducer.dijkstra_on_graph(
                self.unreduced_graph, origin_id, destination_id
            )
            if length_only:
                res.pop("path", None)
            return res

        is_reduced = self.is_reduced

        # 2. Bidirectional algorithms, Contraction Hierarchies, and Transit Node Routing
        is_bidirectional = (
            is_bidirectional
            or getattr(func, "__bidirectional__", False)
            or func.__name__
            in (
                "bidirectional_dijkstra",
                "bidirectional_buckets",
                "contraction_hierarchy",
                "tnr",
            )
        )
        if is_bidirectional:
            res = func(self, *args, **kwargs)
            if isinstance(res, dict) and "path" in res:
                res["path"] = self.expand_path(res["path"])
            return res

        dest_dict = (
            {destination_id: 0.0}
            if isinstance(destination_id, int)
            else (
                {did: 0.0 for did in destination_id}
                if isinstance(destination_id, (set, list))
                else (
                    destination_id if isinstance(destination_id, dict) else None
                )
            )
        )

        # 3. One-sided algorithms with unreduced destinations (or None)
        if dest_dict is None or all(
            not is_reduced[did] for did in dest_dict.keys()
        ):
            res = func(self, *args, **kwargs)
            if isinstance(res, dict) and "path" in res:
                res["path"] = self.expand_path(res["path"])
            return res

        # 4. One-sided algorithm with reduced destination(s)
        # Build effective destination dict expanding reduced destination nodes into boundary entries
        boundary_entries_map = {}
        effective_dest_dict = {}
        for did, ddist in dest_dict.items():
            if not is_reduced[did]:
                if (
                    did not in effective_dest_dict
                    or ddist < effective_dest_dict[did]
                ):
                    effective_dest_dict[did] = ddist
                    boundary_entries_map[did] = (did, did)
            else:
                entry_nodes = self.reduced_inverse_graph[did]
                if not entry_nodes:
                    continue
                for entry_u, entry_dist in entry_nodes.items():
                    tot = ddist + entry_dist
                    if (
                        entry_u not in effective_dest_dict
                        or tot < effective_dest_dict[entry_u]
                    ):
                        effective_dest_dict[entry_u] = tot
                        boundary_entries_map[entry_u] = (did, entry_u)

        if not effective_dest_dict:
            raise Exception(
                "Something went wrong, the origin and destination nodes are not connected."
            )

        call_kwargs = dict(kwargs)
        call_args = list(args)
        if "destination_id" in call_kwargs:
            call_kwargs["destination_id"] = effective_dest_dict
        elif len(call_args) > 1:
            call_args[1] = effective_dest_dict
        else:
            call_kwargs["destination_id"] = effective_dest_dict

        res = func(self, *call_args, **call_kwargs)
        if not isinstance(res, dict):
            return res

        if "path" in res and res["path"]:
            expanded_path = self.expand_path(res["path"])
            reached_boundary = expanded_path[-1]
            if reached_boundary in boundary_entries_map:
                orig_did, best_entry = boundary_entries_map[reached_boundary]
                if orig_did != reached_boundary:
                    # Hidden nodes of the reduced edge best_entry -> orig_did,
                    # best_entry being the last node of expanded_path
                    tail = self.expand_path([best_entry, orig_did])[1:]
                    expanded_path = expanded_path + tail
            res["path"] = expanded_path

        return res

    __run_with_reduced__ = run_with_reduced

    @staticmethod
    def dijkstra_on_graph(
        graph: list[dict[int, float]],
        origin_id: int | set[int] | dict[int, int | float],
        destination_id: int | set[int] | dict[int, int | float],
    ) -> dict:
        """
        Function:

        - Internal Dijkstra solver on a specified graph dictionary list (used for same-chain routing on unreduced graph).
        """
        origin_dict = (
            {origin_id: 0.0}
            if isinstance(origin_id, int)
            else (
                {oid: 0.0 for oid in origin_id}
                if isinstance(origin_id, (set, list))
                else origin_id
            )
        )
        dest_dict = (
            {destination_id: 0.0}
            if isinstance(destination_id, int)
            else (
                {did: 0.0 for did in destination_id}
                if isinstance(destination_id, (set, list))
                else destination_id
            )
        )

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
                for (
                    connected_id,
                    connected_distance,
                ) in graph[current_id].items():
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
        if best_dest_node == -1 or best_dist == float("inf"):
            raise Exception(
                "Something went wrong, the origin and destination nodes are not connected."
            )

        path = []
        curr = best_dest_node
        while curr != -1:
            path.append(curr)
            curr = predecessor[curr]
        path.reverse()

        return {
            "path": path,
            "length": best_dist,
        }

    __dijkstra_on_graph__ = dijkstra_on_graph

    def expand_path(self, path: list[int]) -> list[int]:
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
        if getattr(self, "reduced_graph", None) is None:
            return path
        next_nodes = self.__hidden_next__
        previous_nodes = self.__hidden_previous__
        new_path = []
        append = new_path.append
        extend = new_path.extend
        for i in range(len(path) - 1):
            u = path[i]
            v = path[i + 1]
            append(u)
            expanded = False
            pass_throughs = hidden_nodes(next_nodes, u, v, False)
            if pass_throughs:
                extend(pass_throughs)
                expanded = True
            if not expanded:
                pass_throughs = hidden_nodes(previous_nodes, v, u, True)
                if pass_throughs:
                    extend(pass_throughs)
        if path:
            append(path[-1])
        return new_path

    def is_same_chain(
        self,
        origin_id: int | set[int] | list[int] | dict[int, int | float],
        destination_id: (
            int | set[int] | list[int] | dict[int, int | float] | None
        ),
    ) -> bool:
        """
        Function:

        - Check whether any origin node and any destination node belong to the same reduced chain.

        Required Arguments:

        - `origin_id`
            - Type: int | set[int] | list[int] | dict[int, int | float]
            - What: The id(s) of the origin node(s)
        - `destination_id`
            - Type: int | set[int] | list[int] | dict[int, int | float] | None
            - What: The id(s) of the destination node(s)

        Returns:

        - True if both origin and destination are reduced nodes and share the same chain_id, False otherwise.
        """
        reduced_node_chain_ids = getattr(self, "reduced_node_chain_ids", None)
        if reduced_node_chain_ids is None or destination_id is None:
            return False

        orig_ids = (
            [origin_id]
            if isinstance(origin_id, int)
            else (
                list(origin_id.keys())
                if isinstance(origin_id, dict)
                else list(origin_id)
            )
        )
        dest_ids = (
            [destination_id]
            if isinstance(destination_id, int)
            else (
                list(destination_id.keys())
                if isinstance(destination_id, dict)
                else list(destination_id)
            )
        )

        n = len(reduced_node_chain_ids)
        for s in orig_ids:
            if not (0 <= s < n):
                continue
            s_chain = reduced_node_chain_ids[s]
            if s_chain is None:
                continue
            for t in dest_ids:
                if 0 <= t < n and reduced_node_chain_ids[t] == s_chain:
                    return True
        return False
