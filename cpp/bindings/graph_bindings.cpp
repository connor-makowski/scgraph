#include <nanobind/nanobind.h>
#include <nanobind/stl/vector.h>
#include <nanobind/stl/pair.h>
#include <nanobind/stl/unordered_map.h>
#include <nanobind/stl/set.h>
#include <nanobind/stl/optional.h>
#include <nanobind/stl/variant.h>
#include <nanobind/stl/function.h>
#include <nanobind/stl/string.h>
#include <nanobind/operators.h>
#include "../src/graph.hpp"

namespace nb = nanobind;
using namespace nb::literals;

NB_MODULE(graph_cpp, m) {
    // GraphResult struct
    nb::class_<GraphResult>(m, "GraphResult")
        .def_ro("path", &GraphResult::path)
        .def_ro("length", &GraphResult::length)
        .def("__repr__", [](const GraphResult& r) {
            std::string path_str = "[";
            for (size_t i = 0; i < r.path.size(); ++i) {
                if (i > 0) path_str += ", ";
                path_str += std::to_string(r.path[i]);
            }
            path_str += "]";
            return "GraphResult(path=" + path_str + ", length=" + std::to_string(r.length) + ")";
        }, "Representation")
        .def("__str__", [](const GraphResult& r) {
            std::string path_str = "[";
            for (size_t i = 0; i < r.path.size(); ++i) {
                if (i > 0) path_str += ", ";
                path_str += std::to_string(r.path[i]);
            }
            path_str += "]";
            return "{'path': " + path_str + ", 'length': " + std::to_string(r.length) + "}";
        }, "String representation")
        .def("to_dict", [](const GraphResult& r) {
            nb::dict d;
               d["path"] = r.path;
               d["length"] = r.length;
               return d;
        }, "Convert to dictionary")
        .def("__getitem__", [](const GraphResult& r,
                               const std::string& key) -> nb::object {
            if (key == "path")
                return nb::cast(r.path);
            if (key == "length")
                return nb::cast(r.length);
            throw nb::key_error(("Invalid key: " + key).c_str());
        }, "Get item by key");


    // TreeData struct
    nb::class_<TreeData>(m, "TreeData")
        .def_ro("origin_id", &TreeData::origin_id)
        .def_ro("predecessors", &TreeData::predecessors)
        .def_ro("distance_matrix", &TreeData::distance_matrix);

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
        .def("get_shortest_path_tree", &Graph::get_shortest_path_tree,
             nb::arg("origin_id"),
             "Calculate the shortest path tree using Dijkstra's algorithm")
        .def("get_tree_path", &Graph::get_tree_path,
             nb::arg("origin_id"), nb::arg("destination_id"), 
             nb::arg("tree_data"), nb::arg("length_only") = false,
             "Get the path from origin to destination using tree data")
        
        // Shortest path algorithms
        .def("dijkstra", &Graph::dijkstra,
             nb::arg("origin_id"), nb::arg("destination_id"),
             "Find shortest path using Dijkstra's algorithm")
        .def("dijkstra_negative", &Graph::dijkstra_negative,
             nb::arg("origin_id"), nb::arg("destination_id"),
             nb::arg("cycle_check_iterations") = nb::none(),
             "Find shortest path using Dijkstra with negative cycle detection")
        .def("a_star", &Graph::a_star,
             nb::arg("origin_id"), nb::arg("destination_id"),
             nb::arg("heuristic_fn") = nullptr,
             "Find shortest path using A* algorithm with optional heuristic")
        .def("bellman_ford", &Graph::bellman_ford,
             nb::arg("origin_id"), nb::arg("destination_id"),
             "Find shortest path using Bellman-Ford algorithm")
        .def("bmssp", &Graph::bmssp,
             nb::arg("origin_id"), nb::arg("destination_id"),
             "Find shortest path using BMSSP algorithm (not supported in C++ backend, falls back to Dijkstra)")
        // Cached shortest path
        .def("get_set_cached_shortest_path", &Graph::get_set_cached_shortest_path,
             nb::arg("origin_id"), nb::arg("destination_id"),
             nb::arg("length_only") = false,
             "Get shortest path using cached tree if available");
}