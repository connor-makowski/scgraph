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
//
// WHAT IT READS
//   The index reads the coordinates of the nodes in place, in the order given: position =
//   node id. It keeps the caller's arrays alive through `owner` and never copies them. The
//   coordinates are float64 degrees, or int32 units of 1e-7 degree as network files may
//   store them, decoded at each read as units / 1e7, like the Python index.
//   That order must keep nearby nodes together, as a Hilbert curve does (network files are
//   stored in Hilbert order). The constructor measures how many leaves a query would scan
//   and throws node_order_error above MAX_LEAVES_PER_QUERY, with the way to sort in the
//   message. The index does not sort, as the caller is the one that knows whether its node
//   ids may change.
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
//   have to open. For a box, it computes the squared chord from the point to the box (0 if
//   the point is inside). No node of the box is nearer than this "lower bound".
//   1. First descent. Start at the root. Compute the lower bound of each child of the
//      group, go into the child with the lowest one, and put the other children on the
//      stack. Repeat down to a leaf.
//   2. In the leaf, compute the squared chord to each node. The lowest one is the first
//      best distance.
//   3. Drop from the stack the boxes whose lower bound is above the best distance, and
//      order the others, the nearest on top.
//   4. Open the boxes left, the nearest first. A group puts on the stack its children
//      that are not above the best distance, in order. A leaf is scanned as in step 2,
//      and may give a better best node. A box is dropped if a node nearer than its lower
//      bound was found since it was stacked.
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
//   On unit vectors, with p for the node and q for the point, these rules are two sums of
//   products:
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
//   opened if it can improve at least one of them. It has no first descent: one leaf
//   seldom holds a node of each quadrant, so it runs step 4 from the root.
//
// WHY THE ANSWERS ARE EXACT
//   The index computes on floats, which is fast, and floats round. So floats only select:
//   - a node is a "candidate" if its float squared chord is within a small margin of the
//     best one. At the end, the candidates are compared in double, with the same expression
//     as the Python index, and the lowest id wins a tie;
//   - the float quadrant tests accept a node that is within a small margin of a limit. A
//     node accepted this way counts for a quadrant only if the rule on its latitude and
//     longitude, in double, says so;
//   - boxes are rounded outward, so a box always contains its nodes.
//
// helpers/snap_index.py is the pure-Python version. It gives the same answers. The double
// check here uses the same expression as the Python distance, with the platform's cos and
// sin, and is compiled without fused multiply-add (-ffp-contract=off in CMakeLists.txt).
// So both return the same node when two nodes tie to the last bit. Both must keep the
// same quadrant rules and tie rule, which set the answers. They also share LEAF, FANOUT
// and the leaves-per-query measure and limit, so that they accept and refuse the same
// orders (the limit is a cost bound, not a contract: orders close to it may be judged
// differently).

// Thrown when the nodes are too scattered for the index to be useful (see above)
struct node_order_error : std::invalid_argument {
    using std::invalid_argument::invalid_argument;
};

class SnapIndex {
public:
    // A column of coordinates, read in place: float64 degrees, or int32 units of 1e-7
    // degree (units) decoded by the same division as the Python reader. Read only where
    // the index builds its leaves and checks candidates, never in its loops over 4 floats
    struct Coordinates {
        const void* data;
        bool units;
        double operator[](int i) const {
            return units ? static_cast<const int32_t*>(data)[i] / 1e7
                         : static_cast<const double*>(data)[i];
        }
    };

    // latitudes[i], longitudes[i]: node i, for i < n. The index reads these arrays for as
    // long as it lives and keeps `owner`, which keeps them alive.
    // Throws node_order_error if the nodes are scattered (see above)
    SnapIndex(Coordinates latitudes, Coordinates longitudes, int n,
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
    // Children per group
    static constexpr int FANOUT = 8;
    // Most leaves a query may scan on average: the sum of the leaves' box areas over the
    // area of the box around all nodes. Over twice the most measured on nodes sorted per
    // mode, as build_geograph sorts them (7.0: three world-spanning modes, one after the
    // other)
    static constexpr double MAX_LEAVES_PER_QUERY = 16.0;
    // The six bounds of a box of unit vectors, in the order of Group::bounds. Even values
    // are lower bounds, odd values are upper bounds
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

    int n;
    Coordinates lat;  // by node id, read in place
    Coordinates lon;
    std::shared_ptr<const void> owner;  // keeps lat and lon alive
    std::vector<Leaf> leaves;
    // The groups of every level, level 0 first. level_start[level] is the position of the
    // first group of a level. Child k of group g of a level is leaf (or, above level 0,
    // group) g * FANOUT + k of the level below
    std::vector<Group> groups;
    std::vector<int> level_start;

    void scan_leaf(int leaf, const Query& query, Nearest& nearest) const;
    void scan_leaf_per_quadrant(int leaf, int wanted_quadrants, const Query& query,
                                Nearest* nearest) const;
    int confirm_nearest(const Query& query, const Nearest& nearest) const;
};
