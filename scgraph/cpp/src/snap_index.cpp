#include "snap_index.hpp"

#include <algorithm>
#include <bit>
#include <cmath>
#include <cstdint>
#include <limits>
#include <memory>
#include <stdexcept>
#include <string>
#include <utility>

#include "float4.hpp"

// The header explains the index: what it stores, how a search runs, how a quadrant is
// decided and why the answers are exact. Read it first.

namespace {

constexpr double DEG = 3.14159265358979323846 / 180.0;
constexpr double INF = std::numeric_limits<double>::infinity();
// Coordinate of the unused slots of the last leaf, and bound of the unused slots of a
// group. The distance from any point to such a slot computes to infinity, so that no
// search keeps it
constexpr float UNUSED = std::numeric_limits<float>::infinity();
// Start value of the best squared chord of a search: above every squared chord (at most 4,
// between opposite points of the globe) and below the infinite distance of an unused slot
constexpr float FAR = std::numeric_limits<float>::max();
// Most that the chord computed in float can differ from the chord computed in double.
// Coordinate and query rounding (2^-24 per component) and float arithmetic stay far below
constexpr double CHORD_MARGIN = 1e-6;
// Most that the two float quadrant tests can be wrong by: a node within this margin of the
// limit between two quadrants is accepted for both, then judged in double. The float error
// of p.z - q.z and of q.x * p.y - q.y * p.x stays below 4e-7
constexpr float SIDE_MARGIN = 1e-6f;
// Level of a leaf in a Visit: the level below level 0, the parents of the leaves
constexpr int LEAF_LEVEL = -1;
// More levels than any index has: 10 levels of 8 children over leaves of 32 nodes hold
// more nodes than an int can number
constexpr int MAX_LEVELS = 10;
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

inline double squared_chord(const Unit& a, const Unit& b) {
    double dx = a.x - b.x, dy = a.y - b.y, dz = a.z - b.z;
    return dx * dx + dy * dy + dz * dz;
}

// The nearest float below or equal to a value, and above or equal to it. Boxes are rounded
// with them, outward, so that a box always contains its nodes
inline float round_down(double value) {
    float f = float(value);
    return double(f) > value ? std::nextafter(f, -UNUSED) : f;
}
inline float round_up(double value) {
    float f = float(value);
    return double(f) < value ? std::nextafter(f, UNUSED) : f;
}

inline double wrap180(double degrees) {
    if (degrees > 180.0) return degrees - 360.0;
    if (degrees < -180.0) return degrees + 360.0;
    return degrees;
}

// The quadrants of a node seen from the query point, as bits: 1 north-east, 2 north-west,
// 4 south-east, 8 south-west. Bit 1 << t is quadrant out[t] of closest_idx_per_quadrant.
// This is the rule that sets the answers (the rule of GeoKDTree), computed in double
inline int quadrants_of_node(double latitude, double longitude, double query_latitude,
                             double query_longitude) {
    double eastwards = wrap180(longitude - query_longitude);
    bool north = latitude >= query_latitude, south = latitude <= query_latitude;
    bool east = eastwards >= 0.0 || eastwards == -180.0;
    bool west = eastwards <= 0.0 || eastwards == 180.0;
    return (north && east ? 1 : 0) | (north && west ? 2 : 0) | (south && east ? 4 : 0) |
           (south && west ? 8 : 0);
}

// Area of a box of unit vectors (bounds in the order of SnapIndex::Bound): the product of
// its two largest extents. Same expression as in helpers/snap_index.py
inline double box_area(const double* box) {
    double extent[3] = {box[1] - box[0], box[3] - box[2], box[5] - box[4]};
    std::sort(extent, extent + 3);
    return extent[2] * extent[1];
}

// Squared chord from the query point (qx, qy, qz) to the boxes of children k to k + 3 of a
// group: 0 for a box that contains the point. On each axis, the gap between the point and
// the box is the larger of (lower bound - point) and (point - upper bound), or 0 if both
// are negative, which means that the point is between the bounds.
// `bounds` is Group::bounds; the row names are the values of SnapIndex::Bound
template <class Bounds>
inline Float4 squared_chord_to_boxes(const Bounds& bounds, int k, Float4 qx, Float4 qy,
                                     Float4 qz) {
    const Float4 zero = fill4(0.0f);
    Float4 gap_x = max4(zero, max4(load4(bounds[0] + k) - qx, qx - load4(bounds[1] + k)));
    Float4 gap_y = max4(zero, max4(load4(bounds[2] + k) - qy, qy - load4(bounds[3] + k)));
    Float4 gap_z = max4(zero, max4(load4(bounds[4] + k) - qz, qz - load4(bounds[5] + k)));
    return gap_x * gap_x + gap_y * gap_y + gap_z * gap_z;
}

// The slots of a leaf whose squared chord is at most `reach`, as bits: bit i for slot i
inline uint32_t slots_within(const float* squared_chords, int slot_count, float reach) {
    const Float4 reach4 = fill4(reach);
    uint32_t slots = 0;
    for (int i = 0; i < slot_count; i += 4)
        slots |= uint32_t(lane_bits(load4(squared_chords + i) <= reach4)) << i;
    return slots;
}

}  // namespace

