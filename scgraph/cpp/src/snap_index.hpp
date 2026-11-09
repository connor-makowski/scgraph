#pragma once
#include <cstdint>
#include <memory>
#include <stdexcept>
#include <vector>

// Spatial index for fast nearest-neighbor lookups on a sphere (coordinate snapping).
//
// Design and Invariants:
// - Order requirement:
//   * Nodes are indexed in their given order (node ID == array index).
//   * Requires spatially clustered ordering (e.g. Hilbert curve, used in .scgraph files).
//   * Throws `node_order_error` if query leaves scanned exceed MAX_LEAVES_PER_QUERY.
// - Zero-copy memory management:
//   * Coordinates are read in-place without memory duplication.
//   * The underlying buffer is kept alive via `std::shared_ptr<const void> owner`.
// - Coordinate formats supported:
//   * float64 degrees (double)
//   * int32 scaled units (1e-7 degree, decoded on the fly as units / 1e7)
// - Tree structure:
//   * Leaf: 32 consecutive nodes packed as float unit vectors (x, y, z) for SIMD math.
//   * Hierarchical bounds: 8-way branching tree storing unit-vector and lat/lon bounding boxes.
// - Query algorithm:
//   * Branch-and-bound traversal, visiting closest bounding boxes first.
//   * Subtrees and candidate leaves are pruned using float distances.
//   * Exact spherical distances are re-evaluated in double precision on final candidates.
//   * Tie-breaking: lowest node ID wins.
// - Python parity:
//   * Exact algorithmic equivalent of helpers/snap_index.py.
//   * Produces identical snapping and quadrant results down to the last bit.

// Thrown when node ordering is too scattered for efficient spatial indexing.
struct node_order_error : std::invalid_argument {
    using std::invalid_argument::invalid_argument;
};

class SnapIndex {
public:
    // Read-only coordinate accessor supporting float64 and fixed-point int32.
    // Decodes values on the fly without memory allocation.
    struct Coordinates {
        const void* data;
        bool units;
        double operator[](int i) const {
            return units ? static_cast<const int32_t*>(data)[i] / 1e7
                         : static_cast<const double*>(data)[i];
        }
    };

    // Construct index over latitude and longitude coordinate columns.
    // - latitudes, longitudes: input coordinate arrays
    // - n: total number of nodes
    // - owner: keeps borrowed arrays alive (e.g. memory-mapped file)
    SnapIndex(Coordinates latitudes, Coordinates longitudes, int n,
              std::shared_ptr<const void> owner);

    // Return the node ID closest to (latitude, longitude).
    int closest_idx(double latitude, double longitude) const;

    // Return the nearest node ID in each geographic quadrant around the target point:
    // - out = {North-East, North-West, South-East, South-West}
    // - Value is -1 if no node is found in that quadrant
    void closest_idx_per_quadrant(double latitude, double longitude, int out[4]) const;

private:
    static constexpr int LEAF = 32;
    static constexpr int FANOUT = 8;

    // Maximum average leaves allowed per query.
    // Bounded to guarantee fast snapping on spatially sorted networks.
    static constexpr double MAX_LEAVES_PER_QUERY = 16.0;

    // Bounding box dimensions:
    // - 6 slots for unit vector bounds (min/max for x, y, z)
    // - 4 slots for lat/lon bounds (min/max for lat, lon)
    static constexpr int BOX_SLOTS = 10;
    static constexpr int UNIT_SLOTS = 6;

    struct Leaf { float x[LEAF], y[LEAF], z[LEAF]; };

    // Bounding boxes for the FANOUT children of a tree node:
    // - box: unit-vector bounds
    // - ll:  latitude / longitude bounds
    struct Group {
        float box[UNIT_SLOTS][FANOUT];
        float ll[BOX_SLOTS - UNIT_SLOTS][FANOUT];
    };
    struct Query;
    struct Best;

    int n;
    Coordinates lat;  // Latitude array, read in place
    Coordinates lon;  // Longitude array, read in place
    std::shared_ptr<const void> owner;  // Keeps coordinate memory alive
    std::vector<Leaf> leaves;
    std::vector<std::vector<Group>> levels;  // levels[0] holds leaf parents

    void bounds(const Group& g, const Query& q, float* lb) const;
    void distances(int leaf, const Query& q, float* d) const;
    void visit(int level, int group, const Query& q, Best& best) const;
    void scan(int leaf, const Query& q, Best& best) const;
    void visit_quadrants(int level, int group, int mask, const Query& q, Best* best) const;
    void scan_quadrants(int leaf, int mask, const Query& q, Best* best) const;
    int recheck(const Query& q, const Best& best) const;
};
