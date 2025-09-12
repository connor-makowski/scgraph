from heapq import heappush, heappop
from math import ceil, log

from .bmssp_data_structure import BmsspDataStructure

inf = float("inf")

def cnt_reachable_nodes(root: int, forest: dict[int, set[int]]) -> int:
    """
    Function:

    - Return the number of nodes reachable from root in the directed forest defined by forest.

    Required Arguments:

    - `root`
        - Type: int
        - What: The starting node for the DFS traversal.
    - `forest`
        - Type: dict[int, set[int]]
        - What: Adjacency list representing the directed forest.
    """
    seen = set()
    stack = [root]
    cnt = 0
    while stack:
        x = stack.pop()
        if x in seen:
            continue
        seen.add(x)
        cnt += 1
        stack.extend(forest[x])
    return cnt


class BmsspSolver:
    def __init__(self, graph: list[dict[int, int | float]], origin_ids: set[int] | int):
        """
        Function:

        - Initialize the BMSSP solver with a graph represented as an adjacency list.

        Required Arguments:

        - graph:
            - Type: list[dict[int, int | float]]
            - Description: The graph is represented as an adjacency list, where each node points to a dictionary of its neighbors and their edge weights.
        - origin_ids:
            - Type: set[int] | int
            - What: The IDs of the starting nodes for the BMSSP algorithm.
            - Note: Can be a single integer or a set of integers.

        Optional Arguments:

        - None
        """
        if isinstance(origin_ids, int):
            origin_ids = {origin_ids}
        self.graph = graph
        graph_len = len(graph)
        self.distance_matrix = [inf] * graph_len
        # Addition: Initialize Predecessor array for path reconstruction
        self.predecessor = [-1] * graph_len
        for origin_id in origin_ids:
            self.distance_matrix[origin_id] = 0

        if graph_len <= 2:
            raise ValueError("Your provided graph must have more than 2 nodes")

        # Practical choices (k and t) based on n
        self.pivot_relaxation_steps = max(
            2, int(log(graph_len) ** (1 / 3.0))
        )  # k
        # Modification: Change int to ceil
        self.target_tree_depth = max(
            2, ceil(log(graph_len) ** (2 / 3.0))
        )  # t

        # Compute max_tree_depth based on k and t
        self.max_tree_depth = int(
            ceil(
                    log(graph_len) / self.target_tree_depth
                )
        )

        # Run the solver algorithm
        upper_bound, frontier = self.recursive_bmssp(
            self.max_tree_depth, inf, origin_ids
        )

    def find_pivots(
        self, upper_bound: int | float, frontier: set[int]
    ) -> tuple[set[int], set[int]]:
        """
        Function:

        - Finds pivot sets pivots and temp_frontier according to Algorithm 1.

        Required Arguments:

        - upper_bound:
            - Type: int | float
            - What: The upper bound threshold (B)
        - frontier:
            - Type: set[int]
            - What: Set of vertices (S)

        Optional Arguments:

        - None

        Returns:

        - pivots:
            - Type: Set[int]
            - What: Set of pivot vertices
        - frontier:
            - Type: Set[int]
            - What: Return a new frontier set of vertices within the upper_bound
        """
        temp_frontier = set(frontier)
        prev_frontier = set(frontier)

        # Multi-step limited relaxation from current frontier
        for _ in range(self.pivot_relaxation_steps):
            curr_frontier = set()
            for prev_frontier_idx in prev_frontier:
                prev_frontier_distance = self.distance_matrix[prev_frontier_idx]
                for connection_idx, connection_distance in self.graph[
                    prev_frontier_idx
                ].items():
                    new_distance = prev_frontier_distance + connection_distance
                    # Important: Allow equality on relaxations
                    if new_distance <= self.distance_matrix[connection_idx]:
                        # Addition: Add predecessor tracking
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
        forest = {i: set() for i in temp_frontier}
        indegree = {i: 0 for i in temp_frontier}
        for frontier_idx in temp_frontier:
            frontier_distance = self.distance_matrix[frontier_idx]
            for connection_idx, connection_distance in self.graph[
                frontier_idx
            ].items():
                if (
                    connection_idx in temp_frontier
                    and 
                    (frontier_distance + connection_distance) == self.distance_matrix[connection_idx]
                ):
                    # direction is frontier_idx -> connection_idx (parent to child)
                    forest[frontier_idx].add(connection_idx)
                    indegree[connection_idx] += 1


        pivots = set()
        for frontier_idx in frontier:
            if indegree.get(frontier_idx, 0) == 0:
                size = cnt_reachable_nodes(frontier_idx, forest=forest)
                if size >= self.pivot_relaxation_steps:
                    pivots.add(frontier_idx)

        return pivots, temp_frontier

    def base_case(
        self, upper_bound: int | float, frontier: set[int]
    ) -> tuple[int | float, set[int]]:
        """
        Function:

        - Implements Algorithm 2: Base Case of BMSSP

        Required Arguments:
        - upper_bound:
            - Type: int | float
        - frontier:
            - Type: set
            - What: Set with a single vertex x (complete)

        Returns:
        - new_upper_bound:
            - Type: int | float
            - What: The new upper bound for the search
        - new_frontier:
            - Type: set[int]
            - What: Set of vertices v such that distance_matrix[v] < new_upper_bound
        """
        assert len(frontier) == 1, "Frontier must be a singleton set"
        first_frontier = next(iter(frontier))

        new_frontier = set()
        heap = []
        heappush(heap, (self.distance_matrix[first_frontier], first_frontier))
        # Grow until we exceed pivot_relaxation_steps (practical limit), as in Algorithm 2
        while heap and len(new_frontier) < self.pivot_relaxation_steps + 1:
            frontier_distance, frontier_idx = heappop(heap)
            # Addition: Add check to ensure that we do not get caught in a relaxation loop
            if frontier_idx in new_frontier:
                continue
            new_frontier.add(frontier_idx)
            for connection_idx, connection_distance in self.graph[
                frontier_idx
            ].items():
                new_distance = frontier_distance + connection_distance
                if (
                    new_distance <= self.distance_matrix[connection_idx]
                    and new_distance < upper_bound
                ):
                    # Addition: Add predecessor tracking
                    if new_distance < self.distance_matrix[connection_idx]:
                        self.predecessor[connection_idx] = frontier_idx
                        self.distance_matrix[connection_idx] = new_distance
                    heappush(heap, (new_distance, connection_idx))

        # If we exceeded k, trim by new boundary B' = max db over visited and return new_frontier = {db < B'}
        if len(new_frontier) > self.pivot_relaxation_steps:
            new_upper_bound = max(self.distance_matrix[i] for i in new_frontier)
            new_frontier = {
                i
                for i in new_frontier
                if self.distance_matrix[i] < new_upper_bound
            }
            return new_upper_bound, new_frontier
        else:
            # Success for this base case: return current upper_bound unchanged and the completed set
            return upper_bound, new_frontier

    def recursive_bmssp(
        self, recursion_depth: int, upper_bound: int | float, frontier: set[int]
    ) -> tuple[int | float, set[int]]:
        """
        Function:

        - Implements Algorithm 3: Bounded Multi-Source Shortest Path (BMSSP)

        Required Arguments:

        - recursion_depth:
            - Type: int
            - What: The depth of the recursion
        - upper_bound:
            - Type: float
            - What: The upper bound for the search
        - frontier:
            - Type: set[int]
            - What: The set of vertices to explore

        Returns:

        - new_upper_bound:
            - Type: int | float
            - What: The new upper bound for the search
        - new_frontier:
            - Type: set[int]
            - What: Set of vertices v such that distance_matrix[v] < new_upper_bound
        """
        # Base case
        if recursion_depth == 0:
            return self.base_case(upper_bound, frontier)

        # Step 4: Find pivots and temporary frontier
        pivots, temp_frontier = self.find_pivots(upper_bound, frontier)

        # Step 5–6: initialize data_struct with pivots
        # subset_size = 2^((l-1) * t)
        subset_size = 2 ** ((recursion_depth - 1) * self.target_tree_depth)
        data_struct = BmsspDataStructure(
            subset_size=subset_size, upper_bound=upper_bound
        )
        
        for p in pivots:
            data_struct.insert_key_value(p, self.distance_matrix[p])

        # Track new_frontier and B' according to Algorithm 3
        new_frontier = set()
        # Store the min_pivot_distance for use if the frontier is empty and we break early
        min_pivot_distance = min(
            (self.distance_matrix[p] for p in pivots), default=upper_bound
        )

        # Work budget that scales with level: k^(2*l*t)
        # k = self.pivot_relaxation_steps
        # t = self.target_tree_depth
        work_budget = self.pivot_relaxation_steps ** (
            2 * recursion_depth * self.target_tree_depth
        )

        # Main loop
        while len(new_frontier) < work_budget and not data_struct.is_empty():
            # Step 10: Pull from data_struct: get data_struct_frontier_temp and upper_bound_i
            data_struct_frontier_bound_temp, data_struct_frontier_temp = (
                data_struct.pull()
            )

            # Step 11: Recurse on (l-1, data_struct_frontier_bound_temp, data_struct_frontier_temp)
            min_pivot_distance, new_frontier_temp = self.recursive_bmssp(
                recursion_depth - 1,
                data_struct_frontier_bound_temp,
                data_struct_frontier_temp,
            )

            # Track results
            new_frontier.update(new_frontier_temp)

            # Step 13: Initialize intermediate_frontier to batch-prepend
            intermediate_frontier = set()

            # Step 14–20: relax edges from new_frontier_temp and enqueue into D or intermediate_frontier per their interval
            for new_frontier_idx in new_frontier_temp:
                new_frontier_distance = self.distance_matrix[new_frontier_idx]
                for connection_idx, connection_distance in self.graph[
                    new_frontier_idx
                ].items():
                    # Addition: Avoid self-loops
                    if connection_idx == new_frontier_idx:
                        continue
                    new_distance = new_frontier_distance + connection_distance
                    if new_distance <= self.distance_matrix[connection_idx]:
                        # Addition: Add predecessor tracking
                        if new_distance < self.distance_matrix[connection_idx]:
                            self.predecessor[connection_idx] = new_frontier_idx
                            self.distance_matrix[connection_idx] = new_distance
                        # Insert based on which interval the new distance falls into
                        if (
                            data_struct_frontier_bound_temp
                            <= new_distance
                            < upper_bound
                        ):
                            data_struct.insert_key_value(
                                connection_idx, new_distance
                            )
                        elif (
                            min_pivot_distance
                            <= new_distance
                            < data_struct_frontier_bound_temp
                        ):
                            intermediate_frontier.add(
                                (connection_idx, new_distance)
                            )

            # Step 21: Batch prepend intermediate_frontier plus filtered data_struct_frontier_temp in min_pivot_distance, data_struct_frontier_bound_temp)
            data_struct_frontier_temp_filtered = {
                (x, self.distance_matrix[x])
                for x in data_struct_frontier_temp
                if min_pivot_distance
                <= self.distance_matrix[x]
                < data_struct_frontier_bound_temp
            }

            data_struct.batch_prepend(intermediate_frontier | data_struct_frontier_temp_filtered)

        # Step 22: Final return
        new_bound = min(min_pivot_distance, upper_bound)
        return new_bound, new_frontier | {
            v
            for v in temp_frontier
            if self.distance_matrix[v] < new_bound
        }