// The point of a search, in the three forms that the search needs
struct SnapIndex::Query {
    double latitude, longitude;  // for the rule that decides the quadrants of a node
    Unit unit;                   // for the comparison of candidates in double
    float x, y, z;               // the unit vector in float, for the loops over 4 floats
    Query(double latitude, double longitude)
        : latitude(latitude), longitude(longitude), unit(::unit(latitude, longitude)),
          x(float(unit.x)), y(float(unit.y)), z(float(unit.z)) {}
};

// What a search has found so far for one answer: the nearest node, or the nearest node of
// one quadrant. All distances are float squared chords.
//
// A float squared chord differs a little from the exact one. So the search keeps every node
// that may be the nearest, the "candidates", and confirm_nearest compares them in double at
// the end. The float chord of a node is within CHORD_MARGIN of its exact chord. So the exact
// nearest node has a float chord within 2 CHORD_MARGIN of the lowest float chord, and
// `reach` holds this limit.
//
// `box_reach` is the same limit for boxes, with twice the margin. The lower bound of a box
// is never above the float chord of a node inside it: boxes are rounded outward, and both
// are computed by the same float operations (the file is compiled without fused
// multiply-add, see CMakeLists.txt). So `reach` would be enough; the larger margin costs
// almost nothing. Changing the factors 2 and 4 changes how many boxes and candidates a
// search visits, not its answers, as long as `reach` keeps 2 margins and `box_reach` is not
// below `reach`
struct SnapIndex::Nearest {
    struct Candidate {
        float squared_chord;
        int node;
    };
    // Candidates kept without allocating memory. A search rarely has more than one
    static constexpr int INLINE_CANDIDATES = 8;

    float best = FAR;       // the lowest squared chord found
    float reach = FAR;      // a node is a candidate if its squared chord is at most this
    float box_reach = FAR;  // a box is opened if its lower bound is at most this
    int candidate_count = 0;
    Candidate candidates[INLINE_CANDIDATES];
    std::vector<Candidate> more_candidates;  // used when many nodes are at the same place

    // A node nearer than all the nodes seen before was found
    void improve(float squared_chord) {
        best = squared_chord;
        double chord = std::sqrt(double(squared_chord));
        reach = float((chord + 2 * CHORD_MARGIN) * (chord + 2 * CHORD_MARGIN));
        box_reach = float((chord + 4 * CHORD_MARGIN) * (chord + 4 * CHORD_MARGIN));
    }

    // Keeps a node whose squared chord is within `reach`
    void add(float squared_chord, int node) {
        if (candidate_count == INLINE_CANDIDATES) {
            // Full: drop the candidates that a nearer node, found later, put out of reach
            Candidate* kept = std::remove_if(
                candidates, candidates + INLINE_CANDIDATES,
                [this](const Candidate& c) { return c.squared_chord > reach; });
            candidate_count = int(kept - candidates);
        }
        if (candidate_count < INLINE_CANDIDATES)
            candidates[candidate_count++] = {squared_chord, node};
        else
            more_candidates.push_back({squared_chord, node});
    }
};

