from heapq import heappush, heappop, heapify
from math import ceil, log
from scgraph.utils import transform_to_constant_degree

inf = float('inf')


class BmsspDataStructure:
    """
    Data structure for inserting, updating and pulling the M smallest key-value pairs
    together with a lower bound on the remaining values (or B if empty), as required by Alg. 3.
    """
    def __init__(self, subset_size: int, upper_bound: int | float):
        # subset_size: how many items to return per pull (must match Alg. 3 for level l -> Given as M)
        self.subset_size = max(1, subset_size)
        self.upper_bound = upper_bound
        self.best = {}
        self.heap = []

    def insert_key_value(self, key: int, value: int | float):
        """
        Insert/refresh a key-value pair; keeps only the best value per key.
        """
        if value < self.best.get(key, inf):
            self.best[key] = value
            heappush(self.heap, (value, key))

    def __pop_current__(self):
        """
        Pop the current minimum key that matches self.best.
        Returns None if heap is exhausted of current items.
        """
        while self.heap:
            value, key = heappop(self.heap)
            if self.best.get(key, inf) == value:
                self.best.pop(key, None)  # Remove stale key
                return key
        return None

    def is_empty(self) -> bool:
        """
        Check for empty data structure.
        """
        return len(self.best)==0

    def pull(self):
        """
        Return (remaining_best, subset) where subset is up to self.subset_size keys with *globally* smallest values.
        Remove the returned keys from the structure (matching Alg. 3 semantics).
        remaining_best is the smallest value still present after removal, or self.upper_bound if empty.
        """
        subset = set()
        count = 0

        # Take up to M distinct current keys
        while count < self.subset_size:
            key = self.__pop_current__()
            if key is None:
                break
            subset.add(key)
            count += 1

        # Compute lower bound for remaining
        remaining_best = min(self.best.values()) if self.best else self.upper_bound
        return remaining_best, subset


