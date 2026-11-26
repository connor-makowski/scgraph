// Bindings of the kernels that read the arrays of a GeoGraph.
// They read the points of the nodes and the shapes of the edges (NodePoints, EdgeShapes).
// They also give the snapping index, the selection of node modes and the weights of a metric.
// NB_MODULE in graph_bindings.cpp calls bind_geograph.
#include <nanobind/nanobind.h>
#include <nanobind/ndarray.h>
#include <nanobind/stl/optional.h>
#include <nanobind/stl/pair.h>
#include <nanobind/stl/unique_ptr.h>
#include <nanobind/stl/vector.h>
#include <memory>
#include <optional>
#include <span>
#include <stdexcept>
#include <utility>
#include <vector>
#include "../src/snap_index.hpp"
#include "../src/edge_selection.hpp"
#include "../src/metric_weights.hpp"
#include "ndarray_types.hpp"

namespace nb = nanobind;

// Coordinates as network files store them: int32 in 1e-7 degree (OSM's) or float64 degrees
template <typename T>
using CoordinateArray = nb::ndarray<const T, nb::ndim<1>, nb::c_contig, nb::device::cpu>;
// The same division as the Python reader, so that both read a stored value back exactly
static inline double degrees(int32_t units) { return units / 1e7; }
static inline double degrees(double value) { return value; }

// Returns the points of the nodes in `ids`, as a list of [latitude, longitude] in
// degrees. One C loop builds the list, for NodePoints.take. `node_points` holds the
// latitude, then the longitude, of each node.
template <typename T>
static nb::object coordinate_lists(CoordinateArray<T> node_points, nb::list ids) {
    const T* point = node_points.data();
    const Py_ssize_t n = (Py_ssize_t)node_points.shape(0) / 2;
    if (node_points.shape(0) % 2)
        throw std::invalid_argument("node_points must hold a latitude and a longitude per node");
    const Py_ssize_t count = PyList_Size(ids.ptr());
    nb::object result = nb::steal(PyList_New(count));
    if (!result.is_valid()) throw nb::python_error();
    for (Py_ssize_t k = 0; k < count; ++k) {
        Py_ssize_t i = PyNumber_AsSsize_t(PyList_GetItem(ids.ptr(), k), PyExc_IndexError);
        if (i == -1 && PyErr_Occurred()) throw nb::python_error();
        if (i < 0) i += n;
        if (i < 0 || i >= n) throw nb::index_error("node index out of range");
        PyObject* pair = PyList_New(2);
        if (!pair) throw nb::python_error();
        PyList_SetItem(result.ptr(), k, pair);
        PyObject* a = PyFloat_FromDouble(degrees(point[2 * i]));
        PyObject* b = PyFloat_FromDouble(degrees(point[2 * i + 1]));
        if (!a || !b) {
            Py_XDECREF(a);
            Py_XDECREF(b);
            throw nb::python_error();
        }
        PyList_SetItem(pair, 0, a);
        PyList_SetItem(pair, 1, b);
    }
    return result;
}

