# scgraph Benchmark Results

- **Environment**: Python 3.14.5 (Linux x86_64)
- **C++ Acceleration**: Enabled (`nanobind` C++20)
- **Total Suite Execution Time**: 19.13s

## 1. Built-in GeoGraph Load Times (Unreduced)

| Network | Nodes | Edges | Load Time (ms) |
|---|---|---|---|
| `oak_ridge_maritime` | 10,661 | 25,036 | 45.41 |
| `north_america_rail` | 9,929 | 28,915 | 39.56 |
| `marnet` | 11,062 | 34,698 | 51.95 |
| `us_freeway` | 14,591 | 44,232 | 64.31 |
| `world_highways_and_marnet` | 572,009 | 1,689,541 | 3926.32 |

## 2. Built-in GeoGraph Load Times & Reduction Specs (Reduced)

| Reduced Network | Effective Nodes | Effective Edges | Load Time (ms) | Node Reduction % | Edge Reduction % |
|---|---|---|---|---|---|
| `oak_ridge_maritime` | 1,990 | 6,730 | 279.79 | **81.3%** | **73.1%** |
| `north_america_rail` | 6,717 | 19,366 | 76.87 | **32.3%** | **33.0%** |
| `marnet` | 5,818 | 23,852 | 115.99 | **47.4%** | **31.3%** |
| `us_freeway` | 1,680 | 5,276 | 250.83 | **88.5%** | **88.1%** |
| `world_highways_and_marnet` | 427,100 | 1,389,030 | 5079.65 | **25.3%** | **17.8%** |

## 3. Shortest Path Query Performance on GeoGraphs

| Graph | State | Nodes | Dijkstra (ms) | BiDijkstra (ms) | A* Haversine (ms) | Buckets (ms) | BiBuckets (ms) |
|---|---|---|---|---|---|---|---|
| `marnet` | Original | 11,062 | 0.7915 | 0.7548 | 1.9866 | 0.7863 | 0.7888 |
| `marnet` | Reduced | 11,062 | 0.6969 | 0.4856 | 1.5121 | 0.8803 | 0.6108 |
| `us_freeway` | Original | 14,591 | 0.8206 | 0.9707 | 4.1672 | 0.4742 | 0.6105 |
| `us_freeway` | Reduced | 14,591 | 0.2622 | 0.2002 | 1.2214 | 0.4118 | 0.2466 |
| `world_highways_and_marnet` | Original | 572,009 | 54.1316 | 51.8774 | 75.0871 | 29.6244 | 25.9186 |
| `world_highways_and_marnet` | Reduced | 572,009 | 46.0338 | 39.1202 | 62.3045 | 31.3028 | 27.2930 |

## 4. GridGraph Pathfinding & Obstacle Performance

| Configuration | Nodes | Creation (ms) | Dijkstra (ms) | A* Manhattan (ms) | Buckets (ms) | BiBuckets (ms) |
|---|---|---|---|---|---|---|
| 50x50 Open Grid | 2,500 | 8.04 | 0.1513 | 0.1468 | 0.0934 | 0.2123 |
| 100x100 Open Grid | 10,000 | 32.82 | 0.5992 | 0.6105 | 0.3840 | 0.7930 |
| 200x200 Open Grid | 40,000 | 137.10 | 2.9759 | 2.6158 | 1.5360 | 3.6667 |
| 100x100 L-Barrier & Shape | 10,000 | 41.96 | 0.5887 | 0.5709 | 0.3763 | 0.8500 |

## 5. Hierarchical Preprocessing & Routing (CH & TNR)

| Graph | State | Baseline Dijkstra (ms) | CH Prep (ms) | CH Query (ms) | CH Speedup | TNR Prep (ms) | TNR Query (ms) | TNR Speedup |
|---|---|---|---|---|---|---|---|---|
| `marnet` | Original | 0.4314 | 1334.08 | 0.1072 | **  4.0x** | 1386.17 | 0.1574 | **  2.7x** |
| `marnet` | Reduced | 0.4371 | 1002.51 | 0.0942 | **  4.6x** | 1031.89 | 0.1394 | **  3.1x** |
| `us_freeway` | Original | 0.4823 | 229.92 | 0.0772 | **  6.2x** | 246.60 | 0.1211 | **  4.0x** |
| `us_freeway` | Reduced | 0.1519 | 65.76 | 0.0406 | **  3.7x** | 78.05 | 0.0480 | **  3.2x** |

## 6. Specialized Features & Operations

| Feature / Operation | Target / Input | Execution Time (ms) | Notes / Throughput |
|---|---|---|---|
| Distance Matrix (10x10 = 100 points) | us_freeway | 101.690 | 10,000 OD pairs computed |
| Cached Shortest Path (Tree Build) | us_freeway | 1.127 | Full SPT construction |
| Cached Shortest Path (Tree Hit) | us_freeway | 0.035 | 33x faster tree lookup |
| Visvalingam Line Simplification | 10,000 coordinates | 26.697 | 90% point reduction |
| BMSSP Shortest Path | marnet (node 0 -> 7999) | 22.954 | Bounded Multi-Source SP |
