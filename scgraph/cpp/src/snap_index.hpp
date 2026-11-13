#pragma once
#include <cstdint>
#include <memory>
#include <stdexcept>
#include <vector>

// SnapIndex finds the node of a network that is nearest to a point of the globe. GeoGraph
// uses it to snap the origin and the destination of a route to the network.
//
// WHAT IT ANSWERS
//   closest_idx gives the nearest node. closest_idx_per_quadrant gives the nearest node to
//   the north-east of the point, to the north-west, to the south-east and to the south-west.
//   "Nearest" means the shortest great-circle distance. The answers are exact, and ties go
//   to the lowest node id.
//   Example: nodes 0 = (0 N, 0 E), 1 = (0 N, 10 E), 2 = (10 N, 0 E), and the point
//   (1 N, 1 E). closest_idx gives 0. closest_idx_per_quadrant gives no node to the
//   north-east, node 2 to the north-west, node 1 to the south-east and node 0 to the
//   south-west.
//
// WHAT IT READS
//   The index reads the coordinates of the nodes in place, in the order given: position =
//   node id. It keeps the caller's arrays alive through `owner` and never copies them.
//   The coordinates are float64 degrees, or int32 units of 1e-7 degree, as network files
//   may store them. An int32 value is decoded at each read as units / 1e7, as the Python
//   index does. Latitudes are from -90 to 90.
//   Example: the int32 values 488566000 and 23522000 are the node (48.8566 N, 2.3522 E).
//   The order of the nodes must keep nearby nodes together, as a Hilbert curve does
//   (network files are stored in Hilbert order). The constructor measures how many leaves
//   (blocks of LEAF consecutive nodes, see below) a query would scan. Above
//   MAX_LEAVES_PER_QUERY it throws node_order_error, and the message says how to sort.
//   The index does not sort: a sort changes the node ids, and only the caller knows
//   whether they may change.
//
// HOW DISTANCES ARE COMPARED
//   A node at latitude a and longitude b is the point (cos a cos b, cos a sin b, sin a) of a
//   sphere of radius 1, its "unit vector". The straight line between two unit vectors is a
//   "chord". A longer great-circle distance gives a longer chord, so the nearest node is the
//   node with the shortest chord. The index compares squared chords: they need no square
//   root and no trigonometry.
//   Example: (0 N, 0 E) is (1, 0, 0) and (0 N, 90 E) is (0, 1, 0). Their squared chord is
//   (1-0)^2 + (0-1)^2 + (0-0)^2 = 2, for a quarter of the way round the globe.
//
// HOW THE NODES ARE STORED
//   A leaf holds the unit vectors of LEAF consecutive nodes, as floats.
//   A group has up to FANOUT children. The children of a group of level 0 are consecutive
//   leaves. The children of a group of a higher level are consecutive groups of the level
//   below. For each child, the group stores a box: the lowest and the highest x, y and z of
//   the unit vectors of all the nodes below that child. The last level has one group, the
//   root.
//   Example with 100 nodes: leaf 0 holds nodes 0 to 31, leaf 1 nodes 32 to 63, leaf 2 nodes
//   64 to 95, and leaf 3 nodes 96 to 99 and 28 unused slots. One group, the root, holds the
//   boxes of these 4 leaves.
//   Example with 560,000 nodes: 17,500 leaves, then levels of 2,188 groups, 274, 35, 5 and 1.
//
// HOW A SEARCH RUNS
//   A search keeps the best node found so far, and a stack of boxes that it may still
//   have to open. Each box of the stack is a "visit" still to make. For a box, the search
//   computes the squared chord from the point to the box (0 if the point is inside). No
//   node of the box is nearer than this "lower bound".
//   1. First descent. Start at the root. Compute the lower bound of each child of the
//      group, go into the child with the lowest one, and put the other children on the
//      stack. Repeat down to a leaf.
//   2. In the leaf, compute the squared chord to each node. The lowest one is the first
//      best distance.
//   3. Drop from the stack the boxes whose lower bound is above the best distance (plus
//      the margin of WHY THE ANSWERS ARE EXACT), and order the others, the nearest on top.
//   4. Open the boxes that remain, the nearest first. A group puts on the stack each
//      child whose lower bound is not above the best distance, the nearest on top. A leaf
//      is scanned as in step 2, and may give a better best node. A box is dropped if a
//      node nearer than its lower bound was found since it was stacked.
//   Example: a point in Paris on a network of the world. The first descent follows the
//      boxes that contain the point, down to a leaf of nodes around Paris. That leaf gives
//      a best distance of about 1 km. The stack then holds the boxes of America, of Asia
//      and so on, and some boxes of Europe. Step 3 drops every box that does not reach
//      within 1 km of the point. Step 4 opens the few that do, each down to its leaves.
//
// HOW A QUADRANT IS DECIDED
//   A node is north of the point if its latitude is higher or equal, south if it is lower or
//   equal. It is east if it lies within 180 degrees of longitude eastwards, west likewise
//   (the rules of GeoKDTree). A node on a limit belongs to both sides.
//   On unit vectors, with p for the node and q for the point, these rules are two tests:
//   a comparison of z, and the sign of a difference of two products.
//     north:  p.z >= q.z                    because z = sin(latitude) grows with latitude
//     east:   q.x * p.y - q.y * p.x >= 0    because this is cos(latitude of q) *
//                                           cos(latitude of p) * sin(longitude of p -
//                                           longitude of q), and the sine is positive from
//                                           0 to 180 degrees
//   Example: q = (0 N, 0 E) = (1, 0, 0). For p = (0 N, 90 E) = (0, 1, 0), the east value is
//   1 * 1 - 0 * 0 = 1: east. For p = (0 N, 90 W) = (0, -1, 0), it is -1: west.
//   This form has two uses. The processor applies it to 4 nodes of a leaf at once. And a
//   whole box is judged at one corner: the east value is highest at one corner of the box,
//   known from the signs of q.x and q.y. If it is negative there, no node of the box is east
//   of the point, and the search for the eastern quadrants skips the box.
//   The per-quadrant search is one search with four best nodes, one per quadrant. A box is
//   opened if it can improve at least one of them. This search has no first descent,
//   because one leaf seldom holds a node of each quadrant. It runs step 4 from the root.
//
// WHY THE ANSWERS ARE EXACT
//   The index computes on 32-bit floats, which is fast, but a float result is rounded. So
//   a float result only selects nodes, and a computation in double decides:
//   - a node is a "candidate" if its float chord is within a margin of the shortest one.
//     At the end, the candidates are compared in double, with the same expression as the
//     Python index, and the lowest id wins a tie;
//   - the float quadrant tests accept a node that is within a margin of a limit. A node
//     that these tests accept counts for a quadrant only if its latitude and longitude,
//     compared in double, put it in that quadrant;
//   - boxes are rounded outward, so a box always contains its nodes.
//   Example: a float unit vector places a node within about 40 cm, and the margin on a
//   chord is 1e-6, about 6 m on the ground. Of two nodes 1 cm apart, the float chords do
//   not say which one is nearer. Both are candidates, and the comparison in double gives
//   the nearer one.
//
// THE PURE-PYTHON VERSION
//   helpers/snap_index.py gives the same answers. The comparison in double here uses the
//   same expression as the Python distance, with the platform's cos and sin, and is
//   compiled without fused multiply-add (-ffp-contract=off in CMakeLists.txt). So both
//   return the same node when two nodes tie to the last bit. Both must keep the same
//   quadrant rules and tie rule, which set the answers. They also share LEAF, FANOUT, and
//   the measure and the limit of leaves per query, so that they accept and refuse the same
//   orders. The limit bounds a cost and is not a contract: the two versions may judge
//   differently an order that is close to it.