// A box that a search has still to open: a group, or a leaf
struct SnapIndex::Visit {
    float lower_bound;  // squared chord from the query point to the box
    int level;          // level of the group, or LEAF_LEVEL
    int position;       // position of the group in its level, or of the leaf
    int quadrants;      // per-quadrant search: the quadrants that the box may hold, as bits
};

SnapIndex::SnapIndex(Coordinates latitudes, Coordinates longitudes, int n,
                     std::shared_ptr<const void> owner)
    : n(n), lat(latitudes), lon(longitudes), owner(std::move(owner)) {
    static_assert(LEAF % 4 == 0 && LEAF <= 32 && FANOUT % 4 == 0,
                  "a leaf is read 4 slots at a time, and a set of its slots is 32 bits");
    if (n < 1) throw std::invalid_argument("a snapping index needs at least one node");
    if (!latitudes.units)  // int32 units are always finite
        for (int i = 0; i < n; ++i)
            if (!std::isfinite(latitudes[i]) || !std::isfinite(longitudes[i]))
                throw std::invalid_argument("node coordinates must be finite numbers");

    // The leaves, and the box of each leaf. Box of child c: boxes[BOUNDS * c + bound]
    const int leaf_count = (n + LEAF - 1) / LEAF;
    leaves.resize(leaf_count);
    std::vector<float> boxes(BOUNDS * size_t(leaf_count));
    // In double, for the measure of the node order: the sum of the areas of the leaf
    // boxes, and the box around all nodes
    double leaf_areas = 0.0;
    double box_of_all[BOUNDS] = {INF, -INF, INF, -INF, INF, -INF};
    for (int leaf = 0; leaf < leaf_count; ++leaf) {
        double box[BOUNDS] = {INF, -INF, INF, -INF, INF, -INF};
        for (int slot = 0; slot < LEAF; ++slot) {
            const int node = leaf * LEAF + slot;
            if (node >= n) {
                leaves[leaf].x[slot] = leaves[leaf].y[slot] = leaves[leaf].z[slot] = UNUSED;
                continue;
            }
            const Unit u = unit(lat[node], lon[node]);
            leaves[leaf].x[slot] = float(u.x);
            leaves[leaf].y[slot] = float(u.y);
            leaves[leaf].z[slot] = float(u.z);
            const double coordinate[3] = {u.x, u.y, u.z};
            for (int axis = 0; axis < 3; ++axis) {
                box[2 * axis] = std::min(box[2 * axis], coordinate[axis]);
                box[2 * axis + 1] = std::max(box[2 * axis + 1], coordinate[axis]);
            }
        }
        for (int bound = 0; bound < BOUNDS; ++bound)
            boxes[BOUNDS * size_t(leaf) + bound] =
                bound % 2 == 0 ? round_down(box[bound]) : round_up(box[bound]);
        leaf_areas += box_area(box);
        for (int bound = 0; bound < BOUNDS; bound += 2) {
            box_of_all[bound] = std::min(box_of_all[bound], box[bound]);
            box_of_all[bound + 1] = std::max(box_of_all[bound + 1], box[bound + 1]);
        }
    }

    // Leaves per query: how many leaf boxes cover a point on average. Nodes in Hilbert order
    // give 1 to 4 per network; modes sorted one after the other add up their values (7 for
    // three world-spanning modes); scattered nodes give up to the number of leaves, and
    // every query then scans that many
    const double total_area = box_area(box_of_all);
    const double leaves_per_query = total_area > 0.0 ? leaf_areas / total_area : 0.0;
    if (leaves_per_query > MAX_LEAVES_PER_QUERY)
        throw node_order_error(
            "nodes scattered in the order given: a query would scan about " +
            std::to_string(int64_t(leaves_per_query + 0.5)) + " groups of " +
            std::to_string(LEAF) + " nodes (at most " +
            std::to_string(int(MAX_LEAVES_PER_QUERY)) + "). " + SORT_HINT);

    // The levels of groups, from the parents of the leaves up to the root
    int child_count = leaf_count;
    do {
        const int group_count = (child_count + FANOUT - 1) / FANOUT;
        level_start.push_back(int(groups.size()));
        groups.resize(groups.size() + group_count);
        std::vector<float> group_boxes(BOUNDS * size_t(group_count));
        for (int g = 0; g < group_count; ++g) {
            Group& group = groups[size_t(level_start.back()) + g];
            float box[BOUNDS] = {UNUSED, -UNUSED, UNUSED, -UNUSED, UNUSED, -UNUSED};
            for (int k = 0; k < FANOUT; ++k) {
                const int child = g * FANOUT + k;
                for (int bound = 0; bound < BOUNDS; ++bound) {
                    // A slot without child gets a box with its lower bounds at +infinity
                    // and its upper bounds at -infinity: see UNUSED
                    const bool is_lower = bound % 2 == 0;
                    const float value = child < child_count
                                            ? boxes[BOUNDS * size_t(child) + bound]
                                            : (is_lower ? UNUSED : -UNUSED);
                    group.bounds[bound][k] = value;
                    box[bound] = is_lower ? std::min(box[bound], value)
                                          : std::max(box[bound], value);
                }
            }
            std::copy(box, box + BOUNDS, &group_boxes[BOUNDS * size_t(g)]);
        }
        boxes = std::move(group_boxes);
        child_count = group_count;
    } while (child_count > 1);
}

