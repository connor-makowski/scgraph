#pragma once
#include <vector>

// Nearest node of a point on the sphere, for snapping coordinates to a GeoGraph.
//
// The nodes are read along a Hilbert curve: in the network's own order if it is already
// sorted along one (networks built or converted by scgraph), otherwise in a sorted copy.
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
// tie rule, which set the answers. They also share the order check, LEAF and FANOUT, so
// that one description fits both.
class SnapIndex {
public:
    // latitudes[i], longitudes[i]: node i, in degrees
    SnapIndex(std::vector<double> latitudes, std::vector<double> longitudes);

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
    std::vector<int> id;           // position in the index -> node id
    std::vector<double> lat, lon;  // by position
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
