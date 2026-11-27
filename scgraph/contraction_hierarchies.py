"""Contraction Hierarchies (CH): shortest paths on a graph prepared once.

WHAT IT ANSWERS

`CHGraph.search` returns the shortest route between an origin and a destination, as
`{"path": [...], "length": ...}`. The origin and the destination take the forms of the
searches of `Graph`: one node id, a set of node ids, or a dict of start or exit
distances. The search raises `PathNotFoundError` when no route exists.
`Graph.contraction_hierarchy` builds a `CHGraph` from `search_graph` at its first query
and keeps it.

Example: four nodes form a ring, with edges both ways: 0-1: 2, 0-3: 3, 1-2: 6, 2-3: 7.
The shortest route from node 1 to node 3 is `[1, 0, 3]`, of length 5.

HOW THE DATA IS STORED

The preprocessing contracts the nodes one at a time. To contract a node v is to remove
it from the graph that is left. For two neighbours u and w of v, the contraction adds a
shortcut when the route u, v, w may be the only shortest route from u to w. A shortcut
is an edge from u to w with the length of this route. `ranks[v]` is the position of v in
the order of contraction, from 0. `shortcuts[(u, w)]` is the node v that the shortcut
from u to w skips. `forward_graph[u]` holds the edges from u to the nodes of higher rank,
shortcuts included. `backward_graph[w]` holds the edges into w from the nodes of higher
rank, and `backward_graph[w][u]` is the weight of the edge from u to w.

Example: the order is 0, 1, 2, 3. The contraction of node 0 adds the shortcuts from 1 to
3 and from 3 to 1, of length 5, so `shortcuts` is `{(1, 3): 0, (3, 1): 0}`.
`forward_graph[1]` is `{2: 6, 3: 5}`, and `backward_graph[2]` is `{3: 7}`.

HOW A RUN GOES

Order. A priority queue holds the nodes that are not contracted. The first key of a node
is its number of edges in and out. The node at the head of the queue gets a new value,
`heuristic_fn(self, node)`, unless its value is up to date. If this value is above the
next key in the queue, the node goes back with this value. Otherwise, the node is
contracted and gets the next rank. A contraction marks the neighbours of the node for a
new value. By default, `default_heuristic` gives the number of shortcuts needed, minus
the number of edges in and out of the node, plus the number of its edges to or from
contracted nodes.

Witness search. For a node v and a route u, v, w, a witness is another route from u to w
that is not longer. An edge from u to w that is not longer is a witness. Otherwise a
Dijkstra search from u, which avoids v and the contracted nodes, looks for one. It goes
no further than the longest route through v that it checks. It also stops after it has
scanned `settled_limit` nodes (default 50). A shortcut is added when this search finds
no witness.

Query. `search` runs two Dijkstra searches that only go up in rank. The forward search
starts at the origin and reads `forward_graph`. The backward search starts at the
destination and reads `backward_graph`. They take one step each in turn. When one side
lowers the distance of a node that the other side has reached, the sum of the two
distances is a candidate length. A side stops when the distance it takes from its queue
is above the best length. `_unpack_shortcut` then replaces each shortcut from u to w
by the edges from u to v and from v to w, with v = `shortcuts[(u, w)]`, and repeats this
on the two edges.

Example: every node starts with the key 4, and node 0 comes first by its id. Its value
is 2 shortcuts - 2 edges in - 2 edges out = -2. This value is not above the next key, 4,
so node 0 gets rank 0. The witness search from node 1 looks no further than 5, and the
route 1, 2, 3 has the length 13, so the shortcut from 1 to 3 is added. Node 1 then gets
the value -4 and rank 1, node 2 rank 2, and node 3 rank 3. From 1 to 3, the forward
search follows the shortcut to node 3, at 5. The path `[1, 3]` unpacks to `[1, 0, 3]`.
From 0 to 2, the forward search reaches node 1 at 2 and node 3 at 3. The backward search
reaches node 3 at 7, for a candidate of 10. Then the forward search reaches node 2 at 8
through node 1, and the result is `[0, 1, 2]`, of length 8.

WHY THE RESULT IS RIGHT

A shortcut has the length of a route through a contracted node, so every edge of the
hierarchy stands for a route of the original graph. The contractions keep the shortest
distances between the nodes that are left. A witness search that stops early only adds
shortcuts that are not needed. So for each pair of nodes, a shortest route exists that
goes up in rank, then down. The forward search finds its upward part, and the backward
search finds its downward part. The two meet at its highest node. The weights are not
negative, so a distance that a side takes later from its queue is never lower. A side
can then stop once it passes the best length. Example: the route 1, 0, 3 goes down to
node 0, of rank 0. The shortcut from 1 to 3 replaces it by a route that goes up from
rank 1 to rank 3.
"""

