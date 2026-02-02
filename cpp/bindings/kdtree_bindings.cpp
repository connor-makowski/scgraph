#include <nanobind/nanobind.h>
#include <nanobind/stl/vector.h>
#include <nanobind/stl/pair.h>
#include "../src/kdtree.hpp"

namespace nb = nanobind;

NB_MODULE(kdtree_cpp, m) {
    m.doc() = "KD-Tree implementation for efficient nearest neighbor search";
    
    // ClosestPointResult struct
    nb::class_<ClosestPointResult>(m, "ClosestPointResult")
        .def_ro("point", &ClosestPointResult::point, "The closest point")
        .def_ro("distance", &ClosestPointResult::distance, "The squared distance to the closest point")
        .def("__repr__", [](const ClosestPointResult& r) {
            std::string point_str = "[";
            for (size_t i = 0; i < r.point.size(); ++i) {
                if (i > 0) point_str += ", ";
                point_str += std::to_string(r.point[i]);
            }
            point_str += "]";
            return "ClosestPointResult(point=" + point_str + ", distance=" + std::to_string(r.distance) + ")";
        });
    
    // ClosestIdxResult struct
    nb::class_<ClosestIdxResult>(m, "ClosestIdxResult")
        .def_ro("idx", &ClosestIdxResult::idx, "The index of the closest point")
        .def_ro("distance", &ClosestIdxResult::distance, "The squared distance to the closest point")
        .def("__repr__", [](const ClosestIdxResult& r) {
            return "ClosestIdxResult(idx=" + std::to_string(r.idx) + ", distance=" + std::to_string(r.distance) + ")";
        });
    
    // KDTree class
    nb::class_<KDTree>(m, "KDTree")
        .def(nb::init<const std::vector<std::vector<double>>&>(),
             nb::arg("points"),
             "Build a KD-Tree from a list of points")
        .def("closest_point", &KDTree::closest_point,
             nb::arg("point"),
             "Find the closest point in the tree to the given point")
        .def("closest_point_with_distance", &KDTree::closest_point_with_distance,
             nb::arg("point"),
             "Find the closest point and its distance to the given point");
    
    // GeoKDTree class
    nb::class_<GeoKDTree>(m, "GeoKDTree")
        .def(nb::init<const std::vector<std::pair<double, double>>&>(),
             nb::arg("points"),
             "Build a geographic KD-Tree from a list of (latitude, longitude) pairs")
        .def("closest_idx", &GeoKDTree::closest_idx,
             nb::arg("point"),
             "Find the index of the closest point to the given (lat, lon) pair")
        .def("closest_idx_with_distance", &GeoKDTree::closest_idx_with_distance,
             nb::arg("point"),
             "Find the index and distance of the closest point to the given (lat, lon) pair")
        .def_static("lat_lon_idx_to_xyz_idx", &GeoKDTree::lat_lon_idx_to_xyz_idx,
             nb::arg("lat"), nb::arg("lon"), nb::arg("idx") = 0,
             "Convert latitude and longitude to Cartesian coordinates (x, y, z) with an index");
    
    // Helper functions
    m.def("squared_distance", &kdtree_helpers::squared_distance,
          nb::arg("p1"), nb::arg("p2"), nb::arg("axis_count") = 2,
          "Calculate squared distance between two points");
    
    m.def("squared_distance_3d", &kdtree_helpers::squared_distance_3d,
          nb::arg("p1"), nb::arg("p2"),
          "Calculate squared distance between two 3D points");
    
    m.def("lat_lon_idx_to_xyz_idx", &kdtree_helpers::lat_lon_idx_to_xyz_idx,
          nb::arg("lat"), nb::arg("lon"), nb::arg("idx") = 0,
          "Convert latitude and longitude to Cartesian coordinates");
}