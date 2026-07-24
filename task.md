# Graph Reduction Implementation & Architecture

This document describes the implementation, architecture, and performance characteristics of the Graph Reduction feature in `scgraph`.

---

## 1. Overview & Goals
The goal of Graph Reduction is to speed up shortest-path queries on large, sparse road or marine networks by bypassing "pass-through" nodes during preprocessing. 

By contracting long chains of single-inflow/single-outflow nodes into direct "shortcut" edges with aggregated weights, we significantly reduce the active node and edge count of the graph. This results in much smaller search spaces and faster query execution times.

---

## 2. Architecture & How It Works

Graph Reduction consists of three main phases: **Preprocessing**, **Query Swapping**, and **Path Expansion**.

```mermaid
graph TD
    A[Original Graph] --> B[reduce()]
    B --> C[Identify Pass-Through Nodes]
    C --> D[Bypass Connections & Weights Summed]
    D --> E[Reduced Graph Saved]
    
    F[Query: Origin -> Dest] --> G{Are endpoints reduced?}
    G -- Yes --> H[prepare_query_graph: Add Temp Connections]
    G -- No --> I[Run Solve on Reduced Graph]
    H --> I
    I --> J[expand_path: Reconstruct full route]
    J --> K[restore_query_graph: Clean up Temp Connections]
```

### A. Preprocessing (`reduce`)
When `.reduce()` is called on a graph object, the graph is analyzed to identify **pass-through** nodes:
1. **Single Outflow Node**: If a node has exactly $1$ outflow and $\ge 1$ inflow, it is classified as a pass-through node.
2. **Double Outflow Node**: If a node has exactly $2$ outflows, and the inflows are a subset of the outflows, it is classified as a pass-through node.
3. **Bypassing**: The algorithm bypasses all pass-through nodes, summing up the edge weights to create direct shortcut connections between non-reduced boundary nodes.
4. **Cache Invalidations**: Any modifications to the graph structure (e.g. calling `add_edge`) automatically invalidate the reduction cache, forcing a rebuild on the next solve.

### B. Query-Specific Swapping (`prepare_query_graph`)
When a routing query is made:
1. If both the origin and destination are non-reduced, the query runs directly on the reduced graph.
2. If either the origin or destination node is a reduced node, it cannot be traversed directly in the reduced graph. In this case, we temporarily update the adjacency of the endpoints to connect them to their nearest non-reduced boundary nodes (outgoing for the origin, incoming for the destination).
3. The query runs on this temporarily modified graph.
4. Immediately after the solve, the original graph state is restored (`restore_query_graph`).

### C. Path Expansion (`expand_path`)
The solve returns a path containing only non-reduced boundary nodes. We map each shortcut edge back to its original list of intermediate pass-through nodes to reconstruct the full, detailed path.

---

## 3. Implementation Details

We split the reduction logic into dedicated files for both the Python and C++ backends:

* **Python Modules**:
  * [scgraph/graph_reducer.py](file:///home/conmak/development/personal/scgraph/scgraph/graph_reducer.py): Contains the `GraphReducer` class and the `@use_reduced` decorator which wraps routing functions.
  * [scgraph/graph.py](file:///home/conmak/development/personal/scgraph/scgraph/graph.py): Inherits from `GraphReducer` to gain reduction capabilities.
* **C++ Backend**:
  * [scgraph/cpp/src/graph_reducer.hpp](file:///home/conmak/development/personal/scgraph/scgraph/cpp/src/graph_reducer.hpp) & [scgraph/cpp/src/graph_reducer.cpp](file:///home/conmak/development/personal/scgraph/scgraph/cpp/src/graph_reducer.cpp): Declare and define the C++ `GraphReducer` base class.
  * [scgraph/cpp/src/graph.hpp](file:///home/conmak/development/personal/scgraph/scgraph/cpp/src/graph.hpp) & [scgraph/cpp/src/graph.cpp](file:///home/conmak/development/personal/scgraph/scgraph/cpp/src/graph.cpp): Inherit `Graph` from `GraphReducer` and delegate the query wrappers.
  * [CMakeLists.txt](file:///home/conmak/development/personal/CMakeLists.txt): Configures compilation of the new C++ files.

---

## 4. Performance Timing & Benchmarks

### A. Speedup Benchmarks
Running consistency tests on the `us_freeway` network (14,591 nodes) and `world_highways` network (560,282 nodes) yields the following timings before and after reduction:

#### us_freeway (14,591 nodes)
* **`dijkstra`**: Solve Orig: `2.28` ms | Solve Red: `1.10` ms | **Speedup: 2.08x**
* **`dijkstra_negative`**: Solve Orig: `5.67` ms | Solve Red: `1.42` ms | **Speedup: 3.99x**
* **`a_star`**: Solve Orig: `2.28` ms | Solve Red: `0.97` ms | **Speedup: 2.35x**
* **`cached_shortest_path`**: Solve Orig: `5.53` ms | Solve Red: `1.13` ms | **Speedup: 4.91x**
* **`contraction_hierarchy`**: Solve Orig: `0.64` ms | Solve Red: `1.34` ms | Solve Speedup: 0.48x
  * *Build timing*: Build Orig: `460.54` ms | Build Red: `452.36` ms
* **`tnr`**: Solve Orig: `0.92` ms | Solve Red: `1.50` ms | Solve Speedup: 0.62x
  * *Build timing*: Build Orig: `783.38` ms | Build Red: `754.10` ms

#### world_highways (560,282 nodes)
* **`cached_shortest_path`**: Solve Orig: `183.02` ms | Solve Red: `166.25` ms | **Speedup: 1.10x**
* **`dijkstra_negative`**: Solve Orig: `181.98` ms | Solve Red: `184.25` ms | **Speedup: 0.99x**

---

### B. Micro-Timing Stage Breakdown
Profiling shows that the query-specific prepare and expand overhead is extremely small.

| Algorithm & Backend | Prep Phase (`prepare_query_graph`) | Solve Phase (Core Search) | Expand Phase (`expand_path`) | Total Time |
| :--- | :--- | :--- | :--- | :--- |
| **Python `dijkstra`** | `20.91` us (1.8%) | **`1,128.55` us** (96.6%) | `18.21` us (1.6%) | **`1,167.67` us** |
| **C++ `dijkstra`** | `5.20` us (2.9%) | **`172.78` us** (94.8%) | `4.24` us (2.3%) | **`182.22` us** |
| **Python `a_star`** | `13.03` us (1.0%) | **`1,229.63` us** (97.8%) | `14.98` us (1.2%) | **`1,257.64` us** |
| **C++ `a_star`** | `127.67` us (27.2%) | **`337.04` us** (71.9%) | `3.86` us (0.8%) | **`468.57` us** |

---

## 5. Testing & Verification

A robust test suite has been established under `test/`:
* [test/32_graph_reduction_test.py](file:///home/conmak/development/personal/scgraph/test/32_graph_reduction_test.py): Validates reduced graph structure, endpoints, cache clearing upon edits, rejoining path edge cases, and benchmarks 5 diverse origin-destination pairs.
* [test/33_graph_reduction_consistency_test.py](file:///home/conmak/development/personal/scgraph/test/33_graph_reduction_consistency_test.py): Asserts path and length consistency across all algorithms and the distance matrix calculations, printing benchmarking tables before and after reduction.