// `coordinates` (one per node of `path`) with the shape of each edge of the path between them
template <typename T>
static nb::object shape_path(Int32Array node_first_edge_ids, Int32Array edge_destination_node_ids, Int32Array edge_first_shape_point_ids, CoordinateArray<T> shape_points,
                             nb::list path, nb::list coordinates) {
    const int32_t* off = node_first_edge_ids.data();
    const int32_t* destination_id = edge_destination_node_ids.data();
    const int32_t* start = edge_first_shape_point_ids.data();
    const T* point = shape_points.data();
    const int64_t n = (int64_t)node_first_edge_ids.shape(0) - 1;
    const int64_t m = (int64_t)edge_destination_node_ids.shape(0);
    const int64_t k = (int64_t)shape_points.shape(0) / 2;
    if ((int64_t)edge_first_shape_point_ids.shape(0) != m + 1)
        throw std::invalid_argument("one first shape point id per edge, plus one, expected");
    const Py_ssize_t count = PyList_Size(path.ptr());
    if (PyList_Size(coordinates.ptr()) != count)
        throw std::invalid_argument("one point per path node expected");
    nb::object result = nb::steal(PyList_New(0));
    if (!result.is_valid()) throw nb::python_error();
    auto append = [&](PyObject* item) {
        if (PyList_Append(result.ptr(), item) < 0) throw nb::python_error();
    };
    if (count == 0) return result;
    append(PyList_GetItem(coordinates.ptr(), 0));
    Py_ssize_t origin = PyNumber_AsSsize_t(PyList_GetItem(path.ptr(), 0), PyExc_IndexError);
    if (origin == -1 && PyErr_Occurred()) throw nb::python_error();
    for (Py_ssize_t i = 1; i < count; ++i) {
        Py_ssize_t destination = PyNumber_AsSsize_t(PyList_GetItem(path.ptr(), i), PyExc_IndexError);
        if (destination == -1 && PyErr_Occurred()) throw nb::python_error();
        // Nodes added after loading (add_coord_node) have no shapes
        if (origin >= 0 && origin < n) {
            const int64_t first_edge = off[origin], last_edge = off[origin + 1];
            if (first_edge < 0 || first_edge > last_edge || last_edge > m)
                throw std::invalid_argument("invalid node_first_edge_ids");
            for (int64_t edge = first_edge; edge < last_edge; ++edge) {
                if (destination_id[edge] != destination) continue;
                const int64_t first = start[edge], last = start[edge + 1];
                if (first < 0 || first > last || last > k)
                    throw std::invalid_argument("invalid edge_first_shape_point_ids");
                for (int64_t p = first; p < last; ++p) {
                    PyObject* pair = PyList_New(2);
                    if (!pair) throw nb::python_error();
                    PyObject* a = PyFloat_FromDouble(degrees(point[2 * p]));
                    PyObject* b = PyFloat_FromDouble(degrees(point[2 * p + 1]));
                    if (!a || !b) {
                        Py_XDECREF(a);
                        Py_XDECREF(b);
                        Py_DECREF(pair);
                        throw nb::python_error();
                    }
                    PyList_SetItem(pair, 0, a);
                    PyList_SetItem(pair, 1, b);
                    int failed = PyList_Append(result.ptr(), pair);
                    Py_DECREF(pair);
                    if (failed < 0) throw nb::python_error();
                }
                break;
            }
        }
        append(PyList_GetItem(coordinates.ptr(), i));
        origin = destination;
    }
    return result;
}

// Builds a SnapIndex on the points of the nodes, without a copy. The points are float64
// degrees or int32 units of 1e-7 degree. The index keeps a reference to the array, so
// the array lives as long as the index.
template <typename T>
static std::unique_ptr<SnapIndex> snap_index_from_array(CoordinateArray<T> node_points) {
    if (node_points.shape(0) % 2)
        throw std::invalid_argument("node_points must hold a latitude and a longitude per node");
    auto owner = std::make_shared<decltype(node_points)>(node_points);
    return std::make_unique<SnapIndex>(node_points.data(), int(node_points.shape(0) / 2), owner);
}

// A [latitude, longitude] pair read without nanobind's generic conversion (snapping is called
// once per point, so reading the point is a visible part of its cost). Functions of the
// limited API only: the module is built with the stable ABI
static inline bool read_double(PyObject* o, double& out) {
    if (PyFloat_Check(o) || PyLong_Check(o)) {
        out = PyFloat_AsDouble(o);
        return !(out == -1.0 && PyErr_Occurred());
    }
    return false;
}

static inline std::pair<double, double> read_point(nb::handle h) {
    PyObject* o = h.ptr();
    PyObject *a = nullptr, *b = nullptr;
    if (PyList_Check(o) && PyList_Size(o) == 2) {
        a = PyList_GetItem(o, 0);
        b = PyList_GetItem(o, 1);
    } else if (PyTuple_Check(o) && PyTuple_Size(o) == 2) {
        a = PyTuple_GetItem(o, 0);
        b = PyTuple_GetItem(o, 1);
    }
    double la, lo;
    if (a && b && read_double(a, la) && read_double(b, lo)) return {la, lo};
    PyErr_Clear();
    return nb::cast<std::pair<double, double>>(h);
}

