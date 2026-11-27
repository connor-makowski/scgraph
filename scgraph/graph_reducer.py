"""Graph reduction: hide the pass-through nodes of a graph and search what is left.

WHAT IT ANSWERS

`reduce()` builds a smaller graph that gives the same shortest lengths. A pass-through
node offers no choice. A shortest route that enters it has one way to leave it. A node
is a pass-through node in two cases. In the first case, it has edges to exactly one
other node, and edges from at least one node. In the second case, it has edges to
exactly two other nodes, and every node with an edge into it is one of these two. An
edge from a node to itself does not count. After `reduce()`, the decorator `algorithm`
answers each query on the reduced graph and returns the path in the original graph.

Example: this graph has six nodes, with edges both ways.
    0-4: 2, 4-5: 3, 5-1: 4, 0-2: 6, 0-3: 6, 1-2: 6, 1-3: 6, 2-3: 6
Nodes 4 and 5 have two neighbours each, so they are pass-through nodes. Nodes 0 to 3
have three neighbours each, so they stay.

HOW THE DATA IS STORED

`is_reduced[u]` is True for a pass-through node, a "reduced" node. The other nodes are
"kept". A chain is a group of reduced nodes joined by edges, and
`reduced_node_chain_ids[u]` gives its number. A boundary node of a chain is a kept node
with an edge to or from the chain. `reduced_graph[a][b]` is the length of the shortest
route from node a to a kept node b whose inner nodes are all reduced. Node a is kept or
reduced, so the row of a reduced node lists the boundary nodes that it leads to.
`reduced_inverse_graph[b][a]` is the length of the same kind of route from a kept node
a to node b. The original `graph` does not change.

The hidden nodes of an edge of `reduced_graph` are the reduced nodes of its route.
`_hidden_next[x][b]` is the node after x on the route from x to b, and
`_hidden_previous[x][a]` is the node before x on the route from a to x.
`reduced_graph_connections[a][b]` lists the hidden nodes of the edge from a to b. It is
built from these pointers at its first read.

Example: `is_reduced` is True for nodes 4 and 5 only, and they form chain 0.
`reduced_graph[0]` is `{2: 6, 3: 6, 1: 9}`, and the edge from 0 to 1 hides `[4, 5]`.
`reduced_graph[4]` is `{0: 2, 1: 7}`. `reduced_inverse_graph[5]` is `{0: 5, 1: 4}`.

HOW A RUN GOES

1. The first pass marks the pass-through nodes.
2. Each later pass looks again at the kept nodes next to a reduced node. It counts as
   neighbours the kept nodes that a node reaches through reduced nodes. With
   `iterations=-1`, the default, the passes go on until one marks no new node.
   `iterations=1` runs one pass.
3. The reducer numbers the chains.
4. A Dijkstra search from each kept node goes through reduced nodes and stops at kept
   nodes. A second search on the reversed edges ends at each kept node. These searches
   fill `reduced_graph`, `reduced_inverse_graph` and the pointers.

Example of step 2: take the graph 0-1: 2, 1-2: 3, 2-3: 4, 0-3: 10, 0-4: 6, 4-3: 5,
with edges both ways. The first pass reduces nodes 1, 2 and 4. Every route from node 0
through reduced nodes then ends at node 3, so the second pass reduces node 0.

`run_with_reduced` handles four cases.
- An origin node and a destination node are in the same chain. The pure-Python build
  runs `dijkstra_on_graph` on the original graph, whatever the algorithm asked. The C++
  build runs the asked algorithm on the original graph. It runs Dijkstra for a
  hierarchy (`contraction_hierarchy`, `tnr`) and for a cached tree.
- The origin is reduced. A search in one direction starts at it and reads its row of
  `reduced_graph`. A bidirectional search starts instead from the boundary nodes in this
  row, with their distances as start distances.
- The destination is reduced. It is replaced by the boundary nodes of its row of
  `reduced_inverse_graph`, with their distances as exit distances.
- Both ends are kept. The search runs on the reduced graph as it is.
`contraction_hierarchy` and `tnr` do not go through `run_with_reduced`. Each method
routes a pair of one chain with `dijkstra_on_graph`, or searches its own hierarchy.
`expand_path` then puts the hidden nodes back between each pair of nodes of the path.
When the destination is
reduced, the nodes from the last boundary node to the destination are added.

Example: `dijkstra(origin_id=4, destination_id=1)` reads `reduced_graph[4]` and finds
the path `[4, 1]` of length 7. `_hidden_next[4][1]` is 5, so the result is
`[4, 5, 1]`. From node 2 to node 5, the destination becomes `{0: 5, 1: 4}`. The search
reaches node 1 at 6, for a total of 10, and the result is `[2, 1, 5]`.

WHY THE RESULT IS RIGHT

A route between two kept nodes splits at its kept nodes into pieces whose inner nodes
are reduced. `reduced_graph` holds the shortest such piece between each pair of nodes,
so a search on it finds the shortest length. The hidden nodes follow a shortest piece
too, so the expanded path has this length. A start or an end inside a chain adds the
exact length of a piece to a boundary node. Two nodes of one chain may be joined by a
route that never leaves the chain, so this case searches the original graph. Example:
the edge from 0 to 1 has the length 9 = 2 + 3 + 4 of the route 0, 4, 5, 1.
"""

