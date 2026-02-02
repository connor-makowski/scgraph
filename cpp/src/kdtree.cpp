#include "kdtree.hpp"
#include <cmath>
#include <algorithm>
#include <stdexcept>

namespace kdtree_helpers {
    double squared_distance(const std::vector<double>& p1, const std::vector<double>& p2, int axis_count) {
        double sum = 0.0;
        for (int i = 0; i < axis_count; ++i) {
            double diff = p1[i] - p2[i];
            sum += diff * diff;
        }
        return sum;
    }
    
    double squared_distance_3d(const std::vector<double>& p1, const std::vector<double>& p2) {
        double dx = p1[0] - p2[0];
        double dy = p1[1] - p2[1];
        double dz = p1[2] - p2[2];
        return dx * dx + dy * dy + dz * dz;
    }
    
    std::vector<double> lat_lon_idx_to_xyz_idx(double lat, double lon, int idx) {
        constexpr double PI = 3.14159265358979323846;
        double lat_rad = lat * PI / 180.0;
        double lon_rad = lon * PI / 180.0;
        double cos_lat = std::cos(lat_rad);
        double x = cos_lat * std::cos(lon_rad);
        double y = cos_lat * std::sin(lon_rad);
        double z = std::sin(lat_rad);
        return {x, y, z, static_cast<double>(idx)};
    }
}

// ============================================================================
// KDTree Implementation
// ============================================================================

KDTree::KDTree(const std::vector<std::vector<double>>& points) {
    if (points.empty()) {
        throw std::invalid_argument("Cannot build KDTree from empty point list");
    }
    
    dimensions = points[0].size();
    
    // Make a mutable copy of points for sorting
    std::vector<std::vector<double>> points_copy = points;
    
    root = build_tree(points_copy, 0, dimensions);
}

std::shared_ptr<KDNode> KDTree::build_tree(
    std::vector<std::vector<double>>& points, 
    int depth, 
    int axis_count
) {
    if (points.empty()) {
        return nullptr;
    }
    
    int axis = depth % axis_count;
    
    // Sort points by the current axis
    std::sort(points.begin(), points.end(),
        [axis](const std::vector<double>& a, const std::vector<double>& b) {
            return a[axis] < b[axis];
        }
    );
    
    size_t median = points.size() / 2;
    
    // Create node with median point
    auto node = std::make_shared<KDNode>(points[median], axis);
    
    // Build left and right subtrees
    if (median > 0) {
        std::vector<std::vector<double>> left_points(points.begin(), points.begin() + median);
        node->left = build_tree(left_points, depth + 1, axis_count);
    }
    
    if (median + 1 < points.size()) {
        std::vector<std::vector<double>> right_points(points.begin() + median + 1, points.end());
        node->right = build_tree(right_points, depth + 1, axis_count);
    }
    
    return node;
}

void KDTree::find_closest(
    const std::shared_ptr<KDNode>& node,
    const std::vector<double>& point,
    int depth,
    std::vector<double>& best,
    double& best_dist,
    int axis_count
) const {
    if (!node) {
        return;
    }
    
    // Calculate distance to current node
    double node_dist = kdtree_helpers::squared_distance(point, node->point, axis_count);
    
    // Update best if necessary
    if (best.empty() || node_dist < best_dist) {
        best = node->point;
        best_dist = node_dist;
    }
    
    // Determine which side to search first
    int axis = node->axis;
    double diff = point[axis] - node->point[axis];
    
    auto close = (diff < 0) ? node->left : node->right;
    auto away = (diff < 0) ? node->right : node->left;
    
    // Search the close side first
    find_closest(close, point, depth + 1, best, best_dist, axis_count);
    
    // Check if we need to search the other side
    if (diff * diff < best_dist) {
        find_closest(away, point, depth + 1, best, best_dist, axis_count);
    }
}

std::vector<double> KDTree::closest_point(const std::vector<double>& point) const {
    if (!root) {
        throw std::runtime_error("KDTree is empty");
    }
    
    std::vector<double> best;
    double best_dist = std::numeric_limits<double>::infinity();
    
    find_closest(root, point, 0, best, best_dist, dimensions);
    
    return best;
}

ClosestPointResult KDTree::closest_point_with_distance(const std::vector<double>& point) const {
    if (!root) {
        throw std::runtime_error("KDTree is empty");
    }
    
    std::vector<double> best;
    double best_dist = std::numeric_limits<double>::infinity();
    
    find_closest(root, point, 0, best, best_dist, dimensions);
    
    return ClosestPointResult{best, best_dist};
}