static nb::dict quadrant_dict(const int out[4]) {
    nb::dict d;
    static const char* keys[4] = {"ne", "nw", "se", "sw"};
    for (int t = 0; t < 4; ++t) {
        if (out[t] >= 0) d[keys[t]] = out[t];
        else d[keys[t]] = nb::none();
    }
    return d;
}

void bind_geograph(nb::module_& m) {
    // float64 first: an array of another dtype (e.g. numpy's) is then converted to degrees
    m.def("coordinate_lists", &coordinate_lists<double>, nb::arg("node_points"), nb::arg("ids"));
    m.def("coordinate_lists", &coordinate_lists<int32_t>, nb::arg("node_points"), nb::arg("ids"),
       "[[latitude, longitude] of node i for i in ids] in one C loop, from the points of the nodes "
       "(latitude then longitude of each node, int32 in 1e-7 degree or float64 degrees) and a list of "
       "ids (negative ids count from the end); a route's coordinates for NodePoints.take");

    m.def("select_edges", [](Int32Array node_first_edge_ids, Int32Array edge_destination_node_ids, Uint8Array node_mode_ids,
                            std::vector<bool> is_node_mode_kept, std::optional<Int32Array> edge_first_shape_point_ids) {
        EdgeSelection selection = select_edges(
            {node_first_edge_ids.data(), node_first_edge_ids.shape(0)}, {edge_destination_node_ids.data(), edge_destination_node_ids.shape(0)},
            {node_mode_ids.data(), node_mode_ids.shape(0)}, is_node_mode_kept,
            edge_first_shape_point_ids ? std::span(edge_first_shape_point_ids->data(), edge_first_shape_point_ids->shape(0)) : std::span<const int32_t>());
        return nb::make_tuple(
            owned_view(std::move(selection.node_first_edge_ids)), owned_view(std::move(selection.edge_destination_node_ids)),
            edge_first_shape_point_ids ? owned_view(std::move(selection.edge_first_shape_point_ids)) : nb::none(),
            selection.node_runs, selection.edge_runs, selection.shape_point_runs);
    }, nb::arg("node_first_edge_ids"), nb::arg("edge_destination_node_ids"), nb::arg("node_mode_ids"), nb::arg("is_node_mode_kept"),
       nb::arg("edge_first_shape_point_ids") = nb::none(),
       "The nodes of the kept node modes of a network file and the edges between them, as (node_first_edge_ids, edge_destination_node_ids, "
       "edge_first_shape_point_ids, node_runs, edge_runs, shape_point_runs); explained in scgraph/cpp/src/edge_selection.hpp, "
       "same result as scgraph.helpers.edge_selection.select_edges");

    m.def("compute_weights_from_km", [](Int32Array node_first_edge_ids, Int32Array edge_destination_node_ids, DoubleArray lengths_km,
                                          Uint8Array edge_class_ids, Uint8Array node_mode_ids,
                                          DoubleArray class_weights_per_km, DoubleArray hub_weights) {
        return owned_view(compute_weights_from_km(
            {node_first_edge_ids.data(), node_first_edge_ids.shape(0)}, {edge_destination_node_ids.data(), edge_destination_node_ids.shape(0)},
            {lengths_km.data(), lengths_km.shape(0)}, {edge_class_ids.data(), edge_class_ids.shape(0)},
            {node_mode_ids.data(), node_mode_ids.shape(0)},
            {class_weights_per_km.data(), class_weights_per_km.shape(0)},
            {hub_weights.data(), hub_weights.shape(0)}));
    }, nb::arg("node_first_edge_ids"), nb::arg("edge_destination_node_ids"), nb::arg("lengths_km"), nb::arg("edge_class_ids"),
       nb::arg("node_mode_ids"), nb::arg("class_weights_per_km"), nb::arg("hub_weights"),
       "The weight of each edge from a weight per km for each class and the weight added to it at "
       "a hub; explained in scgraph/cpp/src/metric_weights.hpp, same result as "
       "scgraph.helpers.metric_weights.compute_weights_from_km");

    m.def("compute_weighted_sum", [](std::vector<DoubleArray> weights_of_metrics, DoubleArray coefficients) {
        std::vector<std::span<const double>> weights;
        for (const auto& metric : weights_of_metrics) weights.emplace_back(metric.data(), metric.shape(0));
        return owned_view(compute_weighted_sum(weights, {coefficients.data(), coefficients.shape(0)}));
    }, nb::arg("weights_of_metrics"), nb::arg("coefficients"),
       "The weight of each edge as the sum of its weight in each metric times the coefficient of the "
       "metric; explained in scgraph/cpp/src/metric_weights.hpp, same result as "
       "scgraph.helpers.metric_weights.compute_weighted_sum");

    m.def("shape_path", &shape_path<double>, nb::arg("node_first_edge_ids"), nb::arg("edge_destination_node_ids"), nb::arg("edge_first_shape_point_ids"),
          nb::arg("shape_points"), nb::arg("path"), nb::arg("coordinates"));
    m.def("shape_path", &shape_path<int32_t>, nb::arg("node_first_edge_ids"), nb::arg("edge_destination_node_ids"), nb::arg("edge_first_shape_point_ids"),
          nb::arg("shape_points"), nb::arg("path"), nb::arg("coordinates"),
          "A route's coordinates with the shapes of its edges, in one C loop, from a network file's arrays "
          "(shape points int32 in 1e-7 degree or float64 degrees) and one [latitude, longitude] per path "
          "node; for EdgeShapes.coordinate_path");

    // Raised by SnapIndex when the nodes are too scattered; a ValueError for callers
    nb::exception<node_order_error>(m, "NodeOrderError", PyExc_ValueError);
    nb::class_<SnapIndex>(m, "SnapIndex",
        "Closest node of a point on the sphere, for snapping to a GeoGraph (exact, ties to the lowest id)")
        .def("__init__", [](SnapIndex* self, nb::handle points) {
            auto owned = std::make_shared<std::vector<double>>();
            nb::sequence seq = nb::borrow<nb::sequence>(points);
            size_t count = nb::len(seq);
            owned->reserve(2 * count);
            for (nb::handle point : seq) {
                auto [la, lo] = read_point(point);
                owned->push_back(la);
                owned->push_back(lo);
            }
            new (self) SnapIndex(owned->data(), int(count), owned);
        }, nb::arg("points"), "Index the points, a sequence of [latitude, longitude] in degrees")
        // float64 first: a numpy array of another dtype is then converted to degrees
        .def_static("from_array", &snap_index_from_array<double>, nb::arg("node_points"))
        .def_static("from_array", &snap_index_from_array<int32_t>, nb::arg("node_points"),
           "The same index, from one array that holds the latitude then the longitude of each node: "
           "float64 degrees, or int32 units of 1e-7 degree as network files store them. The index "
           "reads it in place and keeps it while it lives: changing its values afterwards gives "
           "wrong answers (build a new index)")
        .def("closest_idx", [](const SnapIndex& self, nb::handle point) {
            auto [la, lo] = read_point(point);
            return self.closest_idx(la, lo);
        }, nb::arg("point"), "Id of the indexed point closest to point; point is a [latitude, longitude] pair")
        .def("closest_idx_per_quadrant", [](const SnapIndex& self, nb::handle point) {
            auto [la, lo] = read_point(point);
            int out[4];
            self.closest_idx_per_quadrant(la, lo, out);
            return quadrant_dict(out);
        }, nb::arg("point"),
           "Id of the closest indexed point in each quadrant around point, as a dict with the keys 'ne', 'nw', 'se', 'sw' (None if the quadrant is empty)");
}
