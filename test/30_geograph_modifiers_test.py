from copy import deepcopy
from scgraph import GeoGraph
from scgraph.utils import validate, haversine

print("\n===============\nGeoGraph Modifiers Tests:\n===============")

# 4-node square: SW=0, SE=1, NW=2, NE=3
# Symmetric edges: 0<->1:100, 0<->2:200, 1<->3:100, 2<->3:100
# Shortest path 0->3: 0->1->3 = 200
nodes = [
    [0, 0],
    [0, 1],
    [1, 0],
    [1, 1],
]
graph = [
    {1: 100, 2: 200},
    {0: 100, 3: 100},
    {0: 200, 3: 100},
    {1: 100, 2: 100},
]

origin = {"latitude": 0, "longitude": 0}
destination = {"latitude": 1, "longitude": 1}

# add_edge: direct shortcut 0<->3 bypasses the 200km two-hop path
g = GeoGraph(nodes=deepcopy(nodes), graph=deepcopy(graph))
g.add_edge(origin_id=0, destination_id=3, distance=50, symmetric=True)
validate(
    name="add_edge",
    realized=g.get_shortest_path(
        origin_node=origin, destination_node=destination
    ),
    expected={
        "coordinate_path": [[0, 0], [0, 0], [1, 1], [1, 1]],
        "length": 50,
    },
)

# remove_edge: removing 0<->1 forces the longer 0->2->3 = 300 route
g = GeoGraph(nodes=deepcopy(nodes), graph=deepcopy(graph))
g.remove_edge(origin_id=0, destination_id=1, symmetric=True)
validate(
    name="remove_edge",
    realized=g.get_shortest_path(
        origin_node=origin, destination_node=destination
    ),
    expected={
        "coordinate_path": [[0, 0], [0, 0], [1, 0], [1, 1], [1, 1]],
        "length": 300,
    },
)

# add_coord_edge: coords snap to nodes 0 and 3, explicit distance=50
g = GeoGraph(nodes=deepcopy(nodes), graph=deepcopy(graph))
g.add_coord_edge(
    origin_coord_dict={"latitude": 0.1, "longitude": 0.1},
    destination_coord_dict={"latitude": 0.9, "longitude": 0.9},
    distance=50,
    symmetric=True,
)
validate(
    name="add_coord_edge",
    realized=g.get_shortest_path(
        origin_node=origin, destination_node=destination
    ),
    expected={
        "coordinate_path": [[0, 0], [0, 0], [1, 1], [1, 1]],
        "length": 50,
    },
)

# add_coord_node (no auto edge): node is added but isolated
g = GeoGraph(nodes=deepcopy(nodes), graph=deepcopy(graph))
new_id = g.add_coord_node(
    coord_dict={"latitude": 0.5, "longitude": 0.5},
    auto_edge=False,
)
validate(
    name="add_coord_node - returns new node id", realized=new_id, expected=4
)
validate(
    name="add_coord_node - graph grows by one",
    realized=len(g.graph_object.graph),
    expected=5,
)
validate(
    name="add_coord_node - path unchanged when isolated",
    realized=g.get_shortest_path(
        origin_node=origin, destination_node=destination
    ),
    expected={
        "coordinate_path": [[0, 0], [0, 0], [0, 1], [1, 1], [1, 1]],
        "length": 200,
    },
)

# add_coord_node (with auto edge): center node should shorten 0->3 path
g = GeoGraph(nodes=deepcopy(nodes), graph=deepcopy(graph))
g.add_coord_node(
    coord_dict={"latitude": 0.5, "longitude": 0.5},
    auto_edge=True,
    circuity=1.1,
)
validate(
    name="add_coord_node with auto edge - graph grows by one",
    realized=len(g.graph_object.graph),
    expected=5,
)
result = g.get_shortest_path(origin_node=origin, destination_node=destination)
validate(
    name="add_coord_node with auto edge - path shorter than original",
    realized=result["length"] < 200,
    expected=True,
)

# remove_coord_node: add then remove restores the graph
g = GeoGraph(nodes=deepcopy(nodes), graph=deepcopy(graph))
g.add_coord_node(
    coord_dict={"latitude": 0.5, "longitude": 0.5},
    auto_edge=False,
)
g.remove_coord_node()
validate(
    name="remove_coord_node - graph size restored",
    realized=len(g.graph_object.graph),
    expected=4,
)
validate(
    name="remove_coord_node - path unchanged",
    realized=g.get_shortest_path(
        origin_node=origin, destination_node=destination
    ),
    expected={
        "coordinate_path": [[0, 0], [0, 0], [0, 1], [1, 1], [1, 1]],
        "length": 200,
    },
)

# add_haversine_edge: diagonal 0<->3 edge uses actual earth distance (~157 km < 200)
g = GeoGraph(nodes=deepcopy(nodes), graph=deepcopy(graph))
g.add_haversine_edge(origin_idx=0, destination_idx=3, symmetric=True)
expected_dist = haversine(nodes[0], nodes[3])
validate(
    name="add_haversine_edge",
    realized=g.get_shortest_path(
        origin_node=origin, destination_node=destination
    ),
    expected={
        "coordinate_path": [[0, 0], [0, 0], [1, 1], [1, 1]],
        "length": expected_dist,
    },
)
