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

// Helper function to convert GraphResult to dict
static nb::dict graph_result_to_dict(const GraphResult& r) {
    nb::dict d;
    d["path"] = r.path;
    d["length"] = r.length;
    return d;
}
// Helper function to convert TreeData to dict
static nb::dict tree_result_to_dict(const TreeData& t) {
    nb::dict d;
    d["origin_id"] = t.origin_id;
    d["predecessors"] = t.predecessors;
    d["distance_matrix"] = t.distance_matrix;
    return d;
}
// Helper function to convert dict to TreeData
static TreeData dict_to_tree_result(const nb::dict& d) {
    return TreeData(
        nb::cast<int>(d["origin_id"]),
        nb::cast<std::vector<int>>(d["predecessors"]),
        nb::cast<std::vector<double>>(d["distance_matrix"])
    );
}

NB_MODULE(cpp, m) {
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
        
        // IO for cache - get returns a list of dicts, set accepts a list of dicts (or None for empty entries)
        .def("get_cache", [](Graph& self) {
            nb::list cache_list;
            for (const auto& tree_data : self.get_cache()) {
                cache_list.append(tree_result_to_dict(tree_data));
            }
            return cache_list;
        }, "Get the cached shortest path trees")
        .def("set_cache", [](Graph& self, const nb::list& new_cache) {
            std::vector<TreeData> cache_vector;
            cache_vector.resize(new_cache.size());
            for (size_t i = 0; i < new_cache.size(); ++i) {
                const auto& item = new_cache[i];
               // Only push valid items. Leave the others null (default-constructed) to be handled by the get_tree_path function.
                if (!item.is_none()) {
                    cache_vector[i] = dict_to_tree_result(nb::cast<nb::dict>(item));
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
        .def("get_shortest_path_tree", &Graph::get_shortest_path_tree,
             nb::arg("origin_id"),
             "Calculate the shortest path tree using Dijkstra's algorithm")
        .def("get_tree_path", [](Graph& self, int origin_id, int destination_id, 
                                  const TreeData& tree_data, bool length_only) -> nb::dict {
            return graph_result_to_dict(self.get_tree_path(origin_id, destination_id, tree_data, length_only));
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
            return graph_result_to_dict(self.dijkstra_negative(origin_id, destination_id, cycle_check_iterations));
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
           "Find shortest path using BMSSP algorithm (not supported in C++ backend, falls back to Dijkstra)")
        
        // Cached shortest path
        .def("get_set_cached_shortest_path", [](Graph& self,
                                                 int origin_id,
                                                 int destination_id,
                                                 bool length_only) -> nb::dict {
            return graph_result_to_dict(self.get_set_cached_shortest_path(origin_id, destination_id, length_only));
        }, nb::arg("origin_id"), nb::arg("destination_id"),
           nb::arg("length_only") = false,
           "Get shortest path using cached tree if available");
}