import json
from heapq import heappush, heappop, heapify
from collections.abc import Callable
from scgraph.errors import PathNotFoundError
from scgraph.graph_utils import (
    GraphUtils,
    GraphModifiers,
    normalize_node_input,
)


class CHGraphIO:
    def save_as_chjson(self, filename: str) -> None:
        """
        Function:

        - Save the current CHGraph as a JSON file

        Required Arguments:

        - `filename`
            - Type: str
            - What: The filename to save the JSON file as
            - Note: The filename must end with .chjson

        Returns:

        - None
        """
        if not filename.endswith(".chjson"):
            raise ValueError("Filename must end with .chjson")

        # JSON doesn't support tuple keys, so convert shortcuts to string keys
        shortcuts_str = {
            str(key): via_node_id for key, via_node_id in self.shortcuts.items()
        }

        with open(filename, "w") as f:
            json.dump(
                {
                    "type": "CHGraph",
                    "nodes_count": self.nodes_count,
                    "ranks": self.ranks,
                    "forward_graph": self.forward_graph,
                    "backward_graph": self.backward_graph,
                    "shortcuts": shortcuts_str,
                    "original_graph": self.original_graph,
                },
                f,
            )

    @classmethod
    def load_from_chjson(cls, filename: str) -> "CHGraph":
        """
        Function:

        - Load a CHGraph from a JSON file that was saved using the `save_as_chjson` method

        Required Arguments:

        - `filename`
            - Type: str
            - What: The filename of the JSON file to load
            - Note: The filename must end with .chjson

        Returns:

        - A CHGraph object loaded from the JSON file
        """
        if not filename.endswith(".chjson"):
            raise ValueError("Filename must end with .chjson")

        with open(filename, "r") as f:
            data = json.load(f)

        if data.get("type") != "CHGraph":
            raise ValueError("JSON file is not a valid CHGraph.")

        data.pop("type")

        # Convert graph keys back to integers
        data["forward_graph"] = [
            {int(k): v for k, v in d.items()} for d in data["forward_graph"]
        ]
        data["backward_graph"] = [
            {int(k): v for k, v in d.items()} for d in data["backward_graph"]
        ]
        if data["original_graph"] is not None:
            data["original_graph"] = [
                {int(k): v for k, v in d.items()}
                for d in data["original_graph"]
            ]

        return cls(**data)


