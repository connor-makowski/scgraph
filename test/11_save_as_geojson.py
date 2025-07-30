from scgraph import GeoGraph
from scgraph.core import load_geojson_as_geograph


nodes = [
    [0, 0],
    [0, 1],
    [1, 0],
    [1, 1],
    [1, 2],
    [2, 1],
]
graph = [
    {1: 5, 2: 1},
    {0: 5, 2: 2, 3: 1},
    {0: 1, 1: 2, 3: 4, 4: 8},
    {1: 1, 2: 4, 4: 3, 5: 6},
    {2: 8, 3: 3},
    {3: 6},
]

print(
    "\n===============\nExternal Saving, Modification and Loading Tests:\n==============="
)


my_graph = GeoGraph(nodes=nodes, graph=graph)

my_graph.save_as_geojson("11_save_as_geojson_test.geojson")
my_graph.save_as_geograph("11_save_as_geojson_test")
my_graph.save_as_graphjson("11_save_as_geojson_test.graphjson")

my_graph2 = load_geojson_as_geograph(
    "11_save_as_geojson_test.geojson", silent=True
)
my_graph3 = GeoGraph.load_from_graphjson("11_save_as_geojson_test.graphjson")

success = True

try:
    assert my_graph.graph == my_graph2.graph, "Graphs are not equal"
    assert my_graph.nodes == my_graph2.nodes, "Nodes are not equal"
    assert (
        my_graph.graph == my_graph3.graph
    ), "Graphs from graphjson are not equal"
    assert (
        my_graph.nodes == my_graph3.nodes
    ), "Nodes from graphjson are not equal"
except:
    success = False

# Cleanup
import os

os.remove("11_save_as_geojson_test.geojson")
os.remove("11_save_as_geojson_test.graphjson")
os.remove("11_save_as_geojson_test.py")

if success:
    print("PASS")
else:
    print("FAIL")