import gc
import inspect
from collections.abc import Callable
from functools import wraps
from heapq import heappop, heappush
from typing import TYPE_CHECKING

from scgraph.errors import PathNotFoundError
from scgraph.graph_utils import (
    convert_node_input,
    check_node_id,
    _last_search_in_thread,
)

if TYPE_CHECKING:  # annotations only
    from scgraph.contraction_hierarchies import CHGraph


def algorithm(
    func: Callable | None = None,
    *,
    bidirectional: bool = False,
    name: str | None = None,
) -> Callable:
    """
    Function:

    - Decorator and registration helper for graph shortest path algorithms.
    - Transparently enables graph reduction support (same-chain handling, boundary entry solving, path expansion).
    - A decorated algorithm reads `self.search_graph` (and `self.search_inverse_graph` if bidirectional): the reduced graph after `reduce()`, else the original graph.
    - Can be used as a method decorator `@Graph.algorithm` or `@Graph.algorithm(bidirectional=True)`.
    - Can register external algorithms onto Graph via `@Graph.algorithm(name="custom_algo")`.
    - Reads the origin and the destination from the parameters `origin_id` and `destination_id`, or from the first two positions. Other names skip the handling of the reduced graph.
    """

    def decorator(fn):
        @wraps(fn)
        def wrapper(self, *args, **kwargs):
            # The first two arguments are the origin and the destination. The
            # algorithms test `isinstance(origin_id, int)`, so a numpy integer
            # becomes an int here.
            args = [
                convert_node_input(arg) if arg_id < 2 else arg
                for arg_id, arg in enumerate(args)
            ]
            for key in ("origin_id", "destination_id"):
                if key in kwargs:
                    kwargs[key] = convert_node_input(kwargs[key])
            if getattr(self, "reduced_graph", None) is None:
                return fn(self, *args, **kwargs)
            return GraphReducer.run_with_reduced(
                self, fn, *args, is_bidirectional=bidirectional, **kwargs
            )

        wrapper._is_graph_algorithm = True

        if name is not None:
            import scgraph.graph as _graph_mod

            if hasattr(_graph_mod, "Graph"):
                setattr(_graph_mod.Graph, name, wrapper)

        return wrapper

    if func is not None and callable(func):
        return decorator(func)
    return decorator


def list_hidden_nodes(
    pointers: list[dict[int, int] | None], node: int, root: int, inverse: bool
) -> list[int]:
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


def build_reduced_graph_connections(
    pointers: list[dict[int, int] | None], inverse: bool
) -> list[dict[int, list[int]] | None]:
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
                root: list_hidden_nodes(pointers, node, root, inverse)
                for root in roots
            }
        )
        for node, roots in enumerate(pointers)
    ]


