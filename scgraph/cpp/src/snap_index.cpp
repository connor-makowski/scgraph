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

constexpr double RADIANS_PER_DEGREE = 3.14159265358979323846 / 180.0;
constexpr double INF = std::numeric_limits<double>::infinity();
// Coordinate of the unused slots of the last leaf, and bound of the unused slots of a
// group. The distance from any point to such a slot computes to infinity, so that no
// search keeps it
constexpr float UNUSED = std::numeric_limits<float>::infinity();
// Start value of the best squared chord of a search: above every squared chord (at most 4,
// between opposite points of the globe) and below the infinite distance of an unused slot
constexpr float FAR = std::numeric_limits<float>::max();
// The largest difference between a chord computed in float and the same chord computed in
// double. The rounding of the node and of the query point (2^-24 per component) and the
// float arithmetic give at most about 3e-7, for the longest chord
constexpr double CHORD_MARGIN = 1e-6;
// The largest error of the two float quadrant tests: a node within this margin of the
// limit between two quadrants is accepted for both, then judged in double. The float error
// of p.z - q.z and of q.x * p.y - q.y * p.x stays below 4e-7
constexpr float SIDE_MARGIN = 1e-6f;
// Level of a leaf in a Visit. Level 0 holds the parents of the leaves, so a leaf is one
// level below level 0
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

struct UnitVector {
    double x, y, z;
};

// Unit vector of a point. Longitudes -180 and 180 stay distinct (1 ulp apart): networks hold
// separate nodes on each side of the antimeridian, and the one on the query's side is nearer
inline UnitVector to_unit_vector(double latitude, double longitude) {
    double a = latitude * RADIANS_PER_DEGREE, b = longitude * RADIANS_PER_DEGREE, c = std::cos(a);
    return {c * std::cos(b), c * std::sin(b), std::sin(a)};
}

inline double squared_chord(const UnitVector& a, const UnitVector& b) {
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

}  // namespace

// The point of a search, in the forms that the search needs
struct SnapIndex::Query {
    double latitude, longitude;  // for the rule that decides the quadrants of a node
    UnitVector unit_vector;      // for the comparison of candidates in double
    float x, y, z;               // the unit vector in float
    Float4 x4, y4, z4;           // the same in 4 lanes, for the loops over 4 floats
    // For the float quadrant tests of the header, with their margin. A node, or the right
    // corner of a box, is accepted as north if z >= north_limit, as south if z <=
    // south_limit, as east if q.x * y - q.y * x >= east_limit, as west if this value <=
    // west_limit
    Float4 north_limit, south_limit, east_limit, west_limit;

    Query(double latitude, double longitude)
        : latitude(latitude), longitude(longitude),
          unit_vector(to_unit_vector(latitude, longitude)),
          x(float(unit_vector.x)), y(float(unit_vector.y)), z(float(unit_vector.z)),
          x4(fill4(x)), y4(fill4(y)), z4(fill4(z)),
          north_limit(fill4(z - SIDE_MARGIN)), south_limit(fill4(z + SIDE_MARGIN)),
          east_limit(fill4(-SIDE_MARGIN)), west_limit(fill4(SIDE_MARGIN)) {}

    // Squared chord from the point to the boxes of children k to k + 3 of a group: 0 for a
    // box that contains the point. On each axis, the gap between the point and the box is
    // the larger of (minimum - point) and (point - maximum), or 0 if both are
    // negative, which means that the point is between the bounds
    Float4 squared_chord_to_boxes(const Group& group, int k) const {
        const Float4 zero = fill4(0.0f);
        const Float4 gap_x = max4(zero, max4(load4(group.bounds[MIN_X] + k) - x4,
                                             x4 - load4(group.bounds[MAX_X] + k)));
        const Float4 gap_y = max4(zero, max4(load4(group.bounds[MIN_Y] + k) - y4,
                                             y4 - load4(group.bounds[MAX_Y] + k)));
        const Float4 gap_z = max4(zero, max4(load4(group.bounds[MIN_Z] + k) - z4,
                                             z4 - load4(group.bounds[MAX_Z] + k)));
        return gap_x * gap_x + gap_y * gap_y + gap_z * gap_z;
    }
};

