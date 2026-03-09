#include <nanobind/nanobind.h>
#include <nanobind/stl/vector.h>
#include <nanobind/stl/pair.h>
#include <nanobind/stl/unordered_map.h>
#include <nanobind/stl/set.h>
#include <nanobind/stl/optional.h>
#include <nanobind/stl/variant.h>
#include <nanobind/stl/function.h>
#include <nanobind/stl/string.h>
#include <nanobind/stl/tuple.h>
#include <nanobind/stl/shared_ptr.h>
#include <nanobind/operators.h>
#include "../src/graph.hpp"
#include "../src/ch_graph.hpp"

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
        nb::cast<std::variant<int, std::set<int>>>(d["origin_id"]),
        nb::cast<std::vector<int>>(d["predecessors"]),
        nb::cast<std::vector<double>>(d["distance_matrix"])
    };
}

// Returns true if a TreeData entry is the default-constructed sentinel (not yet computed)
static bool is_empty_tree_data(const TreeData& t) {
    return t.predecessors.empty();
}

NB_MODULE(cpp, m) {
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

        // Cache IO
        // get_cache: returns a list matching the Python convention where uncached
        // entries are 0 (int) and cached entries are dicts
        .def("get_cache", [](Graph& self) {
            nb::list cache_list;
            for (const auto& tree_data : self.get_cache()) {
                if (is_empty_tree_data(tree_data)) {
                    cache_list.append(nb::int_(0));
                } else {
                    cache_list.append(tree_data_to_dict(tree_data));
                }
            }
            return cache_list;
        }, "Get the cached shortest path trees")
        // set_cache: accepts a list where entries are either 0 (int) or dicts
        .def("set_cache", [](Graph& self, const nb::list& new_cache) {
            std::vector<TreeData> cache_vector(new_cache.size());
            for (size_t i = 0; i < new_cache.size(); ++i) {
                const auto& item = new_cache[i];
                // Leave default-constructed (empty) TreeData as sentinel for uncached entries
                if (!item.is_none() && !nb::isinstance<nb::int_>(item)) {
                    cache_vector[i] = dict_to_tree_data(nb::cast<nb::dict>(item));
                }
            }
            self.set_cache(cache_vector);
        }, "Set the cached shortest path trees")

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
                                          const std::variant<int, std::set<int>>& origin_id) -> nb::dict {
            return tree_data_to_dict(self.get_shortest_path_tree(origin_id));
        }, nb::arg("origin_id"),
           "Calculate the shortest path tree using Dijkstra's algorithm")

        // get_tree_path: accepts a dict (as returned by get_shortest_path_tree) and returns a dict
        .def("get_tree_path", [](Graph& self, int origin_id, int destination_id,
                                  const nb::dict& tree_data, bool length_only) -> nb::dict {
            return graph_result_to_dict(
                self.get_tree_path(origin_id, destination_id, dict_to_tree_data(tree_data), length_only)
            );
        }, nb::arg("origin_id"), nb::arg("destination_id"),
           nb::arg("tree_data"), nb::arg("length_only") = false,
           "Get the path from origin to destination using tree data")

        // Shortest path algorithms - all return dicts
        .def("dijkstra", [](Graph& self,
                            const std::variant<int, std::set<int>>& origin_id,
                            int destination_id) -> nb::dict {
            return graph_result_to_dict(self.dijkstra(origin_id, destination_id));
        }, nb::arg("origin_id"), nb::arg("destination_id"),
           "Find shortest path using Dijkstra's algorithm")

        .def("dijkstra_negative", [](Graph& self,
                                     const std::variant<int, std::set<int>>& origin_id,
                                     int destination_id,
                                     std::optional<int> cycle_check_iterations) -> nb::dict {
            return graph_result_to_dict(
                self.dijkstra_negative(origin_id, destination_id, cycle_check_iterations)
            );
        }, nb::arg("origin_id"), nb::arg("destination_id"),
           nb::arg("cycle_check_iterations") = nb::none(),
           "Find shortest path using Dijkstra with negative cycle detection")

        .def("a_star", [](Graph& self,
                          const std::variant<int, std::set<int>>& origin_id,
                          int destination_id,
                          std::function<double(int, int)> heuristic_fn) -> nb::dict {
            return graph_result_to_dict(self.a_star(origin_id, destination_id, heuristic_fn));
        }, nb::arg("origin_id"), nb::arg("destination_id"),
           nb::arg("heuristic_fn") = nullptr,
           "Find shortest path using A* algorithm with optional heuristic")

        .def("bellman_ford", [](Graph& self,
                                const std::variant<int, std::set<int>>& origin_id,
                                int destination_id) -> nb::dict {
            return graph_result_to_dict(self.bellman_ford(origin_id, destination_id));
        }, nb::arg("origin_id"), nb::arg("destination_id"),
           "Find shortest path using Bellman-Ford algorithm")

        .def("bmssp", [](Graph& self,
                         const std::variant<int, std::set<int>>& origin_id,
                         int destination_id) -> nb::dict {
            return graph_result_to_dict(self.bmssp(origin_id, destination_id));
        }, nb::arg("origin_id"), nb::arg("destination_id"),
           "Find shortest path using BMSSP algorithm (falls back to Dijkstra in C++ backend)")

        // Cached shortest path
        .def("get_set_cached_shortest_path", [](Graph& self,
                                                 int origin_id,
                                                 int destination_id,
                                                 bool length_only) -> nb::dict {
            return graph_result_to_dict(
                self.get_set_cached_shortest_path(origin_id, destination_id, length_only)
            );
        }, nb::arg("origin_id"), nb::arg("destination_id"),
           nb::arg("length_only") = false,
           "Get shortest path using cached tree if available")

        // Contraction Hierarchies
        .def("create_ch", &Graph::create_ch,
             nb::arg("heuristic_fn") = nullptr,
             "Create a Contraction Hierarchies (CH) graph")
        .def("ch_shortest_path", [](Graph& self, int origin_id, int destination_id) -> nb::dict {
            return graph_result_to_dict(self.ch_shortest_path(origin_id, destination_id));
        }, nb::arg("origin_id"), nb::arg("destination_id"),
           "Get shortest path using Contraction Hierarchies");

    // CHGraph class
    nb::class_<CHGraph>(m, "CHGraph")
        .def(nb::init<const std::vector<std::unordered_map<int, double>>&, std::function<double(int)>>(),
             nb::arg("graph"), nb::arg("heuristic_fn") = nullptr,
             "Initialize and preprocess a CHGraph")
        .def(nb::init<int, const std::vector<int>&, 
                      const std::vector<std::unordered_map<int, double>>&,
                      const std::vector<std::unordered_map<int, double>>&,
                      const std::unordered_map<std::pair<int, int>, int, pair_hash>&,
                      const std::optional<std::vector<std::unordered_map<int, double>>>&>(),
             nb::arg("nodes_count"), nb::arg("ranks"), nb::arg("forward_graph"),
             nb::arg("backward_graph"), nb::arg("shortcuts"), nb::arg("original_graph"),
             "Initialize a CHGraph from pre-calculated data")
        .def("add_node", &CHGraph::add_node,
             nb::arg("node_dict") = std::unordered_map<int, double>{},
             nb::arg("symmetric") = false,
             "Add a node to the graph")
        .def("search", [](CHGraph& self, int origin_id, int destination_id) -> nb::dict {
            return graph_result_to_dict(self.search(origin_id, destination_id));
        }, nb::arg("origin_id"), nb::arg("destination_id"),
           "Perform a bidirectional search on the CH")
        .def("get_shortest_path", [](CHGraph& self, int origin_id, int destination_id) -> nb::dict {
            return graph_result_to_dict(self.get_shortest_path(origin_id, destination_id));
        }, nb::arg("origin_id"), nb::arg("destination_id"),
           "Wrapper for search to match scgraph naming conventions")
        .def_prop_ro("nodes_count", &CHGraph::get_nodes_count)
        .def_prop_ro("ranks", &CHGraph::get_ranks)
        .def_prop_ro("forward_graph", &CHGraph::get_forward_graph)
        .def_prop_ro("backward_graph", &CHGraph::get_backward_graph)
        .def_prop_ro("shortcuts", [](const CHGraph& self) {
            nb::dict d;
            for (const auto& [k, v] : self.get_shortcuts()) {
                d[nb::cast(k)] = v;
            }
            return d;
        })
        .def_prop_ro("original_graph", &CHGraph::get_original_graph)
        .def_prop_ro("graph", &CHGraph::get_original_graph);
}