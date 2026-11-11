#include <nanobind/nanobind.h>
#include <cmath>
#include <nanobind/stl/vector.h>
#include <nanobind/stl/pair.h>
#include <nanobind/stl/unordered_map.h>
#include <nanobind/stl/set.h>
#include <nanobind/stl/optional.h>
#include <nanobind/stl/variant.h>
#include <nanobind/stl/function.h>
#include <nanobind/stl/string.h>
#include <nanobind/stl/tuple.h>
#include <nanobind/ndarray.h>
#include <nanobind/stl/shared_ptr.h>
#include <nanobind/stl/unique_ptr.h>
#include <nanobind/operators.h>
#include <string>
#include <stdexcept>
#include <memory>
#include <type_traits>
#include <tuple>
#include "../src/graph.hpp"
#include "../src/contraction_hierarchies.hpp"
#include "../src/transit_node_routing.hpp"
#include "../src/snap_index.hpp"
#include "array_types.hpp"

namespace nb = nanobind;
using namespace nb::literals;

// Helper function to convert GraphResult to dict
static nb::dict graph_result_to_dict(const GraphResult& r) {
    nb::dict d;
    d["path"] = r.path;
    d["length"] = r.length;
    return d;
}

// Helper function to convert TreeData to dict
static nb::dict tree_data_to_dict(const TreeData& t) {
    nb::dict d;
    d["origin_id"] = t.origin_id;
    d["predecessors"] = t.predecessors;
    d["distance_matrix"] = t.distance_matrix;
    return d;
}

// Helper function to convert dict to TreeData
static TreeData dict_to_tree_data(const nb::dict& d) {
    return TreeData{
        nb::cast<NodeIdVariant>(d["origin_id"]),
        nb::cast<std::vector<int>>(d["predecessors"]),
        nb::cast<std::vector<double>>(d["distance_matrix"])
    };
}

// Returns true if a TreeData entry is the default-constructed sentinel (not yet computed)
static bool is_empty_tree_data(const TreeData& t) {
    return t.predecessors.empty();
}

// Coordinates as network files store them: int32 in 1e-7 degree (OSM's) or float64 degrees
template <typename T>
using CoordinateArray = nb::ndarray<const T, nb::ndim<1>, nb::c_contig, nb::device::cpu>;
// The same division as the Python reader, so that both read a stored value back exactly
static inline double degrees(int32_t units) { return units / 1e7; }
static inline double degrees(double value) { return value; }