// ---- nearest node ---------------------------------------------------------------------

int SnapIndex::closest_idx(double latitude, double longitude) const {
    const Query query(latitude, longitude);
    const Float4 qx = fill4(query.x), qy = fill4(query.y), qz = fill4(query.z);
    Nearest nearest;
    // The boxes still to open, the next one on top. Opening a group takes 1 box off the
    // stack and puts at most FANOUT boxes on it
    Visit stack[MAX_LEVELS * FANOUT];
    int stack_size = 0;
    float lower_bound[FANOUT];

    // 1. First descent: from the root down to one leaf, by the nearest child at each
    // level. The other children go on the stack
    int position = 0;
    for (int level = int(level_start.size()) - 1; level > LEAF_LEVEL; --level) {
        const Group& group = groups[size_t(level_start[level]) + position];
        for (int k = 0; k < FANOUT; k += 4)
            store4(lower_bound + k, squared_chord_to_boxes(group.bounds, k, qx, qy, qz));
        int nearest_child = 0;
        for (int k = 1; k < FANOUT; ++k)
            if (lower_bound[k] < lower_bound[nearest_child]) nearest_child = k;
        for (int k = 0; k < FANOUT; ++k)
            if (k != nearest_child && lower_bound[k] <= FAR)  // not an unused slot
                stack[stack_size++] = {lower_bound[k], level - 1, position * FANOUT + k, 0};
        position = position * FANOUT + nearest_child;
    }
    // 2. The leaf gives a first best distance
    scan_leaf(position, query, nearest);

    // 3. Drop the stacked boxes that this distance puts out of reach, and order the
    // others, the nearest on top. Few boxes stay when the point is near the network
    int kept = 0;
    for (int i = 0; i < stack_size; ++i) {
        const Visit box = stack[i];
        if (!(box.lower_bound <= nearest.box_reach)) continue;
        int at = kept++;
        for (; at > 0 && stack[at - 1].lower_bound < box.lower_bound; --at)
            stack[at] = stack[at - 1];
        stack[at] = box;
    }
    stack_size = kept;

    // 4. Open the boxes within reach, the nearest first
    while (stack_size > 0) {
        const Visit visit = stack[--stack_size];
        // A node nearer than this box may have been found since the box was stacked
        if (visit.lower_bound > nearest.box_reach) continue;
        if (visit.level == LEAF_LEVEL) {
            scan_leaf(visit.position, query, nearest);
            continue;
        }
        const Group& group = groups[size_t(level_start[visit.level]) + visit.position];
        // The children whose box is within reach, as bits: bit k for child k
        int children = 0;
        const Float4 box_reach = fill4(nearest.box_reach);
        for (int k = 0; k < FANOUT; k += 4) {
            const Float4 bound = squared_chord_to_boxes(group.bounds, k, qx, qy, qz);
            store4(lower_bound + k, bound);
            children |= lane_bits(bound <= box_reach) << k;
        }
        // Stack them in order, the nearest on top: each one is inserted at its place
        // among the children already stacked. `rest &= rest - 1` clears the lowest bit
        // set, so the loop takes each child once
        const int first = stack_size;
        for (unsigned rest = unsigned(children); rest != 0; rest &= rest - 1) {
            const int k = std::countr_zero(rest);
            int at = stack_size++;
            for (; at > first && stack[at - 1].lower_bound < lower_bound[k]; --at)
                stack[at] = stack[at - 1];
            stack[at] = {lower_bound[k], visit.level - 1, visit.position * FANOUT + k, 0};
        }
    }
    return confirm_nearest(query, nearest);
}

