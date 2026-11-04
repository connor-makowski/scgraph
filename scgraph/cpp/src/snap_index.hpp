#pragma once
#include <vector>

// Nearest node of a point on the sphere, for snapping coordinates to a GeoGraph.
//
// The nodes are read along a Hilbert curve: in the network's own order if it is already
// sorted along one (networks built by build_geograph), otherwise in a sorted copy. Leaves are 32 consecutive nodes, stored as float unit
// vectors so that a leaf is one vectorised loop; an implicit tree with 8 children per node
// keeps, for each child, the box of its unit vectors and of its latitudes and longitudes.
// A search goes down by increasing distance to the boxes and skips every box farther than
// the best node found. Float distances only select candidates: each candidate is checked
// again in double, so the answer is the exact nearest node (great-circle distance), ties
// going to the lowest id.
class SnapIndex {
public:
    // latitudes[i], longitudes[i]: node i, in degrees
    SnapIndex(std::vector<double> latitudes, std::vector<double> longitudes);

    // Id of the node nearest to the point
    int closest_idx(double latitude, double longitude) const;

    // Nearest node in each quadrant around the point: out = {ne, nw, se, sw}, -1 if none.
    // A node is north if its latitude is >= the point's, south if <=, east if it lies within
    // 180 degrees of longitude eastwards, west likewise (as GeoKDTree)
    void closest_idx_per_quadrant(double latitude, double longitude, int out[4]) const;

private:
    static constexpr int LEAF = 32;
    static constexpr int FANOUT = 8;
    struct Leaf { float x[LEAF], y[LEAF], z[LEAF]; };
    // Boxes of the FANOUT children of a tree node: unit vectors (min x, max x, min y, max y,
    // min z, max z) and latitude/longitude (min lat, max lat, min lon, max lon)
    struct Group { float box[6][FANOUT]; float ll[4][FANOUT]; };
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
