# scgraph Benchmark Results

- **Environment**: Python 3.14.5 (Linux x86_64)
- **C++ Acceleration**: Enabled (`nanobind` C++20)
- **Total Suite Execution Time**: 18.98s

## 1. Built-in GeoGraph Load Times (Unreduced)

| Network | Nodes | Edges | Load Time (ms) |
|---|---|---|---|
| `oak_ridge_maritime` | 10,661 | 25,036 | 51.12 |
| `north_america_rail` | 9,929 | 28,915 | 42.29 |
| `marnet` | 11,062 | 34,698 | 58.05 |
| `us_freeway` | 14,591 | 44,232 | 67.87 |
| `world_highways_and_marnet` | 572,009 | 1,689,541 | 3944.21 |

## 2. Built-in GeoGraph Load Times & Reduction Specs (Reduced)

| Reduced Network | Effective Nodes | Effective Edges | Load Time (ms) | Node Reduction % | Edge Reduction % |
|---|---|---|---|---|---|
| `oak_ridge_maritime` | 1,990 | 6,730 | 256.21 | **81.3%** | **73.1%** |
| `north_america_rail` | 6,717 | 19,366 | 76.24 | **32.3%** | **33.0%** |
| `marnet` | 5,818 | 23,852 | 106.70 | **47.4%** | **31.3%** |
| `us_freeway` | 1,680 | 5,276 | 250.63 | **88.5%** | **88.1%** |
| `world_highways_and_marnet` | 427,100 | 1,389,030 | 5080.57 | **25.3%** | **17.8%** |

## 3. Shortest Path Query Performance on GeoGraphs

| Graph | State | Nodes | Dijkstra (ms) | BiDijkstra (ms) | A* Haversine (ms) | Buckets (ms) |
|---|---|---|---|---|---|---|
| `marnet` | Original | 11,062 | 0.7777 | 0.7617 | 2.0717 | 0.8388 |
| `marnet` | Reduced | 11,062 | 0.7110 | 0.4992 | 1.6917 | 1.4125 |
| `us_freeway` | Original | 14,591 | 0.8768 | 1.1755 | 4.7960 | 0.5338 |
| `us_freeway` | Reduced | 14,591 | 0.2699 | 0.2234 | 1.2588 | 0.4359 |
| `world_highways_and_marnet` | Original | 572,009 | 57.6730 | 54.6225 | 75.7460 | 34.4057 |
| `world_highways_and_marnet` | Reduced | 572,009 | 49.3506 | 38.9516 | 61.3621 | 30.8187 |

## 4. GridGraph Pathfinding & Obstacle Performance

| Configuration | Nodes | Creation (ms) | Dijkstra (ms) | A* Manhattan (ms) | Buckets (ms) |
|---|---|---|---|---|---|
| 50x50 Open Grid | 2,500 | 7.94 | 0.1560 | 0.1505 | 0.0974 |
| 100x100 Open Grid | 10,000 | 32.63 | 0.6081 | 0.6203 | 0.4064 |
| 200x200 Open Grid | 40,000 | 139.43 | 4.9026 | 3.3605 | 1.6904 |
| 100x100 L-Barrier & Shape | 10,000 | 43.65 | 0.5929 | 0.5756 | 0.4142 |

## 5. Hierarchical Preprocessing & Routing (CH & TNR)

| Graph | State | Baseline Dijkstra (ms) | CH Prep (ms) | CH Query (ms) | CH Speedup | TNR Prep (ms) | TNR Query (ms) | TNR Speedup |
|---|---|---|---|---|---|---|---|---|
| `marnet` | Original | 0.4216 | 1321.30 | 0.1058 | **  4.0x** | 1361.92 | 0.1810 | **  2.3x** |
| `marnet` | Reduced | 0.4212 | 1008.91 | 0.1188 | **  3.5x** | 1033.20 | 0.1458 | **  2.9x** |
| `us_freeway` | Original | 0.5817 | 238.49 | 0.0785 | **  7.4x** | 253.56 | 0.1310 | **  4.4x** |
| `us_freeway` | Reduced | 0.1544 | 68.55 | 0.0394 | **  3.9x** | 78.96 | 0.0577 | **  2.7x** |

## 6. Specialized Features & Operations

| Feature / Operation | Target / Input | Execution Time (ms) | Notes / Throughput |
|---|---|---|---|
| Distance Matrix (10x10 = 100 points) | us_freeway | 105.900 | 10,000 OD pairs computed |
| Cached Shortest Path (Tree Build) | us_freeway | 1.302 | Full SPT construction |
| Cached Shortest Path (Tree Hit) | us_freeway | 0.040 | 32x faster tree lookup |
| Visvalingam Line Simplification | 10,000 coordinates | 35.134 | 90% point reduction |
| BMSSP Shortest Path | marnet (node 0 -> 7999) | 23.416 | Bounded Multi-Source SP |
