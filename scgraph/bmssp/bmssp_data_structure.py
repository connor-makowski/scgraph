from heapq import heappush, heappop, heapify

inf = float("inf")
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

    def pop_current(self):
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
        return len(self.best) == 0

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
            key = self.pop_current()
            if key is None:
                break
            subset.add(key)
            count += 1

        # Compute lower bound for remaining
        remaining_best = (
            min(self.best.values()) if self.best else self.upper_bound
        )
        return remaining_best, subset

    def batch_insert(self, key_value_pairs: set[tuple[int, int | float]]):
        """
        Insert/refresh multiple key-value pairs at once.
        """
        for key, value in key_value_pairs:
            if value < self.best.get(key, inf):
                self.best[key] = value
                heappush(self.heap, (value, key))

    # def batch_insert_alt(self, key_value_pairs: set[tuple[int, int | float]]):
    #     """
    #     Insert/refresh multiple key-value pairs at once.
    #     This only recalculates the invariant heap once at the end, which is faster for large batches.
    #     - Note: In testing, this was found to be slower.
    #     """
    #     for key, value in key_value_pairs:
    #         if value < self.best.get(key, inf):
    #             self.best[key] = value
    #             self.heap.append((value, key))
    #     # Re-heapify after bulk insertion
    #     heapify(self.heap)