class CHGraphPreprocessing:
    def default_heuristic(self, node_id: int) -> int | float:
        """
        Function:

        - Calculate the default contraction heuristic for a node
        - Uses edge difference plus the number of already-contracted neighbors

        Required Arguments:

        - `node_id`
            - Type: int
            - What: The id of the node to calculate the heuristic for

        Returns:

        - The heuristic value for the node as an int or float
        """
        contracting_graph = self.contracting_graph
        contracting_inverse_graph = self.contracting_inverse_graph
        contracted = self.contracted

        shortcuts_needed, found_shortcuts = self._count_shortcuts(node_id)
        if hasattr(self, "_shortcuts_cache_table") and 0 <= node_id < len(
            self._shortcuts_cache_table
        ):
            self._shortcuts_cache_table[node_id] = found_shortcuts

        in_edges = len(contracting_inverse_graph[node_id])
        out_edges = len(contracting_graph[node_id])
        edge_diff = shortcuts_needed - in_edges - out_edges

        # Count neighbors that are already contracted
        contracted_neighbors = 0
        for neighbor in contracting_graph[node_id]:
            if contracted[neighbor]:
                contracted_neighbors += 1
        for neighbor in contracting_inverse_graph[node_id]:
            if contracted[neighbor]:
                contracted_neighbors += 1

        return edge_diff + contracted_neighbors

    def _count_shortcuts(
        self, node_id: int
    ) -> tuple[int, list[tuple[int, int, int | float, int]]]:
        """
        Function:

        - Calculate how many shortcuts are needed if node_id is contracted

        Required Arguments:

        - `node_id`
            - Type: int
            - What: The id of the node to calculate shortcuts for

        Returns:

        - A tuple of (count, list_of_shortcuts) where:
            - count: The number of shortcuts needed
            - list_of_shortcuts: A list of tuples (in_neighbor_id, out_neighbor_id, shortcut_distance, node_id) representing each shortcut
        """
        shortcuts = []
        in_neighbors = self.contracting_inverse_graph[node_id]
        out_neighbors = self.contracting_graph[node_id]
        contracted = self.contracted

        for in_neighbor_id, in_weight in in_neighbors.items():
            if contracted[in_neighbor_id]:
                continue

            # Max distance we care about for witness search from in_neighbor_id
            max_dist = 0
            witness_targets = {}
            witness_target_ids = []
            for out_neighbor_id, out_weight in out_neighbors.items():
                if (
                    contracted[out_neighbor_id]
                    or in_neighbor_id == out_neighbor_id
                ):
                    continue
                shortcut_distance = in_weight + out_weight

                # Direct edge check
                if out_neighbor_id in self.contracting_graph[in_neighbor_id]:
                    if (
                        self.contracting_graph[in_neighbor_id][out_neighbor_id]
                        <= shortcut_distance + 1e-9
                    ):
                        continue

                witness_targets[out_neighbor_id] = shortcut_distance
                witness_target_ids.append(out_neighbor_id)
                if shortcut_distance > max_dist:
                    max_dist = shortcut_distance

            if not witness_target_ids:
                continue

            # Witness search from in_neighbor_id
            distances = self._witness_search(
                in_neighbor_id,
                node_id,
                max_dist,
                witness_targets,
                witness_target_ids,
            )

            for out_neighbor_id in witness_target_ids:
                shortcut_distance = witness_targets[out_neighbor_id]
                if (
                    not self._witness_resolved[out_neighbor_id]
                    or distances[out_neighbor_id] > shortcut_distance + 1e-9
                ):
                    shortcuts.append(
                        (
                            in_neighbor_id,
                            out_neighbor_id,
                            shortcut_distance,
                            node_id,
                        )
                    )

            # Cleanup search state
            for v in self._witness_visited:
                self._witness_distances[v] = float("inf")
            self._witness_visited.clear()

            for t in witness_target_ids:
                self._witness_resolved[t] = False

        return len(shortcuts), shortcuts

    def _witness_search(
        self,
        start_node: int,
        avoid_node: int,
        max_dist: float,
        targets: dict[int, float],
        target_ids: list[int],
    ) -> list[float]:
        """
        Function:

        - Perform a Dijkstra search to find paths from start_node to other nodes
          without passing through avoid_node, up to a maximum distance
        - Used during contraction to determine if a shortcut is necessary

        Required Arguments:

        - `start_node`
            - Type: int
            - What: The id of the node to start the search from
        - `avoid_node`
            - Type: int
            - What: The id of the node to avoid during the search (the node being contracted)
        - `max_dist`
            - Type: int | float
            - What: The maximum distance to search up to

        Returns:

        - A list of shortest distances from start_node to visited nodes
        """
        witness_distances = self._witness_distances
        witness_resolved = self._witness_resolved
        witness_visited = self._witness_visited
        contracting_graph = self.contracting_graph
        contracted = self.contracted
        settled_limit = self.settled_limit
        _inf = float("inf")

        witness_distances[start_node] = 0.0
        witness_visited.append(start_node)

        open_leaves = [(0.0, start_node)]
        settled_count = 0
        resolved_count = 0
        num_targets = len(target_ids)

        while open_leaves:
            current_distance, current_id = heappop(open_leaves)
            if current_distance > max_dist:
                continue
            if current_distance > witness_distances[current_id]:
                continue

            if (
                current_id in targets
                and current_distance <= targets[current_id]
            ):
                if not witness_resolved[current_id]:
                    witness_resolved[current_id] = True
                    resolved_count += 1
                    if resolved_count == num_targets:
                        break

            settled_count += 1
            if settled_count > settled_limit:
                break

            for neighbor_id, weight in contracting_graph[current_id].items():
                if neighbor_id == avoid_node or contracted[neighbor_id]:
                    continue
                possible_distance = current_distance + weight
                if (
                    possible_distance <= max_dist
                    and possible_distance < witness_distances[neighbor_id]
                ):
                    if witness_distances[neighbor_id] == _inf:
                        witness_visited.append(neighbor_id)
                    witness_distances[neighbor_id] = possible_distance
                    heappush(open_leaves, (possible_distance, neighbor_id))

        return witness_distances

    def _preprocess(
        self,
        heuristic_fn: Callable[["CHGraph", int], int | float] | None = None,
    ) -> None:
        """
        Function:

        - Perform node contraction to build the Contraction Hierarchy
        - Contracts nodes in order of their heuristic values, adding shortcuts as needed
        - Builds the final forward and backward graphs used during query

        Optional Arguments:

        - `heuristic_fn`
            - Type: callable | None
            - What: A function that takes (graph, node_id) and returns a heuristic value for node ordering
            - Default: None (uses `default_heuristic`)

        Returns:

        - None
        """
        # None: `default_heuristic` has not counted the shortcuts of the node
        self._shortcuts_cache_table = [None] * self.nodes_count
        self._witness_distances = [float("inf")] * self.nodes_count
        self._witness_resolved = [False] * self.nodes_count
        self._witness_visited = []

        if heuristic_fn is None:

            def heuristic_fn(graph, node):
                return graph.default_heuristic(node)

        contracting_graph = self.contracting_graph
        contracting_inverse_graph = self.contracting_inverse_graph
        ranks = self.ranks
        contracted = self.contracted
        shortcuts = self.shortcuts

        up_to_date = [False] * self.nodes_count

        open_leaves = []
        for node_id in range(self.nodes_count):
            initial_val = len(contracting_graph[node_id]) + len(
                contracting_inverse_graph[node_id]
            )
            heappush(open_leaves, (initial_val, node_id))

        rank = 0
        while open_leaves:
            heuristic_value, node_id = heappop(open_leaves)

            if contracted[node_id]:
                continue

            current_heuristic = heuristic_value
            evaluated_now = False
            if not up_to_date[node_id]:
                self._shortcuts_cache_table[node_id] = None
                current_heuristic = heuristic_fn(self, node_id)
                up_to_date[node_id] = True
                evaluated_now = True
                if open_leaves and current_heuristic > open_leaves[0][0]:
                    heappush(open_leaves, (current_heuristic, node_id))
                    continue

            # Contract node_id
            ranks[node_id] = rank
            rank += 1
            contracted[node_id] = True
            self.contracted_count += 1

            # Reuse the shortcuts that `default_heuristic` counted for this node
            # during the heuristic call above. A list counted earlier can be out of
            # date, as other nodes were contracted since.
            if (
                evaluated_now
                and 0 <= node_id < len(self._shortcuts_cache_table)
                and self._shortcuts_cache_table[node_id] is not None
            ):
                found_shortcuts = self._shortcuts_cache_table[node_id]
            else:
                _, found_shortcuts = self._count_shortcuts(node_id)

            # Add shortcuts to the contracting graph
            for (
                origin_id,
                destination_id,
                distance,
                via_node_id,
            ) in found_shortcuts:
                if distance < contracting_graph[origin_id].get(
                    destination_id, float("inf")
                ):
                    contracting_graph[origin_id][destination_id] = distance
                    contracting_inverse_graph[destination_id][
                        origin_id
                    ] = distance
                    shortcuts[(origin_id, destination_id)] = via_node_id

            # Mark remaining neighbors as dirty
            for neighbor_id in contracting_graph[node_id]:
                if (
                    neighbor_id < self.nodes_count
                    and not contracted[neighbor_id]
                ):
                    up_to_date[neighbor_id] = False
            for neighbor_id in contracting_inverse_graph[node_id]:
                if (
                    neighbor_id < self.nodes_count
                    and not contracted[neighbor_id]
                ):
                    up_to_date[neighbor_id] = False

        # Build final forward and backward graphs
        for origin_id in range(self.nodes_count):
            for destination_id, weight in contracting_graph[origin_id].items():
                if ranks[origin_id] < ranks[destination_id]:
                    self.forward_graph[origin_id][destination_id] = weight
            for destination_id, weight in contracting_inverse_graph[
                origin_id
            ].items():
                if ranks[origin_id] < ranks[destination_id]:
                    self.backward_graph[origin_id][destination_id] = weight


