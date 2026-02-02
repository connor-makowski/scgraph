# C++ Graph Library

A C++20 translation of the Python Graph library for shortest path algorithms and graph manipulation.

## Features

### Graph Algorithms
- **Dijkstra's Algorithm**: Standard shortest path for non-negative weights
- **Dijkstra (Negative-aware)**: Modified Dijkstra with negative cycle detection
- **A* Algorithm**: Heuristic-guided shortest path search
- **Bellman-Ford**: Shortest path with negative edge support

### Graph Operations
- Add/remove nodes
- Add/remove edges (with optional symmetry)
- Graph validation (symmetry and connectivity checks)
- Cached shortest path tree computations

### Data Structures
- **Graph**: Adjacency list representation using `std::vector<std::unordered_map<int, double>>`
- **GraphResult**: Contains path (vector of node IDs) and length
- **TreeData**: Shortest path tree with predecessors and distance matrix

## Building

### Using g++ directly:
```bash
g++ -std=c++20 -c graph.cpp -o graph.o
g++ -std=c++20 your_file.cpp graph.o -o your_program
```

### Using CMake:
```bash
mkdir build && cd build
cmake ..
make
```

## Usage Example

```cpp
#include "graph.hpp"

int main() {
    // Create graph
    std::vector<std::unordered_map<int, double>> graph_data = {
        {{1, 1.0}, {2, 4.0}},           // Node 0
        {{0, 1.0}, {2, 2.0}, {3, 5.0}}, // Node 1
        {{0, 4.0}, {1, 2.0}, {3, 1.0}}, // Node 2
        {{1, 5.0}, {2, 1.0}}            // Node 3
    };
    
    Graph g(graph_data);
    
    // Find shortest path
    auto result = g.dijkstra(0, 3);
    // result.path = [0, 1, 2, 3]
    // result.length = 4.0
    
    // Multiple origins
    std::set<int> origins = {0, 1};
    auto result2 = g.dijkstra(origins, 3);
    
    // A* with heuristic
    auto heuristic = [](int from, int to) -> double {
        return std::abs(to - from) * 0.5;
    };
    auto result3 = g.a_star(0, 3, heuristic);
    
    // Add node
    int new_id = g.add_node({{3, 2.0}}, true);
    
    // Add edge
    g.add_edge(0, new_id, 3.0, true);
    
    // Remove edge
    auto removed = g.remove_edge(0, new_id);
    
    // Remove node
    auto edges = g.remove_node(true);
    
    return 0;
}
```

## API Reference

### Constructor
```cpp
Graph(const std::vector<std::unordered_map<int, double>>& graph_data, bool validate = false)
```

### Shortest Path Algorithms
```cpp
GraphResult dijkstra(const std::variant<int, std::set<int>>& origin_id, int destination_id)
GraphResult dijkstra_negative(const std::variant<int, std::set<int>>& origin_id, int destination_id, 
                              std::optional<int> cycle_check_iterations = std::nullopt)
GraphResult a_star(const std::variant<int, std::set<int>>& origin_id, int destination_id,
                   std::function<double(int, int)> heuristic_fn = nullptr)
GraphResult bellman_ford(const std::variant<int, std::set<int>>& origin_id, int destination_id)
```

### Tree Operations
```cpp
TreeData get_shortest_path_tree(const std::variant<int, std::set<int>>& origin_id)
GraphResult get_tree_path(int origin_id, int destination_id, const TreeData& tree_data, bool length_only = false)
GraphResult get_set_cached_shortest_path(int origin_id, int destination_id, bool length_only = false)
```

### Graph Modification
```cpp
int add_node(const std::unordered_map<int, double>& node_dict = {}, bool symmetric = false)
void add_edge(int origin_id, int destination_id, double distance, bool symmetric = false)
std::unordered_map<int, double> remove_node(bool symmetric_node = false)
std::optional<double> remove_edge(int origin_id, int destination_id, bool symmetric = false)
```

### Validation & Utility
```cpp
void validate(bool check_symmetry = true, bool check_connected = true)
void reset_cache()
const std::unordered_map<int, double>& get(int idx) const
int size() const
```

## Key Differences from Python Implementation

1. **Type Safety**: Uses `std::variant<int, std::set<int>>` for origin_id instead of duck typing
2. **Memory Management**: Automatic via RAII and STL containers
3. **Error Handling**: Uses exceptions instead of assertions
4. **Optional Values**: Uses `std::optional` for nullable returns
5. **Heuristic Functions**: Uses `std::function<double(int, int)>` for A* heuristics

## Nanobind Integration

The class-based design makes it straightforward to create Python bindings with nanobind:

```cpp
#include <nanobind/nanobind.h>
#include <nanobind/stl/vector.h>
#include <nanobind/stl/unordered_map.h>
#include <nanobind/stl/set.h>
#include <nanobind/stl/optional.h>
#include <nanobind/stl/variant.h>
#include "graph.hpp"

namespace nb = nanobind;

NB_MODULE(graph_ext, m) {
    nb::class_<GraphResult>(m, "GraphResult")
        .def_ro("path", &GraphResult::path)
        .def_ro("length", &GraphResult::length);
    
    nb::class_<Graph>(m, "Graph")
        .def(nb::init<const std::vector<std::unordered_map<int, double>>&, bool>(),
             nb::arg("graph_data"), nb::arg("validate") = false)
        .def("dijkstra", &Graph::dijkstra)
        .def("add_node", &Graph::add_node, 
             nb::arg("node_dict") = std::unordered_map<int, double>{}, 
             nb::arg("symmetric") = false)
        .def("add_edge", &Graph::add_edge)
        .def("remove_node", &Graph::remove_node)
        .def("remove_edge", &Graph::remove_edge)
        .def("size", &Graph::size)
        // ... add more methods as needed
        ;
}
```

## License

Same as the original Python implementation.
