# scgraph Benchmark Results

- **Environment**: Python 3.14.5 (Linux x86_64)
- **C++ Acceleration**: Enabled (`nanobind` C++20)
- **Total Suite Execution Time**: 18.57s

## 1. Built-in GeoGraph Load Times (Unreduced)

| Network | Nodes | Edges | Load Time (ms) |
|---|---|---|---|
| `oak_ridge_maritime` | 10,661 | 25,036 | 45.57 |
| `north_america_rail` | 9,929 | 28,915 | 39.13 |
| `marnet` | 11,062 | 34,698 | 52.61 |
| `us_freeway` | 14,591 | 44,232 | 64.85 |
| `world_highways_and_marnet` | 572,009 | 1,689,541 | 3876.84 |

## 2. Built-in GeoGraph Load Times & Reduction Specs (Reduced)

| Reduced Network | Effective Nodes | Effective Edges | Load Time (ms) | Node Reduction % | Edge Reduction % |
|---|---|---|---|---|---|
| `oak_ridge_maritime` | 1,990 | 6,730 | 252.60 | **81.3%** | **73.1%** |
| `north_america_rail` | 6,717 | 19,366 | 76.48 | **32.3%** | **33.0%** |
| `marnet` | 5,818 | 23,852 | 106.98 | **47.4%** | **31.3%** |
| `us_freeway` | 1,680 | 5,276 | 241.45 | **88.5%** | **88.1%** |
| `world_highways_and_marnet` | 427,100 | 1,389,030 | 4934.22 | **25.3%** | **17.8%** |

## 3. Shortest Path Query Performance on GeoGraphs

| Graph | State | Nodes | Dijkstra (ms) | BiDijkstra (ms) | A* Haversine (ms) | Buckets (ms) | BiBuckets (ms) |
|---|---|---|---|---|---|---|---|
| `marnet` | Original | 11,062 | 0.7917 | 0.7671 | 1.9676 | 0.7585 | 0.7197 |
| `marnet` | Reduced | 11,062 | 0.7090 | 0.4883 | 1.4972 | 0.7409 | 0.5292 |
| `us_freeway` | Original | 14,591 | 0.8493 | 1.0014 | 4.1446 | 0.4459 | 0.5144 |
| `us_freeway` | Reduced | 14,591 | 0.2645 | 0.2055 | 1.2323 | 0.2800 | 0.1886 |
| `world_highways_and_marnet` | Original | 572,009 | 54.0591 | 51.1098 | 71.3644 | 27.5843 | 22.4004 |
| `world_highways_and_marnet` | Reduced | 572,009 | 45.0504 | 37.6140 | 58.5362 | 24.4183 | 20.5814 |

## 4. GridGraph Pathfinding & Obstacle Performance

| Configuration | Nodes | Creation (ms) | Dijkstra (ms) | A* Manhattan (ms) | Buckets (ms) | BiBuckets (ms) |
|---|---|---|---|---|---|---|
| 50x50 Open Grid | 2,500 | 7.83 | 0.1559 | 0.1518 | 0.0957 | 0.2260 |
| 100x100 Open Grid | 10,000 | 32.02 | 0.6508 | 0.6410 | 0.3919 | 0.7738 |
| 200x200 Open Grid | 40,000 | 133.41 | 2.8875 | 2.7316 | 1.5437 | 3.7048 |
| 100x100 L-Barrier & Shape | 10,000 | 42.44 | 0.5942 | 0.6108 | 0.3833 | 0.8303 |

## 5. Hierarchical Preprocessing & Routing (CH & TNR)

| Graph | State | Baseline Dijkstra (ms) | CH Prep (ms) | CH Query (ms) | CH Speedup | TNR Prep (ms) | TNR Query (ms) | TNR Speedup |
|---|---|---|---|---|---|---|---|---|
| `marnet` | Original | 0.4322 | 1290.71 | 0.0999 | **  4.3x** | 1321.98 | 0.1636 | **  2.6x** |
| `marnet` | Reduced | 0.4018 | 973.31 | 0.0954 | **  4.2x** | 1002.04 | 0.1308 | **  3.1x** |
| `us_freeway` | Original | 0.4791 | 233.74 | 0.1085 | **  4.4x** | 248.46 | 0.1253 | **  3.8x** |
| `us_freeway` | Reduced | 0.1299 | 65.83 | 0.0372 | **  3.5x** | 76.62 | 0.0482 | **  2.7x** |

## 6. Specialized Features & Operations

| Feature / Operation | Target / Input | Execution Time (ms) | Notes / Throughput |
|---|---|---|---|
| Distance Matrix (10x10 = 100 points) | us_freeway | 99.431 | 10,000 OD pairs computed |
| Cached Shortest Path (Tree Build) | us_freeway | 1.096 | Full SPT construction |
| Cached Shortest Path (Tree Hit) | us_freeway | 0.027 | 40x faster tree lookup |
| Visvalingam Line Simplification | 10,000 coordinates | 26.690 | 90% point reduction |
| BMSSP Shortest Path | marnet (node 0 -> 7999) | 23.151 | Bounded Multi-Source SP |
