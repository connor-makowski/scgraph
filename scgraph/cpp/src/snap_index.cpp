#include "snap_index.hpp"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <string>
#include <limits>
#include <stdexcept>
#include <utility>

namespace {

constexpr double DEG = 3.14159265358979323846 / 180.0;
constexpr double INF = std::numeric_limits<double>::infinity();
constexpr float FINF = std::numeric_limits<float>::infinity();
// Slack on the chord between a float and a double distance on the unit sphere: coordinate
// and query rounding (2^-24 per component) and float arithmetic stay far below it
constexpr double EPS = 1e-6;
// Coordinate of the unused slots of the last leaf: never within reach of a query
constexpr float PAD = 1000.0f;
// How to fix a scattered order, in the error message. Same text in helpers/snap_index.py
constexpr const char* SORT_HINT =
    "Sort them along a Hilbert curve and map the answers back: "
    "order = scgraph.helpers.hilbert.hilbert_order(nodes); "
    "index = SnapIndex([nodes[i] for i in order]); "
    "node = order[index.closest_idx(point)]";

struct Unit {
    double x, y, z;
};

// Unit vector of a point. Longitudes -180 and 180 stay distinct (1 ulp apart): networks hold
// separate nodes on each side of the antimeridian, and the one on the query's side is nearer
inline Unit unit(double latitude, double longitude) {
    double a = latitude * DEG, b = longitude * DEG, c = std::cos(a);
    return {c * std::cos(b), c * std::sin(b), std::sin(a)};
}

inline double chord2(const Unit& a, const Unit& b) {
    double dx = a.x - b.x, dy = a.y - b.y, dz = a.z - b.z;
    return dx * dx + dy * dy + dz * dz;
}

// Float bounds rounded outward, so that a box always contains its nodes
inline float down(double v) {
    float f = float(v);
    return double(f) > v ? std::nextafter(f, -FINF) : f;
}
inline float up(double v) {
    float f = float(v);
    return double(f) < v ? std::nextafter(f, FINF) : f;
}
// Selects by value: std::max returns a reference, which keeps the loop from vectorising
inline float vmax(float a, float b) { return a > b ? a : b; }

inline double wrap180(double d) {
    if (d > 180.0) return d - 360.0;
    if (d < -180.0) return d + 360.0;
    return d;
}

// Quadrant bits of a node seen from the query: 1 ne, 2 nw, 4 se, 8 sw. Bit 1 << t is
// quadrant out[t] of closest_idx_per_quadrant. The rules are GeoKDTree's
inline int node_quadrants(double la, double lo, double qlat, double qlon) {
    double d = wrap180(lo - qlon);
    bool north = la >= qlat, south = la <= qlat;
    bool east = d >= 0.0 || d == -180.0, west = d <= 0.0 || d == 180.0;
    return (north && east ? 1 : 0) | (north && west ? 2 : 0) | (south && east ? 4 : 0) |
           (south && west ? 8 : 0);
}

// Quadrant bits a latitude/longitude box may hold (conservative)
inline int box_quadrants(double minlat, double maxlat, double minlon, double maxlon,
                         double qlat, double qlon) {
    int mask = 15;
    if (maxlat < qlat) mask &= 4 | 8;
    if (minlat > qlat) mask &= 1 | 2;
    double width = maxlon - minlon;
    if (width < 180.0) {
        double start = wrap180(minlon - qlon);
        if (start > 0.0 && start + width < 180.0) mask &= 1 | 4;
        else if (start > -180.0 && start + width < 0.0) mask &= 2 | 8;
    }
    return mask;
}

inline float widest(int mask, const float* thresholds) {
    float w = 0.0f;
    for (int t = 0; t < 4; ++t)
        if (mask & (1 << t)) w = std::max(w, thresholds[t]);
    return w;
}

// Area of a box of unit vectors (min x, max x, min y, max y, min z, max z): the product of
// its two largest extents. Same expression as in helpers/snap_index.py
inline double unit_area(const double* b) {
    double e[3] = {b[1] - b[0], b[3] - b[2], b[5] - b[4]};
    std::sort(e, e + 3);
    return e[2] * e[1];
}

}  // namespace