// [[latitudes[i], longitudes[i]] for i in ids] in degrees, in one C loop (NodeCoordinates.take)
template <typename T>
static nb::object coordinate_lists(CoordinateArray<T> latitudes, CoordinateArray<T> longitudes, nb::list ids) {
    const T* la = latitudes.data();
    const T* lo = longitudes.data();
    const Py_ssize_t n = (Py_ssize_t)latitudes.shape(0);
    if ((Py_ssize_t)longitudes.shape(0) != n)
        throw std::invalid_argument("latitudes and longitudes must have the same length");
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
        PyObject* a = PyFloat_FromDouble(degrees(la[i]));
        PyObject* b = PyFloat_FromDouble(degrees(lo[i]));
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

// `coordinates` (one per node of `path`) with the shape of each arc of the path between them
template <typename T>
static nb::object shape_path(CsrInts offsets, CsrInts heads, CsrInts shape_offsets, CoordinateArray<T> shape_points,
                             nb::list path, nb::list coordinates) {
    const int32_t* off = offsets.data();
    const int32_t* head = heads.data();
    const int32_t* start = shape_offsets.data();
    const T* point = shape_points.data();
    const int64_t n = (int64_t)offsets.shape(0) - 1;
    const int64_t m = (int64_t)heads.shape(0);
    const int64_t k = (int64_t)shape_points.shape(0) / 2;
    if ((int64_t)shape_offsets.shape(0) != m + 1)
        throw std::invalid_argument("one shape offset per arc, plus one, expected");
    const Py_ssize_t count = PyList_Size(path.ptr());
    if (PyList_Size(coordinates.ptr()) != count)
        throw std::invalid_argument("one coordinate per path node expected");
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
            const int64_t first_arc = off[origin], last_arc = off[origin + 1];
            if (first_arc < 0 || first_arc > last_arc || last_arc > m)
                throw std::invalid_argument("invalid offsets");
            for (int64_t arc = first_arc; arc < last_arc; ++arc) {
                if (head[arc] != destination) continue;
                const int64_t first = start[arc], last = start[arc + 1];
                if (first < 0 || first > last || last > k)
                    throw std::invalid_argument("invalid shape offsets");
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

// A SnapIndex reading two arrays of coordinates in place (float64 degrees, or int32 units of
// 1e-7 degree), which it keeps alive
template <typename T>
static std::unique_ptr<SnapIndex> snap_index_from_arrays(
        nb::ndarray<const T, nb::ndim<1>, nb::c_contig, nb::device::cpu> latitudes,
        nb::ndarray<const T, nb::ndim<1>, nb::c_contig, nb::device::cpu> longitudes) {
    if (latitudes.shape(0) != longitudes.shape(0))
        throw std::invalid_argument("latitudes and longitudes must have the same length");
    auto owner = std::make_shared<std::pair<decltype(latitudes), decltype(longitudes)>>(latitudes, longitudes);
    const bool units = std::is_same_v<T, int32_t>;
    return std::make_unique<SnapIndex>(SnapIndex::Coordinates{latitudes.data(), units},
                                       SnapIndex::Coordinates{longitudes.data(), units},
                                       int(latitudes.shape(0)), owner);
}

// A Graph from arcs stored by origin: copied, or read in place and kept alive (in_place)
static std::unique_ptr<Graph> csr_graph(CsrInts offsets, CsrInts heads, CsrDoubles weights, bool in_place) {
    if (offsets.shape(0) < 1 || heads.shape(0) != weights.shape(0)) {
        throw std::invalid_argument("expected one offset per node plus one and one weight per arc");
    }
    std::shared_ptr<const void> owner;
    if (in_place) {
        owner = std::make_shared<std::tuple<CsrInts, CsrInts, CsrDoubles>>(offsets, heads, weights);
    }
    auto graph = std::make_unique<Graph>(std::vector<std::unordered_map<int, double>>{});
    graph->load_csr(offsets.data(), heads.data(), weights.data(),
                    (int)offsets.shape(0) - 1, (int64_t)heads.shape(0), owner);
    return graph;
}

// The arcs by origin (offsets, heads, weights), in the order searches visit them, as
// read-only memoryviews of the graph's own arrays: the capsule's copy of the handle keeps
// them alive after the graph is edited or deleted. With an order (order[new] = old), the
// rows of the nodes in that order, heads renumbered, in one new copy
static nb::tuple graph_csr(const Graph& graph, std::optional<std::vector<int32_t>> order) {
    auto* arcs = new Adjacency(graph.arcs());
    nb::capsule owner(arcs, [](void* arcs) noexcept { delete static_cast<Adjacency*>(arcs); });
    if (order) {
        const int n = arcs->size();
        std::vector<int32_t> new_id(n, -1), offsets{0}, heads;
        std::vector<double> weights;
        if (order->size() != static_cast<size_t>(n)) throw nb::index_error("order must list every node once");
        for (int32_t i = 0; i < n; ++i) {
            const int32_t old = (*order)[i];
            if (old < 0 || old >= n || new_id[old] != -1) throw nb::index_error("order must list every node once");
            new_id[old] = i;
        }
        heads.reserve(arcs->arcs());
        weights.reserve(arcs->arcs());
        for (int32_t old : *order) {
            for (const auto& [head, weight] : (*arcs)[old]) {
                heads.push_back(new_id[head]);
                weights.push_back(weight);
            }
            // At most the graph's arc count, which fits in int32 (Adjacency)
            offsets.push_back(static_cast<int32_t>(heads.size()));
        }
        *arcs = Adjacency(std::move(offsets), std::move(heads), std::move(weights));
    }
    auto view = [&](auto values) {
        using Value = typename decltype(values)::element_type;
        return nb::ndarray<nb::memview, Value, nb::ndim<1>>(values.data(), {values.size()}, owner);
    };
    return nb::make_tuple(view(arcs->all_offsets()), view(arcs->all_heads()), view(arcs->all_weights()));
}

// reduced_graph_connections or reduced_inverse_graph_connections as a list: None or
// {b: [hidden nodes]} per node, built from the pointers (GraphReducer::hidden_nodes)
static nb::list reduced_connections(const Graph& graph, bool inverse) {
    const auto& pointers = inverse ? graph.get_reduced_inverse_graph_connections_internal()
                                   : graph.get_reduced_graph_connections_internal();
    nb::list res;
    for (size_t i = 0; i < pointers.size(); ++i) {
        if (pointers[i].empty()) {
            res.append(nb::none());
        } else {
            nb::dict d;
            for (const auto& [root, _] : pointers[i]) {
                d[nb::cast(root)] = graph.hidden_nodes((int)i, root, inverse);
            }
            res.append(d);
        }
    }
    return res;
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

// The pipelines' kernels, in their own translation unit (pipelines_bindings.cpp)
void bind_pipelines(nb::module_& m);

NB_MODULE(cpp, m) {
    bind_pipelines(m);

    // float64 first: an array of another dtype (e.g. numpy's) is then converted to degrees
    m.def("coordinate_lists", &coordinate_lists<double>, nb::arg("latitudes"), nb::arg("longitudes"), nb::arg("ids"));
    m.def("coordinate_lists", &coordinate_lists<int32_t>, nb::arg("latitudes"), nb::arg("longitudes"), nb::arg("ids"),
       "[[latitudes[i], longitudes[i]] for i in ids] in one C loop, from two arrays of coordinates (int32 in "
       "1e-7 degree or float64 degrees) and a list of ids (negative ids count from the end); a route's "
       "coordinates for NodeCoordinates.take");

    m.def("shape_path", &shape_path<double>, nb::arg("offsets"), nb::arg("heads"), nb::arg("shape_offsets"),
          nb::arg("shape_points"), nb::arg("path"), nb::arg("coordinates"));
    m.def("shape_path", &shape_path<int32_t>, nb::arg("offsets"), nb::arg("heads"), nb::arg("shape_offsets"),
          nb::arg("shape_points"), nb::arg("path"), nb::arg("coordinates"),
          "A route's coordinates with the shapes of its arcs, in one C loop, from a network file's arrays "
          "(shape points int32 in 1e-7 degree or float64 degrees) and one [latitude, longitude] per path "
          "node; for ArcShapes.coordinate_path");

    // Raised by SnapIndex when the nodes are too scattered; a ValueError for callers
    nb::exception<node_order_error>(m, "NodeOrderError", PyExc_ValueError);
    nb::class_<SnapIndex>(m, "SnapIndex",
        "Nearest node of a point on the sphere, for snapping to a GeoGraph (exact, ties to the lowest id)")
        .def("__init__", [](SnapIndex* self, nb::handle points) {
            struct Owned { std::vector<double> latitudes, longitudes; };
            auto owned = std::make_shared<Owned>();
            nb::sequence seq = nb::borrow<nb::sequence>(points);
            size_t count = nb::len(seq);
            owned->latitudes.resize(count);
            owned->longitudes.resize(count);
            size_t i = 0;
            for (nb::handle point : seq) {
                auto [la, lo] = read_point(point);
                owned->latitudes[i] = la;
                owned->longitudes[i] = lo;
                ++i;
            }
            new (self) SnapIndex({owned->latitudes.data(), false}, {owned->longitudes.data(), false},
                                 int(count), owned);
        }, nb::arg("points"), "Index the points, a sequence of [latitude, longitude] in degrees")
        // float64 first: a numpy array of another dtype is then converted to degrees
        .def_static("from_arrays", &snap_index_from_arrays<double>, nb::arg("latitudes"), nb::arg("longitudes"))
        .def_static("from_arrays", &snap_index_from_arrays<int32_t>, nb::arg("latitudes"), nb::arg("longitudes"),
           "The same index, from two arrays of the same dtype: float64 degrees, or int32 units of "
           "1e-7 degree as network files may store them. The index reads them in place and keeps "
           "them while it lives: changing their values afterwards gives wrong answers (build a new "
           "index)")
        .def("closest_idx", [](const SnapIndex& self, nb::handle point) {
            auto [la, lo] = read_point(point);
            return self.closest_idx(la, lo);
        }, nb::arg("point"), "Id of the indexed point nearest to point; point is a [latitude, longitude] pair")
        .def("closest_idx_per_quadrant", [](const SnapIndex& self, nb::handle point) {
            auto [la, lo] = read_point(point);
            int out[4];
            self.closest_idx_per_quadrant(la, lo, out);
            return quadrant_dict(out);
        }, nb::arg("point"),
           "Id of the nearest indexed point in each quadrant around point, as a dict with the keys 'ne', 'nw', 'se', 'sw' (None if the quadrant is empty)");

    // Graph class
    nb::class_<Graph>(m, "Graph")
        // Constructor
        .def(nb::init<const std::vector<std::unordered_map<int, double>>&, bool>(),
             nb::arg("graph"), nb::arg("validate") = false,
             "Initialize a Graph object with adjacency list representation")

        // Validation and utility
        .def("validate", &Graph::validate,
             nb::arg("check_symmetry") = true, nb::arg("check_connected") = true,
             "Validate that the graph is properly formatted")
        .def("reset_cache", &Graph::reset_cache,
             "Reset the cached shortest path trees")
        .def("get", &Graph::get, nb::arg("idx"),
             "Get the adjacency dictionary for a specific node")
        .def("size", &Graph::size,
             "Get the number of nodes in the graph")
        .def_prop_ro("graph", &Graph::get_graph,
             "Get the entire graph adjacency list")
        .def_prop_ro("unreduced_graph", &Graph::get_graph,
             "Same as graph")
        .def("_csr", &graph_csr, nb::arg("order") = nb::none(),
             "The graph (unreduced) as arcs by origin: int32 offsets and heads, float64 weights, in the order searches visit them (read-only views of the graph's arrays); with an order (order[new] = old), the rows in that order, heads renumbered (one copy)")
        .def_prop_ro("inverse_graph", &Graph::get_inverse_graph,
             "Get the inverse of the graph: every edge reversed")
        .def_prop_ro("search_graph", [](const Graph& self) -> std::vector<std::unordered_map<int, double>> {
            if (self.get_has_reduced_graph()) {
                return self.get_reduced_graph();
            }
            return self.get_graph();
        }, "The graph searched by the algorithms: reduced_graph after reduce(), else graph")
        .def_prop_ro("search_inverse_graph", [](Graph& self) -> std::vector<std::unordered_map<int, double>> {
            if (self.get_has_reduced_graph()) {
                return self.get_reduced_inverse_graph();
            }
            return self.get_inverse_graph();
        }, "The inverse searched by the bidirectional algorithms: reduced_inverse_graph after reduce(), else inverse_graph")
        .def("reduce", &Graph::reduce, nb::arg("iterations") = -1,
             "Reduce the graph by bypassing pass-through nodes")
        .def_prop_ro("reduced_graph", [](const Graph& self) -> std::optional<std::vector<std::unordered_map<int, double>>> {
            if (!self.get_has_reduced_graph()) {
                return std::nullopt;
            }
            std::vector<std::unordered_map<int, double>> res(self.size());
            const auto& rg = self.get_reduced_graph_internal();
            for (size_t i = 0; i < rg.size(); ++i) {
                for (const auto& edge : rg[i]) {
                    res[i][edge.first] = edge.second;
                }
            }
            return res;
        })
        .def_prop_ro("is_reduced", [](const Graph& self) -> std::optional<std::vector<bool>> {
            if (!self.get_has_reduced_graph()) {
                return std::nullopt;
            }
            return self.get_is_reduced_internal();
        })
        .def_prop_ro("reduced_node_chain_ids", [](const Graph& self) -> std::optional<nb::list> {
            if (!self.get_has_reduced_graph()) {
                return std::nullopt;
            }
            nb::list res;
            const auto& chain_ids = self.get_reduced_node_chain_ids_internal();
            for (int cid : chain_ids) {
                if (cid == -1) {
                    res.append(nb::none());
                } else {
                    res.append(cid);
                }
            }
            return res;
        })
        .def("is_same_chain", &Graph::is_same_chain,
             nb::arg("origin_id"), nb::arg("destination_id") = nb::none(),
             "Check if origin and destination belong to the same reduced chain")
        .def("expand_path", &Graph::expand_path,
             nb::arg("path"),
             "Expand a path of reduced graph nodes")
        .def_prop_ro("reduced_graph_connections", [](const Graph& self) -> std::optional<nb::list> {
            if (!self.get_has_reduced_graph()) {
                return std::nullopt;
            }
            return reduced_connections(self, false);
        })
        .def_prop_ro("reduced_inverse_graph", [](const Graph& self) -> std::optional<std::vector<std::unordered_map<int, double>>> {
            if (!self.get_has_reduced_graph()) {
                return std::nullopt;
            }
            std::vector<std::unordered_map<int, double>> res(self.size());
            const auto& rig = self.get_reduced_inverse_graph_internal();
            for (size_t i = 0; i < rig.size(); ++i) {
                for (const auto& edge : rig[i]) {
                    res[i][edge.first] = edge.second;
                }
            }
            return res;
        })
        .def_prop_ro("reduced_inverse_graph_connections", [](const Graph& self) -> std::optional<nb::list> {
            if (!self.get_has_reduced_graph()) {
                return std::nullopt;
            }
            return reduced_connections(self, true);
        })

        // Cache IO
        // get_cache: returns a list matching the Python convention where uncached
        // entries are 0 (int) and cached entries are dicts
        .def("get_cache", [](Graph& self) {
            nb::list cache_list;
            for (int i = 0; i < self.size(); ++i) {
                cache_list.append(nb::int_(0));
            }
            for (const auto& [origin, tree_data] : self.get_cache()) {
                if (!is_empty_tree_data(tree_data)) {
                    cache_list[origin] = tree_data_to_dict(tree_data);
                }
            }
            return cache_list;
        }, "Get the cached shortest path trees")
        // set_cache: accepts a list where entries are either 0 (int) or dicts
        .def("set_cache", [](Graph& self, const nb::list& new_cache) {
            // get_cache writes each tree at its origin in a list of size() entries
            if (new_cache.size() != static_cast<size_t>(self.size())) {
                throw std::invalid_argument("Cache must be the same length as the graph");
            }
            std::unordered_map<int, TreeData> cache_map;
            for (size_t i = 0; i < new_cache.size(); ++i) {
                const auto& item = new_cache[i];
                if (!item.is_none() && !nb::isinstance<nb::int_>(item)) {
                    cache_map[static_cast<int>(i)] = dict_to_tree_data(nb::cast<nb::dict>(item));
                }
            }
            self.set_cache(std::move(cache_map));
        }, "Set the cached shortest path trees")

        // Path weight
        .def("get_path_weight", &Graph::get_path_weight,
             nb::arg("path"),
             "Sum the graph weights along a sequence of node ids")

        // Graph modification methods
        .def("add_node", &Graph::add_node,
             nb::arg("node_dict") = std::unordered_map<int, double>{},
             nb::arg("symmetric") = false,
             "Add a node to the graph")
        .def("add_edge", &Graph::add_edge,
             nb::arg("origin_id"), nb::arg("destination_id"),
             nb::arg("distance"), nb::arg("symmetric") = false,
             "Add an edge to the graph")
        .def("remove_node", &Graph::remove_node,
             nb::arg("symmetric_node") = false,
             "Remove the last node from the graph")
        .def("remove_edge", &Graph::remove_edge,
             nb::arg("origin_id"), nb::arg("destination_id"),
             nb::arg("symmetric") = false,
             "Remove an edge from the graph")

        // Tree algorithms
        // get_shortest_path_tree: returns a dict to match the Python API
        .def("get_shortest_path_tree", [](Graph& self,
                                          const NodeIdVariant& origin_id) -> nb::dict {
            return tree_data_to_dict(self.get_shortest_path_tree(origin_id));
        }, nb::arg("origin_id"),
           "Calculate the shortest path tree using Dijkstra's algorithm")

        // get_tree_path: accepts a dict (as returned by get_shortest_path_tree) and returns a dict
        .def("get_tree_path", [](Graph& self, const NodeIdVariant& origin_id, const NodeIdVariant& destination_id,
                                  const nb::dict& tree_data, bool length_only) -> nb::dict {
            return graph_result_to_dict(
                self.get_tree_path(origin_id, destination_id, dict_to_tree_data(tree_data), length_only)
            );
        }, nb::arg("origin_id"), nb::arg("destination_id"),
           nb::arg("tree_data"), nb::arg("length_only") = false,
           "Get the path from origin to destination using tree data")

        // Shortest path algorithms - all return dicts
        .def("dijkstra", [](Graph& self,
                            const NodeIdVariant& origin_id,
                            const NodeIdVariant& destination_id) -> nb::dict {
            return graph_result_to_dict(self.dijkstra(origin_id, destination_id));
        }, nb::arg("origin_id"), nb::arg("destination_id"),
           "Find shortest path using Dijkstra's algorithm")

        .def("bidirectional_dijkstra", [](Graph& self,
                                          const NodeIdVariant& origin_id,
                                          const NodeIdVariant& destination_id) -> nb::dict {
            return graph_result_to_dict(self.bidirectional_dijkstra(origin_id, destination_id));
        }, nb::arg("origin_id"), nb::arg("destination_id"),
           "Find shortest path using bidirectional Dijkstra's algorithm")

        .def("dijkstra_buckets", [](Graph& self,
                                    const NodeIdVariant& origin_id,
                                    const NodeIdVariant& destination_id,
                                    std::optional<double> max_edge_weight,
                                    std::optional<double> bucket_width) -> nb::dict {
            return graph_result_to_dict(self.dijkstra_buckets(origin_id, destination_id, max_edge_weight, bucket_width));
        }, nb::arg("origin_id"), nb::arg("destination_id"),
           nb::arg("max_edge_weight") = nb::none(), nb::arg("bucket_width") = nb::none(),
           "Find shortest path using Dijkstra with buckets")

        .def("bidirectional_buckets", [](Graph& self,
                                         const NodeIdVariant& origin_id,
                                         const NodeIdVariant& destination_id,
                                         std::optional<double> max_edge_weight,
                                         std::optional<double> bucket_width) -> nb::dict {
            return graph_result_to_dict(self.bidirectional_buckets(origin_id, destination_id, max_edge_weight, bucket_width));
        }, nb::arg("origin_id"), nb::arg("destination_id"),
           nb::arg("max_edge_weight") = nb::none(), nb::arg("bucket_width") = nb::none(),
           "Find shortest path using bidirectional Dijkstra with buckets")

        .def("dijkstra_negative", [](Graph& self,
                                     const NodeIdVariant& origin_id,
                                     const NodeIdVariant& destination_id,
                                     std::optional<int> cycle_check_iterations) -> nb::dict {
            return graph_result_to_dict(
                self.dijkstra_negative(origin_id, destination_id, cycle_check_iterations)
            );
        }, nb::arg("origin_id"), nb::arg("destination_id"),
           nb::arg("cycle_check_iterations") = nb::none(),
           "Find shortest path using Dijkstra with negative cycle detection")

        .def("a_star", [](Graph& self,
                          const NodeIdVariant& origin_id,
                          const NodeIdVariant& destination_id,
                          std::function<double(int, int)> heuristic_fn) -> nb::dict {
            return graph_result_to_dict(self.a_star(origin_id, destination_id, heuristic_fn));
        }, nb::arg("origin_id"), nb::arg("destination_id"),
           nb::arg("heuristic_fn") = nullptr,
           "Find shortest path using A* algorithm with optional heuristic")

        .def("a_star_great_circle", [](Graph& self,
                                       const NodeIdVariant& origin_id,
                                       const NodeIdVariant& destination_id,
                                       nb::ndarray<const double, nb::ndim<1>, nb::c_contig, nb::device::cpu> latitudes,
                                       nb::ndarray<const double, nb::ndim<1>, nb::c_contig, nb::device::cpu> longitudes,
                                       double radius) -> nb::dict {
            if (latitudes.shape(0) < (size_t)self.size() || longitudes.shape(0) < (size_t)self.size()) {
                throw std::invalid_argument("latitudes and longitudes must have an entry for every graph node");
            }
            const double* lat = latitudes.data();
            const double* lon = longitudes.data();
            // Same formula and operation order as scgraph.utils.haversine
            std::function<double(int, int)> heuristic_fn = [lat, lon, radius](int origin, int destination) {
                double a = std::pow(std::sin((lat[destination] - lat[origin]) / 2), 2)
                    + std::cos(lat[origin]) * std::cos(lat[destination])
                    * std::pow(std::sin((lon[destination] - lon[origin]) / 2), 2);
                return 2 * std::asin(std::pow(a, 0.5)) * radius;
            };
            return graph_result_to_dict(self.a_star(origin_id, destination_id, heuristic_fn));
        }, nb::arg("origin_id"), nb::arg("destination_id"),
           nb::arg("latitudes"), nb::arg("longitudes"), nb::arg("radius"),
           "A* with the great-circle distance as heuristic, computed natively from node latitudes and longitudes in radians")

        .def_static("from_csr", [](CsrInts offsets, CsrInts heads, CsrDoubles weights) {
            return csr_graph(offsets, heads, weights, false);
        }, nb::arg("offsets"), nb::arg("heads"), nb::arg("weights"),
           "Create a Graph from its arcs stored by origin (compressed sparse rows), as in a .scgraph network file")
        // For load_from_scgraph: the arrays of a file mapped read-only, read in place
        .def_static("_from_mapped_csr", [](CsrInts offsets, CsrInts heads, CsrDoubles weights) {
            return csr_graph(offsets, heads, weights, true);
        }, nb::arg("offsets"), nb::arg("heads"), nb::arg("weights"))

        .def("bellman_ford", [](Graph& self,
                                const NodeIdVariant& origin_id,
                                const NodeIdVariant& destination_id) -> nb::dict {
            return graph_result_to_dict(self.bellman_ford(origin_id, destination_id));
        }, nb::arg("origin_id"), nb::arg("destination_id"),
           "Find shortest path using Bellman-Ford algorithm")

        .def("bmssp", [](Graph& self,
                         const NodeIdVariant& origin_id,
                         const NodeIdVariant& destination_id) -> nb::dict {
            return graph_result_to_dict(self.bmssp(origin_id, destination_id));
        }, nb::arg("origin_id"), nb::arg("destination_id"),
           "Find shortest path using BMSSP algorithm (falls back to Dijkstra in C++ backend)")

        // Cached shortest path
        .def("cached_shortest_path", [](Graph& self,
                                        const NodeIdVariant& origin_id,
                                        const NodeIdVariant& destination_id,
                                        bool length_only) -> nb::dict {
            return graph_result_to_dict(
                self.cached_shortest_path(origin_id, destination_id, length_only)
            );
        }, nb::arg("origin_id"), nb::arg("destination_id"),
           nb::arg("length_only") = false,
           "Get shortest path using cached tree if available")

        // Contraction Hierarchies
        .def("create_contraction_hierarchy", &Graph::create_contraction_hierarchy,
             nb::arg("heuristic_fn") = nullptr, nb::arg("settled_limit") = 50,
             "Create a Contraction Hierarchies (CH) graph")
        .def("contraction_hierarchy", [](Graph& self, const NodeIdVariant& origin_id, const NodeIdVariant& destination_id, bool length_only) -> nb::dict {
            return graph_result_to_dict(self.contraction_hierarchy(origin_id, destination_id, length_only));
        }, nb::arg("origin_id"), nb::arg("destination_id"), nb::arg("length_only") = false,
           "Get shortest path using Contraction Hierarchies")

        // Transit Node Routing
        .def("create_tnr_hierarchy", &Graph::create_tnr_hierarchy,
             nb::arg("num_transit_nodes") = 100, nb::arg("heuristic_fn") = nullptr, nb::arg("settled_limit") = 50,
             "Create a Transit Node Routing (TNR) graph")
        .def("set_tnr_graph", &Graph::set_tnr_graph, nb::arg("tnr_graph"),
             "Set the TNRGraph object for the graph")
        .def("tnr", [](Graph& self, const NodeIdVariant& origin_id, const NodeIdVariant& destination_id, bool length_only) -> nb::dict {
            return graph_result_to_dict(self.tnr(origin_id, destination_id, length_only));
        }, nb::arg("origin_id"), nb::arg("destination_id"), nb::arg("length_only") = false,
           "Get shortest path using Transit Node Routing");

    // CHGraph class
    nb::class_<CHGraph>(m, "CHGraph")
        .def(nb::init<const std::vector<std::unordered_map<int, double>>&, int, std::function<double(CHGraph*, int)>>(),
             nb::arg("graph"), nb::arg("settled_limit") = 50, nb::arg("heuristic_fn") = nullptr,
             "Initialize and preprocess a CHGraph")
        .def(nb::init<int, const std::vector<int>&, 
                      const std::vector<std::unordered_map<int, double>>&,
                      const std::vector<std::unordered_map<int, double>>&,
                      const std::unordered_map<std::pair<int, int>, int, pair_hash>&,
                      const std::optional<std::vector<std::unordered_map<int, double>>>&,
                      int>(),
             nb::arg("nodes_count"), nb::arg("ranks"), nb::arg("forward_graph"),
             nb::arg("backward_graph"), nb::arg("shortcuts"), nb::arg("original_graph"),
             nb::arg("settled_limit") = 50,
             "Initialize a CHGraph from pre-calculated data")
        .def("add_node", &CHGraph::add_node,
             nb::arg("node_dict") = std::unordered_map<int, double>{},
             nb::arg("symmetric") = false,
             "Add a node to the graph")
        .def("search", [](CHGraph& self, const NodeIdVariant& origin_id, const NodeIdVariant& destination_id, bool length_only) -> nb::dict {
            return graph_result_to_dict(self.search(origin_id, destination_id, length_only));
        }, nb::arg("origin_id"), nb::arg("destination_id"), nb::arg("length_only") = false,
           "Perform a bidirectional search on the CH")
        .def("get_shortest_path", [](CHGraph& self, const NodeIdVariant& origin_id, const NodeIdVariant& destination_id, bool length_only) -> nb::dict {
            return graph_result_to_dict(self.get_shortest_path(origin_id, destination_id, length_only));
        }, nb::arg("origin_id"), nb::arg("destination_id"), nb::arg("length_only") = false,
           "Wrapper for search to match scgraph naming conventions")
        .def_prop_ro("nodes_count", &CHGraph::get_nodes_count)
        .def_prop_ro("ranks", &CHGraph::get_ranks)
        .def_prop_ro("forward_graph", &CHGraph::get_forward_graph)
        .def_prop_ro("backward_graph", &CHGraph::get_backward_graph)
        .def_prop_ro("shortcuts", [](const CHGraph& self) {
            nb::dict d;
            for (const auto& [key, via_node_id] : self.get_shortcuts()) {
                d[nb::cast(key)] = via_node_id;
            }
            return d;
        })
        .def_prop_ro("original_graph", &CHGraph::get_original_graph)
        .def_prop_ro("graph", &CHGraph::get_original_graph)
        .def("save_as_chjson", [](const CHGraph& self, const std::string& filename) {
            if (filename.size() < 7 || filename.substr(filename.size() - 7) != ".chjson") {
                throw std::invalid_argument("Filename must end with .chjson");
            }

            nb::dict d;
            d["type"] = "CHGraph";
            d["nodes_count"] = self.get_nodes_count();
            d["ranks"] = self.get_ranks();
            d["forward_graph"] = self.get_forward_graph();
            d["backward_graph"] = self.get_backward_graph();
            
            nb::dict shortcuts_str;
            for (const auto& [key, via_node_id] : self.get_shortcuts()) {
                std::string key_str = "(" + std::to_string(key.first) + ", " + std::to_string(key.second) + ")";
                shortcuts_str[nb::cast(key_str)] = via_node_id;
            }
            d["shortcuts"] = shortcuts_str;
            d["original_graph"] = self.get_original_graph();

            nb::module_ json = nb::module_::import_("json");
            nb::module_ builtins = nb::module_::import_("builtins");
            nb::object f = builtins.attr("open")(filename, "w");
            json.attr("dump")(d, f);
            f.attr("close")();
        }, nb::arg("filename"), "Save the current CHGraph as a JSON file.")
        .def_static("load_from_chjson", [](const std::string& filename) {
            if (filename.size() < 7 || filename.substr(filename.size() - 7) != ".chjson") {
                throw std::invalid_argument("Filename must end with .chjson");
            }

            nb::module_ json = nb::module_::import_("json");
            nb::module_ builtins = nb::module_::import_("builtins");
            nb::object f = builtins.attr("open")(filename, "r");
            nb::dict data = nb::cast<nb::dict>(json.attr("load")(f));
            f.attr("close")();

            if (!data.contains("type") || nb::cast<std::string>(data["type"]) != "CHGraph") {
                throw std::invalid_argument("JSON file is not a valid CHGraph.");
            }

            int nodes_count = nb::cast<int>(data["nodes_count"]);
            std::vector<int> ranks = nb::cast<std::vector<int>>(data["ranks"]);
            
            auto convert_graph = [](nb::list raw_graph) {
                std::vector<std::unordered_map<int, double>> graph;
                for (auto item : raw_graph) {
                    nb::dict d = nb::cast<nb::dict>(item);
                    std::unordered_map<int, double> node_map;
                    for (auto [k, v] : d) {
                        node_map[std::stoi(nb::cast<std::string>(k))] = nb::cast<double>(v);
                    }
                    graph.push_back(node_map);
                }
                return graph;
            };

            std::vector<std::unordered_map<int, double>> forward_graph = convert_graph(nb::cast<nb::list>(data["forward_graph"]));
            std::vector<std::unordered_map<int, double>> backward_graph = convert_graph(nb::cast<nb::list>(data["backward_graph"]));

            nb::dict shortcuts_raw = nb::cast<nb::dict>(data["shortcuts"]);
            std::unordered_map<std::pair<int, int>, int, pair_hash> shortcuts;
            for (auto [key, via_node_id] : shortcuts_raw) {
                std::string key_str = nb::cast<std::string>(key);
                // Parse "(origin_id, destination_id)" or "(origin_id,destination_id)"
                size_t comma = key_str.find(',');
                int shortcut_origin_id = std::stoi(key_str.substr(1, comma - 1));
                size_t start_dest = comma + 1;
                while (start_dest < key_str.size() && (key_str[start_dest] == ' ' || key_str[start_dest] == '\t')) start_dest++;
                int shortcut_destination_id = std::stoi(key_str.substr(start_dest, key_str.size() - start_dest - 1));
                shortcuts[{shortcut_origin_id, shortcut_destination_id}] = nb::cast<int>(via_node_id);
            }

            std::optional<std::vector<std::unordered_map<int, double>>> original_graph = std::nullopt;
            if (data.contains("original_graph") && !data["original_graph"].is_none()) {
                original_graph = convert_graph(nb::cast<nb::list>(data["original_graph"]));
            }

            return CHGraph(nodes_count, ranks, forward_graph, backward_graph, shortcuts, original_graph);
            }, nb::arg("filename"), "Load a CHGraph from a JSON file.");

            // TNRGraph class
            nb::class_<TNRGraph, CHGraph>(m, "TNRGraph")
                .def(nb::init<const std::vector<std::unordered_map<int, double>>&, int, int, std::function<double(CHGraph*, int)>>(),
                     nb::arg("graph"), nb::arg("settled_limit") = 50, nb::arg("num_transit_nodes") = 100, nb::arg("heuristic_fn") = nullptr,
                     "Initialize and preprocess a TNRGraph")
                .def(nb::init<int, const std::vector<int>&, 
                      const std::vector<std::unordered_map<int, double>>&,
                      const std::vector<std::unordered_map<int, double>>&,
                      const std::unordered_map<std::pair<int, int>, int, pair_hash>&,
                      const std::optional<std::vector<std::unordered_map<int, double>>>&,
                      const std::set<int>&,
                      const std::unordered_map<std::pair<int, int>, double, pair_hash>&,
                      const std::vector<std::unordered_map<int, double>>&,
                      const std::vector<std::unordered_map<int, double>>&,
                      int>(),
              nb::arg("nodes_count"), nb::arg("ranks"), nb::arg("forward_graph"),
              nb::arg("backward_graph"), nb::arg("shortcuts"), nb::arg("original_graph"),
              nb::arg("transit_nodes"), nb::arg("distance_table"),
              nb::arg("forward_access_nodes"), nb::arg("backward_access_nodes"),
              nb::arg("settled_limit") = 50,
              "Initialize a TNRGraph from pre-calculated data")
            .def("search", [](TNRGraph& self, const NodeIdVariant& origin_id, const NodeIdVariant& destination_id, bool length_only) -> nb::dict {
            return graph_result_to_dict(self.search(origin_id, destination_id, length_only));
            }, nb::arg("origin_id"), nb::arg("destination_id"), nb::arg("length_only") = false,
            "Perform a bidirectional search on the TNR")
            .def("get_shortest_path", [](TNRGraph& self, const NodeIdVariant& origin_id, const NodeIdVariant& destination_id, bool length_only) -> nb::dict {
            return graph_result_to_dict(self.get_shortest_path(origin_id, destination_id, length_only));
            }, nb::arg("origin_id"), nb::arg("destination_id"), nb::arg("length_only") = false,
            "Wrapper for search to match scgraph naming conventions")
            .def_prop_ro("transit_nodes", &TNRGraph::get_transit_nodes)
            .def_prop_ro("distance_table", [](const TNRGraph& self) {
            nb::dict d;
            for (const auto& [key, dist] : self.get_distance_table()) {
                d[nb::cast(key)] = dist;
            }
            return d;
            })
            .def_prop_ro("forward_access_nodes", &TNRGraph::get_forward_access_nodes)
            .def_prop_ro("backward_access_nodes", &TNRGraph::get_backward_access_nodes)
            .def("save_as_tnrjson", [](const TNRGraph& self, const std::string& filename) {
                if (filename.size() < 8 || filename.substr(filename.size() - 8) != ".tnrjson") {
                    throw std::invalid_argument("Filename must end with .tnrjson");
                }

                nb::dict d;
                d["type"] = "TNRGraph";
                d["nodes_count"] = self.get_nodes_count();

                nb::list t_nodes;
                for (int node : self.get_transit_nodes()) {
                    t_nodes.append(node);
                }
                d["transit_nodes"] = t_nodes;

                nb::dict dist_table_str;
                for (const auto& [key, dist] : self.get_distance_table()) {
                    std::string key_str = "(" + std::to_string(key.first) + "," + std::to_string(key.second) + ")";
                    dist_table_str[nb::cast(key_str)] = dist;
                }
                d["distance_table"] = dist_table_str;

                auto convert_access_nodes = [](const std::vector<std::unordered_map<int, double>>& access_nodes) {
                    nb::list access_str;
                    for (const auto& node_map : access_nodes) {
                        nb::dict d_map;
                        for (const auto& [k, v] : node_map) {
                            d_map[nb::cast(std::to_string(k))] = v;
                        }
                        access_str.append(d_map);
                    }
                    return access_str;
                };

                d["forward_access_nodes"] = convert_access_nodes(self.get_forward_access_nodes());
                d["backward_access_nodes"] = convert_access_nodes(self.get_backward_access_nodes());

                nb::dict ch_data;
                ch_data["ranks"] = self.get_ranks();
                ch_data["forward_graph"] = self.get_forward_graph();
                ch_data["backward_graph"] = self.get_backward_graph();

                nb::dict shortcuts_str;
                for (const auto& [key, via_node_id] : self.get_shortcuts()) {
                    std::string key_str = "(" + std::to_string(key.first) + ", " + std::to_string(key.second) + ")";
                    shortcuts_str[nb::cast(key_str)] = via_node_id;
                }
                ch_data["shortcuts"] = shortcuts_str;
                ch_data["original_graph"] = self.get_original_graph();
                ch_data["nodes_count"] = self.get_nodes_count();

                d["ch_data"] = ch_data;

                nb::module_ json = nb::module_::import_("json");
                nb::module_ builtins = nb::module_::import_("builtins");
                nb::object f = builtins.attr("open")(filename, "w");
                json.attr("dump")(d, f);
                f.attr("close")();
            }, nb::arg("filename"), "Save the current TNRGraph as a JSON file.")
            .def_static("load_from_tnrjson", [](const std::string& filename) {
                if (filename.size() < 8 || filename.substr(filename.size() - 8) != ".tnrjson") {
                    throw std::invalid_argument("Filename must end with .tnrjson");
                }

                nb::module_ json = nb::module_::import_("json");
                nb::module_ builtins = nb::module_::import_("builtins");
                nb::object f = builtins.attr("open")(filename, "r");
                nb::dict data = nb::cast<nb::dict>(json.attr("load")(f));
                f.attr("close")();

                if (!data.contains("type") || nb::cast<std::string>(data["type"]) != "TNRGraph") {
                    throw std::invalid_argument("JSON file is not a valid TNRGraph.");
                }

                int nodes_count = nb::cast<int>(data["nodes_count"]);

                std::set<int> transit_nodes;
                for (auto item : nb::cast<nb::list>(data["transit_nodes"])) {
                    transit_nodes.insert(nb::cast<int>(item));
                }

                std::unordered_map<std::pair<int, int>, double, pair_hash> distance_table;
                for (auto [key, dist] : nb::cast<nb::dict>(data["distance_table"])) {
                    std::string key_str = nb::cast<std::string>(key);
                    size_t comma = key_str.find(',');
                    int t_f = std::stoi(key_str.substr(1, comma - 1));
                    int t_b = std::stoi(key_str.substr(comma + 1, key_str.size() - comma - 2));
                    distance_table[{t_f, t_b}] = nb::cast<double>(dist);
                }

                auto convert_access_nodes = [](nb::list access_str) {
                    std::vector<std::unordered_map<int, double>> access_nodes;
                    for (auto item : access_str) {
                        nb::dict d = nb::cast<nb::dict>(item);
                        std::unordered_map<int, double> node_map;
                        for (auto [k, v] : d) {
                            node_map[std::stoi(nb::cast<std::string>(k))] = nb::cast<double>(v);
                        }
                        access_nodes.push_back(node_map);
                    }
                    return access_nodes;
                };

                std::vector<std::unordered_map<int, double>> forward_access_nodes = convert_access_nodes(nb::cast<nb::list>(data["forward_access_nodes"]));
                std::vector<std::unordered_map<int, double>> backward_access_nodes = convert_access_nodes(nb::cast<nb::list>(data["backward_access_nodes"]));

                nb::dict ch_data = nb::cast<nb::dict>(data["ch_data"]);
                std::vector<int> ranks = nb::cast<std::vector<int>>(ch_data["ranks"]);

                auto convert_graph = [](nb::list raw_graph) {
                    std::vector<std::unordered_map<int, double>> graph;
                    for (auto item : raw_graph) {
                        nb::dict d = nb::cast<nb::dict>(item);
                        std::unordered_map<int, double> node_map;
                        for (auto [k, v] : d) {
                            node_map[std::stoi(nb::cast<std::string>(k))] = nb::cast<double>(v);
                        }
                        graph.push_back(node_map);
                    }
                    return graph;
                };

                std::vector<std::unordered_map<int, double>> forward_graph = convert_graph(nb::cast<nb::list>(ch_data["forward_graph"]));
                std::vector<std::unordered_map<int, double>> backward_graph = convert_graph(nb::cast<nb::list>(ch_data["backward_graph"]));

                nb::dict shortcuts_raw = nb::cast<nb::dict>(ch_data["shortcuts"]);
                std::unordered_map<std::pair<int, int>, int, pair_hash> shortcuts;
                for (auto [key, via_node_id] : shortcuts_raw) {
                    std::string key_str = nb::cast<std::string>(key);
                    size_t comma = key_str.find(',');
                    int shortcut_origin_id = std::stoi(key_str.substr(1, comma - 1));
                    size_t start_dest = comma + 1;
                    while (start_dest < key_str.size() && (key_str[start_dest] == ' ' || key_str[start_dest] == '\t')) start_dest++;
                    int shortcut_destination_id = std::stoi(key_str.substr(start_dest, key_str.size() - start_dest - 1));
                    shortcuts[{shortcut_origin_id, shortcut_destination_id}] = nb::cast<int>(via_node_id);
                }

                std::optional<std::vector<std::unordered_map<int, double>>> original_graph = std::nullopt;
                if (ch_data.contains("original_graph") && !ch_data["original_graph"].is_none()) {
                    original_graph = convert_graph(nb::cast<nb::list>(ch_data["original_graph"]));
                }

                return TNRGraph(nodes_count, ranks, forward_graph, backward_graph, shortcuts, original_graph, transit_nodes, distance_table, forward_access_nodes, backward_access_nodes);
            }, nb::arg("filename"), "Load a TNRGraph from a JSON file.");
            }