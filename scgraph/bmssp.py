import heapq
from math import ceil, log
from scgraph.graph import Graph

inf=float('inf')

class BmsspDataStructure:
    """
    Data Structure for inserting, updating and pulling min key value pairs.
    """
    def __init__(self, subset_size:int, upper_bound:int|float):
        self.subset_size = max(1, subset_size)
        self.upper_bound = upper_bound
        self.best_dict = {}
        self.heap = []

    def insert_key_value(self, key:int, value:int|float):
        """
        Insert a key-value pair into the data structure, keeping only the best (min) values.
        """
        if value < self.best_dict.get(key, inf):
            self.best_dict[key] = value
            heapq.heappush(self.heap, (value, key))

    def pull(self):
        """
        Return (remaining_best, subset) where subset is up to self.subset_size keys with the smallest values.
        Clear out returned values from the best_dict.
        """
        subset = set()
        while len(subset) < self.subset_size and self.heap:
            value, key = heapq.heappop(self.heap)
            if value == self.best_dict.pop(key, inf):
                subset.add(key)

        remaining_best = min(self.best_dict.values()) if self.best_dict else self.upper_bound
        return remaining_best, subset

class BmsspSolver:
    def __init__(self, graph: list[dict[int, int|float]]):
        """
        Initialize the BMSSP solver with a graph represented as an adjacency list.
        """
        self.graph = graph
        self.graph_length = len(graph)
        self.distance_matrix = [inf] * self.graph_length
        self.predecessor = [-1] * self.graph_length

        if self.graph_length <= 2:
            raise ValueError("Your provided graph must have more than 2 nodes")
        
        # Automatically apply practical choices for pivot exploration depth and target tree depth
        self.pivot_relaxation_steps = max(2, int(log(self.graph_length) ** (1/3.0)))
        self.target_tree_depth = max(2, int(log(self.graph_length) ** (2/3.0)))

    def find_pivots(self, upper_bound, frontier):
        """
        Finds pivot sets pivots and temp_frontier according to Algorithm 1.

        Parameters:
        - upper_bound: float, the upper bound threshold (B)
        - frontier: set of vertices (S)

        Returns:
        - pivots: set of pivot vertices
        - temp_frontier: set of vertices explored within upper_bound
        """
        temp_frontier = set(frontier)
        prev_frontier = set(frontier)

        for _ in range(1, self.pivot_relaxation_steps + 1):
            curr_frontier = set()
            for frontier_idx in prev_frontier:
                for connection_idx, connection_weight in self.graph[frontier_idx].items():
                    if self.distance_matrix[frontier_idx] + connection_weight <= self.distance_matrix[connection_idx]:
                        self.distance_matrix[connection_idx] = self.distance_matrix[frontier_idx] + connection_weight
                        if self.distance_matrix[connection_idx] < upper_bound:
                            curr_frontier.add(connection_idx)
                            temp_frontier.add(connection_idx)
            if len(temp_frontier) > self.pivot_relaxation_steps * len(frontier):
                pivots = set(frontier)
                return pivots, temp_frontier
            prev_frontier = curr_frontier

        directed_forest = set()
        for frontier_idx in temp_frontier:
            for connection_idx, connection_weight in self.graph[frontier_idx].items():
                if connection_idx in temp_frontier and abs(self.distance_matrix[connection_idx] - (self.distance_matrix[frontier_idx] + connection_weight)) < 1e-9:
                    directed_forest.add((frontier_idx, connection_idx))

        # Compute indegree for nodes in temp_frontier
        indegree = {node: 0 for node in temp_frontier}
        adj = {node: set() for node in temp_frontier}
        for connection_idx, connection_distance in directed_forest:
            adj[connection_idx].add(connection_distance)
            indegree[connection_idx] += 1

        def dfs_count(node_idx, visited:set = set()):
            count = 1
            visited.add(node_idx)
            for child in adj[node_idx]:
                if child not in visited:
                    count += dfs_count(child, visited)
            return count

        pivots = set()
        for frontier_idx in frontier:
            if indegree[frontier_idx] == 0:
                size = dfs_count(frontier_idx)
                if size >= self.pivot_relaxation_steps:
                    pivots.add(frontier_idx)

        return pivots, temp_frontier
        

    def base_case(self, upper_bound, frontier):
        """
        Implements Algorithm 2: Base Case of BMSSP

        Parameters:
        - upper_bound: float, boundary B
        - frontier: set with a single vertex x (complete)

        Returns:
        - new_upper_bound
        - new_frontier with vertices v such that distance_matrix[v] < new_upper_bound
        """
        assert len(frontier) == 1, "Frontier must be a singleton set"
        x = next(iter(frontier))

        new_frontier = set(frontier)

        # Min-heap of (distance, vertex)
        heap = []
        heapq.heappush(heap, (self.distance_matrix[x], x))

        visited = set()

        while heap and len(new_frontier) < self.pivot_relaxation_steps + 1:
            _, frontier_idx = heapq.heappop(heap)
            if frontier_idx in visited:
                continue
            visited.add(frontier_idx)
            new_frontier.add(frontier_idx)

            for connection_idx, connection_distances in self.graph[frontier_idx].items():
                new_dist = self.distance_matrix[frontier_idx] + connection_distances
                if new_dist <= self.distance_matrix[connection_idx] and new_dist < upper_bound:
                    self.distance_matrix[connection_idx] = new_dist
                    self.predecessor[connection_idx] = frontier_idx
                    heapq.heappush(heap, (new_dist, connection_idx))

        if len(new_frontier) > self.pivot_relaxation_steps:
            upper_bound = max(self.distance_matrix[v] for v in new_frontier)
            new_frontier = {v for v in new_frontier if self.distance_matrix[v] < upper_bound}
        return upper_bound, new_frontier
    

    def bmssp(self, recursion_depth, upper_bound, frontier):
        """
        Implements Algorithm 3: Bounded Multi-Source Shortest Path (BMSSP)

        Parameters:
        - recursion_depth: int, recursion depth
        - upper_bound: float, boundary B
        - frontier: set of vertices S (|S| <= 2)

        Returns:
        - new_upper_bound
        - new_frontier
        """
        # Base case when recursion depth is zero
        if recursion_depth == 0:
            return self.base_case(upper_bound, frontier)

        # Step 4: Find pivots and temp frontier
        pivots, temp_frontier = self.find_pivots(upper_bound, frontier)

        # Step 5: Initialize D
        data_struct = BmsspDataStructure(
            subset_size=2 * (recursion_depth - 1) * self.target_tree_depth, 
            upper_bound=upper_bound
        )

        # Step 6: Insert pivots into D

        for pivot in pivots:
            data_struct.insert_key_value(pivot, self.distance_matrix[pivot])

        i = 0
        new_frontiers_explored = set()

        # Step 8: Loop while new_frontiers_explored size < k^2 * t and D non-empty
        while len(new_frontiers_explored) < (self.pivot_relaxation_steps ** 2) * self.target_tree_depth and data_struct.heap:
            i += 1

            # Step 10: Pull from D
            upper_bound_i, frontier_i = data_struct.pull()

            # Step 11: Recursive BMSSP call
            upper_bound_prime, new_frontier_i = self.bmssp(recursion_depth - 1, upper_bound_i, frontier_i)

            # Step 12: Union new_frontier_i into new_frontiers_explored
            new_frontiers_explored.update(new_frontier_i)

            # Step 13: Initialize K
            intermediate_frontier = set()

            # Step 14-20: Relax edges from new_frontier_i
            for new_frontier_i_item in new_frontier_i:
                for new_frontier_i_connection_idx, new_frontier_i_connection_distance in self.graph[new_frontier_i_item].items():
                    new_dist = self.distance_matrix[new_frontier_i_item] + new_frontier_i_connection_distance
                    if new_dist <= self.distance_matrix[new_frontier_i_connection_idx]:
                        self.distance_matrix[new_frontier_i_connection_idx] = new_dist
                        self.predecessor[new_frontier_i_connection_idx] = new_frontier_i_item
                        if upper_bound_i <= new_dist < upper_bound:
                            data_struct.insert_key_value(new_frontier_i_connection_idx, new_dist)
                        elif upper_bound_prime <= new_dist < upper_bound_i:
                            intermediate_frontier.add((new_frontier_i_connection_idx, new_dist))

            # Step 21: Batch prepend intermediate_frontier plus filtered frontier_i elements
            frontier_i_filtered = {(x, self.distance_matrix[x]) for x in frontier_i if upper_bound_prime <= self.distance_matrix[x] < upper_bound_i}
            for frontier_i_idx, frontier_i_distance in frontier_i_filtered.union(intermediate_frontier):
                data_struct.insert_key_value(frontier_i_idx, frontier_i_distance)

        # Step 22: Final return
        new_upper_bound = min(min(self.distance_matrix[pivot] for pivot in pivots), upper_bound)
        new_frontier = {x for x in temp_frontier if self.distance_matrix[x] < new_upper_bound}

        return new_upper_bound, new_frontier

def BMSSP(graph, origin_id, destination_id):
    """
    Full BMSSP-style solver with safety checks + final Dijkstra finalizer.
    Returns: a dictionary with 'length' and 'path' keys or raises an exception if no path is found.
    """
    solver = BmsspSolver(graph)
    solver.distance_matrix[origin_id] = 0

    # compute max_tree_depth = ceil(log n / target_tree_depth)
    max_tree_depth = int(ceil(log(max(2, solver.graph_length)) / max(1, solver.target_tree_depth)))

    # run a single top-level recursive_bmssp call (paper runs more structured loops; finalizer ensures correctness)
    solver.bmssp(max_tree_depth, inf, {origin_id})

    if solver.distance_matrix[destination_id] == inf:
        raise Exception("Something went wrong, the origin and destination nodes are not connected.")
    return {
        'path': Graph.reconstruct_path(destination_id, solver.predecessor),
        'length': solver.distance_matrix[destination_id], 
    }


