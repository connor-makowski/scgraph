# scgraph Benchmark Results

- **Environment**: Python 3.14.5 (Linux x86_64)
- **C++ Acceleration**: Enabled (`nanobind` C++20)
- **Total Suite Execution Time**: 18.25s

## 1. Built-in GeoGraph Load Times & Reduction Specs

| Network | Nodes | Edges | Load Time (ms) | Reduced Nodes (1-Pass) | Chain Reduction |
|---|---|---|---|---|---|
| `oak_ridge_maritime` | 10,661 | 25,036 | 46.60 | 1,991 | **81.3% simplified** |
| `north_america_rail` | 9,929 | 28,915 | 40.20 | 6,718 | **32.3% simplified** |
| `marnet` | 11,062 | 34,698 | 53.19 | 5,819 | **47.4% simplified** |
| `us_freeway` | 14,591 | 44,232 | 64.71 | 1,689 | **88.4% simplified** |
| `world_highways_and_marnet` | 572,009 | 1,689,541 | 3850.13 | 427,101 | **25.3% simplified** |

## 2. Shortest Path Query Performance on GeoGraphs

| Graph | State | Nodes | Dijkstra (ms) | BiDijkstra (ms) | A* Haversine (ms) | Buckets (ms) |
|---|---|---|---|---|---|---|
| `marnet` | Original | 11,062 | 0.7824 | 0.7675 | 1.9672 | 0.8406 |
| `marnet` | Reduced | 11,062 | 0.6761 | 0.4807 | 1.5021 | 0.9001 |
| `us_freeway` | Original | 14,591 | 0.8164 | 0.9841 | 4.2739 | 0.4850 |
| `us_freeway` | Reduced | 14,591 | 0.2583 | 0.2142 | 1.2071 | 0.4219 |
| `world_highways_and_marnet` | Original | 572,009 | 55.8083 | 60.6166 | 75.4813 | 33.2931 |
| `world_highways_and_marnet` | Reduced | 572,009 | 47.8640 | 40.1784 | 60.8490 | 32.8864 |

## 3. GridGraph Pathfinding & Obstacle Performance

| Configuration | Nodes | Creation (ms) | Dijkstra (ms) | A* Manhattan (ms) | Buckets (ms) |
|---|---|---|---|---|---|
| 50x50 Open Grid | 2,500 | 8.99 | 0.1531 | 0.1486 | 0.0977 |
| 100x100 Open Grid | 10,000 | 34.04 | 0.6227 | 0.6028 | 0.4164 |
| 200x200 Open Grid | 40,000 | 147.36 | 4.0411 | 2.7098 | 1.5920 |
| 100x100 L-Barrier & Shape | 10,000 | 42.76 | 0.5931 | 0.5735 | 0.4052 |

## 4. Hierarchical Preprocessing & Routing (CH & TNR)

| Graph | State | Baseline Dijkstra (ms) | CH Prep (ms) | CH Query (ms) | CH Speedup | TNR Prep (ms) | TNR Query (ms) | TNR Speedup |
|---|---|---|---|---|---|---|---|---|
| `marnet` | Original | 0.4226 | 1282.38 | 0.1028 | **  4.1x** | 1314.41 | 0.1636 | **  2.6x** |
| `marnet` | Reduced | 0.4061 | 958.34 | 0.0944 | **  4.3x** | 972.37 | 0.1437 | **  2.8x** |
| `us_freeway` | Original | 0.4644 | 225.63 | 0.0821 | **  5.7x** | 238.49 | 0.1181 | **  3.9x** |
| `us_freeway` | Reduced | 0.1529 | 65.61 | 0.0389 | **  3.9x** | 75.22 | 0.0503 | **  3.0x** |

## 5. Specialized Features & Operations

| Feature / Operation | Target / Input | Execution Time (ms) | Notes / Throughput |
|---|---|---|---|
| Distance Matrix (10x10 = 100 points) | us_freeway | 102.364 | 10,000 OD pairs computed |
| Cached Shortest Path (Tree Build) | us_freeway | 1.133 | Full SPT construction |
| Cached Shortest Path (Tree Hit) | us_freeway | 0.028 | 41x faster tree lookup |
| Visvalingam Line Simplification | 10,000 coordinates | 27.022 | 90% point reduction |
| BMSSP Shortest Path | marnet (node 0 -> 7999) | 22.827 | Bounded Multi-Source SP |
