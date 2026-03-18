import json
from heapq import heappush, heappop
from typing import Callable, Any, Optional, Union
from scgraph.graph_utils import GraphUtils, GraphModifiers


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
        shortcuts_needed, _ = self.__count_shortcuts__(node_id)
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

    def __count_shortcuts__(
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

        for in_neighbor_id, in_weight in in_neighbors.items():
            if self.contracted[in_neighbor_id]:
                continue

            # Max distance we care about for witness search from in_neighbor_id
            max_dist = 0
            targets = {}
            for out_neighbor_id, out_weight in out_neighbors.items():
                if self.contracted[out_neighbor_id] or in_neighbor_id == out_neighbor_id:
                    continue
                shortcut_distance = in_weight + out_weight
                targets[out_neighbor_id] = shortcut_distance
                if shortcut_distance > max_dist:
                    max_dist = shortcut_distance

            if not targets:
                continue

            # Witness search from in_neighbor_id
            distances = self.__witness_search__(in_neighbor_id, node_id, max_dist)

            for out_neighbor_id, shortcut_distance in targets.items():
                if distances.get(out_neighbor_id, float("inf")) > shortcut_distance + 1e-9:
                    shortcuts.append((in_neighbor_id, out_neighbor_id, shortcut_distance, node_id))

        return len(shortcuts), shortcuts

    def __witness_search__(
        self, start_node: int, avoid_node: int, max_dist: int | float
    ) -> dict[int, int | float]:
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

        - A dictionary mapping reachable node ids to their shortest distances from start_node
        """
        distances = {start_node: 0}
        open_leaves = [(0, start_node)]

        while open_leaves:
            current_distance, current_id = heappop(open_leaves)
            if current_distance > max_dist:
                continue
            if current_distance > distances.get(current_id, float("inf")):
                continue

            for neighbor_id, weight in self.contracting_graph[current_id].items():
                if neighbor_id == avoid_node or self.contracted[neighbor_id]:
                    continue
                possible_distance = current_distance + weight
                if possible_distance <= max_dist and possible_distance < distances.get(
                    neighbor_id, float("inf")
                ):
                    distances[neighbor_id] = possible_distance
                    heappush(open_leaves, (possible_distance, neighbor_id))
        return distances

    def __preprocess__(
        self, heuristic_fn: Optional[Callable[[Any, int], int | float]] = None
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
        if heuristic_fn is None:
            heuristic_fn = lambda g, n: g.default_heuristic(n)

        open_leaves = []
        for node_id in range(self.nodes_count):
            heappush(open_leaves, (heuristic_fn(self, node_id), node_id))

        rank = 0
        while open_leaves:
            heuristic_value, node_id = heappop(open_leaves)

            # Lazy update
            updated_heuristic = heuristic_fn(self, node_id)
            if open_leaves and updated_heuristic > open_leaves[0][0]:
                heappush(open_leaves, (updated_heuristic, node_id))
                continue

            # Contract node_id
            self.ranks[node_id] = rank
            rank += 1
            self.contracted[node_id] = True
            self.contracted_count += 1

            _, shortcuts = self.__count_shortcuts__(node_id)

            # Add shortcuts to the contracting graph
            for origin_id, destination_id, distance, via_node_id in shortcuts:
                if distance < self.contracting_graph[origin_id].get(destination_id, float("inf")):
                    self.contracting_graph[origin_id][destination_id] = distance
                    self.contracting_inverse_graph[destination_id][origin_id] = distance
                    self.shortcuts[(origin_id, destination_id)] = via_node_id

        # Build final forward and backward graphs
        for origin_id in range(self.nodes_count):
            for destination_id, weight in self.contracting_graph[origin_id].items():
                if self.ranks[origin_id] < self.ranks[destination_id]:
                    self.forward_graph[origin_id][destination_id] = weight
            for destination_id, weight in self.contracting_inverse_graph[origin_id].items():
                if self.ranks[origin_id] < self.ranks[destination_id]:
                    self.backward_graph[origin_id][destination_id] = weight


class CHGraphAlgorithms:
    def __get_rank__(self, node_id: int) -> int | float:
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

    def __get_neighbors__(
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
            node_rank = self.__get_rank__(node_id)
            for neighbor_id, weight in self.original_graph[node_id].items():
                if (
                    self.__get_rank__(neighbor_id) > node_rank
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

    def search(self, origin_id: int, destination_id: int) -> dict[str, Any]:
        """
        Function:

        - Perform a bidirectional Dijkstra search on the Contraction Hierarchy

        Required Arguments:

        - `origin_id`
            - Type: int
            - What: The id of the origin node
        - `destination_id`
            - Type: int
            - What: The id of the destination node

        Returns:

        - A dictionary with the following keys:
            - `path`: A list of node ids representing the shortest path
            - `length`: The total length of the shortest path
        """
        if origin_id == destination_id:
            return {"path": [origin_id], "length": 0}

        # Forward search state
        forward_distances = {origin_id: 0}
        forward_parent = {origin_id: -1}
        forward_open_leaves = [(0, origin_id)]

        # Backward search state
        backward_distances = {destination_id: 0}
        backward_parent = {destination_id: -1}
        backward_open_leaves = [(0, destination_id)]

        best_dist = float("inf")
        meeting_node = -1

        while forward_open_leaves or backward_open_leaves:
            # Forward step
            if forward_open_leaves:
                current_distance, current_id = heappop(forward_open_leaves)
                if current_distance > best_dist:
                    forward_open_leaves = []  # Done with forward search
                else:
                    # Get upward neighbors
                    current_rank = self.__get_rank__(current_id)
                    if current_id < self.nodes_count:
                        neighbors = self.forward_graph[current_id]
                    else:
                        neighbors = self.original_graph[current_id]

                    for neighbor_id, weight in neighbors.items():
                        if self.__get_rank__(neighbor_id) <= current_rank and neighbor_id < self.nodes_count:
                            continue
                        new_dist = current_distance + weight
                        if new_dist < forward_distances.get(neighbor_id, float("inf")):
                            forward_distances[neighbor_id] = new_dist
                            forward_parent[neighbor_id] = current_id
                            heappush(forward_open_leaves, (new_dist, neighbor_id))
                            if neighbor_id in backward_distances and new_dist + backward_distances[neighbor_id] < best_dist:
                                best_dist = new_dist + backward_distances[neighbor_id]
                                meeting_node = neighbor_id

            # Backward step
            if backward_open_leaves:
                current_distance, current_id = heappop(backward_open_leaves)
                if current_distance > best_dist:
                    backward_open_leaves = []  # Done with backward search
                else:
                    # Get upward neighbors (in backward graph)
                    current_rank = self.__get_rank__(current_id)
                    if current_id < self.nodes_count:
                        neighbors = self.backward_graph[current_id]
                    else:
                        # For nodes added after preprocessing, we use the original graph
                        # because they were added symmetrically or we need to find who connects to them.
                        # In GeoGraph, origin/dest connect TO the graph.
                        # So for backward search from destination, we look at its neighbors.
                        neighbors = self.original_graph[current_id]

                    for neighbor_id, weight in neighbors.items():
                        if self.__get_rank__(neighbor_id) <= current_rank and neighbor_id < self.nodes_count:
                            continue
                        new_dist = current_distance + weight
                        if new_dist < backward_distances.get(neighbor_id, float("inf")):
                            backward_distances[neighbor_id] = new_dist
                            backward_parent[neighbor_id] = current_id
                            heappush(backward_open_leaves, (new_dist, neighbor_id))
                            if neighbor_id in forward_distances and new_dist + forward_distances[neighbor_id] < best_dist:
                                best_dist = new_dist + forward_distances[neighbor_id]
                                meeting_node = neighbor_id

            forward_min = forward_open_leaves[0][0] if forward_open_leaves else float("inf")
            backward_min = backward_open_leaves[0][0] if backward_open_leaves else float("inf")
            if forward_min > best_dist and backward_min > best_dist:
                break

        if meeting_node == -1:
            raise Exception("No path found between origin and destination")

        path = self.__reconstruct_ch_path__(
            origin_id, destination_id, meeting_node, forward_parent, backward_parent
        )
        return {"path": path, "length": best_dist}

    def __reconstruct_ch_path__(
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
            path.extend(self.__unpack_shortcut__(origin_id, destination_id))
        path.append(contracted_path[-1])
        return path

    def __unpack_shortcut__(self, origin_id: int, destination_id: int) -> list[int]:
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
            return self.__unpack_shortcut__(origin_id, via_node_id) + self.__unpack_shortcut__(
                via_node_id, destination_id
            )
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
        graph: Optional[list[dict[int, int | float]]] = None,
        heuristic_fn: Optional[Callable[[Any, int], int | float]] = None,
        ranks: Optional[list[int]] = None,
        forward_graph: Optional[list[dict[int, int | float]]] = None,
        backward_graph: Optional[list[dict[int, int | float]]] = None,
        shortcuts: Optional[dict[Union[str, tuple[int, int]], int]] = None,
        nodes_count: Optional[int] = None,
        original_graph: Optional[list[dict[int, int | float]]] = None,
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
                    shortcut_origin_id, shortcut_destination_id = map(int, key.strip("()").split(","))
                    self.shortcuts[(shortcut_origin_id, shortcut_destination_id)] = via_node_id
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
            self.contracting_inverse_graph = [
                {} for _ in range(self.nodes_count)
            ]
            for origin_id, edges in enumerate(self.original_graph):
                for destination_id, weight in edges.items():
                    self.contracting_inverse_graph[destination_id][origin_id] = weight

            self.contracted = [False] * self.nodes_count
            self.contracted_count = 0

            self.__preprocess__(heuristic_fn=heuristic_fn)

    @property
    def graph(self) -> list[dict[int, int | float]]:
        return self.original_graph

    def get_shortest_path(
        self, origin_id: int, destination_id: int, **kwargs: Any
    ) -> dict[str, Any]:
        """
        Function:

        - Identify the shortest path between two nodes using the Contraction Hierarchy

        Required Arguments:

        - `origin_id`
            - Type: int
            - What: The id of the origin node
        - `destination_id`
            - Type: int
            - What: The id of the destination node

        Returns:

        - A dictionary with the following keys:
            - `path`: A list of node ids representing the shortest path
            - `length`: The total length of the shortest path
        """
        return self.search(origin_id, destination_id)
