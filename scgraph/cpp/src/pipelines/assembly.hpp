#pragma once
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <stdexcept>
#include <unordered_set>
#include <utility>
#include <vector>

// Kernels that assemble a network file from raw arcs, for networks too large for Python
// (the planet's roads). Each has a pure-Python twin in scgraph/pipelines/steps/assembly.py
// that gives the same results; the contracts are written there.
namespace assembly {

constexpr int64_t MAX_INT32 = 2147483647;
// Arcs and ids are read at random positions: the memory of the one AHEAD is fetched while
// the current one is handled
constexpr int64_t AHEAD = 16;
#if defined(__GNUC__) || defined(__clang__)
#define ASSEMBLY_PREFETCH(address) __builtin_prefetch(address)
#else
#define ASSEMBLY_PREFETCH(address) ((void)0)
#endif

// Sort and remove duplicates: least significant digit radix sort, 11 bits per pass, over
// the bits where the ids differ only (OSM ids: 3 or 4 passes)
inline void sort_unique(std::vector<int64_t>& ids) {
    if (ids.empty()) return;
    uint64_t differ = 0;
    for (int64_t id : ids) differ |= static_cast<uint64_t>(id ^ ids[0]);
    std::vector<int64_t> buffer(ids.size());
    for (int shift = 0; shift < 64 && (differ >> shift); shift += 11) {
        // The sign bit flipped, so that negative ids come first
        auto digit = [shift](int64_t id) {
            return ((static_cast<uint64_t>(id) ^ (uint64_t{1} << 63)) >> shift) & 2047;
        };
        std::vector<int64_t> start(2049, 0);
        for (int64_t id : ids) ++start[digit(id) + 1];
        for (int d = 0; d < 2048; ++d) start[d + 1] += start[d];
        for (int64_t id : ids) buffer[start[digit(id)]++] = id;
        ids.swap(buffer);
    }
    ids.erase(std::unique(ids.begin(), ids.end()), ids.end());
}

// Positions of ids in sorted unique ids (-1 if absent). A table of where each run of high
// bits starts narrows the binary search to a few ids
class IdIndex {
public:
    explicit IdIndex(const std::vector<int64_t>& ids) : ids(ids) {
        if (ids.empty()) return;
        const uint64_t range = bucket(ids.back());
        while (shift < 63 && (range >> shift) > ids.size() / 4) ++shift;
        start.assign((range >> shift) + 2, 0);
        for (int64_t id : ids) ++start[(bucket(id) >> shift) + 1];
        for (size_t b = 1; b < start.size(); ++b) start[b] += start[b - 1];
    }
    // f(a, position of keys[a]) for each key, fetching ahead the table entry then the ids
    template <class F>
    void find_each(const int64_t* keys, int64_t count, F&& f) const {
        for (int64_t a = 0; a < count; ++a) {
            if (a + 2 * AHEAD < count) ASSEMBLY_PREFETCH(entry(keys[a + 2 * AHEAD]));
            if (a + AHEAD < count && entry(keys[a + AHEAD])) ASSEMBLY_PREFETCH(&ids[*entry(keys[a + AHEAD])]);
            const int64_t* range = entry(keys[a]);
            int64_t position = -1;
            if (range) {
                auto first = ids.begin() + range[0], last = ids.begin() + range[1];
                auto found = std::lower_bound(first, last, keys[a]);
                if (found != last && *found == keys[a]) position = found - ids.begin();
            }
            f(a, position);
        }
    }

private:
    const std::vector<int64_t>& ids;
    int shift = 0;
    std::vector<int64_t> start;
    uint64_t bucket(int64_t id) const { return static_cast<uint64_t>(id) - static_cast<uint64_t>(ids.front()); }
    const int64_t* entry(int64_t id) const {
        if (ids.empty() || id < ids.front() || id > ids.back()) return nullptr;
        return &start[bucket(id) >> shift];
    }
};

struct ArcTable {
    std::vector<int64_t> node_ids;
    std::vector<int32_t> offsets, heads, kept;
    std::vector<double> weights;
};

inline ArcTable csr_from_arcs(const int64_t* origins, const int64_t* destinations,
                              const double* weights, int64_t arc_count) {
    if (arc_count > MAX_INT32) throw std::invalid_argument("at most 2**31 - 1 arcs");
    // The origins, then the destinations that are not origins (few: most nodes are both)
    ArcTable table;
    std::vector<int64_t>& ids = table.node_ids;
    ids.reserve(arc_count);
    for (int64_t a = 0; a < arc_count; ++a) {
        if (origins[a] != destinations[a]) ids.push_back(origins[a]);
    }
    sort_unique(ids);
    {
        std::vector<int64_t> others;
        IdIndex(ids).find_each(destinations, arc_count, [&](int64_t a, int64_t position) {
            if (origins[a] != destinations[a] && position < 0) others.push_back(destinations[a]);
        });
        sort_unique(others);
        // Merge from the back, in place
        size_t i = ids.size(), j = others.size(), k = ids.size() + others.size();
        ids.resize(k);
        while (j > 0) ids[--k] = i > 0 && ids[i - 1] > others[j - 1] ? ids[--i] : others[--j];
    }
    ids.shrink_to_fit();
    if (static_cast<int64_t>(ids.size()) > MAX_INT32) throw std::invalid_argument("at most 2**31 - 1 nodes");
    const int32_t n = static_cast<int32_t>(ids.size());

    // Arcs by position, self-loops marked -1
    std::vector<int32_t> tails(arc_count, -1), heads(arc_count, -1);
    const IdIndex index(ids);
    index.find_each(origins, arc_count, [&](int64_t a, int64_t position) {
        if (origins[a] != destinations[a]) tails[a] = static_cast<int32_t>(position);
    });
    index.find_each(destinations, arc_count, [&](int64_t a, int64_t position) {
        if (origins[a] != destinations[a]) heads[a] = static_cast<int32_t>(position);
    });

    // Arcs by tail (a counting sort), each packed as head << 32 | input index, then each
    // row sorted: by head, then input index. Rows are short and in one place
    std::vector<int32_t> start(static_cast<size_t>(n) + 1, 0);
    for (int64_t a = 0; a < arc_count; ++a) {
        if (a + AHEAD < arc_count && tails[a + AHEAD] >= 0) ASSEMBLY_PREFETCH(&start[tails[a + AHEAD] + 1]);
        if (tails[a] >= 0) ++start[tails[a] + 1];
    }
    for (int32_t u = 0; u < n; ++u) start[u + 1] += start[u];
    std::vector<uint64_t> arcs(start[n]);
    for (int64_t a = 0; a < arc_count; ++a) {
        if (a + 2 * AHEAD < arc_count && tails[a + 2 * AHEAD] >= 0) ASSEMBLY_PREFETCH(&start[tails[a + 2 * AHEAD]]);
        if (a + AHEAD < arc_count && tails[a + AHEAD] >= 0) ASSEMBLY_PREFETCH(&arcs[start[tails[a + AHEAD]]]);
        if (tails[a] >= 0) arcs[start[tails[a]]++] = static_cast<uint64_t>(heads[a]) << 32 | a;
    }
    // Free them (assigning {} would keep the memory)
    std::vector<int32_t>().swap(tails);
    std::vector<int32_t>().swap(heads);

    // Now start[u] is where row u ends; offsets overwrite it, behind the reads. Of
    // parallel arcs, keep the shortest, the first in the input on a tie
    table.heads.reserve(arcs.size());
    table.weights.reserve(arcs.size());
    table.kept.reserve(arcs.size());
    int32_t begin = 0;
    for (int32_t u = 0; u < n; ++u) {
        const int32_t end = start[u];
        start[u] = static_cast<int32_t>(table.heads.size());
        std::sort(arcs.begin() + begin, arcs.begin() + end);
        for (int64_t i = begin + AHEAD; i < end + AHEAD && i < static_cast<int64_t>(arcs.size()); ++i) {
            ASSEMBLY_PREFETCH(&weights[static_cast<uint32_t>(arcs[i])]);
        }
        for (int32_t i = begin; i < end;) {
            const uint32_t head = arcs[i] >> 32;
            uint32_t best = static_cast<uint32_t>(arcs[i]);
            for (++i; i < end && arcs[i] >> 32 == head; ++i) {
                const uint32_t a = static_cast<uint32_t>(arcs[i]);
                if (weights[a] < weights[best]) best = a;
            }
            table.heads.push_back(head);
            table.kept.push_back(best);
            table.weights.push_back(weights[best]);
        }
        begin = end;
    }
    start[n] = static_cast<int32_t>(table.heads.size());
    table.offsets = std::move(start);
    return table;
}

// Offsets of rows over count items: from 0 to count, never decreasing
inline void check_offsets(const int32_t* offsets, int64_t rows, int64_t count) {
    bool valid = rows >= 0 && offsets[0] == 0 && offsets[rows] == count;
    for (int64_t r = 0; valid && r < rows; ++r) valid = offsets[r] <= offsets[r + 1];
    if (!valid) throw std::invalid_argument("offsets must rise from 0 to the number of items");
}

struct Components {
    std::vector<int32_t> labels, sizes;
};

inline Components strongly_connected_components(const int32_t* offsets, const int32_t* heads, int64_t node_count,
                                                int64_t arc_count) {
    check_offsets(offsets, node_count, arc_count);
    const int32_t n = static_cast<int32_t>(node_count);
    for (int64_t a = 0; a < arc_count; ++a) {
        if (heads[a] < 0 || heads[a] >= n) throw std::out_of_range("head out of range");
    }
    // Kosaraju: order the nodes by the end of a depth-first search, then search the
    // reverse graph from the last one finished
    std::vector<int32_t> finished;
    std::vector<char> seen(n, 0);
    std::vector<std::pair<int32_t, int32_t>> path;  // node, its next arc
    for (int32_t first = 0; first < n; ++first) {
        if (seen[first]) continue;
        seen[first] = 1;
        path.push_back({first, offsets[first]});
        while (!path.empty()) {
            const auto [node, arc] = path.back();
            if (arc == offsets[node + 1]) {
                path.pop_back();
                finished.push_back(node);
                continue;
            }
            path.back().second = arc + 1;
            if (!seen[heads[arc]]) {
                seen[heads[arc]] = 1;
                path.push_back({heads[arc], offsets[heads[arc]]});
            }
        }
    }
    std::vector<int32_t> reverse_start(static_cast<size_t>(n) + 1, 0), reverse(arc_count);
    for (int64_t a = 0; a < arc_count; ++a) ++reverse_start[heads[a] + 1];
    for (int32_t u = 0; u < n; ++u) reverse_start[u + 1] += reverse_start[u];
    std::vector<int32_t> next(reverse_start.begin(), reverse_start.end() - 1);
    for (int32_t u = 0; u < n; ++u) {
        for (int32_t a = offsets[u]; a < offsets[u + 1]; ++a) reverse[next[heads[a]]++] = u;
    }
    std::vector<int32_t> component(n, -1), stack;
    int32_t count = 0;
    for (auto it = finished.rbegin(); it != finished.rend(); ++it) {
        if (component[*it] != -1) continue;
        component[*it] = count;
        stack.push_back(*it);
        while (!stack.empty()) {
            const int32_t node = stack.back();
            stack.pop_back();
            for (int32_t a = reverse_start[node]; a < reverse_start[node + 1]; ++a) {
                if (component[reverse[a]] == -1) {
                    component[reverse[a]] = count;
                    stack.push_back(reverse[a]);
                }
            }
        }
        ++count;
    }
    // Number the components in the order of their smallest node
    Components result;
    std::vector<int32_t> number(count, -1);
    for (int32_t u = 0; u < n; ++u) {
        int32_t& label = number[component[u]];
        if (label == -1) {
            label = static_cast<int32_t>(result.sizes.size());
            result.sizes.push_back(0);
        }
        component[u] = label;
        ++result.sizes[label];
    }
    result.labels = std::move(component);
    return result;
}

struct Contracted {
    std::vector<int32_t> kept, origins, heads, member_offsets, members;
    std::vector<double> weights;
};

// Same rules and order of operations as the Python twin (contract_chains)
inline Contracted contract_chains(const int32_t* offsets, const int32_t* heads, const double* weights,
                                  const uint8_t* modes, int64_t node_count, int64_t arc_count, double max_km) {
    check_offsets(offsets, node_count, arc_count);
    const int32_t n = static_cast<int32_t>(node_count);
    std::vector<int32_t> indegree(n, 0), first(n, -1), second(n, -1);
    for (int32_t u = 0; u < n; ++u) {
        for (int32_t a = offsets[u]; a < offsets[u + 1]; ++a) {
            const int32_t v = heads[a];
            if (v < 0 || v >= n || v == u || (a > offsets[u] && v <= heads[a - 1]))
                throw std::out_of_range("rows must rise within the nodes, without loops");
            if (indegree[v] == 0) first[v] = u;
            else if (indegree[v] == 1) second[v] = u;
            ++indegree[v];
        }
    }
    auto degree = [&](int32_t v) { return offsets[v + 1] - offsets[v]; };
    std::vector<char> chain(n), keep(n), seen(n, 0);
    for (int32_t v = 0; v < n; ++v) {
        const int32_t* out = heads + offsets[v];
        // Predecessors are seen in rising order, so first < second
        const bool two_way = degree(v) == 2 && indegree[v] == 2 && first[v] == out[0] && second[v] == out[1];
        const bool one_way = degree(v) == 1 && indegree[v] == 1 && first[v] != out[0];
        chain[v] = (two_way || one_way) &&
                   (!modes || (modes[out[0]] == modes[v] && modes[two_way ? out[1] : first[v]] == modes[v]));
        keep[v] = !chain[v];
    }
    for (auto* unused : {&indegree, &first, &second}) std::vector<int32_t>().swap(*unused);
    auto arc = [&](int32_t u, int32_t v) {  // the index of arc u -> v
        return static_cast<int32_t>(std::lower_bound(heads + offsets[u], heads + offsets[u + 1], v) - heads);
    };
    std::unordered_set<uint64_t> pairs;  // (origin, head) of the arcs made by contraction
    auto exists = [&](int32_t u, int32_t v) {  // an input arc, or an arc made
        return pairs.count(static_cast<uint64_t>(u) << 32 | v) || std::binary_search(heads + offsets[u], heads + offsets[u + 1], v);
    };
    // Each input arc is the member of one arc at most: reserved once, never copied as
    // they grow, and only the pages used are resident
    struct Arc { int32_t u, v; double km; int32_t first, count; };
    std::vector<Arc> arcs;
    std::vector<int32_t> pool;  // the arcs' members, each arc's in a run
    arcs.reserve(arc_count), pool.reserve(arc_count);
    auto add = [&](int32_t u, int32_t v, double km, int64_t first) {
        arcs.push_back({u, v, km, static_cast<int32_t>(first), static_cast<int32_t>(pool.size() - first)});
        pairs.insert(static_cast<uint64_t>(u) << 32 | v);
    };
    for (int32_t u = 0; u < n; ++u) {
        for (int32_t a = offsets[u]; a < offsets[u + 1]; ++a) {
            if (keep[u] && keep[heads[a]]) pool.push_back(a), arcs.push_back({u, heads[a], weights[a], (int32_t)pool.size() - 1, 1});
        }
    }
    std::vector<int32_t> nodes, path;
    std::vector<std::pair<int32_t, int32_t>> pieces;
    auto contract = [&](int32_t s, int32_t a) {
        nodes.assign(1, s);
        path.assign(1, a);
        while (!keep[heads[path.back()]]) {  // walk to the next kept node
            const int32_t v = heads[path.back()];
            seen[v] = 1;
            nodes.push_back(v);
            path.push_back(offsets[v] + (degree(v) == 2 && heads[offsets[v]] == nodes[nodes.size() - 2]));
        }
        nodes.push_back(heads[path.back()]);
        // Cut where the length from the canonical end reaches max_km
        const int32_t length = static_cast<int32_t>(path.size());
        double total = 0.0;
        pieces.clear();
        for (int32_t i = 1, start = 0; i <= length; ++i) {
            total += weights[path[i - 1]];
            if (total >= max_km || i == length) pieces.push_back({start, i}), start = i, total = 0.0;
        }
        std::reverse(pieces.begin(), pieces.end());
        const bool both = degree(nodes[1]) == 2;
        while (!pieces.empty()) {
            const auto [i, j] = pieces.back();
            pieces.pop_back();
            const int32_t b = nodes[i], e = nodes[j];
            if (j - i > 1 && (b == e || exists(b, e) || (both && exists(e, b)))) {
                pieces.push_back({i + (j - i) / 2, j});
                pieces.push_back({i, i + (j - i) / 2});
                continue;
            }
            keep[b] = keep[e] = 1;
            const int64_t forward = static_cast<int64_t>(pool.size());
            double km = 0;
            for (int32_t k = i; k < j; ++k) km += weights[path[k]], pool.push_back(path[k]);
            add(b, e, km, forward);
            if (both) {  // members in travel order, summed from the canonical end
                const int64_t backward = static_cast<int64_t>(pool.size());
                km = 0;
                for (int32_t k = i; k < j; ++k) km += weights[arc(nodes[k + 1], nodes[k])];
                for (int32_t k = j - 1; k >= i; --k) pool.push_back(arc(nodes[k + 1], nodes[k]));
                add(e, b, km, backward);
            }
        }
    };
    for (int32_t s = 0; s < n; ++s) {
        for (int32_t a = offsets[s]; a < offsets[s + 1]; ++a) {
            if (!chain[s] && chain[heads[a]] && !seen[heads[a]]) contract(s, a);
        }
    }
    for (int32_t v = 0; v < n; ++v) {  // isolated cycles
        if (chain[v] && !seen[v]) keep[v] = seen[v] = 1, contract(v, offsets[v]);
    }
    std::unordered_set<uint64_t>().swap(pairs);  // freed before the result is built
    std::vector<char>().swap(chain), std::vector<char>().swap(seen);
    Contracted result;
    std::vector<int32_t> position(n, -1);
    for (int32_t v = 0; v < n; ++v) {
        if (keep[v]) position[v] = static_cast<int32_t>(result.kept.size()), result.kept.push_back(v);
    }
    std::sort(arcs.begin(), arcs.end(), [](const Arc& x, const Arc& y) { return std::pair(x.u, x.v) < std::pair(y.u, y.v); });
    // The members first, then the pool is freed; then the arcs' columns
    result.members.reserve(pool.size());
    result.member_offsets.reserve(arcs.size() + 1);
    result.member_offsets.push_back(0);
    for (const Arc& x : arcs) {
        result.members.insert(result.members.end(), pool.begin() + x.first, pool.begin() + x.first + x.count);
        result.member_offsets.push_back(static_cast<int32_t>(result.members.size()));
    }
    std::vector<int32_t>().swap(pool);
    result.origins.reserve(arcs.size()), result.heads.reserve(arcs.size()), result.weights.reserve(arcs.size());
    for (const Arc& x : arcs) {
        result.origins.push_back(position[x.u]);
        result.heads.push_back(position[x.v]);
        result.weights.push_back(x.km);
    }
    return result;
}

struct Shapes {
    std::vector<int32_t> points, offsets;
};

// Same formulas and order of operations as the Python twin, and no fused multiply-add
// (CMakeLists.txt), so that both keep the same points
inline Shapes simplify_shapes(const int32_t* points, int64_t point_count, const int32_t* offsets,
                              const int32_t* ends, int64_t shape_count, double tolerance_m) {
    if (!(tolerance_m >= 0)) throw std::invalid_argument("tolerance_m must be >= 0");
    check_offsets(offsets, shape_count, point_count);
    constexpr double PI = 3.141592653589793;
    constexpr double METRES = 6371000.0 * PI / 1.8e9;  // per 1e-7 degree of latitude
    const double tolerance2 = tolerance_m * tolerance_m;
    Shapes result;
    result.offsets.push_back(0);
    std::vector<double> x, y;
    std::vector<char> keep;
    std::vector<std::pair<int64_t, int64_t>> stack;
    for (int64_t s = 0; s < shape_count; ++s) {
        const int32_t* end = ends + 4 * s;
        const int64_t base = 2 * (static_cast<int64_t>(offsets[s]) - 1);  // point i of the polyline at base + 2 * i
        const int64_t last = offsets[s + 1] - offsets[s] + 1;
        const double kx = METRES * std::cos(end[0] * PI / 1.8e9);
        x.resize(last + 1);
        y.resize(last + 1);
        // Local metres from the arc's origin, longitudes across the antimeridian unwrapped
        auto place = [&](int64_t i, int32_t latitude, int32_t longitude) {
            int64_t dlon = static_cast<int64_t>(longitude) - end[1];
            if (dlon > 1800000000) dlon -= 3600000000;
            else if (dlon < -1800000000) dlon += 3600000000;
            x[i] = dlon * kx;
            y[i] = (static_cast<int64_t>(latitude) - end[0]) * METRES;
        };
        place(0, end[0], end[1]);
        for (int64_t i = 1; i < last; ++i) place(i, points[base + 2 * i], points[base + 2 * i + 1]);
        place(last, end[2], end[3]);
        keep.assign(last + 1, 0);
        stack.assign(1, {0, last});
        while (!stack.empty()) {
            const auto [a, b] = stack.back();
            stack.pop_back();
            const double dx = x[b] - x[a], dy = y[b] - y[a], length2 = dx * dx + dy * dy;
            int64_t farthest = -1;
            double worst = tolerance2;
            for (int64_t i = a + 1; i < b; ++i) {
                double px = x[i] - x[a], py = y[i] - y[a];
                if (length2 > 0) {
                    double t = (px * dx + py * dy) / length2;
                    t = t < 0 ? 0 : t > 1 ? 1 : t;
                    px = px - t * dx;
                    py = py - t * dy;
                }
                const double d2 = px * px + py * py;
                if (d2 > worst) farthest = i, worst = d2;
            }
            if (farthest >= 0) {
                keep[farthest] = 1;
                stack.push_back({a, farthest});
                stack.push_back({farthest, b});
            }
        }
        for (int64_t i = 1; i < last; ++i) {
            if (keep[i]) result.points.insert(result.points.end(), points + (base + 2 * i), points + (base + 2 * i + 2));
        }
        result.offsets.push_back(static_cast<int32_t>(result.points.size() / 2));
    }
    return result;
}

}  // namespace assembly
