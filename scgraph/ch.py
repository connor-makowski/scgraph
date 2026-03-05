import json
from heapq import heappush, heappop
from .graph import GraphUtils, GraphModifiers


class CHGraphIO:
    def save_as_chjson(self, filename: str) -> None:
        """
        Save the current CHGraph as a JSON file.
        """
        if not filename.endswith(".chjson"):
            raise ValueError("Filename must end with .chjson")

        # JSON doesn't support tuple keys, so convert shortcuts to string keys
        shortcuts_str = {str(k): v for k, v in self.shortcuts.items()}

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

    @staticmethod
    def load_from_chjson(filename: str) -> "CHGraph":
        """
        Load a CHGraph from a JSON file.
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

        return CHGraph(**data)


class CHGraphPreprocessing:
    def default_heuristic(self, node_id):
        """
        Heuristic: Edge Difference + Number of Contracted Neighbors
        """
        shortcuts_needed, _ = self._count_shortcuts(node_id)
        in_edges = len(self.contracting_inverse_graph[node_id])
        out_edges = len(self.contracting_graph[node_id])
        edge_diff = shortcuts_needed - in_edges - out_edges

        # Count neighbors that are already contracted
        contracted_neighbors = 0
        for neighbor in self.contracting_graph[node_id]:
            if self.contracted[neighbor]:
                contracted_neighbors += 1
        for neighbor in self.contracting_inverse_graph[node_id]:
            if self.contracted[neighbor]:
                contracted_neighbors += 1

        return edge_diff + contracted_neighbors

    def _count_shortcuts(self, v):
        """
        Calculate how many shortcuts are needed if node v is contracted.
        Returns (count, list_of_shortcuts)
        """
        shortcuts = []
        in_neighbors = self.contracting_inverse_graph[v]
        out_neighbors = self.contracting_graph[v]

        for u, w_uv in in_neighbors.items():
            if self.contracted[u]:
                continue

            # Max distance we care about for witness search from u
            max_dist = 0
            targets = {}
            for w, w_vw in out_neighbors.items():
                if self.contracted[w] or u == w:
                    continue
                dist_uvw = w_uv + w_vw
                targets[w] = dist_uvw
                if dist_uvw > max_dist:
                    max_dist = dist_uvw

            if not targets:
                continue

            # Witness search from u
            distances = self._witness_search(u, v, max_dist)

            for w, dist_uvw in targets.items():
                if distances.get(w, float("inf")) > dist_uvw + 1e-9:
                    shortcuts.append((u, w, dist_uvw, v))

        return len(shortcuts), shortcuts

    def _witness_search(self, start_node, avoid_node, max_dist):
        """
        A Dijkstra search to find if there's a path from start_node to
        other nodes without passing through avoid_node, with distance <= max_dist.
        """
        distances = {start_node: 0}
        pq = [(0, start_node)]

        while pq:
            d, u = heappop(pq)
            if d > max_dist:
                continue
            if d > distances.get(u, float("inf")):
                continue

            for v, weight in self.contracting_graph[u].items():
                if v == avoid_node or self.contracted[v]:
                    continue
                new_dist = d + weight
                if new_dist <= max_dist and new_dist < distances.get(
                    v, float("inf")
                ):
                    distances[v] = new_dist
                    heappush(pq, (new_dist, v))
        return distances

    def _preprocess(self, heuristic=None):
        """
        Perform node contraction and build the CH.
        """
        heuristic_fn = heuristic or self.default_heuristic
        pq = []
        for i in range(self.nodes_count):
            heappush(pq, (heuristic_fn(i), i))

        rank = 0
        while pq:
            h, v = heappop(pq)

            # Lazy update
            new_h = heuristic_fn(v)
            if pq and new_h > pq[0][0]:
                heappush(pq, (new_h, v))
                continue

            # Contract v
            self.ranks[v] = rank
            rank += 1
            self.contracted[v] = True
            self.contracted_count += 1

            _, shortcuts = self._count_shortcuts(v)

            # Add shortcuts to the contracting graph
            for u, w, dist, v_mid in shortcuts:
                if dist < self.contracting_graph[u].get(w, float("inf")):
                    self.contracting_graph[u][w] = dist
                    self.contracting_inverse_graph[w][u] = dist
                    self.shortcuts[(u, w)] = v_mid

        # Build final forward and backward graphs
        for u in range(self.nodes_count):
            for v, w in self.contracting_graph[u].items():
                if self.ranks[u] < self.ranks[v]:
                    self.forward_graph[u][v] = w
            for v, w in self.contracting_inverse_graph[u].items():
                if self.ranks[u] < self.ranks[v]:
                    self.backward_graph[u][v] = w


class CHGraphAlgorithms:
    def _get_rank(self, node_id: int) -> int:
        """
        Get the rank of a node. Returns infinity for nodes added after preprocessing.
        """
        if node_id < len(self.ranks):
            return self.ranks[node_id]
        return float("inf")

    def _get_neighbors(self, node_id: int, forward: bool = True) -> dict:
        """
        Get upward neighbors for a node in the bidirectional search.
        Handles nodes added after preprocessing (e.g., origin/destination in GeoGraph).
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
            for v, weight in self.original_graph[node_id].items():
                if (
                    self._get_rank(v) > node_rank
                ):  # This won't happen if node_rank is inf
                    neighbors[v] = weight
                elif (
                    not forward
                ):  # If we are looking for backward neighbors, we need nodes that can reach us
                    # This is slightly tricky for added nodes.
                    # For GeoGraph, added nodes connect to existing nodes symmetrically.
                    neighbors[v] = weight
                elif forward:  # For forward search, we can go to any neighbor
                    neighbors[v] = weight
            return neighbors

    def search(self, origin_id: int, destination_id: int) -> dict:
        """
        Perform a bidirectional search on the CH.
        Returns a dictionary with 'path' and 'length'.
        """
        if origin_id == destination_id:
            return {"path": [origin_id], "length": 0}

        # Forward search state
        f_dist = {origin_id: 0}
        f_parent = {origin_id: -1}
        f_pq = [(0, origin_id)]

        # Backward search state
        b_dist = {destination_id: 0}
        b_parent = {destination_id: -1}
        b_pq = [(0, destination_id)]

        best_dist = float("inf")
        meeting_node = -1

        while f_pq or b_pq:
            # Forward step
            if f_pq:
                d, u = heappop(f_pq)
                if d > best_dist:
                    f_pq = []  # Done with forward search
                else:
                    # Get upward neighbors
                    u_rank = self._get_rank(u)
                    if u < self.nodes_count:
                        neighbors = self.forward_graph[u]
                    else:
                        neighbors = self.original_graph[u]

                    for v, weight in neighbors.items():
                        if self._get_rank(v) <= u_rank and v < self.nodes_count:
                            continue
                        new_dist = d + weight
                        if new_dist < f_dist.get(v, float("inf")):
                            f_dist[v] = new_dist
                            f_parent[v] = u
                            heappush(f_pq, (new_dist, v))
                            if v in b_dist and new_dist + b_dist[v] < best_dist:
                                best_dist = new_dist + b_dist[v]
                                meeting_node = v

            # Backward step
            if b_pq:
                d, u = heappop(b_pq)
                if d > best_dist:
                    b_pq = []  # Done with backward search
                else:
                    # Get upward neighbors (in backward graph)
                    u_rank = self._get_rank(u)
                    if u < self.nodes_count:
                        neighbors = self.backward_graph[u]
                    else:
                        # For nodes added after preprocessing, we use the original graph
                        # because they were added symmetrically or we need to find who connects to them.
                        # In GeoGraph, origin/dest connect TO the graph.
                        # So for backward search from destination, we look at its neighbors.
                        neighbors = self.original_graph[u]

                    for v, weight in neighbors.items():
                        if self._get_rank(v) <= u_rank and v < self.nodes_count:
                            continue
                        new_dist = d + weight
                        if new_dist < b_dist.get(v, float("inf")):
                            b_dist[v] = new_dist
                            b_parent[v] = u
                            heappush(b_pq, (new_dist, v))
                            if v in f_dist and new_dist + f_dist[v] < best_dist:
                                best_dist = new_dist + f_dist[v]
                                meeting_node = v

            f_min = f_pq[0][0] if f_pq else float("inf")
            b_min = b_pq[0][0] if b_pq else float("inf")
            if f_min > best_dist and b_min > best_dist:
                break

        if meeting_node == -1:
            raise Exception("No path found between origin and destination")

        path = self._reconstruct_ch_path(
            origin_id, destination_id, meeting_node, f_parent, b_parent
        )
        return {"path": path, "length": best_dist}

    def get_shortest_path(self, origin_id: int, destination_id: int) -> dict:
        """
        Wrapper to match scgraph naming conventions.
        """
        # Support for GeoGraph naming (origin_idx, destination_idx)
        return self.search(origin_id, destination_id)

    def _reconstruct_ch_path(
        self, origin_id, destination_id, meeting_node, f_parent, b_parent
    ):
        # Forward part: origin -> ... -> meeting_node
        f_path = []
        curr = meeting_node
        while curr != -1:
            f_path.append(curr)
            curr = f_parent.get(curr, -1)
        f_path.reverse()

        # Backward part: meeting_node -> ... -> destination
        b_path = []
        curr = b_parent.get(meeting_node, -1)
        while curr != -1:
            b_path.append(curr)
            curr = b_parent.get(curr, -1)

        full_ch_path = f_path + b_path

        # Unpack shortcuts
        actual_path = []
        for i in range(len(full_ch_path) - 1):
            u = full_ch_path[i]
            v = full_ch_path[i + 1]
            actual_path.extend(self._unpack_shortcut(u, v))
        actual_path.append(full_ch_path[-1])
        return actual_path

    def _unpack_shortcut(self, u, w):
        if (u, w) in self.shortcuts:
            v_mid = self.shortcuts[(u, w)]
            return self._unpack_shortcut(u, v_mid) + self._unpack_shortcut(
                v_mid, w
            )
        else:
            return [u]


