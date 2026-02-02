#pragma once
#include <vector>
#include <tuple>
#include <algorithm>
#include <cmath>
#include <limits>
#include <memory>
#include <optional>

// Forward declarations
struct KDNode;
struct GeoKDNode;

// Result structures
struct ClosestPointResult {
    std::vector<double> point;
    double distance;
};

struct ClosestIdxResult {
    int idx;
    double distance;
};

// KD-Tree node structure
struct KDNode {
    std::vector<double> point;
    int axis;
    std::shared_ptr<KDNode> left;
    std::shared_ptr<KDNode> right;
    
    KDNode(const std::vector<double>& pt, int ax)
        : point(pt), axis(ax), left(nullptr), right(nullptr) {}
};

// Geo KD-Tree node structure (includes index)
struct GeoKDNode {
    std::vector<double> point;  // [x, y, z, idx]
    int axis;
    std::shared_ptr<GeoKDNode> left;
    std::shared_ptr<GeoKDNode> right;
    
    GeoKDNode(const std::vector<double>& pt, int ax)
        : point(pt), axis(ax), left(nullptr), right(nullptr) {}
};

// Helper functions
namespace kdtree_helpers {
    double squared_distance(const std::vector<double>& p1, const std::vector<double>& p2, int axis_count = 2);
    double squared_distance_3d(const std::vector<double>& p1, const std::vector<double>& p2);
    std::vector<double> lat_lon_idx_to_xyz_idx(double lat, double lon, int idx = 0);
}

// Standard KD-Tree class
class KDTree {
private:
    std::shared_ptr<KDNode> root;
    int dimensions;
    
    // Build tree recursively
    std::shared_ptr<KDNode> build_tree(std::vector<std::vector<double>>& points, int depth, int axis_count);
    
    // Find closest point recursively
    void find_closest(
        const std::shared_ptr<KDNode>& node,
        const std::vector<double>& point,
        int depth,
        std::vector<double>& best,
        double& best_dist,
        int axis_count
    ) const;

public:
    // Constructor
    explicit KDTree(const std::vector<std::vector<double>>& points);
    
    // Find the closest point to the given point
    std::vector<double> closest_point(const std::vector<double>& point) const;
    
    // Find the closest point and distance
    ClosestPointResult closest_point_with_distance(const std::vector<double>& point) const;
};

// Geographic KD-Tree class (for lat/lon coordinates)
class GeoKDTree {
private:
    std::shared_ptr<GeoKDNode> root;
    
    // Build tree recursively
    std::shared_ptr<GeoKDNode> build_tree(std::vector<std::vector<double>>& points, int depth);
    
    // Find closest point recursively
    void find_closest_3d(
        const std::shared_ptr<GeoKDNode>& node,
        const std::vector<double>& point,
        int depth,
        std::vector<double>& best,
        double& best_dist
    ) const;

public:
    // Constructor - takes lat/lon pairs
    explicit GeoKDTree(const std::vector<std::pair<double, double>>& points);

    // Find the index of the closest point
    int closest_idx(const std::pair<double, double>& point) const;
    
    // Find the index and distance of the closest point
    ClosestIdxResult closest_idx_with_distance(const std::pair<double, double>& point) const;
    
    // Static helper for coordinate conversion
    static std::vector<double> lat_lon_idx_to_xyz_idx(double lat, double lon, int idx = 0);
};