// What a search has found so far for one answer: the nearest node, or the nearest node of
// one quadrant. All distances are float squared chords.
//
// A float squared chord differs a little from the exact one. So the search keeps every node
// that may be the nearest, the "candidates", and confirm_nearest compares them in double at
// the end. `reach` is the limit for a candidate and for a box: 3 CHORD_MARGIN above the
// lowest float chord found, one margin for each of these facts.
// - The float chord of the best node found is at most 1 margin below its exact chord.
// - The float chord of the exact nearest node is at most 1 margin above its exact chord.
// - The lower bound of the box that holds this node is not above its float chord: boxes
//   are rounded outward, and both values are computed by the same float operations. The
//   third margin is for a compiler that would not round both in the same way.
// A larger factor makes a search visit more boxes and candidates, with the same answers
struct SnapIndex::Nearest {
    struct Candidate {
        float squared_chord;
        int node;
    };
    // Candidates kept without allocating memory. A search rarely has more than one
    static constexpr int INLINE_CANDIDATES = 8;

    float best = FAR;   // the lowest squared chord found
    float reach = FAR;  // a node is a candidate, and a box is opened, up to this value
    int candidate_count = 0;
    Candidate candidates[INLINE_CANDIDATES];
    // Used when many nodes are at the same place, or at the same distance from the point
    std::vector<Candidate> more_candidates;

    // A node nearer than all the nodes seen before was found
    void improve(float squared_chord) {
        best = squared_chord;
        const double limit = std::sqrt(double(squared_chord)) + 3 * CHORD_MARGIN;
        reach = float(limit * limit);
    }