class CHGraphAlgorithms:
    def _get_rank(self, node_id: int) -> int | float:
        """
        Function:

        - Get the contraction rank of a node
        - Returns infinity for nodes added after preprocessing (e.g., temporary origin/destination nodes)

        Required Arguments:

        - `node_id`
            - Type: int
            - What: The id of the node to get the rank for

        Returns:

        - The rank of the node as an int, or float('inf') if the node was added after preprocessing
        """
        if node_id < len(self.ranks):
            return self.ranks[node_id]
        return float("inf")

    def _get_neighbors(
        self, node_id: int, forward: bool = True
    ) -> dict[int, int | float]:
        """
        Function:

        - Get the upward neighbors for a node in the bidirectional CH search
        - Handles nodes added after preprocessing (e.g., temporary origin/destination nodes in GeoGraph)

        Required Arguments:

        - `node_id`
            - Type: int
            - What: The id of the node to get neighbors for

        Optional Arguments:

        - `forward`
            - Type: bool
            - What: Whether to get forward (True) or backward (False) neighbors
            - Default: True

        Returns:

        - A dictionary mapping neighbor node ids to their edge weights
        """
        if node_id < self.nodes_count:
            # Preprocessed node
            return (
                self.forward_graph[node_id]
                if forward
                else self.backward_graph[node_id]
            )
        else:
            # Node added after preprocessing (always infinite rank)
            # It can reach any of its neighbors that have a rank
            neighbors = {}
            node_rank = self._get_rank(node_id)
            for neighbor_id, weight in self.original_graph[node_id].items():
                if (
                    self._get_rank(neighbor_id) > node_rank
                ):  # This won't happen if node_rank is inf
                    neighbors[neighbor_id] = weight
                elif (
                    not forward
                ):  # If we are looking for backward neighbors, we need nodes that can reach us
                    # This is slightly tricky for added nodes.
                    # For GeoGraph, added nodes connect to existing nodes symmetrically.
                    neighbors[neighbor_id] = weight
                elif forward:  # For forward search, we can go to any neighbor
                    neighbors[neighbor_id] = weight
            return neighbors

    def search(
        self,
        origin_id: int | set[int] | dict[int, int | float],
        destination_id: int | set[int] | dict[int, int | float],
        length_only: bool = False,
    ) -> dict:
        """
        Function:

        - Perform a bidirectional Dijkstra search on the Contraction Hierarchy

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

        Returns:

        - A dictionary with the following keys:
            - `path`: A list of node ids representing the shortest path (empty if length_only=True)
            - `length`: The total length of the shortest path
        """
        origin_dict = normalize_node_input(origin_id)
        destination_dict = normalize_node_input(destination_id)

        overlap = set(origin_dict.keys()) & set(destination_dict.keys())
        best_dist = float("inf")
        meeting_node = -1
        if overlap:
            for node in overlap:
                dist = origin_dict[node] + destination_dict[node]
                if dist < best_dist:
                    best_dist = dist
                    meeting_node = node

        # Forward search state
        forward_distances = {node: dist for node, dist in origin_dict.items()}
        forward_parent = {node: -1 for node in origin_dict}
        forward_open_leaves = [
            (dist, node) for node, dist in origin_dict.items()
        ]
        heapify(forward_open_leaves)

        # Backward search state
        backward_distances = {
            node: dist for node, dist in destination_dict.items()
        }
        backward_parent = {node: -1 for node in destination_dict}
        backward_open_leaves = [
            (dist, node) for node, dist in destination_dict.items()
        ]
        heapify(backward_open_leaves)

        while forward_open_leaves or backward_open_leaves:
            # Forward step
            if forward_open_leaves:
                current_distance, current_id = heappop(forward_open_leaves)
                if current_distance > best_dist:
                    forward_open_leaves = []  # Done with forward search
                else:
                    # Optimization: Split edge relaxation loops based on node status.
                    # Since forward_graph only contains upward rank edges, we bypass rank checks completely.
                    if current_id < self.nodes_count:
                        for neighbor_id, weight in self.forward_graph[
                            current_id
                        ].items():
                            new_dist = current_distance + weight
                            if new_dist < forward_distances.get(
                                neighbor_id, float("inf")
                            ):
                                forward_distances[neighbor_id] = new_dist
                                forward_parent[neighbor_id] = current_id
                                heappush(
                                    forward_open_leaves, (new_dist, neighbor_id)
                                )
                                if (
                                    neighbor_id in backward_distances
                                    and new_dist
                                    + backward_distances[neighbor_id]
                                    < best_dist
                                ):
                                    best_dist = (
                                        new_dist
                                        + backward_distances[neighbor_id]
                                    )
                                    meeting_node = neighbor_id
                    else:
                        for neighbor_id, weight in self.original_graph[
                            current_id
                        ].items():
                            new_dist = current_distance + weight
                            if new_dist < forward_distances.get(
                                neighbor_id, float("inf")
                            ):
                                forward_distances[neighbor_id] = new_dist
                                forward_parent[neighbor_id] = current_id
                                heappush(
                                    forward_open_leaves, (new_dist, neighbor_id)
                                )
                                if (
                                    neighbor_id in backward_distances
                                    and new_dist
                                    + backward_distances[neighbor_id]
                                    < best_dist
                                ):
                                    best_dist = (
                                        new_dist
                                        + backward_distances[neighbor_id]
                                    )
                                    meeting_node = neighbor_id

            # Backward step
            if backward_open_leaves:
                current_distance, current_id = heappop(backward_open_leaves)
                if current_distance > best_dist:
                    backward_open_leaves = []  # Done with backward search
                else:
                    # Optimization: Split edge relaxation loops based on node status.
                    # Since backward_graph only contains upward rank edges, we bypass rank checks completely.
                    if current_id < self.nodes_count:
                        for neighbor_id, weight in self.backward_graph[
                            current_id
                        ].items():
                            new_dist = current_distance + weight
                            if new_dist < backward_distances.get(
                                neighbor_id, float("inf")
                            ):
                                backward_distances[neighbor_id] = new_dist
                                backward_parent[neighbor_id] = current_id
                                heappush(
                                    backward_open_leaves,
                                    (new_dist, neighbor_id),
                                )
                                if (
                                    neighbor_id in forward_distances
                                    and new_dist
                                    + forward_distances[neighbor_id]
                                    < best_dist
                                ):
                                    best_dist = (
                                        new_dist
                                        + forward_distances[neighbor_id]
                                    )
                                    meeting_node = neighbor_id
                    else:
                        for neighbor_id, weight in self.original_graph[
                            current_id
                        ].items():
                            new_dist = current_distance + weight
                            if new_dist < backward_distances.get(
                                neighbor_id, float("inf")
                            ):
                                backward_distances[neighbor_id] = new_dist
                                backward_parent[neighbor_id] = current_id
                                heappush(
                                    backward_open_leaves,
                                    (new_dist, neighbor_id),
                                )
                                if (
                                    neighbor_id in forward_distances
                                    and new_dist
                                    + forward_distances[neighbor_id]
                                    < best_dist
                                ):
                                    best_dist = (
                                        new_dist
                                        + forward_distances[neighbor_id]
                                    )
                                    meeting_node = neighbor_id

            forward_min = (
                forward_open_leaves[0][0]
                if forward_open_leaves
                else float("inf")
            )
            backward_min = (
                backward_open_leaves[0][0]
                if backward_open_leaves
                else float("inf")
            )
            if forward_min > best_dist and backward_min > best_dist:
                break

        if meeting_node == -1:
            raise PathNotFoundError(
                "No path found between origin and destination"
            )

        if length_only:
            return {"path": [], "length": best_dist}

        path = self._reconstruct_ch_path(
            origin_id,
            destination_id,
            meeting_node,
            forward_parent,
            backward_parent,
        )
        return {"path": path, "length": best_dist}

    def _reconstruct_ch_path(
        self,
        origin_id: int,
        destination_id: int,
        meeting_node: int,
        forward_parent: dict[int, int],
        backward_parent: dict[int, int],
    ) -> list[int]:
        """
        Function:

        - Reconstruct the full shortest path from the forward and backward parent maps
        - Unpacks any shortcuts into their constituent original edges

        Required Arguments:

        - `origin_id`
            - Type: int
            - What: The id of the origin node
        - `destination_id`
            - Type: int
            - What: The id of the destination node
        - `meeting_node`
            - Type: int
            - What: The node where the forward and backward searches met
        - `forward_parent`
            - Type: dict[int, int]
            - What: A dictionary mapping each node to its parent in the forward search
        - `backward_parent`
            - Type: dict[int, int]
            - What: A dictionary mapping each node to its parent in the backward search

        Returns:

        - A list of node ids representing the full shortest path from origin to destination
        """
        # Forward part: origin -> ... -> meeting_node
        forward_path = []
        current_id = meeting_node
        while current_id != -1:
            forward_path.append(current_id)
            current_id = forward_parent.get(current_id, -1)
        forward_path.reverse()

        # Backward part: meeting_node -> ... -> destination
        backward_path = []
        current_id = backward_parent.get(meeting_node, -1)
        while current_id != -1:
            backward_path.append(current_id)
            current_id = backward_parent.get(current_id, -1)

        contracted_path = forward_path + backward_path

        # Unpack shortcuts
        path = []
        for i in range(len(contracted_path) - 1):
            origin_id = contracted_path[i]
            destination_id = contracted_path[i + 1]
            path.extend(self._unpack_shortcut(origin_id, destination_id))
        path.append(contracted_path[-1])
        return path

    def _unpack_shortcut(
        self, origin_id: int, destination_id: int
    ) -> list[int]:
        """
        Function:

        - Recursively unpack a shortcut edge into its original constituent nodes
        - If no shortcut exists between origin_id and destination_id, returns [origin_id] as a base case

        Required Arguments:

        - `origin_id`
            - Type: int
            - What: The id of the origin node of the (potential) shortcut edge
        - `destination_id`
            - Type: int
            - What: The id of the destination node of the (potential) shortcut edge

        Returns:

        - A list of node ids representing the unpacked path from origin_id (exclusive of destination_id)
        """
        if (origin_id, destination_id) in self.shortcuts:
            via_node_id = self.shortcuts[(origin_id, destination_id)]
            return self._unpack_shortcut(
                origin_id, via_node_id
            ) + self._unpack_shortcut(via_node_id, destination_id)
        else:
            return [origin_id]