// ============================================================================
// GeoKDTree Implementation
// ============================================================================

GeoKDTree::GeoKDTree(const std::vector<std::pair<double, double>>& points) {
    if (points.empty()) {
        throw std::invalid_argument("Cannot build GeoKDTree from empty point list");
    }
    
    // Convert lat/lon points to xyz coordinates
    std::vector<std::vector<double>> xyz_points;
    xyz_points.reserve(points.size());
    
    for (size_t i = 0; i < points.size(); ++i) {
        xyz_points.push_back(
            kdtree_helpers::lat_lon_idx_to_xyz_idx(
                points[i].first,
                points[i].second,
                i
            )
        );
    }
    
    root = build_tree(xyz_points, 0);
}

std::shared_ptr<GeoKDNode> GeoKDTree::build_tree(
    std::vector<std::vector<double>>& points,
    int depth
) {
    if (points.empty()) {
        return nullptr;
    }
    
    int axis = depth % 3;  // 3D for x, y, z
    
    // Sort points by the current axis
    std::sort(points.begin(), points.end(),
        [axis](const std::vector<double>& a, const std::vector<double>& b) {
            return a[axis] < b[axis];
        }
    );
    
    size_t median = points.size() / 2;
    
    // Create node with median point
    auto node = std::make_shared<GeoKDNode>(points[median], axis);
    
    // Build left and right subtrees
    if (median > 0) {
        std::vector<std::vector<double>> left_points(points.begin(), points.begin() + median);
        node->left = build_tree(left_points, depth + 1);
    }
    
    if (median + 1 < points.size()) {
        std::vector<std::vector<double>> right_points(points.begin() + median + 1, points.end());
        node->right = build_tree(right_points, depth + 1);
    }
    
    return node;
}

void GeoKDTree::find_closest_3d(
    const std::shared_ptr<GeoKDNode>& node,
    const std::vector<double>& point,
    int depth,
    std::vector<double>& best,
    double& best_dist
) const {
    if (!node) {
        return;
    }
    
    // Calculate distance to current node (only first 3 dimensions - x, y, z)
    double node_dist = kdtree_helpers::squared_distance_3d(point, node->point);
    
    // Update best if necessary
    if (best.empty() || node_dist < best_dist) {
        best = node->point;
        best_dist = node_dist;
    }
    
    // Determine which side to search first
    int axis = node->axis;
    double diff = point[axis] - node->point[axis];
    
    auto close = (diff < 0) ? node->left : node->right;
    auto away = (diff < 0) ? node->right : node->left;
    
    // Search the close side first
    find_closest_3d(close, point, depth + 1, best, best_dist);
    
    // Check if we need to search the other side
    if (diff * diff < best_dist) {
        find_closest_3d(away, point, depth + 1, best, best_dist);
    }
}

int GeoKDTree::closest_idx(const std::pair<double, double>& point) const {
    if (!root) {
        throw std::runtime_error("GeoKDTree is empty");
    }
    
    // Convert query point to xyz
    auto query_point = kdtree_helpers::lat_lon_idx_to_xyz_idx(point.first, point.second, 0);
    
    std::vector<double> best;
    double best_dist = std::numeric_limits<double>::infinity();
    
    find_closest_3d(root, query_point, 0, best, best_dist);
    
    // Return the index (4th element)
    return static_cast<int>(best[3]);
}

ClosestIdxResult GeoKDTree::closest_idx_with_distance(const std::pair<double, double>& point) const {
    if (!root) {
        throw std::runtime_error("GeoKDTree is empty");
    }
    
    // Convert query point to xyz
    auto query_point = kdtree_helpers::lat_lon_idx_to_xyz_idx(point.first, point.second, 0);
    
    std::vector<double> best;
    double best_dist = std::numeric_limits<double>::infinity();
    
    find_closest_3d(root, query_point, 0, best, best_dist);
    
    // Return the index and distance
    return ClosestIdxResult{static_cast<int>(best[3]), best_dist};
}

std::vector<double> GeoKDTree::lat_lon_idx_to_xyz_idx(double lat, double lon, int idx) {
    return kdtree_helpers::lat_lon_idx_to_xyz_idx(lat, lon, idx);
}