struct SnapIndex::Query {
    double lat, lon;  // used by the quadrant rules
    Unit u;           // used by the double check of candidates
    float x, y, z;    // used by the float distances to boxes and leaves
    Query(double latitude, double longitude)
        : lat(latitude), lon(longitude), u(unit(latitude, longitude)),
          x(float(u.x)), y(float(u.y)), z(float(u.z)) {}
};

// Best float squared chord so far, and two thresholds derived from it.
// thr: a node is a candidate if its float squared chord is at most thr; candidates are
// checked again in double. The float chord of a node is within EPS of its exact chord, so
// the exact nearest node has a float chord within 2 EPS of the best one and stays a
// candidate.
// prune: a box is skipped if its float bound is above prune. A box's bound is never above
// the float distance of any node inside it: boxes are rounded outward, and bounds() and
// distances() round alike as the file is compiled without fused multiply-add
// (CMakeLists.txt). So skipping boxes above thr would be enough; prune adds 2 EPS of
// margin. Changing the factors 2 and 4 changes how many boxes and candidates are visited,
// not the answers, as long as thr keeps at least 2 EPS and prune stays >= thr
struct SnapIndex::Best {
    float best = FINF, thr = FINF, prune = FINF;
    // Points to the caller's thread_local vector, which keeps its allocation across queries
    std::vector<std::pair<float, int>>* candidates = nullptr;  // (float distance, position)
    void update(float d) {
        best = d;
        double c = std::sqrt(double(d));
        thr = float((c + 2 * EPS) * (c + 2 * EPS));
        prune = float((c + 4 * EPS) * (c + 4 * EPS));
    }
};

SnapIndex::SnapIndex(const double* latitudes, const double* longitudes, int n,
                     std::shared_ptr<const void> owner)
    : n(n), lat(latitudes), lon(longitudes), owner(std::move(owner)) {
    if (n < 1) throw std::invalid_argument("a snapping index needs at least one node");
    for (int i = 0; i < n; ++i)
        if (!std::isfinite(latitudes[i]) || !std::isfinite(longitudes[i]))
            throw std::invalid_argument("node coordinates must be finite numbers");
    // Leaves, and the box of each leaf (BOX_SLOTS floats, rounded outward by down and up)
    int nleaves = (n + LEAF - 1) / LEAF;
    leaves.resize(nleaves);
    std::vector<float> boxes(BOX_SLOTS * size_t(nleaves));
    // The leaves' unit boxes in double: the sum of their areas and the box around them all
    double leaf_areas = 0.0;
    double all[UNIT_SLOTS] = {INF, -INF, INF, -INF, INF, -INF};
    for (int j = 0; j < nleaves; ++j) {
        double b[BOX_SLOTS] = {INF, -INF, INF, -INF, INF, -INF, INF, -INF, INF, -INF};
        for (int i = 0; i < LEAF; ++i) {
            int p = j * LEAF + i;
            if (p >= n) {
                leaves[j].x[i] = leaves[j].y[i] = leaves[j].z[i] = PAD;
                continue;
            }
            Unit u = unit(lat[p], lon[p]);
            leaves[j].x[i] = float(u.x);
            leaves[j].y[i] = float(u.y);
            leaves[j].z[i] = float(u.z);
            const double v[BOX_SLOTS / 2] = {u.x, u.y, u.z, lat[p], lon[p]};
            for (int t = 0; t < BOX_SLOTS / 2; ++t) {
                b[2 * t] = std::min(b[2 * t], v[t]);
                b[2 * t + 1] = std::max(b[2 * t + 1], v[t]);
            }
        }
        for (int t = 0; t < BOX_SLOTS; ++t)
            boxes[BOX_SLOTS * j + t] = t % 2 == 0 ? down(b[t]) : up(b[t]);
        leaf_areas += unit_area(b);
        for (int t = 0; t < UNIT_SLOTS; t += 2) {
            all[t] = std::min(all[t], b[t]);
            all[t + 1] = std::max(all[t + 1], b[t + 1]);
        }
    }
    // Leaves per query: how many leaf boxes cover a point on average. Nodes in Hilbert order
    // give 1 to 4 per network, plus one per mode sorted on its own; scattered nodes give up to
    // the number of leaves, and every query then scans that many
    const double total = unit_area(all);
    const double per_query = total > 0.0 ? leaf_areas / total : 0.0;
    if (per_query > MAX_LEAVES_PER_QUERY)
        throw node_order_error(
            "nodes scattered in memory: a query would scan about " +
            std::to_string(int64_t(per_query + 0.5)) + " groups of 32 nodes (at most " +
            std::to_string(int(MAX_LEAVES_PER_QUERY)) + "). " + SORT_HINT);
    // Tree levels, bottom up, until a single group
    int children = nleaves;
    do {
        int count = (children + FANOUT - 1) / FANOUT;
        std::vector<Group> groups(count);
        std::vector<float> parents(BOX_SLOTS * size_t(count));
        for (int g = 0; g < count; ++g) {
            float pb[BOX_SLOTS] = {FINF, -FINF, FINF, -FINF, FINF, -FINF, FINF, -FINF, FINF, -FINF};
            for (int k = 0; k < FANOUT; ++k) {
                int c = g * FANOUT + k;
                for (int t = 0; t < BOX_SLOTS; ++t) {
                    // A slot without a child gets a box with min > max. visit and
                    // visit_quadrants test the first unit slot and skip such a slot
                    float v = c < children ? boxes[BOX_SLOTS * c + t] : (t % 2 == 0 ? FINF : -FINF);
                    if (t < UNIT_SLOTS) groups[g].box[t][k] = v;
                    else groups[g].ll[t - UNIT_SLOTS][k] = v;
                    pb[t] = t % 2 == 0 ? std::min(pb[t], v) : std::max(pb[t], v);
                }
            }
            std::memcpy(&parents[BOX_SLOTS * size_t(g)], pb, sizeof pb);
        }
        levels.push_back(std::move(groups));
        boxes = std::move(parents);
        children = count;
    } while (children > 1);
}

