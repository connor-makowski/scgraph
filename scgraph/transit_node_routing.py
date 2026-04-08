import json
from heapq import heappush, heappop
from typing import Any, Optional
from scgraph.contraction_hierarchies import CHGraph


class TNRGraphIO:
    def save_as_tnrjson(self, filename: str) -> None:
        """
        Function:
        - Save the current TNRGraph as a JSON file

        Required Arguments:
        - `filename`
            - Type: str
            - What: The filename to save the JSON file as
            - Note: The filename must end with .tnrjson
        """
        if not filename.endswith(".tnrjson"):
            raise ValueError("Filename must end with .tnrjson")

        # Convert tuple keys in distance_table to strings for JSON
        dist_table_str = {
            f"({k[0]},{k[1]})": v for k, v in self.distance_table.items()
        }

        # Convert access node keys to strings
        f_access_str = [
            {str(k): v for k, v in d.items()} for d in self.forward_access_nodes
        ]
        b_access_str = [
            {str(k): v for k, v in d.items()}
            for d in self.backward_access_nodes
        ]

        # Shortcuts also need string keys
        shortcuts_str = {
            str(key): via_node_id for key, via_node_id in self.shortcuts.items()
        }

        with open(filename, "w") as f:
            json.dump(
                {
                    "type": "TNRGraph",
                    "nodes_count": self.nodes_count,
                    "transit_nodes": list(self.transit_nodes),
                    "distance_table": dist_table_str,
                    "forward_access_nodes": f_access_str,
                    "backward_access_nodes": b_access_str,
                    "ch_data": {
                        "ranks": self.ranks,
                        "forward_graph": self.forward_graph,
                        "backward_graph": self.backward_graph,
                        "shortcuts": shortcuts_str,
                        "original_graph": self.original_graph,
                        "nodes_count": self.nodes_count,
                    },
                },
                f,
            )

    @classmethod
    def load_from_tnrjson(cls, filename: str) -> "TNRGraph":
        """
        Function:
        - Load a TNRGraph from a JSON file

        Required Arguments:
        - `filename`
            - Type: str
            - What: The filename of the JSON file to load
        """
        if not filename.endswith(".tnrjson"):
            raise ValueError("Filename must end with .tnrjson")

        with open(filename, "r") as f:
            data = json.load(f)

        if data.get("type") != "TNRGraph":
            raise ValueError("JSON file is not a valid TNRGraph.")

        data.pop("type")
        return cls(**data)


class TNRGraphPreprocessing:
    def __compute_access_nodes__(
        self, node_id: int, forward: bool = True
    ) -> dict[int, float]:
        """
        Function:
        - Perform a restricted upward CH search to find the first transit nodes encountered
        """
        access_nodes = {}
        distances = {node_id: 0}
        open_leaves = [(0, node_id)]

        while open_leaves:
            dist, current_id = heappop(open_leaves)
            if dist > distances.get(current_id, float("inf")):
                continue

            # If we hit a transit node, we stop searching this branch
            if current_id in self.transit_nodes:
                if dist < access_nodes.get(current_id, float("inf")):
                    access_nodes[current_id] = dist
                continue

            # Check neighbors in the upward graph
            # If current_id is an added node (rank inf), it uses original_graph logic
            # (handled by inheriting from CHGraph)
            neighbors = self.__get_neighbors__(current_id, forward)

            for neighbor_id, weight in neighbors.items():
                new_dist = dist + weight
                if new_dist < distances.get(neighbor_id, float("inf")):
                    distances[neighbor_id] = new_dist
                    heappush(open_leaves, (new_dist, neighbor_id))
        return access_nodes

    def __preprocess_tnr__(self, num_transit_nodes: int):
        """
        Function:
        - Perform TNR preprocessing on top of an existing CH
        """
        # 1. Select Transit Nodes (Top N by rank)
        ranked_nodes = sorted(
            range(self.nodes_count), key=lambda i: self.ranks[i], reverse=True
        )
        self.transit_nodes = set(ranked_nodes[:num_transit_nodes])

        # 2. Compute Access Nodes for all nodes
        self.forward_access_nodes = [
            self.__compute_access_nodes__(i, True)
            for i in range(self.nodes_count)
        ]
        self.backward_access_nodes = [
            self.__compute_access_nodes__(i, False)
            for i in range(self.nodes_count)
        ]

        # 3. Compute Distance Table between transit nodes
        self.distance_table = {}
        t_nodes_list = list(self.transit_nodes)

        # Note: This is O(T^2) which is slow for Python.
        # For a production implementation, we'd use many-to-one Dijkstra.
        for origin in t_nodes_list:
            # We use CH search for distance
            # This can be optimized by using a simpler Dijkstra if we're only going transit-to-transit
            for target in t_nodes_list:
                if origin == target:
                    self.distance_table[(origin, target)] = 0
                    continue
                # Bidirectional CH search is very fast
                res = CHGraph.search(self, origin, target)
                self.distance_table[(origin, target)] = res["length"]