class CHGraph(
    GraphUtils,
    GraphModifiers,
    CHGraphIO,
    CHGraphPreprocessing,
    CHGraphAlgorithms,
):
    def __init__(
        self,
        graph: list[dict[int, int | float]] | None = None,
        *,
        heuristic_fn: Callable[["CHGraph", int], int | float] | None = None,
        ranks: list[int] | None = None,
        forward_graph: list[dict[int, int | float]] | None = None,
        backward_graph: list[dict[int, int | float]] | None = None,
        shortcuts: dict[str | tuple[int, int], int] | None = None,
        nodes_count: int | None = None,
        original_graph: list[dict[int, int | float]] | None = None,
        settled_limit: int = 50,
        inverse_graph: list[dict[int, int | float]] | None = None,
    ):
        """
        Function:

        - Create a Contraction Hierarchies Graph object
        - If `ranks`, `forward_graph`, `backward_graph`, `shortcuts`, and `nodes_count` are all provided,
          the graph will be initialized from these pre-computed values instead of being preprocessed

        Optional Arguments:

        - `graph`
            - Type: list[dict[int, int | float]] | None
            - What: The original graph as a list of adjacency dictionaries
            - Default: None
            - Note: Required if not loading from a saved state
        - `heuristic_fn`
            - Type: callable | None
            - What: A function that takes (graph, node_id) and returns a heuristic value for node ordering
            - Default: None (uses `default_heuristic`)
        - `ranks`
            - Type: list[int] | None
            - What: Pre-calculated contraction ranks for each node
            - Default: None
        - `forward_graph`
            - Type: list[dict[int, int | float]] | None
            - What: Pre-calculated forward graph (upward edges by rank)
            - Default: None
        - `backward_graph`
            - Type: list[dict[int, int | float]] | None
            - What: Pre-calculated backward graph (upward edges by rank in reverse direction)
            - Default: None
        - `shortcuts`
            - Type: dict | None
            - What: Pre-calculated shortcuts mapping (origin_id, destination_id) tuples to via_node_ids
            - Default: None
        - `nodes_count`
            - Type: int | None
            - What: The number of nodes in the original graph
            - Default: None
        - `original_graph`
            - Type: list[dict[int, int | float]] | None
            - What: The original graph, used when loading from a saved state
            - Default: None
        """
        # Set original_graph from either 'graph' or 'original_graph'
        self.original_graph = graph if graph is not None else original_graph
        self._graph = self.original_graph
        self.settled_limit = settled_limit

        if all(
            x is not None
            for x in [
                ranks,
                forward_graph,
                backward_graph,
                shortcuts,
                nodes_count,
            ]
        ):
            self.nodes_count = nodes_count
            self.ranks = ranks
            self.forward_graph = forward_graph
            self.backward_graph = backward_graph
            # JSON keys are strings, convert back to tuples for shortcuts
            if len(shortcuts) > 0 and isinstance(
                list(shortcuts.keys())[0], str
            ):
                self.shortcuts = {}
                for key, via_node_id in shortcuts.items():
                    shortcut_origin_id, shortcut_destination_id = map(
                        int, key.strip("()").split(",")
                    )
                    self.shortcuts[
                        (shortcut_origin_id, shortcut_destination_id)
                    ] = via_node_id
            else:
                self.shortcuts = shortcuts
        else:
            if self.original_graph is None:
                raise ValueError(
                    "Original graph must be provided if not loading from saved state."
                )
            self.nodes_count = len(self.original_graph)
            self.ranks = [-1] * self.nodes_count
            self.forward_graph = [{} for _ in range(self.nodes_count)]
            self.backward_graph = [{} for _ in range(self.nodes_count)]
            self.shortcuts = {}  # (origin_id, destination_id): via_node_id

            # Working copy of the graph for contraction
            self.contracting_graph = [d.copy() for d in self.original_graph]
            if inverse_graph is not None:
                self.contracting_inverse_graph = [
                    d.copy() for d in inverse_graph
                ]
            else:
                self.contracting_inverse_graph = [
                    {} for _ in range(self.nodes_count)
                ]
                for origin_id, edges in enumerate(self.original_graph):
                    for destination_id, weight in edges.items():
                        self.contracting_inverse_graph[destination_id][
                            origin_id
                        ] = weight

            self.contracted = [False] * self.nodes_count
            self.contracted_count = 0

            self._preprocess(heuristic_fn=heuristic_fn)

    @property
    def graph(self) -> list[dict[int, int | float]]:
        return self.original_graph

    def get_shortest_path(
        self,
        origin_id: int | set[int] | dict[int, int | float],
        destination_id: int | set[int] | dict[int, int | float],
        **kwargs,
    ) -> dict:
        """
        Function:

        - Identify the shortest path between two nodes using the Contraction Hierarchy

        Required Arguments:

        - `origin_id`
            - Type: int | set[int] | dict[int, int | float]
            - What: The origin node id(s), optionally with starting distances
        - `destination_id`
            - Type: int | set[int] | dict[int, int | float]
            - What: The destination node id(s), optionally with exit distances

        Returns:

        - A dictionary with the following keys:
            - `path`: A list of node ids representing the shortest path
            - `length`: The total length of the shortest path
        """
        return self.search(origin_id, destination_id, **kwargs)