// ---- nearest node ---------------------------------------------------------------------

// Squared chord from the query to the box of each child, 0 inside (vectorised: one SIMD
// operation per coordinate and lane group)
void SnapIndex::bounds(const Group& g, const Query& q, float* lb) const {
    for (int k = 0; k < FANOUT; ++k) {
        float dx = vmax(0.0f, vmax(g.box[0][k] - q.x, q.x - g.box[1][k]));
        float dy = vmax(0.0f, vmax(g.box[2][k] - q.y, q.y - g.box[3][k]));
        float dz = vmax(0.0f, vmax(g.box[4][k] - q.z, q.z - g.box[5][k]));
        lb[k] = dx * dx + dy * dy + dz * dz;
    }
}

// Squared chord from the query to each node of a leaf, in float (one vectorised loop)
void SnapIndex::distances(int leaf, const Query& q, float* d) const {
    const Leaf& l = leaves[leaf];
    for (int i = 0; i < LEAF; ++i) {
        float dx = q.x - l.x[i], dy = q.y - l.y[i], dz = q.z - l.z[i];
        d[i] = dx * dx + dy * dy + dz * dz;
    }
}

int SnapIndex::closest_idx(double latitude, double longitude) const {
    Query q(latitude, longitude);
    thread_local std::vector<std::pair<float, int>> candidates;
    candidates.clear();
    Best best;
    best.candidates = &candidates;
    visit(int(levels.size()) - 1, 0, q, best);
    return recheck(q, best);
}

void SnapIndex::visit(int level, int group, const Query& q, Best& best) const {
    const Group& g = levels[level][group];
    alignas(32) float lb[FANOUT];
    bounds(g, q, lb);
    int order[FANOUT], kept = 0;
    for (int k = 0; k < FANOUT; ++k)
        if (g.box[0][k] <= g.box[1][k] && lb[k] <= best.prune) order[kept++] = k;
    std::sort(order, order + kept, [&lb](int a, int b) { return lb[a] < lb[b]; });
    for (int a = 0; a < kept; ++a) {
        int k = order[a];
        if (lb[k] > best.prune) break;
        if (level == 0) scan(group * FANOUT + k, q, best);
        else visit(level - 1, group * FANOUT + k, q, best);
    }
}