// Looks at the nodes of a leaf: keeps as candidates those within reach of the best node
void SnapIndex::scan_leaf(int leaf, const Query& query, Nearest& nearest) const {
    const Leaf& slots = leaves[leaf];
    const Float4 qx = fill4(query.x), qy = fill4(query.y), qz = fill4(query.z);
    float squared_chords[LEAF];
    Float4 lowest4_so_far = fill4(UNUSED);
    for (int i = 0; i < LEAF; i += 4) {
        const Float4 dx = qx - load4(slots.x + i);
        const Float4 dy = qy - load4(slots.y + i);
        const Float4 dz = qz - load4(slots.z + i);
        const Float4 chord = dx * dx + dy * dy + dz * dz;
        store4(squared_chords + i, chord);
        lowest4_so_far = min4(lowest4_so_far, chord);
    }
    const float lowest = lowest4(lowest4_so_far);
    // Written so that a query that is not a number, which compares false, stops here
    if (!(lowest <= nearest.reach)) return;
    if (lowest < nearest.best) nearest.improve(lowest);
    // The usual case is one slot within reach, the lowest. An unused slot never is
    for (uint32_t rest = slots_within(squared_chords, LEAF, nearest.reach); rest != 0;
         rest &= rest - 1) {
        const int slot = std::countr_zero(rest);
        nearest.add(squared_chords[slot], leaf * LEAF + slot);
    }
}

// The answer of a search: the candidate with the lowest squared chord in double, and the
// lowest id among equal ones. Returns -1 if the search found no node
int SnapIndex::confirm_nearest(const Query& query, const Nearest& nearest) const {
    auto exact = [&](int node) {
        return squared_chord(query.unit, unit(lat[node], lon[node]));
    };
    // With one candidate, the usual case, no distance is computed in double
    int only_candidate = -1, found = -1;
    double found_chord = INF;
    auto consider = [&](const Nearest::Candidate& candidate) {
        // A candidate kept early may be out of reach of the best node found since
        if (candidate.squared_chord > nearest.reach) return;
        if (only_candidate < 0) {
            only_candidate = candidate.node;
            return;
        }
        if (found < 0) {
            found = only_candidate;
            found_chord = exact(only_candidate);
        }
        const double chord = exact(candidate.node);
        if (chord < found_chord || (chord == found_chord && candidate.node < found)) {
            found_chord = chord;
            found = candidate.node;
        }
    };
    for (int i = 0; i < nearest.candidate_count; ++i) consider(nearest.candidates[i]);
    for (const Nearest::Candidate& candidate : nearest.more_candidates) consider(candidate);
    return found >= 0 ? found : only_candidate;
}

// ---- nearest node per quadrant --------------------------------------------------------