// Thrown when the nodes are too scattered for the index to be useful (see above)
struct node_order_error : std::invalid_argument {
    using std::invalid_argument::invalid_argument;
};

class SnapIndex {
public:
    // A column of coordinates in degrees, read in place. It is built from a pointer to
    // float64 degrees or to int32 units of 1e-7 degree: the type of the pointer says which.
    // An int32 value is decoded by the same division as the Python reader. The index reads
    // a column only where it builds its leaves and checks candidates, never in its loops
    // over 4 floats
    class Coordinates {
    public:
        Coordinates(const double* degrees) : degrees_(degrees) {}
        Coordinates(const int32_t* units) : units_(units) {}
        double operator[](int i) const { return degrees_ ? degrees_[i] : units_[i] / 1e7; }

    private:
        const double* degrees_ = nullptr;  // set for float64 degrees
        const int32_t* units_ = nullptr;   // set for int32 units of 1e-7 degree
    };

    // latitudes[i], longitudes[i]: node i, for i < node_count. Both columns are built from pointers
    // of the same type. The index reads these arrays for as long as it lives and keeps
    // `owner`, which keeps them alive.
    // Throws node_order_error if the nodes are scattered (see above)
    SnapIndex(Coordinates latitudes, Coordinates longitudes, int node_count,
              std::shared_ptr<const void> owner);