class TNRGraphAlgorithms:
    def __local_search__(
        self,
        origin_id: int,
        destination_id: int,
        upper_bound: float,
        length_only: bool,
    ) -> Optional[dict]:
        forward_distances = {origin_id: 0}
        forward_parent = {origin_id: -1}
        forward_open_leaves = [(0, origin_id)]

        backward_distances = {destination_id: 0}
        backward_parent = {destination_id: -1}
        backward_open_leaves = [(0, destination_id)]

        best_dist = upper_bound
        meeting_node = -1

        while forward_open_leaves or backward_open_leaves:
            if forward_open_leaves:
                current_distance, current_id = heappop(
                    forward_open_leaves
                )
                if current_distance > best_dist:
                    forward_open_leaves = []
                elif current_id not in self.transit_nodes:
                    current_rank = self.__get_rank__(current_id)
                    neighbors = (
                        self.forward_graph[current_id]
                        if current_id < self.nodes_count
                        else self.original_graph[current_id]
                    )

                    for neighbor_id, weight in neighbors.items():
                        if (
                            self.__get_rank__(neighbor_id) <= current_rank
                            and neighbor_id < self.nodes_count
                        ):
                            continue
                        new_dist = current_distance + weight
                        if new_dist < forward_distances.get(
                            neighbor_id, float("inf")
                        ):
                            forward_distances[neighbor_id] = new_dist
                            if not length_only:
                                forward_parent[neighbor_id] = current_id
                            heappush(
                                forward_open_leaves, (new_dist, neighbor_id)
                            )
                            if (
                                neighbor_id in backward_distances
                                and new_dist + backward_distances[neighbor_id]
                                < best_dist
                            ):
                                best_dist = (
                                    new_dist + backward_distances[neighbor_id]
                                )
                                meeting_node = neighbor_id

            if backward_open_leaves:
                current_distance, current_id = heappop(
                    backward_open_leaves
                )
                if current_distance > best_dist:
                    backward_open_leaves = []
                elif current_id not in self.transit_nodes:
                    current_rank = self.__get_rank__(current_id)
                    neighbors = (
                        self.backward_graph[current_id]
                        if current_id < self.nodes_count
                        else self.original_graph[current_id]
                    )

                    for neighbor_id, weight in neighbors.items():
                        if (
                            self.__get_rank__(neighbor_id) <= current_rank
                            and neighbor_id < self.nodes_count
                        ):
                            continue
                        new_dist = current_distance + weight
                        if new_dist < backward_distances.get(
                            neighbor_id, float("inf")
                        ):
                            backward_distances[neighbor_id] = new_dist
                            if not length_only:
                                backward_parent[neighbor_id] = current_id
                            heappush(
                                backward_open_leaves, (new_dist, neighbor_id)
                            )
                            if (
                                neighbor_id in forward_distances
                                and new_dist + forward_distances[neighbor_id]
                                < best_dist
                            ):
                                best_dist = (
                                    new_dist + forward_distances[neighbor_id]
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

        if length_only:
            return {"length": best_dist}

        if meeting_node != -1:
            path = self.__reconstruct_ch_path__(
                origin_id,
                destination_id,
                meeting_node,
                forward_parent,
                backward_parent,
            )
            return {"path": path, "length": best_dist}

        return None

    def search(
        self,
        origin_id: int,
        destination_id: int,
        length_only: bool = False,
        **kwargs,
    ) -> dict[str, Any]:
        """
        Function:
        - Perform a TNR search with a highly pruned local CH fallback
        """
        if origin_id == destination_id:
            return (
                {"length": 0}
                if length_only
                else {"path": [origin_id], "length": 0}
            )

        # Access Nodes for origin/destination
        if origin_id < self.nodes_count:
            f_access = self.forward_access_nodes[origin_id]
        else:
            f_access = self.__compute_access_nodes__(origin_id, True)

        if destination_id < self.nodes_count:
            b_access = self.backward_access_nodes[destination_id]
        else:
            b_access = self.__compute_access_nodes__(destination_id, False)

        best_dist = float("inf")

        # Global Query via Distance Table
        for t_f, d_f in f_access.items():
            for t_b, d_b in b_access.items():
                d_table = self.distance_table.get((t_f, t_b), float("inf"))
                total = d_f + d_table + d_b
                if total < best_dist:
                    best_dist = total

        # Locality Filter / Correctness Check
        if length_only:
            return self.__local_search__(
                origin_id, destination_id, best_dist, True
            )

        local_res = self.__local_search__(
            origin_id, destination_id, best_dist, False
        )
        if local_res is not None:
            return local_res

        # Reconstructing path from transit pairs is complex without unpacking tables.
        # Fall back to a standard CH search if global TNR path is needed.
        return CHGraph.search(self, origin_id, destination_id)


class TNRGraph(TNRGraphIO, TNRGraphPreprocessing, TNRGraphAlgorithms, CHGraph):
    def __init__(
        self,
        graph: Optional[list[dict[int, int | float]]] = None,
        num_transit_nodes: int = 100,
        **kwargs,
    ):
        """
        Function:
        - Create a Transit Node Routing Graph object

        Optional Arguments:
        - `graph`: Original graph adjacency list
        - `num_transit_nodes`: Number of top-ranked nodes to use as transit nodes
        - `kwargs`: Used when loading from saved state
        """
        if "transit_nodes" in kwargs:
            # Loading from saved state
            self.nodes_count = kwargs.get("nodes_count")
            self.transit_nodes = set(kwargs.get("transit_nodes"))

            # Reconstruct distance_table (keys are strings like "(1,2)")
            self.distance_table = {}
            for k, v in kwargs.get("distance_table").items():
                pair = tuple(map(int, k.strip("()").split(",")))
                self.distance_table[pair] = v

            # Reconstruct access nodes
            self.forward_access_nodes = [
                {int(k): v for k, v in d.items()}
                for d in kwargs.get("forward_access_nodes")
            ]
            self.backward_access_nodes = [
                {int(k): v for k, v in d.items()}
                for d in kwargs.get("backward_access_nodes")
            ]

            # Initialize CH part
            ch_data = kwargs.get("ch_data")
            # Convert graph keys to integers
            for key in ["forward_graph", "backward_graph", "original_graph"]:
                if ch_data.get(key) is not None:
                    ch_data[key] = [
                        {int(k): v for k, v in d.items()} for d in ch_data[key]
                    ]
            super().__init__(**ch_data)
        else:
            # Preprocess from original graph
            super().__init__(graph=graph)
            self.__preprocess_tnr__(num_transit_nodes)

    def get_shortest_path(
        self, origin_id: int, destination_id: int, **kwargs: Any
    ) -> dict[str, Any]:
        return self.search(origin_id, destination_id)