void SnapIndex::closest_idx_per_quadrant(double latitude, double longitude, int out[4]) const {
    const Query query(latitude, longitude);
    const Float4 qx = fill4(query.x), qy = fill4(query.y), qz = fill4(query.z);
    // The float tests of the header, with their margin. North: z >= north_limit. South:
    // z <= south_limit. East: q.x * y - q.y * x >= -margin. West: the same value <= margin
    const Float4 north_limit = fill4(query.z - SIDE_MARGIN);
    const Float4 south_limit = fill4(query.z + SIDE_MARGIN);
    const Float4 margin = fill4(SIDE_MARGIN), minus_margin = fill4(-SIDE_MARGIN);
    // The east value q.x * y - q.y * x is highest at the corner of a box where y is the
    // highest if q.x is positive, else the lowest, and where x is the lowest if q.y is
    // positive, else the highest. It is lowest at the opposite corner
    const Bound y_most_east = query.x >= 0.0f ? MAX_Y : MIN_Y;
    const Bound x_most_east = query.y >= 0.0f ? MIN_X : MAX_X;
    const Bound y_most_west = query.x >= 0.0f ? MIN_Y : MAX_Y;
    const Bound x_most_west = query.y >= 0.0f ? MAX_X : MIN_X;

    Nearest nearest[4];  // one per quadrant
    Visit stack[MAX_LEVELS * FANOUT];
    int stack_size = 0;
    stack[stack_size++] = {0.0f, int(level_start.size()) - 1, 0, 15};  // the root
    while (stack_size > 0) {
        const Visit visit = stack[--stack_size];
        // The quadrants that this box may hold and for which it is still within reach
        int wanted = 0;
        for (int t = 0; t < 4; ++t)
            wanted |= int(visit.lower_bound <= nearest[t].box_reach) << t;
        wanted &= visit.quadrants;
        if (wanted == 0) continue;
        if (visit.level == LEAF_LEVEL) {
            scan_leaf_per_quadrant(visit.position, wanted, query, nearest);
            continue;
        }
        const Group& group = groups[size_t(level_start[visit.level]) + visit.position];
        // For each quadrant, the children that may hold a nearer node of the quadrant, as
        // bits: bit k for child k. A quadrant that is not wanted gets no child
        float lower_bound[FANOUT];
        int children_for[4] = {0, 0, 0, 0};
        Float4 box_reach[4];
        for (int t = 0; t < 4; ++t)
            box_reach[t] = fill4((wanted >> t & 1) ? nearest[t].box_reach : -1.0f);
        for (int k = 0; k < FANOUT; k += 4) {
            const Float4 bound = squared_chord_to_boxes(group.bounds, k, qx, qy, qz);
            store4(lower_bound + k, bound);
            const Mask4 north = load4(group.bounds[MAX_Z] + k) >= north_limit;
            const Mask4 south = load4(group.bounds[MIN_Z] + k) <= south_limit;
            const Mask4 east = qx * load4(group.bounds[y_most_east] + k) -
                                   qy * load4(group.bounds[x_most_east] + k) >= minus_margin;
            const Mask4 west = qx * load4(group.bounds[y_most_west] + k) -
                                   qy * load4(group.bounds[x_most_west] + k) <= margin;
            children_for[0] |= lane_bits((bound <= box_reach[0]) & north & east) << k;
            children_for[1] |= lane_bits((bound <= box_reach[1]) & north & west) << k;
            children_for[2] |= lane_bits((bound <= box_reach[2]) & south & east) << k;
            children_for[3] |= lane_bits((bound <= box_reach[3]) & south & west) << k;
        }
        // Stack the children in order, the nearest on top: each one is inserted at its
        // place among the children already stacked. Here the order of all children counts,
        // as each quadrant has its own nearest box
        const int first = stack_size;
        const int children =
            children_for[0] | children_for[1] | children_for[2] | children_for[3];
        for (unsigned rest = unsigned(children); rest != 0; rest &= rest - 1) {
            const int k = std::countr_zero(rest);
            const int quadrants = (children_for[0] >> k & 1) | (children_for[1] >> k & 1) << 1 |
                                  (children_for[2] >> k & 1) << 2 |
                                  (children_for[3] >> k & 1) << 3;
            int at = stack_size++;
            for (; at > first && stack[at - 1].lower_bound < lower_bound[k]; --at)
                stack[at] = stack[at - 1];
            stack[at] = {lower_bound[k], visit.level - 1, visit.position * FANOUT + k,
                         quadrants};
        }
    }
    for (int t = 0; t < 4; ++t) out[t] = confirm_nearest(query, nearest[t]);
}