    // Id of the node nearest to the point (latitude and longitude in degrees)
    int closest_idx(double latitude, double longitude) const;

    // Id of the nearest node in each quadrant around the point: out = {north-east,
    // north-west, south-east, south-west}, -1 for a quadrant without node.
    // In the .cpp, quadrant out[t] is bit 1 << t of a set of quadrants
    void closest_idx_per_quadrant(double latitude, double longitude, int out[4]) const;

private:
    // Nodes per leaf. A leaf is scanned 4 nodes at a time, and a set of its nodes is the
    // bits of one 32-bit integer
    static constexpr int LEAF = 32;
    // Children per group: the boxes of a group are computed as two sets of 4 floats. The
    // Python index has the same value
    static constexpr int FANOUT = 8;
    // Most leaves a query may scan on average: the sum of the leaves' box areas over the
    // area of the box around all nodes. The limit is over twice the highest value measured
    // on nodes sorted per mode, as build_geograph sorts them: 7.0, for three world-spanning
    // modes stored one after the other
    static constexpr double MAX_LEAVES_PER_QUERY = 16.0;
    // The six bounds of a box of unit vectors, in the order of Group::bounds. Even values
    // are minimums, odd values are maximums
    enum Bound { MIN_X, MAX_X, MIN_Y, MAX_Y, MIN_Z, MAX_Z, BOUNDS };

    // The unit vectors of LEAF consecutive nodes: node i of the leaf is (x[i], y[i], z[i]).
    // One array per coordinate, so that 4 consecutive nodes load as 4 lanes
    struct alignas(64) Leaf {
        float x[LEAF], y[LEAF], z[LEAF];
    };
    // The boxes of the children of a group: child k has the box bounds[MIN_X][k] to
    // bounds[MAX_Z][k]. One array per bound, for the same reason
    struct alignas(64) Group {
        float bounds[BOUNDS][FANOUT];
    };
    struct Query;
    struct Nearest;
    struct Visit;

    Coordinates latitudes_;  // by node id, read in place
    Coordinates longitudes_;
    std::shared_ptr<const void> owner_;  // keeps the two columns alive
    std::vector<Leaf> leaves_;
    // The groups of every level, level 0 first. level_start_[level] is the position of the
    // first group of a level. Child k of group g of a level is leaf (or, above level 0,
    // group) g * FANOUT + k of the level below
    std::vector<Group> groups_;
    std::vector<int> level_start_;

    void scan_leaf(int leaf, const Query& query, Nearest& nearest) const;
    void scan_leaf_per_quadrant(int leaf, int wanted_quadrants, const Query& query,
                                Nearest* nearest) const;
    int confirm_nearest(const Query& query, const Nearest& nearest) const;
};
