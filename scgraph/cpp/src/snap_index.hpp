#pragma once
#include <memory>
#include <stdexcept>
#include <vector>

// Nearest node of a point on the sphere, for snapping coordinates to a GeoGraph.
//
// The index reads the nodes in the order given, position = node id, in place: it keeps the
// caller's arrays alive through `owner` and never copies them. That order must keep nearby
// nodes together, as a Hilbert curve does (network files are stored in Hilbert order): the
// constructor measures how many leaves a query would scan and throws node_order_error above
// MAX_LEAVES_PER_QUERY, with the way to sort in the message. The index does not sort, as
// the caller is the one that knows whether its node ids may change.
// A leaf holds 32 consecutive nodes as float unit vectors, so that one vectorised loop
// computes the distances to a whole leaf. An implicit tree with 8 children per node keeps,
// for each child, the box of its unit vectors and the box of its latitudes and longitudes.
// A search goes down the tree, nearest box first, and skips every box farther than the
// best node found so far. Float distances only select candidates: each candidate is
// checked again in double. So the answer is the exact nearest node by great-circle
// distance, and ties go to the lowest id.
//
// helpers/snap_index.py is the pure-Python version. It gives the same answers. The double
// check here uses the same expression as the Python distance, with the platform's cos and
// sin, and is compiled without fused multiply-add (CMakeLists.txt). So both return the
// same node when two nodes tie to the last bit. Both must keep the same quadrant rules and
// tie rule, which set the answers. They also share LEAF, FANOUT and the leaves-per-query
// measure and limit, so that they accept and refuse the same orders (the limit is a cost
// bound, not a contract: orders close to it may be judged differently).

// Thrown when the nodes are too scattered for the index to be useful (see above)
struct node_order_error : std::invalid_argument {
    using std::invalid_argument::invalid_argument;
};

class SnapIndex {
public:
    // latitudes[i], longitudes[i]: node i, in degrees, for i < n. The index reads these
    // arrays for as long as it lives and keeps `owner`, which keeps them alive.
    // Throws node_order_error if the nodes are scattered (see above)
    SnapIndex(const double* latitudes, const double* longitudes, int n,
              std::shared_ptr<const void> owner);

    // Id of the node nearest to the point
    int closest_idx(double latitude, double longitude) const;

    // Nearest node in each quadrant around the point: out = {ne, nw, se, sw}, -1 if none.
    // In the .cpp, quadrant out[t] is bit 1 << t of a mask. A node is north if its
    // latitude is >= the point's, south if <=, east if it lies within 180 degrees of
    // longitude eastwards, west likewise (the rules of GeoKDTree)
    void closest_idx_per_quadrant(double latitude, double longitude, int out[4]) const;

private:
    static constexpr int LEAF = 32;
    static constexpr int FANOUT = 8;
    // Most leaves a query may scan on average: the sum of the leaves' box areas over the
    // area of the box around all nodes. Twice the most measured on nodes sorted per mode, as
    // build_geograph sorts them (7.0: three world-spanning modes, one after the other)
    static constexpr double MAX_LEAVES_PER_QUERY = 16.0;
    // A box is BOX_SLOTS values: min x, max x, min y, max y, min z, max z of the unit
    // vectors (the first UNIT_SLOTS), then min lat, max lat, min lon, max lon. Even slots
    // hold minima, odd slots maxima
    static constexpr int BOX_SLOTS = 10;
    static constexpr int UNIT_SLOTS = 6;
    struct Leaf { float x[LEAF], y[LEAF], z[LEAF]; };
    // Boxes of the FANOUT children of a tree node, one row per slot: box holds the
    // unit-vector slots, ll the latitude/longitude slots
    struct Group {
        float box[UNIT_SLOTS][FANOUT];
        float ll[BOX_SLOTS - UNIT_SLOTS][FANOUT];
    };
    struct Query;
    struct Best;

    int n;
    const double* lat;  // by node id, read in place
    const double* lon;
    std::shared_ptr<const void> owner;  // keeps lat and lon alive
    std::vector<Leaf> leaves;
    std::vector<std::vector<Group>> levels;  // levels[0] holds the parents of the leaves

    void bounds(const Group& g, const Query& q, float* lb) const;
    void distances(int leaf, const Query& q, float* d) const;
    void visit(int level, int group, const Query& q, Best& best) const;
    void scan(int leaf, const Query& q, Best& best) const;
    void visit_quadrants(int level, int group, int mask, const Query& q, Best* best) const;
    void scan_quadrants(int leaf, int mask, const Query& q, Best* best) const;
    int recheck(const Query& q, const Best& best) const;
};