// Looks at the nodes of a leaf for the quadrants in `wanted_quadrants` (bits): for each
// one, keeps as candidates the nodes of the quadrant within reach of its best node
void SnapIndex::scan_leaf_per_quadrant(int leaf, int wanted_quadrants, const Query& query,
                                       Nearest* nearest) const {
    const Leaf& slots = leaves[leaf];
    const Float4 qx = fill4(query.x), qy = fill4(query.y), qz = fill4(query.z);
    const Float4 north_limit = fill4(query.z - SIDE_MARGIN);
    const Float4 south_limit = fill4(query.z + SIDE_MARGIN);
    const Float4 margin = fill4(SIDE_MARGIN), minus_margin = fill4(-SIDE_MARGIN);
    const Float4 unused = fill4(UNUSED);
    // For each quadrant: the slots whose node may lie in it by the float tests (bit i for
    // slot i), and the lowest squared chord among them
    float squared_chords[LEAF];
    uint32_t slots_in[4] = {0, 0, 0, 0};
    Float4 lowest4_in[4] = {unused, unused, unused, unused};
    for (int i = 0; i < LEAF; i += 4) {
        const Float4 x = load4(slots.x + i), y = load4(slots.y + i), z = load4(slots.z + i);
        const Float4 dx = qx - x, dy = qy - y, dz = qz - z;
        const Float4 chord = dx * dx + dy * dy + dz * dz;
        store4(squared_chords + i, chord);
        const Float4 east_value = qx * y - qy * x;
        const Mask4 north = z >= north_limit, south = z <= south_limit;
        const Mask4 east = east_value >= minus_margin, west = east_value <= margin;
        const Mask4 in[4] = {north & east, north & west, south & east, south & west};
        for (int t = 0; t < 4; ++t) {
            slots_in[t] |= uint32_t(lane_bits(in[t])) << i;
            lowest4_in[t] = min4(lowest4_in[t], select4(in[t], chord, unused));
        }
    }
    for (int t = 0; t < 4; ++t) {
        if (!(wanted_quadrants >> t & 1)) continue;
        Nearest& found = nearest[t];
        const float lowest = lowest4(lowest4_in[t]);
        if (!(lowest <= found.reach)) continue;
        // Keeps the node of a slot if the rule in double confirms its quadrant
        auto consider = [&](int slot) {
            const int node = leaf * LEAF + slot;
            const int quadrants =
                quadrants_of_node(lat[node], lon[node], query.latitude, query.longitude);
            if (!(quadrants >> t & 1)) return;
            if (squared_chords[slot] < found.best) found.improve(squared_chords[slot]);
            found.add(squared_chords[slot], node);
        };
        // The nearest slot first: it is the slot of the quadrant that holds `lowest`. Once
        // it is confirmed, the reach shrinks to its distance, and the rule in double is
        // not computed for the other slots of the leaf, unless they tie with it
        int nearest_slot = std::countr_zero(slots_in[t]);
        for (uint32_t rest = slots_in[t]; squared_chords[nearest_slot] != lowest;
             nearest_slot = std::countr_zero(rest))
            rest &= rest - 1;
        consider(nearest_slot);
        const uint32_t other_slots = slots_within(squared_chords, LEAF, found.reach) &
                                     slots_in[t] & ~(uint32_t(1) << nearest_slot);
        for (uint32_t rest = other_slots; rest != 0; rest &= rest - 1)
            consider(std::countr_zero(rest));
    }
}