void SnapIndex::scan(int leaf, const Query& q, Best& best) const {
    alignas(32) float d[LEAF];
    distances(leaf, q, d);
    float lowest = d[0];
#if defined(__GNUC__)
    // Minimum over 8 lanes (GCC and Clang vector extensions: two SSE registers or one AVX one)
    typedef float v8f __attribute__((vector_size(32)));
    v8f m;
    std::memcpy(&m, d, sizeof m);
    for (int i = 8; i < LEAF; i += 8) {
        v8f v;
        std::memcpy(&v, d + i, sizeof v);
        m = v < m ? v : m;
    }
    for (int k = 0; k < 8; ++k) lowest = m[k] < lowest ? m[k] : lowest;
#else
    for (int i = 1; i < LEAF; ++i) lowest = d[i] < lowest ? d[i] : lowest;
#endif
    if (lowest > best.thr) return;
    if (lowest < best.best) best.update(lowest);
    for (int i = 0; i < LEAF; ++i)
        if (d[i] <= best.thr) best.candidates->emplace_back(d[i], leaf * LEAF + i);
}

int SnapIndex::recheck(const Query& q, const Best& best) const {
    int found = -1;
    double found_d = INF;
    for (const auto& [d, p] : *best.candidates) {
        if (d > best.thr) continue;
        double exact = chord2(q.u, unit(lat[p], lon[p]));
        if (exact < found_d || (exact == found_d && p < found)) {
            found_d = exact;
            found = p;
        }
    }
    return found;
}

// ---- nearest node per quadrant --------------------------------------------------------

void SnapIndex::closest_idx_per_quadrant(double latitude, double longitude, int out[4]) const {
    Query q(latitude, longitude);
    thread_local std::vector<std::pair<float, int>> candidates[4];
    Best best[4];
    for (int t = 0; t < 4; ++t) {
        candidates[t].clear();
        best[t].candidates = &candidates[t];
    }
    visit_quadrants(int(levels.size()) - 1, 0, 15, q, best);
    for (int t = 0; t < 4; ++t) out[t] = recheck(q, best[t]);
}

void SnapIndex::visit_quadrants(int level, int group, int mask, const Query& q, Best* best) const {
    const Group& g = levels[level][group];
    alignas(32) float lb[FANOUT];
    bounds(g, q, lb);
    float prune[4];
    for (int t = 0; t < 4; ++t) prune[t] = best[t].prune;
    int order[FANOUT], masks[FANOUT], kept = 0;
    for (int k = 0; k < FANOUT; ++k) {
        if (g.box[0][k] > g.box[1][k]) continue;  // no child
        int mk = box_quadrants(g.ll[0][k], g.ll[1][k], g.ll[2][k], g.ll[3][k], q.lat, q.lon) & mask;
        if (!mk || lb[k] > widest(mk, prune)) continue;
        masks[k] = mk;
        order[kept++] = k;
    }
    std::sort(order, order + kept, [&lb](int a, int b) { return lb[a] < lb[b]; });
    for (int a = 0; a < kept; ++a) {
        int k = order[a];
        for (int t = 0; t < 4; ++t) prune[t] = best[t].prune;
        if (lb[k] > widest(masks[k], prune)) continue;
        if (level == 0) scan_quadrants(group * FANOUT + k, masks[k], q, best);
        else visit_quadrants(level - 1, group * FANOUT + k, masks[k], q, best);
    }
}

void SnapIndex::scan_quadrants(int leaf, int mask, const Query& q, Best* best) const {
    alignas(32) float d[LEAF];
    distances(leaf, q, d);
    float thr[4];
    for (int t = 0; t < 4; ++t) thr[t] = best[t].thr;
    float reach = widest(mask, thr);
    // Stop before the padding slots of the last leaf: they hold no node.
    // scan may read them, as a PAD distance is never within thr
    int end = std::min(LEAF, n - leaf * LEAF);
    for (int i = 0; i < end; ++i) {
        if (d[i] > reach) continue;
        int p = leaf * LEAF + i;
        int quadrants = node_quadrants(lat[p], lon[p], q.lat, q.lon) & mask;
        for (int t = 0; t < 4; ++t) {
            if (!(quadrants & (1 << t)) || d[i] > best[t].thr) continue;
            if (d[i] < best[t].best) best[t].update(d[i]);
            best[t].candidates->emplace_back(d[i], p);
        }
    }
}
