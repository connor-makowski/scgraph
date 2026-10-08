# scgraph Benchmark Results

- **Environment**: Python 3.14.5 (Linux x86_64)
- **C++ Acceleration**: Enabled (`nanobind` C++20)
- **Total Suite Execution Time**: 15.49s

## 1. Built-in GeoGraph Load Times (Unreduced)

| Network | Nodes | Edges | Load Time (ms) |
|---|---|---|---|
| `oak_ridge_maritime` | 10,661 | 25,036 | 35.54 |
| `north_america_rail` | 9,929 | 28,915 | 28.71 |
| `marnet` | 11,062 | 34,698 | 38.14 |
| `us_freeway` | 14,591 | 44,232 | 49.00 |
| `world_highways_and_marnet` | 572,009 | 1,689,541 | 2501.43 |

## 2. Built-in GeoGraph Load Times & Reduction Specs (Reduced)

| Reduced Network | Effective Nodes | Effective Edges | Load Time (ms) | Node Reduction % | Edge Reduction % |
|---|---|---|---|---|---|
| `oak_ridge_maritime` | 1,990 | 6,730 | 121.85 | **81.3%** | **73.1%** |
| `north_america_rail` | 6,717 | 19,366 | 41.49 | **32.3%** | **33.0%** |
| `marnet` | 5,818 | 23,852 | 74.63 | **47.4%** | **31.3%** |
| `us_freeway` | 1,680 | 5,276 | 211.17 | **88.5%** | **88.1%** |
| `world_highways_and_marnet` | 427,100 | 1,389,030 | 3466.33 | **25.3%** | **17.8%** |

## 3. Shortest Path Query Performance on GeoGraphs

| Graph | State | Nodes | Dijkstra (ms) | BiDijkstra (ms) | A* Haversine (ms) | Buckets (ms) | BiBuckets (ms) |
|---|---|---|---|---|---|---|---|
| `marnet` | Original | 11,062 | 0.8257 | 0.8224 | 2.1129 | 0.8373 | 0.7719 |
| `marnet` | Reduced | 11,062 | 0.5398 | 0.4648 | 2.1162 | 0.5625 | 0.5490 |
| `us_freeway` | Original | 14,591 | 0.9073 | 1.0048 | 4.6548 | 0.5316 | 0.6369 |
| `us_freeway` | Reduced | 14,591 | 0.1820 | 0.2084 | 1.3715 | 0.1908 | 0.1856 |
| `world_highways_and_marnet` | Original | 572,009 | 58.6288 | 52.2718 | 78.5201 | 31.5306 | 23.7502 |
| `world_highways_and_marnet` | Reduced | 572,009 | 49.0444 | 40.5976 | 64.6542 | 26.8932 | 20.8115 |

## 4. GridGraph Pathfinding & Obstacle Performance

| Configuration | Nodes | Creation (ms) | Dijkstra (ms) | A* Manhattan (ms) | Buckets (ms) | BiBuckets (ms) |
|---|---|---|---|---|---|---|
| 50x50 Open Grid | 2,500 | 7.80 | 0.1689 | 0.1651 | 0.1304 | 0.2035 |
| 100x100 Open Grid | 10,000 | 31.50 | 0.7532 | 0.7019 | 0.4608 | 0.7749 |
| 200x200 Open Grid | 40,000 | 135.80 | 3.0712 | 3.0195 | 2.3323 | 3.3424 |
| 100x100 L-Barrier & Shape | 10,000 | 41.61 | 0.6640 | 0.6439 | 0.4814 | 0.9031 |

## 5. Hierarchical Preprocessing & Routing (CH & TNR)

| Graph | State | Baseline Dijkstra (ms) | CH Prep (ms) | CH Query (ms) | CH Speedup | TNR Prep (ms) | TNR Query (ms) | TNR Speedup |
|---|---|---|---|---|---|---|---|---|
| `marnet` | Original | 0.4489 | 1271.42 | 0.1319 | **  3.4x** | 1304.82 | 0.1610 | **  2.8x** |
| `marnet` | Reduced | 0.2617 | 948.07 | 0.0907 | **  2.9x** | 968.36 | 0.1387 | **  1.9x** |
| `us_freeway` | Original | 0.4983 | 226.17 | 0.0770 | **  6.5x** | 235.54 | 0.1205 | **  4.1x** |
| `us_freeway` | Reduced | 0.0888 | 67.84 | 0.0403 | **  2.2x** | 80.71 | 0.0540 | **  1.6x** |

## 6. Specialized Features & Operations

| Feature / Operation | Target / Input | Execution Time (ms) | Notes / Throughput |
|---|---|---|---|
| Distance Matrix (10x10 = 100 points) | us_freeway | 100.849 | 10,000 OD pairs computed |
| Cached Shortest Path (Tree Build) | us_freeway | 1.104 | Full SPT construction |
| Cached Shortest Path (Tree Hit) | us_freeway | 0.035 | 32x faster tree lookup |
| Visvalingam Line Simplification | 10,000 coordinates | 27.148 | 90% point reduction |
| BMSSP Shortest Path | marnet (node 0 -> 7999) | 23.166 | Bounded Multi-Source SP |
