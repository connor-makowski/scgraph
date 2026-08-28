# scgraph Benchmark Results

- **Environment**: Python 3.14.5 (Linux x86_64)
- **C++ Acceleration**: Enabled (`nanobind` C++20)
- **Iterations per query**: 10

## Algorithm Query Performance

| Graph | State | Nodes | Dijkstra (ms) | Bidirectional Dijkstra (ms) | A* (ms) | Dijkstra Buckets (ms) |
|---|---|---|---|---|---|---|
| `marnet` | Original | 11,062 | 0.7324 | 0.6501 | 2.0564 | 0.8074 |
| `marnet` | Reduced | 11,062 | 0.6066 | 0.4360 | 1.6187 | 0.8125 |
| `marnet` | Fully Reduced | 11,062 | 0.5608 | 0.4377 | 1.4758 | 0.7451 |
| `us_freeway` | Original | 14,591 | 0.8177 | 0.8505 | 3.6212 | 0.4782 |
| `us_freeway` | Reduced | 14,591 | 0.2623 | 0.1820 | 1.0321 | 0.3764 |
| `us_freeway` | Fully Reduced | 14,591 | 0.2365 | 0.1638 | 0.9348 | 0.3418 |
| `world_highways_and_marnet` | Original | 572,009 | 50.5872 | 48.3783 | 64.4693 | 28.4303 |
| `world_highways_and_marnet` | Reduced | 572,009 | 44.6572 | 38.3318 | 59.9901 | 31.8868 |
| `world_highways_and_marnet` | Fully Reduced | 572,009 | 47.4627 | 35.9849 | 67.6185 | 35.0525 |

## Graph Reduction Impact

| Graph | State | Total Nodes | Simplified Chain Nodes | Reduction Ratio |
|---|---|---|---|---|
| `marnet` | Reduced (1 pass) | 11,062 | 5,243 | **47.4% simplified** |
| `marnet` | Fully Reduced | 11,062 | 5,510 | **49.8% simplified** |
| `us_freeway` | Reduced (1 pass) | 14,591 | 12,902 | **88.4% simplified** |
| `us_freeway` | Fully Reduced | 14,591 | 13,118 | **89.9% simplified** |
| `world_highways_and_marnet` | Reduced (1 pass) | 572,009 | 144,908 | **25.3% simplified** |
| `world_highways_and_marnet` | Fully Reduced | 572,009 | 195,033 | **34.1% simplified** |