class CHGraph(
    GraphUtils,
    GraphModifiers,
    CHGraphIO,
    CHGraphPreprocessing,
    CHGraphAlgorithms,
):
    def __init__(
        self,
        graph: list[dict[int, int | float]] = None,
        heuristic=None,
        ranks: list[int] = None,
        forward_graph: list[dict[int, int | float]] = None,
        backward_graph: list[dict[int, int | float]] = None,
        shortcuts: dict = None,
        nodes_count: int = None,
        original_graph: list[dict[int, int | float]] = None,
    ):
        """
        Initialize a Contraction Hierarchies Graph.

        If `ranks`, `forward_graph`, `backward_graph`, and `shortcuts` are provided,
        the graph will be initialized from these values instead of being preprocessed.

        Required Arguments:
        - `graph`: The original graph as a list of adjacency dictionaries. (Required if not loading from saved state)

        Optional Arguments:
        - `heuristic`: A function that takes (node_id)
          and returns a heuristic value for node ordering.
          Defaults to edge difference + other factors.
        - `ranks`: Pre-calculated ranks.
        - `forward_graph`: Pre-calculated forward graph.
        - `backward_graph`: Pre-calculated backward graph.
        - `shortcuts`: Pre-calculated shortcuts.
        - `nodes_count`: Number of nodes in the graph.
        - `original_graph`: The original graph (used when loading from saved state).
        """
        # Set original_graph from either 'graph' or 'original_graph'
        self.original_graph = graph if graph is not None else original_graph

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
                for k, v in shortcuts.items():
                    u, w = map(int, k.strip("()").split(","))
                    self.shortcuts[(u, w)] = v
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
            self.shortcuts = (
                {}
            )  # (u, w): (v, w_uv, w_vw) - store intermediate node and weights

            # Working copy of the graph for contraction
            self.contracting_graph = [d.copy() for d in self.original_graph]
            self.contracting_inverse_graph = [
                {} for _ in range(self.nodes_count)
            ]
            for u, edges in enumerate(self.original_graph):
                for v, w in edges.items():
                    self.contracting_inverse_graph[v][u] = w

            self.contracted = [False] * self.nodes_count
            self.contracted_count = 0

            self._preprocess(heuristic=heuristic)

    @property
    def graph(self):
        return self.original_graph

    def get_shortest_path(self, origin_id, destination_id, **kwargs):
        # Match GeoGraph calling signature which uses origin_id and destination_id
        return self.search(origin_id, destination_id)
