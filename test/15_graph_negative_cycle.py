from scgraph import Graph
from time import time

print("\n===============\nGridGraph Import Export Tests:\n===============")

print_timings = True

graph = [
    {1: -1},
    {2: 2},
    {0: 2},
]
graph_negative_cycle = [
    {1: -5},
    {2: 2},
    {0: 2},
]
success = True

try:
    Graph.dijkstra_negative(
        graph=graph,
        origin_id=0,
        destination_id=1,
        cycle_check_iterations=10
    )
except:
    # print("An exception was raised when no negative cycle was expected.")
    success = False


try:
    Graph.dijkstra_negative(
        graph=graph_negative_cycle,
        origin_id=0,
        destination_id=1,
        cycle_check_iterations=10
    )
    # print("No exception was raised when a negative cycle was expected.")
    success = False
except:
    pass



if success == False:
    print("Dijkstra Negative Cycle Test: FAIL")
else:
    print("Dijkstra Negative Cycle Test: PASS")
