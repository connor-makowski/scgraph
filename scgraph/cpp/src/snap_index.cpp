#include "snap_index.hpp"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <limits>
#include <numeric>
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
// The network's order is kept if at most one in ORDER_CHECK_RUN of the sampled pairs of
// neighbours goes down the curve; about ORDER_CHECK_PAIRS pairs are sampled (as
// helpers/snap_index.py)
constexpr int ORDER_CHECK_PAIRS = 2048;
constexpr int ORDER_CHECK_RUN = 64;

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

// Quadrant bits of a node seen from the query: 1 ne, 2 nw, 4 se, 8 sw, so that bit 1 << t
// is quadrant out[t] (GeoKDTree's rules)
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

// Copy of hilbert_key in scgraph/helpers/hilbert.py, which orders the nodes of converted and
// built networks: change both together. If they differ, networks ordered by hilbert.py may
// fail the order check and be sorted at every load (same answers, slower, no test fails)
constexpr int CURVE_ORDER = 16;

// Position on the Hilbert curve of order CURVE_ORDER over longitude (x) and latitude (y)
inline uint64_t hilbert_key(double latitude, double longitude) {
    const int64_t side = int64_t(1) << CURVE_ORDER;
    // Clamped in double: converting a double beyond the range of int64_t is undefined
    const double top = double(side - 1);
    int64_t x = int64_t(std::clamp((longitude + 180.0) / 360.0 * double(side), 0.0, top));
    int64_t y = int64_t(std::clamp((latitude + 90.0) / 180.0 * double(side), 0.0, top));
    uint64_t key = 0;
    for (int64_t s = side >> 1; s > 0; s >>= 1) {
        int64_t rx = (x & s) ? 1 : 0, ry = (y & s) ? 1 : 0;
        key += uint64_t(s) * uint64_t(s) * uint64_t((3 * rx) ^ ry);
        if (!ry) {
            if (rx) {
                x = s - 1 - x;
                y = s - 1 - y;
            }
            std::swap(x, y);
        }
    }
    return key;
}

}  // namespace

struct SnapIndex::Query {
    double lat, lon;  // for the quadrant rules
    Unit u;           // for the double check
    float x, y, z;    // for the float distances to boxes and leaves
    Query(double latitude, double longitude)
        : lat(latitude), lon(longitude), u(unit(latitude, longitude)),
          x(float(u.x)), y(float(u.y)), z(float(u.z)) {}
};

// Best float squared chord so far, and the thresholds derived from it. The float chord of
// every node is within EPS of its exact chord, so the exact nearest node has a float chord
// within 2 EPS of the best one: nodes up to thr are candidates, checked again in double. A
// box's float bound never exceeds the float distance of a node inside it (outward boxes;
// bounds() and distances() round alike, without contraction: CMakeLists.txt), so skipping
// boxes beyond thr would be enough; prune adds 2 EPS of margin. Changing these factors
// changes how many boxes and candidates are visited, not the answers, as long as thr keeps
// at least 2 EPS and prune >= thr
struct SnapIndex::Best {
    float best = FINF, thr = FINF, prune = FINF;
    // Not owned: the caller's thread_local vector, whose allocation is reused across queries
    std::vector<std::pair<float, int>>* candidates = nullptr;  // (float distance, position)
    void update(float d) {
        best = d;
        double c = std::sqrt(double(d));
        thr = float((c + 2 * EPS) * (c + 2 * EPS));
        prune = float((c + 4 * EPS) * (c + 4 * EPS));
    }
};

SnapIndex::SnapIndex(std::vector<double> latitudes, std::vector<double> longitudes) {
    if (latitudes.size() != longitudes.size())
        throw std::invalid_argument("latitudes and longitudes must have the same length");
    if (latitudes.empty()) throw std::invalid_argument("a snapping index needs at least one node");
    n = int(latitudes.size());
    for (int i = 0; i < n; ++i)
        if (!std::isfinite(latitudes[i]) || !std::isfinite(longitudes[i]))
            throw std::invalid_argument("node coordinates must be finite numbers");
    // Keep the network's order if it is already sorted along a Hilbert curve, in runs of
    // ORDER_CHECK_RUN nodes or more on average (the modes of a multimodal network are sorted
    // one by one), as judged on every pair of neighbours up to 4,096 nodes, else on 2,048 to
    // 3,072 evenly spaced pairs; otherwise sort a copy along one.
    // An order that is only coherent along lines would give long, loose leaves
    auto key = [&](int i) { return hilbert_key(latitudes[i], longitudes[i]); };
    int64_t pairs = 0, descents = 0;
    const int step = std::max(1, (n - 1) / ORDER_CHECK_PAIRS);
    for (int i = 1; i < n; i += step, ++pairs) descents += key(i) < key(i - 1);
    id.resize(n);
    std::iota(id.begin(), id.end(), 0);
    if (descents * ORDER_CHECK_RUN > pairs) {
        std::vector<uint64_t> keys(n);
        for (int i = 0; i < n; ++i) keys[i] = key(i);
        std::sort(id.begin(), id.end(), [&keys](int a, int b) {
            return keys[a] != keys[b] ? keys[a] < keys[b] : a < b;
        });
    }
    lat.resize(n);
    lon.resize(n);
    for (int p = 0; p < n; ++p) {
        lat[p] = latitudes[id[p]];
        lon[p] = longitudes[id[p]];
    }

    // Leaves, and the box of each leaf (BOX_SLOTS floats, rounded outward)
    int nleaves = (n + LEAF - 1) / LEAF;
    leaves.resize(nleaves);
    std::vector<float> boxes(BOX_SLOTS * size_t(nleaves));
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
    }
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
                    // A slot without a child has an inverted box (min > max): never
                    // visited (visit and visit_quadrants test the first unit slot)
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
        if (exact < found_d || (exact == found_d && id[p] < id[found])) {
            found_d = exact;
            found = p;
        }
    }
    return found < 0 ? -1 : id[found];
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
    // Stops before the padding of the last leaf: lat and lon have no entry for it (scan
    // reads it, as PAD is never a candidate)
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