    // The slots of a leaf whose squared chord is within `reach`, as bits: bit i for slot i
    uint32_t slots_within_reach(const float* squared_chords) const {
        const Float4 reach4 = fill4(reach);
        uint32_t slots = 0;
        for (int i = 0; i < LEAF; i += 4)
            slots |= uint32_t(lane_bits(load4(squared_chords + i) <= reach4)) << i;
        return slots;
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

// A visit that a search has still to make: the box of a group or of a leaf, to open
struct SnapIndex::Visit {
    float lower_bound;  // squared chord from the query point to the box
    int level;          // level of the group, or LEAF_LEVEL
    int position;       // position of the group in its level, or of the leaf
    int quadrants;      // per-quadrant search: the quadrants that the box may hold, as bits

    // Puts a visit on the stack, at its place among the visits stacked from `first` on: the
    // lower the lower bound, the nearer to the top, which is the visit made next
    static void push_in_order(Visit* stack, int first, int& stack_size, const Visit& visit) {
        int at = stack_size++;
        for (; at > first && stack[at - 1].lower_bound < visit.lower_bound; --at)
            stack[at] = stack[at - 1];
        stack[at] = visit;
    }
};

SnapIndex::SnapIndex(Coordinates latitudes, Coordinates longitudes, int node_count,
                     std::shared_ptr<const void> owner)
    : latitudes_(latitudes), longitudes_(longitudes), owner_(std::move(owner)) {
    static_assert(LEAF % 4 == 0 && LEAF <= 32 && FANOUT % 4 == 0,
                  "a leaf is read 4 slots at a time, and a set of its slots is 32 bits");
    if (node_count < 1) throw std::invalid_argument("a snapping index needs at least one node");

    // Area of a box of unit vectors: the product of its two largest extents. Same expression
    // as in helpers/snap_index.py
    auto box_area = [](const double* box) {
        double extent[3] = {box[MAX_X] - box[MIN_X], box[MAX_Y] - box[MIN_Y],
                            box[MAX_Z] - box[MIN_Z]};
        std::sort(extent, extent + 3);
        return extent[2] * extent[1];
    };

    // The leaves, and the box of each leaf. Box of child c: boxes[BOUNDS * c + bound]
    const int leaf_count = (node_count + LEAF - 1) / LEAF;
    leaves_.resize(leaf_count);
    std::vector<float> boxes(BOUNDS * size_t(leaf_count));
    // In double, for the measure of the node order: the sum of the areas of the leaf
    // boxes, and the box around all nodes
    double leaf_areas = 0.0;
    double box_of_all[BOUNDS] = {INF, -INF, INF, -INF, INF, -INF};
    for (int leaf = 0; leaf < leaf_count; ++leaf) {
        double box[BOUNDS] = {INF, -INF, INF, -INF, INF, -INF};
        for (int slot = 0; slot < LEAF; ++slot) {
            const int node = leaf * LEAF + slot;
            if (node >= node_count) {
                leaves_[leaf].x[slot] = leaves_[leaf].y[slot] = leaves_[leaf].z[slot] = UNUSED;
                continue;
            }
            const double latitude = latitudes_[node], longitude = longitudes_[node];
            if (!std::isfinite(latitude) || !std::isfinite(longitude))
                throw std::invalid_argument("node coordinates must be finite numbers");
            const UnitVector u = to_unit_vector(latitude, longitude);
            leaves_[leaf].x[slot] = float(u.x);
            leaves_[leaf].y[slot] = float(u.y);
            leaves_[leaf].z[slot] = float(u.z);
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
    // give 1 to 4 per network. Modes sorted one after the other add up their values: 7 for
    // three world-spanning modes. Scattered nodes give up to the number of leaves, and every
    // query then scans that many
    const double total_area = box_area(box_of_all);
    const double leaves_per_query = total_area > 0.0 ? leaf_areas / total_area : 0.0;
    if (leaves_per_query > MAX_LEAVES_PER_QUERY)
        throw node_order_error(
            "nodes scattered in the order given: a query would scan about " +
            std::to_string(int64_t(leaves_per_query + 0.5)) + " blocks of " +
            std::to_string(LEAF) + " nodes (at most " +
            std::to_string(int(MAX_LEAVES_PER_QUERY)) + "). " + SORT_HINT);

    // The levels of groups, from the parents of the leaves up to the root
    int child_count = leaf_count;
    do {
        const int group_count = (child_count + FANOUT - 1) / FANOUT;
        level_start_.push_back(int(groups_.size()));
        groups_.resize(groups_.size() + group_count);
        std::vector<float> group_boxes(BOUNDS * size_t(group_count));
        for (int g = 0; g < group_count; ++g) {
            Group& group = groups_[size_t(level_start_.back()) + g];
            float box[BOUNDS] = {UNUSED, -UNUSED, UNUSED, -UNUSED, UNUSED, -UNUSED};
            for (int k = 0; k < FANOUT; ++k) {
                const int child = g * FANOUT + k;
                for (int bound = 0; bound < BOUNDS; ++bound) {
                    // A slot without child gets a box with its minimums at +infinity
                    // and its maximums at -infinity: see UNUSED
                    const bool is_minimum = bound % 2 == 0;
                    const float value = child < child_count
                                            ? boxes[BOUNDS * size_t(child) + bound]
                                            : (is_minimum ? UNUSED : -UNUSED);
                    group.bounds[bound][k] = value;
                    box[bound] = is_minimum ? std::min(box[bound], value)
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
    Nearest nearest;
    // The visits still to make, the next one on top. The first descent leaves at most
    // FANOUT - 1 visits per level. Step 4 may then open the visit of the highest level
    // first. Each level below it then adds at most FANOUT - 1 visits again
    Visit stack[2 * MAX_LEVELS * FANOUT];
    int stack_size = 0;
    float lower_bound[FANOUT];

    // 1. First descent: from the root down to one leaf, by the nearest child at each
    // level. The other children go on the stack
    int position = 0;
    for (int level = int(level_start_.size()) - 1; level > LEAF_LEVEL; --level) {
        const Group& group = groups_[size_t(level_start_[level]) + position];
        for (int k = 0; k < FANOUT; k += 4)
            store4(lower_bound + k, query.squared_chord_to_boxes(group, k));
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

    // 3. Drop the stacked visits that this distance puts out of reach, and order the
    // others, the nearest on top. Few stay when the point is near the network. `kept` is
    // never above i, so the visits not yet read stay intact. The test is written so that
    // a query that is not a number, which makes every comparison false, keeps no visit
    int kept = 0;
    for (int i = 0; i < stack_size; ++i) {
        const Visit visit = stack[i];
        if (!(visit.lower_bound <= nearest.reach)) continue;
        Visit::push_in_order(stack, 0, kept, visit);
    }
    stack_size = kept;

    // 4. Open the boxes within reach, the nearest first
    while (stack_size > 0) {
        const Visit visit = stack[--stack_size];
        // A node nearer than this box may have been found since the visit was stacked
        if (visit.lower_bound > nearest.reach) continue;
        if (visit.level == LEAF_LEVEL) {
            scan_leaf(visit.position, query, nearest);
            continue;
        }
        const Group& group = groups_[size_t(level_start_[visit.level]) + visit.position];
        // The children whose box is within reach, as bits: bit k for child k
        int children = 0;
        const Float4 reach = fill4(nearest.reach);
        for (int k = 0; k < FANOUT; k += 4) {
            const Float4 lower_bounds = query.squared_chord_to_boxes(group, k);
            store4(lower_bound + k, lower_bounds);
            children |= lane_bits(lower_bounds <= reach) << k;
        }
        // Stack them in order, the nearest on top. `rest &= rest - 1` clears the lowest
        // bit set, so the loop takes each child once
        const int first = stack_size;
        for (unsigned rest = unsigned(children); rest != 0; rest &= rest - 1) {
            const int k = std::countr_zero(rest);
            Visit::push_in_order(
                stack, first, stack_size,
                {lower_bound[k], visit.level - 1, visit.position * FANOUT + k, 0});
        }
    }
    return confirm_nearest(query, nearest);
}

// Looks at the nodes of a leaf: keeps as candidates those within reach of the best node
void SnapIndex::scan_leaf(int leaf, const Query& query, Nearest& nearest) const {
    const Leaf& vectors = leaves_[leaf];
    float squared_chords[LEAF];
    Float4 lowest4_so_far = fill4(UNUSED);
    for (int i = 0; i < LEAF; i += 4) {
        const Float4 dx = query.x4 - load4(vectors.x + i);
        const Float4 dy = query.y4 - load4(vectors.y + i);
        const Float4 dz = query.z4 - load4(vectors.z + i);
        const Float4 chord = dx * dx + dy * dy + dz * dz;
        store4(squared_chords + i, chord);
        lowest4_so_far = min4(lowest4_so_far, chord);
    }
    const float lowest = lowest4(lowest4_so_far);
    // A query that is not a number makes every comparison false, and stops here
    if (!(lowest <= nearest.reach)) return;
    if (lowest < nearest.best) nearest.improve(lowest);
    // The usual case is one slot within reach, the lowest. An unused slot is never within
    // reach
    for (uint32_t rest = nearest.slots_within_reach(squared_chords); rest != 0;
         rest &= rest - 1) {
        const int slot = std::countr_zero(rest);
        nearest.add(squared_chords[slot], leaf * LEAF + slot);
    }
}

// The answer of a search: the candidate with the lowest squared chord in double, and the
// lowest id among equal ones. Returns -1 if the search found no node
int SnapIndex::confirm_nearest(const Query& query, const Nearest& nearest) const {
    auto exact = [&](int node) {
        return squared_chord(query.unit_vector,
                             to_unit_vector(latitudes_[node], longitudes_[node]));
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
    // The east value q.x * y - q.y * x grows with y if q.x is positive, and falls as x
    // grows if q.y is positive. So its highest value in a box is at one corner: y is the
    // highest if q.x is positive, else the lowest, and x is the lowest if q.y is positive,
    // else the highest. Its lowest value is at the opposite corner
    const Bound y_most_east = query.x >= 0.0f ? MAX_Y : MIN_Y;
    const Bound x_most_east = query.y >= 0.0f ? MIN_X : MAX_X;
    const Bound y_most_west = query.x >= 0.0f ? MIN_Y : MAX_Y;
    const Bound x_most_west = query.y >= 0.0f ? MAX_X : MIN_X;

    Nearest nearest[4];  // one per quadrant
    // The visits still to make, the next one on top. Opening a group takes 1 visit off
    // the stack and puts at most FANOUT visits on it
    Visit stack[MAX_LEVELS * FANOUT];
    int stack_size = 0;
    stack[stack_size++] = {0.0f, int(level_start_.size()) - 1, 0, 15};  // the root
    while (stack_size > 0) {
        const Visit visit = stack[--stack_size];
        // The quadrants that this box may hold and for which it is still within reach
        int wanted_quadrants = 0;
        for (int t = 0; t < 4; ++t)
            wanted_quadrants |= int(visit.lower_bound <= nearest[t].reach) << t;
        wanted_quadrants &= visit.quadrants;
        if (wanted_quadrants == 0) continue;
        if (visit.level == LEAF_LEVEL) {
            scan_leaf_per_quadrant(visit.position, wanted_quadrants, query, nearest);
            continue;
        }
        const Group& group = groups_[size_t(level_start_[visit.level]) + visit.position];
        // For each quadrant, the children that may hold a nearer node of the quadrant, as
        // bits: bit k for child k. A quadrant that is not wanted gets the reach -1, which
        // no lower bound is within, and so no child
        float lower_bound[FANOUT];
        int children_for[4] = {0, 0, 0, 0};
        Float4 reach[4];
        for (int t = 0; t < 4; ++t)
            reach[t] = fill4((wanted_quadrants >> t & 1) ? nearest[t].reach : -1.0f);
        for (int k = 0; k < FANOUT; k += 4) {
            const Float4 lower_bounds = query.squared_chord_to_boxes(group, k);
            store4(lower_bound + k, lower_bounds);
            const Mask4 north = load4(group.bounds[MAX_Z] + k) >= query.north_limit;
            const Mask4 south = load4(group.bounds[MIN_Z] + k) <= query.south_limit;
            const Mask4 east = query.x4 * load4(group.bounds[y_most_east] + k) -
                                   query.y4 * load4(group.bounds[x_most_east] + k) >=
                               query.east_limit;
            const Mask4 west = query.x4 * load4(group.bounds[y_most_west] + k) -
                                   query.y4 * load4(group.bounds[x_most_west] + k) <=
                               query.west_limit;
            children_for[0] |= lane_bits((lower_bounds <= reach[0]) & north & east) << k;
            children_for[1] |= lane_bits((lower_bounds <= reach[1]) & north & west) << k;
            children_for[2] |= lane_bits((lower_bounds <= reach[2]) & south & east) << k;
            children_for[3] |= lane_bits((lower_bounds <= reach[3]) & south & west) << k;
        }
        // Stack the children in order, the nearest on top
        const int first = stack_size;
        const int children =
            children_for[0] | children_for[1] | children_for[2] | children_for[3];
        for (unsigned rest = unsigned(children); rest != 0; rest &= rest - 1) {
            const int k = std::countr_zero(rest);
            const int quadrants = (children_for[0] >> k & 1) | (children_for[1] >> k & 1) << 1 |
                                  (children_for[2] >> k & 1) << 2 |
                                  (children_for[3] >> k & 1) << 3;
            Visit::push_in_order(
                stack, first, stack_size,
                {lower_bound[k], visit.level - 1, visit.position * FANOUT + k, quadrants});
        }
    }
    for (int t = 0; t < 4; ++t) out[t] = confirm_nearest(query, nearest[t]);
}

// Looks at the nodes of a leaf for the quadrants in `wanted_quadrants` (bits): for each
// one, keeps as candidates the nodes of the quadrant within reach of its best node
void SnapIndex::scan_leaf_per_quadrant(int leaf, int wanted_quadrants, const Query& query,
                                       Nearest* nearest) const {
    const Leaf& vectors = leaves_[leaf];
    const Float4 unused = fill4(UNUSED);
    // For each quadrant: the slots whose node may lie in it by the float tests (bit i for
    // slot i), and the lowest squared chord among them
    float squared_chords[LEAF];
    uint32_t slots_in[4] = {0, 0, 0, 0};
    Float4 lowest4_in[4] = {unused, unused, unused, unused};
    for (int i = 0; i < LEAF; i += 4) {
        const Float4 x = load4(vectors.x + i), y = load4(vectors.y + i), z = load4(vectors.z + i);
        const Float4 dx = query.x4 - x, dy = query.y4 - y, dz = query.z4 - z;
        const Float4 chord = dx * dx + dy * dy + dz * dz;
        store4(squared_chords + i, chord);
        const Float4 east_value = query.x4 * y - query.y4 * x;
        const Mask4 north = z >= query.north_limit, south = z <= query.south_limit;
        const Mask4 east = east_value >= query.east_limit;
        const Mask4 west = east_value <= query.west_limit;
        const Mask4 in[4] = {north & east, north & west, south & east, south & west};
        for (int t = 0; t < 4; ++t) {
            slots_in[t] |= uint32_t(lane_bits(in[t])) << i;
            lowest4_in[t] = min4(lowest4_in[t], select4(in[t], chord, unused));
        }
    }
    for (int t = 0; t < 4; ++t) {
        if (!(wanted_quadrants >> t & 1)) continue;
        Nearest& quadrant_nearest = nearest[t];
        const float lowest = lowest4(lowest4_in[t]);
        if (!(lowest <= quadrant_nearest.reach)) continue;
        // Keeps the node of a slot if the rule in double confirms its quadrant
        auto consider = [&](int slot) {
            const int node = leaf * LEAF + slot;
            const int quadrants =
                quadrants_of_node(latitudes_[node], longitudes_[node], query.latitude,
                                  query.longitude);
            if (!(quadrants >> t & 1)) return;
            if (squared_chords[slot] < quadrant_nearest.best)
                quadrant_nearest.improve(squared_chords[slot]);
            quadrant_nearest.add(squared_chords[slot], node);
        };
        // The nearest slot first: it is the first slot of the quadrant that holds `lowest`.
        // Once it is confirmed, the reach shrinks to its distance, and the rule in double
        // is not computed for the other slots of the leaf, unless they tie with it
        uint32_t from_nearest = slots_in[t];
        while (squared_chords[std::countr_zero(from_nearest)] != lowest)
            from_nearest &= from_nearest - 1;
        const int nearest_slot = std::countr_zero(from_nearest);
        consider(nearest_slot);
        const uint32_t other_slots = quadrant_nearest.slots_within_reach(squared_chords) &
                                     slots_in[t] & ~(uint32_t(1) << nearest_slot);
        for (uint32_t rest = other_slots; rest != 0; rest &= rest - 1)
            consider(std::countr_zero(rest));
    }
}
