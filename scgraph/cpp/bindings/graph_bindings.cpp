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
#include <string>
#include <stdexcept>
#include <memory>
#include "../src/graph.hpp"
#include "../src/contraction_hierarchies.hpp"
#include "../src/transit_node_routing.hpp"

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

        .def("dijkstra_buckets", [](Graph& self,
                                    const std::variant<int, std::set<int>>& origin_id,
                                    int destination_id,
                                    std::optional<double> max_edge_weight) -> nb::dict {
            return graph_result_to_dict(self.dijkstra_buckets(origin_id, destination_id, max_edge_weight));
        }, nb::arg("origin_id"), nb::arg("destination_id"),
           nb::arg("max_edge_weight") = nb::none(),
           "Find shortest path using Dijkstra with buckets")

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
        .def("cached_shortest_path", [](Graph& self,
                                        int origin_id,
                                        int destination_id,
                                        bool length_only) -> nb::dict {
            return graph_result_to_dict(
                self.cached_shortest_path(origin_id, destination_id, length_only)
            );
        }, nb::arg("origin_id"), nb::arg("destination_id"),
           nb::arg("length_only") = false,
           "Get shortest path using cached tree if available")

        // Contraction Hierarchies
        .def("create_contraction_hierarchy", &Graph::create_contraction_hierarchy,
             nb::arg("heuristic_fn") = nullptr,
             "Create a Contraction Hierarchies (CH) graph")
        .def("contraction_hierarchy", [](Graph& self, int origin_id, int destination_id) -> nb::dict {
            return graph_result_to_dict(self.contraction_hierarchy(origin_id, destination_id));
        }, nb::arg("origin_id"), nb::arg("destination_id"),
           "Get shortest path using Contraction Hierarchies")

        // Transit Node Routing
        .def("create_tnr_hierarchy", &Graph::create_tnr_hierarchy,
             nb::arg("num_transit_nodes") = 100, nb::arg("heuristic_fn") = nullptr,
             "Create a Transit Node Routing (TNR) graph")
        .def("set_tnr_graph", &Graph::set_tnr_graph, nb::arg("tnr_graph"),
             "Set the TNRGraph object for the graph")
        .def("tnr", [](Graph& self, int origin_id, int destination_id, bool length_only) -> nb::dict {
            return graph_result_to_dict(self.tnr(origin_id, destination_id, length_only));
        }, nb::arg("origin_id"), nb::arg("destination_id"), nb::arg("length_only") = false,
           "Get shortest path using Transit Node Routing");

    // CHGraph class
    nb::class_<CHGraph>(m, "CHGraph")
        .def(nb::init<const std::vector<std::unordered_map<int, double>>&, std::function<double(CHGraph*, int)>>(),
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
                .def(nb::init<const std::vector<std::unordered_map<int, double>>&, int, std::function<double(CHGraph*, int)>>(),
                     nb::arg("graph"), nb::arg("num_transit_nodes") = 100, nb::arg("heuristic_fn") = nullptr,
                     "Initialize and preprocess a TNRGraph")
                .def(nb::init<int, const std::vector<int>&, 
 
                      const std::vector<std::unordered_map<int, double>>&,
                      const std::vector<std::unordered_map<int, double>>&,
                      const std::unordered_map<std::pair<int, int>, int, pair_hash>&,
                      const std::optional<std::vector<std::unordered_map<int, double>>>&,
                      const std::set<int>&,
                      const std::unordered_map<std::pair<int, int>, double, pair_hash>&,
                      const std::vector<std::unordered_map<int, double>>&,
                      const std::vector<std::unordered_map<int, double>>&>(),
             nb::arg("nodes_count"), nb::arg("ranks"), nb::arg("forward_graph"),
             nb::arg("backward_graph"), nb::arg("shortcuts"), nb::arg("original_graph"),
             nb::arg("transit_nodes"), nb::arg("distance_table"),
             nb::arg("forward_access_nodes"), nb::arg("backward_access_nodes"),
             "Initialize a TNRGraph from pre-calculated data")
            .def("search", [](TNRGraph& self, int origin_id, int destination_id, bool length_only) -> nb::dict {
            return graph_result_to_dict(self.search(origin_id, destination_id, length_only));
            }, nb::arg("origin_id"), nb::arg("destination_id"), nb::arg("length_only") = false,
            "Perform a bidirectional search on the TNR")
            .def("get_shortest_path", [](TNRGraph& self, int origin_id, int destination_id, bool length_only) -> nb::dict {
            return graph_result_to_dict(self.search(origin_id, destination_id, length_only));
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