class BmsspSolver:
    def __init__(self, graph: list[dict[int, int | float]], origin_id: int):
        """
        Initialize the BMSSP solver with a graph represented as an adjacency list.
        """
        self.graph = graph
        self.original_graph_length = len(graph)
        self.graph_length = len(self.graph)
        self.distance_matrix = [inf] * self.graph_length
        self.predecessor = [-1] * self.graph_length
        self.distance_matrix[origin_id] = 0

        if self.graph_length <= 2:
            raise ValueError("Your provided graph must have more than 2 nodes")

        # Practical choices (k and t) based on n
        self.pivot_relaxation_steps = max(2, int(log(self.graph_length) ** (1 / 3.0)))  # k
        self.target_tree_depth = max(2, int(log(self.graph_length) ** (2 / 3.0)))       # t

        # Compute max_tree_depth based on k and t
        self.max_tree_depth = int(ceil(log(max(2, self.graph_length)) / max(1, self.target_tree_depth)))

        # Run the solver algorithm
        upper_bound, frontier = self.recursive_bmssp(self.max_tree_depth, inf, {origin_id})

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

        # Multi-step limited relaxation from current frontier
        for _ in range(self.pivot_relaxation_steps):
            curr_frontier = set()
            for prev_frontier_idx in prev_frontier:
                prev_frontier_distance = self.distance_matrix[prev_frontier_idx]
                for connection_idx, connection_distance in self.graph[prev_frontier_idx].items():
                    new_distance = prev_frontier_distance + connection_distance
                    # Important: Allow equality on relaxations
                    if new_distance <= self.distance_matrix[connection_idx]:
                        if new_distance < self.distance_matrix[connection_idx]:
                            self.predecessor[connection_idx] = prev_frontier_idx
                            self.distance_matrix[connection_idx] = new_distance
                        if new_distance < upper_bound:
                            curr_frontier.add(connection_idx)
            temp_frontier.update(curr_frontier)
            # If the search balloons, take the current frontier as pivots
            if len(temp_frontier) > self.pivot_relaxation_steps * len(frontier):
                pivots = set(frontier)
                return pivots, temp_frontier
            prev_frontier = curr_frontier

        # Build tight-edge forest F on temp_frontier: edges (u -> v) with db[u] + w == db[v]
        forest_adj = {i: set() for i in temp_frontier}
        indegree = {i: 0 for i in temp_frontier}
        for frontier_idx in temp_frontier:
            frontier_distance = self.distance_matrix[frontier_idx]
            for connection_idx, connection_distance in self.graph[frontier_idx].items():
                if connection_idx in temp_frontier and abs((frontier_distance + connection_distance) - self.distance_matrix[connection_idx]) < 1e-12:
                    # direction is frontier_idx -> connection_idx (parent to child)
                    forest_adj[frontier_idx].add(connection_idx)
                    indegree[connection_idx] += 1

        # Non-sticky DFS that counts size of the reachable tree
        def dfs_count(root):
            seen = set()
            stack = [root]
            cnt = 0
            while stack:
                x = stack.pop()
                if x in seen:
                    continue
                seen.add(x)
                cnt += 1
                stack.extend(forest_adj[x])
            return cnt

        pivots = set()
        for frontier_idx in frontier:
            if indegree.get(frontier_idx, 0) == 0:
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
        first_frontier = next(iter(frontier))

        new_frontier = set()
        heap = []
        heappush(heap, (self.distance_matrix[first_frontier], first_frontier))
        visited = set()
        # grow until we exceed pivot_relaxation_steps (practical limit), as in Algorithm 2
        while heap and len(new_frontier) < self.pivot_relaxation_steps + 1:
            frontier_distance, frontier_idx = heappop(heap)
            if frontier_idx in visited:
                continue
            visited.add(frontier_idx)
            new_frontier.add(frontier_idx)
            for connection_idx, connection_distance in self.graph[frontier_idx].items():
                new_distance = frontier_distance + connection_distance
                if new_distance <= self.distance_matrix[connection_idx] and new_distance < upper_bound:
                    if new_distance < self.distance_matrix[connection_idx]:
                        self.predecessor[connection_idx] = frontier_idx
                        self.distance_matrix[connection_idx] = new_distance
                    heappush(heap, (new_distance, connection_idx))

        # If we exceeded k, trim by new boundary B' = max db over visited and return new_frontier = {db < B'}
        if len(new_frontier) > self.pivot_relaxation_steps:
            new_upper_bound = max(self.distance_matrix[i] for i in new_frontier)
            new_frontier = {i for i in new_frontier if self.distance_matrix[i] < new_upper_bound}
            return new_upper_bound, new_frontier
        else:
            # Success for this base case: return current upper_bound unchanged and the completed set
            return upper_bound, new_frontier

    def recursive_bmssp(self, recursion_depth, upper_bound, frontier):
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
        # Base case
        if recursion_depth == 0:
            return self.base_case(upper_bound, frontier)

        # Step 4: Find pivots and temporary frontier
        pivots, temp_frontier = self.find_pivots(upper_bound, frontier)

        # Step 5–6: initialize data_struct with pivots
        # subset_size = 2^((l-1) * t)
        subset_size = 2 ** ((recursion_depth - 1) * self.target_tree_depth)
        data_struct = BmsspDataStructure(subset_size=subset_size, upper_bound=upper_bound)
        for pivot in pivots:
            data_struct.insert_key_value(pivot, self.distance_matrix[pivot])

        # Track new_frontier and B' according to Algorithm 3
        new_frontier = set()
        min_pivot_distance = min((self.distance_matrix[p] for p in pivots), default=upper_bound)
        last_min_pivot_distance = min_pivot_distance

        # Work budget that scales with level: k^(2*l*t)
        # k = self.pivot_relaxation_steps
        # t = self.target_tree_depth
        work_budget = self.pivot_relaxation_steps ** (2 * recursion_depth * self.target_tree_depth)

        # Main loop
        while len(new_frontier) < work_budget and not data_struct.is_empty():
            # Step 10: Pull from data_struct: get data_struct_frontier_i and upper_bound_i
            data_struct_frontier_bound_i, data_struct_frontier_i = data_struct.pull()
            if not data_struct_frontier_i:
                # data_struct is empty -> success at this level
                break

            # Step 11: Recurse on (l-1, data_struct_frontier_bound_i, data_struct_frontier_i)
            last_min_pivot_distance_i, new_frontier_i = self.recursive_bmssp(recursion_depth - 1, data_struct_frontier_bound_i, data_struct_frontier_i)

            # Track results
            new_frontier.update(new_frontier_i)
            last_min_pivot_distance = last_min_pivot_distance_i  # If we later stop due to budget, we must return the last_min_pivot_distance

            # Step 13: Initialize intermediate_frontier to batch-prepend
            intermediate_frontier = set()

            # Step 14–20: relax edges from new_frontier_i and enqueue into D or intermediate_frontier per their interval
            for new_frontier_idx in new_frontier_i:
                new_frontier_distance = self.distance_matrix[new_frontier_idx]
                for connection_idx, connection_distance in self.graph[new_frontier_idx].items():
                    # Avoid self-loops
                    if connection_idx == new_frontier_idx:
                        continue
                    new_distance = new_frontier_distance + connection_distance
                    if new_distance <= self.distance_matrix[connection_idx]:
                        if new_distance < self.distance_matrix[connection_idx]:
                            self.predecessor[connection_idx] = new_frontier_idx
                            self.distance_matrix[connection_idx] = new_distance
                        # Insert based on which interval the new distance falls into
                        if data_struct_frontier_bound_i <= new_distance < upper_bound:
                            data_struct.insert_key_value(connection_idx, new_distance)
                        elif last_min_pivot_distance_i <= new_distance < data_struct_frontier_bound_i:
                            intermediate_frontier.add((connection_idx, new_distance))

            # Step 21: Batch prepend intermediate_frontier plus filtered data_struct_frontier_i in last_min_pivot_distance_i, data_struct_frontier_bound_i)
            data_struct_frontier_i_filtered = {(x, self.distance_matrix[x]) for x in data_struct_frontier_i
                            if last_min_pivot_distance_i <= self.distance_matrix[x] < data_struct_frontier_bound_i}
            for frontier_idx, frontier_distance in (intermediate_frontier | data_struct_frontier_i_filtered):
                data_struct.insert_key_value(frontier_idx, frontier_distance)

        # Step 22: Final return
        return min(last_min_pivot_distance, upper_bound), new_frontier | {v for v in temp_frontier if self.distance_matrix[v] < last_min_pivot_distance}

if __name__ == "__main__":
    graph = [
        {1:1,2:1},
        {2:1,3:3},
        {3:1,4:2},
        {4:1},
        {}
    ]
    solver = BmsspSolver(graph, 0)
    if solver.distance_matrix != [0, 1, 1, 2, 3]:
        print("BMSSP Test: Failed")
    else:
        print("BMSSP Test: Passed")