def _without_gc(fn):
    # reduce() allocates one dict per node and per direction; the cyclic garbage
    # collector, triggered by these allocations, has nothing to collect there and
    # costs a fifth of the call on large networks. Collection is paused for the
    # call and the previous state restored; the skipped collection runs at the
    # caller's next allocation.
    @wraps(fn)
    def wrapper(self, *args, **kwargs):
        was_enabled = gc.isenabled()
        gc.disable()
        try:
            return fn(self, *args, **kwargs)
        finally:
            if was_enabled:
                gc.enable()

    return wrapper


class GraphReducer:
    # The two connection lists are built on first read and kept until the next
    # reduce(): scgraph itself reads the pointers (see list_hidden_nodes)
    @property
    def reduced_graph_connections(
        self,
    ) -> list[dict[int, list[int]] | None] | None:
        if getattr(self, "_reduced_graph_connections", None) is None:
            pointers = getattr(self, "_hidden_next", None)
            if pointers is None:
                return None
            self._reduced_graph_connections = build_reduced_graph_connections(
                pointers, False
            )
        return self._reduced_graph_connections

    @property
    def reduced_inverse_graph_connections(
        self,
    ) -> list[dict[int, list[int]] | None] | None:
        if getattr(self, "_reduced_inverse_graph_connections", None) is None:
            pointers = getattr(self, "_hidden_previous", None)
            if pointers is None:
                return None
            self._reduced_inverse_graph_connections = (
                build_reduced_graph_connections(pointers, True)
            )
        return self._reduced_inverse_graph_connections

    @_without_gc
    def reduce(self, iterations: int = -1) -> None:
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
            - Default: -1

        Returns:

        - None

        Raises:

        - `TypeError`: `iterations` is not an integer
        - `ValueError`: `iterations` is below -1
        """
        if not isinstance(iterations, int):
            raise TypeError(f"iterations must be an int, not {iterations!r}")
        if iterations < -1:
            raise ValueError(f"iterations must be -1 or more, not {iterations}")
        self.reset_cache()
        if iterations == 0:
            return

        self._ensure_inverse_graph()

        # 1. Identify pass-through nodes iteratively
        graph = self._graph
        inverse_graph = self._inverse_graph
        n = len(graph)
        is_reduced = [False] * n

        current_iter = 0
        # Nodes to examine in later passes (never read with one pass)
        dirty = None
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
                # Later passes can only change nodes next to a reduced node
                if iterations != 1:
                    dirty = bytearray(n)
                    for u in range(n):
                        if is_reduced[u]:
                            for v in graph[u]:
                                if not is_reduced[v]:
                                    dirty[v] = 1
                            for v in inverse_graph[u]:
                                if not is_reduced[v]:
                                    dirty[v] = 1
            else:
                # Subsequent iterations: find pass-through nodes on current reduced topology
                # Reducing u changes the flows of its own outflows and inflows
                # only, so only those are marked dirty: those after u are
                # examined in this pass, the others in the next one. The scan
                # keeps the increasing order of a scan of every node, so the
                # result is the same.
                u = dirty.find(1)
                while u != -1:
                    dirty[u] = 0
                    if is_reduced[u]:
                        u = dirty.find(1, u + 1)
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
                    if is_reduced[u]:
                        for w in outflows | inflows:
                            dirty[w] = 1
                    u = dirty.find(1, u + 1)

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

        # 3. Search from each non-reduced node a through reduced nodes: it gives
        # the reduced_graph edges a -> b to non-reduced nodes b, and the
        # reduced_inverse_graph edges a -> b into reduced nodes b (whose own
        # searches would cost O(L) each on a chain of L nodes). Hidden nodes are
        # stored as pointers from these searches (see list_hidden_nodes).
        self.reduced_graph = [{} for _ in range(len(graph))]
        self.reduced_inverse_graph = [{} for _ in range(len(graph))]
        self._hidden_previous = [None] * len(graph)
        self._reduced_inverse_graph_connections = None
        reduced_graph = self.reduced_graph
        reduced_inverse_graph = self.reduced_inverse_graph
        previous_nodes = self._hidden_previous

        for a in range(len(graph)):
            if is_reduced[a]:
                continue
            best_dist = {a: 0}
            predecessor = {}
            open_leaves = [(0, a)]

            while open_leaves:
                dist, u = heappop(open_leaves)
                if dist > best_dist[u]:
                    continue

                if u != a:
                    if predecessor[u] != a:
                        if previous_nodes[u] is None:
                            previous_nodes[u] = {}
                        previous_nodes[u][a] = predecessor[u]
                    if is_reduced[u]:
                        reduced_inverse_graph[u][a] = dist
                    else:
                        # Boundary non-reduced node. Record connection.
                        reduced_graph[a][u] = dist
                        continue

                for v, w in graph[u].items():
                    new_dist = dist + w
                    if v not in best_dist or new_dist < best_dist[v]:
                        best_dist[v] = new_dist
                        predecessor[v] = u
                        heappush(open_leaves, (new_dist, v))

        # 4. Inverse search into each non-reduced node b: it gives the
        # reduced_inverse_graph edges a -> b from non-reduced nodes a, and the
        # reduced_graph edges a -> b from reduced nodes a.
        self._hidden_next = [None] * len(graph)
        self._reduced_graph_connections = None  # rebuilt on first read
        next_nodes = self._hidden_next

        for b in range(len(graph)):
            if is_reduced[b]:
                continue
            best_dist = {b: 0}
            predecessor = {}
            open_leaves = [(0, b)]

            while open_leaves:
                dist, u = heappop(open_leaves)
                if dist > best_dist[u]:
                    continue

                if u != b:
                    if predecessor[u] != b:
                        if next_nodes[u] is None:
                            next_nodes[u] = {}
                        next_nodes[u][b] = predecessor[u]
                    if is_reduced[u]:
                        reduced_graph[u][b] = dist
                    else:
                        # Boundary non-reduced node reaching b
                        reduced_inverse_graph[b][u] = dist
                        continue

                for v, w in inverse_graph[u].items():
                    new_dist = dist + w
                    if v not in best_dist or new_dist < best_dist[v]:
                        best_dist[v] = new_dist
                        predecessor[v] = u
                        heappush(open_leaves, (new_dist, v))

    def wrap_heuristic(
        self,
        heuristic_fn: Callable[["CHGraph", int], int | float] | None = None,
    ) -> Callable[["CHGraph", int], int | float] | None:
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

    def _limit_transit_nodes(self, num_transit_nodes: int) -> int:
        """Return the number of transit nodes of the TNR graph of this graph:
        `num_transit_nodes`, or at most the number of nodes left after
        `reduce()`. Same rule as GraphReducer::create_tnr_graph (C++)."""
        is_reduced = getattr(self, "is_reduced", None)
        if is_reduced is None:
            return num_transit_nodes
        # Transit nodes are the last contracted, and reduced nodes are
        # contracted first: no more transit nodes than nodes left
        return min(num_transit_nodes, max(1, is_reduced.count(False)))

    def run_with_reduced(
        self, func: Callable, *args, is_bidirectional: bool = False, **kwargs
    ) -> object:
        """
        Function:

        - Run a graph routing function on the reduced graph.
        - Same-chain queries route directly on the unreduced graph.
        - Other algorithms: reduced destinations are replaced by their boundary entry nodes (reduced_inverse_graph); for bidirectional algorithms, reduced origins are also replaced by the boundary nodes they reach (reduced_graph).

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

        # The steps below read `is_reduced` at each origin and destination node.
        # The search checks its arguments only later, so this loop checks the
        # node ids first. A dict gives its node ids when the loop reads it.
        is_reduced = self.is_reduced
        for node_input, name in (
            (origin_id, "Origin node"),
            (destination_id, "Destination node"),
        ):
            node_ids = (
                [node_input] if isinstance(node_input, int) else node_input
            )
            if isinstance(node_ids, (set, list, dict)):
                for node_id in node_ids:
                    check_node_id(node_id, len(is_reduced), name)

        # 1. Same-chain check: solve on unreduced graph with dijkstra
        if destination_id is not None and self.is_same_chain(
            origin_id, destination_id
        ):
            length_only = kwargs.get("length_only", False)
            if len(args) > 2:  # length_only may also be passed by position
                length_only = (
                    inspect.signature(func)
                    .bind(self, *args, **kwargs)
                    .arguments.get("length_only", length_only)
                )
            # A decorated algorithm may get a C++ Graph as `self`: call this
            # method from its class.
            return GraphReducer._dijkstra_on_same_chain(
                self, origin_id, destination_id, length_only
            )

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

        # Bidirectional searches must start and end on non-reduced nodes: only
        # there is reduced_inverse_graph exactly the reverse of reduced_graph.
        # Their reduced origins are replaced by the boundary nodes they reach
        # (rows of reduced_graph); reduced destinations are replaced by their
        # boundary entry nodes for every search (step 3). One-sided searches
        # keep a reduced origin: they only read reduced_graph.
        origin_dict = (
            {origin_id: 0.0}
            if isinstance(origin_id, int)
            else (
                {oid: 0.0 for oid in origin_id}
                if isinstance(origin_id, (set, list))
                else (origin_id if isinstance(origin_id, dict) else None)
            )
        )
        origin_map = {}
        if (
            is_bidirectional
            and origin_dict is not None
            and any(is_reduced[oid] for oid in origin_dict)
        ):
            effective_origin_dict = {}
            for oid, odist in origin_dict.items():
                exits = (
                    self.reduced_graph[oid].items()
                    if is_reduced[oid]
                    else [(oid, 0.0)]
                )
                for exit_u, exit_dist in exits:
                    tot = odist + exit_dist
                    if (
                        exit_u not in effective_origin_dict
                        or tot < effective_origin_dict[exit_u]
                    ):
                        effective_origin_dict[exit_u] = tot
                        origin_map[exit_u] = oid
            if not effective_origin_dict:
                raise PathNotFoundError(
                    "Something went wrong, the origin and destination nodes are not connected."
                )
            args = list(args)
            if "origin_id" in kwargs or not args:
                kwargs = dict(kwargs)
                kwargs["origin_id"] = effective_origin_dict
            else:
                args[0] = effective_origin_dict

        def restore_origin(path):
            if (
                path
                and path[0] in origin_map
                and origin_map[path[0]] != path[0]
            ):
                return [origin_map[path[0]]] + path
            return path

        # 2. Unreduced destinations (or None)
        if dest_dict is None or all(
            not is_reduced[did] for did in dest_dict.keys()
        ):
            res = func(self, *args, **kwargs)
            if isinstance(res, dict) and "path" in res:
                res["path"] = self.expand_path(restore_origin(res["path"]))
            return res

        # 3. Reduced destination(s)
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
            raise PathNotFoundError(
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
            expanded_path = self.expand_path(restore_origin(res["path"]))
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

    def _dijkstra_on_same_chain(
        self,
        origin_id: int | set[int] | dict[int, int | float],
        destination_id: int | set[int] | dict[int, int | float],
        length_only: bool,
    ) -> dict:
        """Route between nodes of one chain on the unreduced graph. The reduced
        graph has no route inside a chain. `contraction_hierarchy`, `tnr` and
        `run_with_reduced` call this method."""
        res = GraphReducer.dijkstra_on_graph(
            self.unreduced_graph, origin_id, destination_id
        )
        if length_only:
            res["path"] = []
        return res

    @staticmethod
    def dijkstra_on_graph(
        graph: list[dict[int, int | float]],
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
        _last_search_in_thread.node_scans = node_scans
        if best_dest_node == -1 or best_dist == float("inf"):
            raise PathNotFoundError(
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
        next_nodes = self._hidden_next
        previous_nodes = self._hidden_previous
        new_path = []
        append = new_path.append
        extend = new_path.extend
        for i in range(len(path) - 1):
            u = path[i]
            v = path[i + 1]
            append(u)
            expanded = False
            pass_throughs = list_hidden_nodes(next_nodes, u, v, False)
            if pass_throughs:
                extend(pass_throughs)
                expanded = True
            if not expanded:
                pass_throughs = list_hidden_nodes(previous_nodes, v, u, True)
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
