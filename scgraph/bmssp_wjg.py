import math
import heapq
from collections import defaultdict

Length = float
Vertex = int

class Entry:
    def __init__(self, b, u_set):
        self._b = b
        self._u_set = set(u_set)

    def b(self):
        return self._b

    def u_set(self):
        return self._u_set

    @staticmethod
    def new(b, u_set):
        return Entry(b, u_set)


class Edge:
    def __init__(self, vertex, length):
        self._vertex = vertex
        self._length = length

    def vertex(self):
        return self._vertex

    def length(self):
        return self._length


class Heap:
    """Min-heap for (distance, vertex)."""
    def __init__(self):
        self.h = []

    def push(self, v, dist):
        heapq.heappush(self.h, (dist, v))

    def pop(self):
        if self.h:
            dist, v = heapq.heappop(self.h)
            return Edge(v, dist)
        return None

    def is_empty(self):
        return not self.h


class BlockHeap:
    """
    Bucketed heap used by BMSSP.

    - If b is finite, split [0, b) into m equal-width buckets (width = b/m).
    - If b is infinite (or <=0), use absolute bucket width = m.

    pull() returns the entire smallest bucket; Entry.b() is that bucket's UPPER BOUND.
    """
    def __init__(self, m, b):
        self.m = max(int(m), 1)
        self.b = b
        self.buckets = defaultdict(list)  # UB -> list[(dist, vertex)]
        self.bucket_keys = []             # min-heap of bucket UBs
        self.size = 0

        if math.isinf(b) or b <= 0:
            self.mode = "abs"
            self.width = float(self.m)
        else:
            self.mode = "ratio"
            self.width = b / float(self.m)

        if self.width <= 0:
            self.width = 1.0

    def _bucket_bounds(self, dist):
        if dist < 0:
            idx = 0
        else:
            idx = int(dist // self.width)
        lb = idx * self.width
        ub = (idx + 1) * self.width
        return lb, ub

    def insert(self, v, dist):
        lb, ub = self._bucket_bounds(dist)
        key = ub  # use UB to order buckets
        if key not in self.buckets:
            heapq.heappush(self.bucket_keys, key)
        self.buckets[key].append((dist, v))
        self.size += 1

    def pull(self):
        if not self.bucket_keys:
            return None
        key = heapq.heappop(self.bucket_keys)
        items = self.buckets.pop(key, [])
        self.size -= len(items)
        u_set = {v for (_, v) in items}
        return Entry(key, u_set)  # key is the bucket's UPPER bound

    def batch_prepend(self, items):
        for v, dist in items:
            self.insert(v, dist)

    def is_empty(self):
        return self.size == 0


class Pivots:
    def __init__(self, p, w):
        self.p = p
        self.w = w

    @staticmethod
    def new(p, w):
        return Pivots(p, w)


class BmsspWjg:
    def __init__(self, graph):
        """
        graph: list of dicts where graph[u] = {v: weight, ...}
        """
        self.graph = graph
        self.t = 0
        self.k = 0
        self.dhat = []
        self.prev = []
        self.previous = []
        self.tree_size = []
        self.f = []

    def get(self, s: Vertex):
        n = len(self.graph)
        self.dhat = [math.inf] * n
        self.dhat[s] = 0.0
        self.prev = [None] * n
        self.previous = [-1] * n
        self.tree_size = [None] * n
        self.f = [[] for _ in range(n)]

        n_f = float(n)
        t = math.floor((math.log2(n_f) ** (2.0 / 3.0)))
        if t <= 0:
            t = 1
        self.k = max(1, math.ceil((math.log2(n_f) ** (1.0 / 3.0))))
        self.t = t
        l = math.ceil(math.log2(n_f) / t)

        self.bmssp(l, math.inf, [s])
        return self.dhat.copy(), self.previous.copy()

    def bmssp(self, l: int, b: Length, s: list[Vertex]) -> Entry:
        if l == 0:
            return self.base_case(b, s)

        pivots = self.find_pivots(b, s)

        m = 2 ** ((l - 1) * self.t)
        d = BlockHeap(m, b)
        bd = math.inf

        for u in pivots.p:
            d.insert(u, self.dhat[u])
            bd = min(bd, self.dhat[u])

        u_set = set()

        while len(u_set) < self.k * 2 ** (l * self.t) and not d.is_empty():
            entry = d.pull()
            if entry is None:
                break

            b_entry = self.bmssp(l - 1, entry.b(), list(entry.u_set()))

            for u in b_entry.u_set():
                u_set.add(u)

            k_vec = []
            for u in b_entry.u_set():
                for v, w in self.graph[u].items():
                    if v == u:
                        continue
                    if self.dhat[v] >= self.dhat[u] + w:
                        new_dist = self.dhat[u] + w
                        self.dhat[v] = new_dist
                        self.prev[v] = u
                        self.previous[v] = u
                        if entry.b() <= new_dist < b:
                            d.insert(v, new_dist)
                        elif b_entry.b() <= new_dist < entry.b():
                            k_vec.append((v, new_dist))

            for u in entry.u_set():
                if b_entry.b() <= self.dhat[u] < entry.b():
                    k_vec.append((u, self.dhat[u]))

            d.batch_prepend(k_vec)
            bd = b_entry.b()

        bd = min(bd, b)
        for u in pivots.w:
            if self.dhat[u] < bd:
                u_set.add(u)

        return Entry.new(bd, list(u_set))

    def base_case(self, b: Length, s: list[Vertex]) -> Entry:
        assert len(s) == 1
        x = s[0]
        u0 = set(s)

        h = Heap()
        h.push(x, self.dhat[x])

        while not h.is_empty() and len(u0) < self.k + 1:
            edge = h.pop()
            if edge is None:
                break
            u = edge.vertex()
            u0.add(u)

            for v, w in self.graph[u].items():
                if self.dhat[v] >= self.dhat[u] + w and self.dhat[u] + w < b:
                    self.dhat[v] = self.dhat[u] + w
                    h.push(v, self.dhat[v])

        if len(u0) <= self.k:
            return Entry.new(b, list(u0))
        else:
            bd = max(self.dhat[u] for u in u0)
            u_vec = [u for u in u0 if self.dhat[u] < bd]
            return Entry.new(bd, u_vec)

    def find_pivots(self, b: Length, s: list[Vertex]) -> Pivots:
        w = set(s)
        wp = set(s)

        for v in w:
            self.prev[v] = None

        for _ in range(self.k):
            wi = set()
            for u in wp:
                for v, wlen in self.graph[u].items():
                    if self.dhat[v] >= self.dhat[u] + wlen and self.dhat[u] + wlen < b:
                        self.dhat[v] = self.dhat[u] + wlen
                        self.prev[v] = u
                        self.previous[v] = u
                        wi.add(v)

            w |= wi

            if len(w) >= self.k * len(s):
                return Pivots.new(s.copy(), list(w))
            wp = wi

        for v in w:
            self.tree_size[v] = None
            self.f[v].clear()

        for v in w:
            if self.prev[v] is not None:
                self.f[self.prev[v]].append(v)

        p = []
        for u in s:
            if self.find_tree_size(u) >= self.k and self.prev[u] is None:
                p.append(u)

        return Pivots.new(p, list(w))

    def find_tree_size(self, u: int) -> int:
        if self.tree_size[u] is not None:
            return self.tree_size[u]

        res = 1
        for v in self.f[u]:
            res += self.find_tree_size(v)
        self.tree_size[u] = res
        return res


